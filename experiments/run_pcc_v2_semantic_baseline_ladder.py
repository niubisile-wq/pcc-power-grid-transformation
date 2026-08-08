from __future__ import annotations

import copy
import csv
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "cgmes", ROOT / "experiments"):
    import sys

    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_pcc_v2_attack_matrix import (  # noqa: E402
    ATTACK_FAMILIES,
    CASES,
    download_case,
    parse_branches,
    source_snapshot,
    transform,
)


SOURCE_RESULTS = ROOT / "outputs" / "pcc_v2_attack_matrix" / "attack_matrix_results.csv"
OUTPUT = ROOT / "outputs" / "pcc_v2_semantic_baseline_ladder"
BASELINES = (
    "B0_structural_only",
    "B1_signed_artifact_v1",
    "B2_global_identity",
    "B3_task_footprint",
    "B4_attribute_invariants",
    "B5_full_PCC_v2",
)
REQUIRED_ATTRIBUTES = ("asset_type", "from_bus", "to_bus", "r_pu", "x_pu")


def _close(left: Any, right: Any, tolerance: float = 1e-12) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance)
    return left == right


def global_identity_accepts(source: dict, target: dict, relations: list[dict]) -> bool:
    assignments: dict[str, list[int]] = {}
    for relation_index, relation in enumerate(relations):
        source_ids = list(relation.get("source_ids", []))
        target_ids = list(relation.get("target_ids", []))
        kind = relation.get("relation_type")
        if not source_ids or not target_ids or not relation.get("authoritative_evidence"):
            return False
        if kind in {"exact", "rename"} and (len(source_ids) != 1 or len(target_ids) != 1):
            return False
        if kind == "split" and (len(source_ids) != 1 or len(target_ids) < 2):
            return False
        if kind == "merge" and (len(source_ids) < 2 or len(target_ids) != 1):
            return False
        if kind not in {"exact", "rename", "split", "merge", "derived"}:
            return False
        if any(source_id not in source["assets"] for source_id in source_ids):
            return False
        if any(target_id not in target["assets"] for target_id in target_ids):
            return False
        for target_id in target_ids:
            assignments.setdefault(target_id, []).append(relation_index)
    return all(len(relation_indices) == 1 for relation_indices in assignments.values())


def task_footprint_accepts(source: dict, target: dict, relations: list[dict]) -> bool:
    if not global_identity_accepts(source, target, relations):
        return False
    by_source: dict[str, list[dict]] = {}
    mapped_targets: set[str] = set()
    for relation in relations:
        source_ids = list(relation["source_ids"])
        target_ids = list(relation["target_ids"])
        if relation["relation_type"] == "merge" and not relation.get("group_intervention_authorized", False):
            return False
        for source_id in source_ids:
            by_source.setdefault(source_id, []).append(relation)
            mapped_targets.update(target_ids)
    return (
        all(len(by_source.get(source_id, [])) == 1 for source_id in source["assets"])
        and mapped_targets == set(target["assets"])
    )


def attribute_invariants_accept(source: dict, target: dict, relations: list[dict]) -> bool:
    if not task_footprint_accepts(source, target, relations):
        return False
    for relation in relations:
        if relation["relation_type"] not in {"exact", "rename"}:
            continue
        source_asset = source["assets"][relation["source_ids"][0]]
        target_asset = target["assets"][relation["target_ids"][0]]
        if any(not _close(source_asset.get(field), target_asset.get(field)) for field in REQUIRED_ATTRIBUTES):
            return False
    return True


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return center - margin, center + margin


def mcnemar_log10_p(improvements: int, regressions: int) -> float:
    discordant = improvements + regressions
    if discordant == 0:
        return 0.0
    tail = min(improvements, regressions)
    probability = sum(math.comb(discordant, k) for k in range(tail + 1)) / (2**discordant)
    return min(0.0, math.log10(min(1.0, 2 * probability)))


def main() -> None:
    existing = {row["scenario_id"]: row for row in csv.DictReader(SOURCE_RESULTS.open(encoding="utf-8"))}
    rows: list[dict[str, Any]] = []
    for case_name in CASES:
        case_path, _ = download_case(case_name)
        source = source_snapshot(parse_branches(case_path))
        scenarios = [("lawful", "none", seed) for seed in range(30)] + [
            ("harmful", family, seed) for family in ATTACK_FAMILIES for seed in range(10)
        ]
        for transform_class, family, seed in scenarios:
            scenario_id = f"{case_name}:{family}:{seed:02d}"
            target, relations, _ = transform(source, family, seed)
            frozen = existing[scenario_id]
            decisions = {
                "B0_structural_only": bool(target.get("assets")),
                "B1_signed_artifact_v1": frozen["v1_decision"] == "accept",
                "B2_global_identity": global_identity_accepts(source, target, relations),
                "B3_task_footprint": task_footprint_accepts(source, target, relations),
                "B4_attribute_invariants": attribute_invariants_accept(source, target, relations),
                "B5_full_PCC_v2": frozen["v2_decision"] == "accept",
            }
            rows.append({
                "scenario_id": scenario_id,
                "network": case_name,
                "transform_class": transform_class,
                "attack_family": family,
                **{baseline: "accept" if value else "fail_closed" for baseline, value in decisions.items()},
            })
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / "baseline_ladder_results.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    harmful = [row for row in rows if row["transform_class"] == "harmful"]
    lawful = [row for row in rows if row["transform_class"] == "lawful"]
    metrics = {}
    for baseline in BASELINES:
        harmful_accepts = sum(row[baseline] == "accept" for row in harmful)
        lawful_accepts = sum(row[baseline] == "accept" for row in lawful)
        low, high = wilson(harmful_accepts, len(harmful))
        metrics[baseline] = {
            "harmful_accepts": harmful_accepts,
            "harmful_n": len(harmful),
            "harmful_acceptance_rate": harmful_accepts / len(harmful),
            "harmful_acceptance_wilson_95": [low, high],
            "lawful_accepts": lawful_accepts,
            "lawful_n": len(lawful),
            "lawful_acceptance_rate": lawful_accepts / len(lawful),
            "by_attack_family_harmful_accepts": {
                family: sum(row[baseline] == "accept" and row["attack_family"] == family for row in harmful)
                for family in ATTACK_FAMILIES
            },
        }
    comparisons = []
    for left, right in zip(BASELINES, BASELINES[1:]):
        improvements = sum(row[left] == "accept" and row[right] != "accept" for row in harmful)
        regressions = sum(row[left] != "accept" and row[right] == "accept" for row in harmful)
        comparisons.append({
            "left": left,
            "right": right,
            "improvements": improvements,
            "regressions": regressions,
            "absolute_risk_reduction": metrics[left]["harmful_acceptance_rate"] - metrics[right]["harmful_acceptance_rate"],
            "mcnemar_exact_two_sided_log10_p": mcnemar_log10_p(improvements, regressions),
        })
    ranked = sorted(range(len(comparisons)), key=lambda index: comparisons[index]["mcnemar_exact_two_sided_log10_p"])
    previous_adjusted_log10 = float("-inf")
    for rank, index in enumerate(ranked):
        multiplier = len(comparisons) - rank
        candidate = min(
            0.0, comparisons[index]["mcnemar_exact_two_sided_log10_p"] + math.log10(multiplier)
        )
        adjusted = max(previous_adjusted_log10, candidate)
        comparisons[index]["holm_adjusted_log10_p"] = adjusted
        previous_adjusted_log10 = adjusted
    summary = {
        "protocol": "pcc_v2_semantic_baseline_ladder_v1",
        "networks": len(CASES),
        "harmful_n": len(harmful),
        "lawful_n": len(lawful),
        "metrics": metrics,
        "adjacent_paired_comparisons": comparisons,
        "full_vs_signed_artifact": {
            "absolute_risk_reduction": metrics["B1_signed_artifact_v1"]["harmful_acceptance_rate"] - metrics["B5_full_PCC_v2"]["harmful_acceptance_rate"],
            "harmful_releases_prevented": metrics["B1_signed_artifact_v1"]["harmful_accepts"] - metrics["B5_full_PCC_v2"]["harmful_accepts"],
            "lawful_acceptance_difference": metrics["B5_full_PCC_v2"]["lawful_acceptance_rate"] - metrics["B1_signed_artifact_v1"]["lawful_acceptance_rate"],
            "full_zero_event_one_sided_clopper_pearson_upper_95": 1 - 0.05 ** (1 / len(harmful)),
        },
        "ready": metrics["B5_full_PCC_v2"]["harmful_accepts"] == 0 and all(metrics[b]["lawful_acceptance_rate"] == 1.0 for b in BASELINES),
        "scope": "controlled semantic attacks; not natural field prevalence",
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
