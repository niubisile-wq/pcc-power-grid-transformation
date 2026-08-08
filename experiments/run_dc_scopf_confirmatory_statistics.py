"""Summarize the frozen 5 x 10 DC-SCOPF confirmatory experiment.

The network is the confirmatory unit. Candidate-outage rows are repeated
measurements within a network/state and are therefore reported descriptively;
uncertainty is estimated with a hierarchical network-cluster bootstrap.
"""

from __future__ import annotations

import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from build_epsr_evidence_dashboard import dc_confirmatory_gate, dc_summary_priority


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "outputs" / "pcc_v2_dc_scopf_gate"
CASE500_INPUT = ROOT / "outputs" / "pcc_v2_dc_scopf_case500_clarabel_portfolio"
OUTPUT = ROOT / "outputs" / "pcc_v2_dc_scopf_statistics"
CASES = ("case39", "case73", "case118", "case300", "case500")
OFFSETS = tuple(range(10))
SEED = 20260807
REPETITIONS = 20000
SUPERSEDED_CASE500_ARTIFACTS = [
    "outputs/pcc_v2_dc_scopf_gate/dc_scopf_gate_all_case500_offset0_1states_summary.json",
    "outputs/pcc_v2_dc_scopf_case500_screened/aborted_v3_exact_alias_timeout_attempts.jsonl",
    "outputs/pcc_v2_dc_scopf_case500_constraint_generation/aborted_v4_highs_cg_timeout_attempts.jsonl",
    "outputs/pcc_v2_dc_scopf_case500_clarabel/aborted_v5_clarabel_add_all_numerical_error_attempts.jsonl",
    "outputs/pcc_v2_dc_scopf_case500_clarabel_top1/aborted_v6_offset2_clarabel_top1_attempts.jsonl",
    "outputs/pcc_v2_dc_scopf_case500_hybrid_exact/aborted_v7_offset1_hybrid_attempts.jsonl",
    "protocols/dc_scopf_case500_clarabel_portfolio_v8.yaml",
    "outputs/pcc_v2_dc_scopf_case500_clarabel_portfolio/dc_scopf_gate_all_case500_offset0_1states_v8_summary.json",
    "protocols/dc_scopf_case500_base_clarabel_v9.yaml",
    "protocols/dc_scopf_case500_full_clarabel_v10.yaml",
    "outputs/pcc_v2_dc_scopf_case500_clarabel_portfolio/dc_scopf_gate_all_case500_offset0_1states_v10_summary.json",
    "protocols/dc_scopf_case500_tight_dual_v11.yaml",
    "outputs/pcc_v2_dc_scopf_case500_clarabel_portfolio/solver_attempts.jsonl",
]


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def descriptive(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "median": None, "iqr": [None, None], "range": [None, None]}
    return {
        "n": len(values),
        "median": statistics.median(values),
        "iqr": [quantile(values, 0.25), quantile(values, 0.75)],
        "range": [min(values), max(values)],
    }


def hierarchical_cluster_bootstrap(rows: list[dict], field: str) -> list[float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[row["network"]].append(float(row[field]))
    networks = sorted(grouped)
    rng = random.Random(SEED)
    samples: list[float] = []
    for _ in range(REPETITIONS):
        values: list[float] = []
        for network in rng.choices(networks, k=len(networks)):
            cluster = grouped[network]
            values.extend(rng.choices(cluster, k=len(cluster)))
        samples.append(statistics.median(values))
    return samples


def summarize_effect(rows: list[dict], field: str) -> dict:
    values = [float(row[field]) for row in rows]
    if not values:
        return {**descriptive(values), "networks": 0, "ready": False}
    network_medians = {
        network: statistics.median(float(row[field]) for row in rows if row["network"] == network)
        for network in sorted({row["network"] for row in rows})
    }
    nonzero = [value for value in network_medians.values() if value != 0]
    positive = sum(value > 0 for value in nonzero)
    sign_p = (
        sum(math.comb(len(nonzero), k) for k in range(positive, len(nonzero) + 1)) / 2 ** len(nonzero)
        if nonzero
        else 1.0
    )
    bootstrap = hierarchical_cluster_bootstrap(rows, field)
    return {
        **descriptive(values),
        "networks": len(network_medians),
        "positive_rows": sum(value > 0 for value in values),
        "network_medians": network_medians,
        "positive_network_medians": positive,
        "nonzero_network_medians": len(nonzero),
        "exact_one_sided_network_sign_p": sign_p,
        "hierarchical_cluster_bootstrap_median_95": [
            quantile(bootstrap, 0.025),
            quantile(bootstrap, 0.975),
        ],
        "bootstrap_seed": SEED,
        "bootstrap_repetitions": REPETITIONS,
        "ready": True,
    }


def load_terminal_states() -> tuple[dict[tuple[str, int], dict], dict[tuple[str, int], Path]]:
    summaries: dict[tuple[str, int], dict] = {}
    csv_paths: dict[tuple[str, int], Path] = {}
    for directory in (INPUT, CASE500_INPUT):
        for path in sorted(directory.glob("dc_scopf_gate_all_*_summary.json")):
            summary = json.loads(path.read_text(encoding="utf-8"))
            cases = summary.get("cases_requested", [])
            if (
                not dc_summary_priority(summary)
                or summary.get("candidate_mode") != "all"
                or len(cases) != 1
                or summary.get("states_per_case_requested") != 1
            ):
                continue
            key = (str(cases[0]), int(summary.get("state_offset", -1)))
            if key in summaries and dc_summary_priority(summary) <= dc_summary_priority(summaries[key]):
                continue
            summaries[key] = summary
            csv_path = path.with_name(path.name.replace("_summary.json", "_results.csv"))
            if csv_path.exists():
                csv_paths[key] = csv_path
            else:
                csv_paths.pop(key, None)
    return summaries, csv_paths


def main() -> None:
    summaries, csv_paths = load_terminal_states()
    retained_v2_case500_path = (
        INPUT / "dc_scopf_gate_all_case500_offset0_1states_summary.json"
    )
    retained_v2_case500 = (
        json.loads(retained_v2_case500_path.read_text(encoding="utf-8"))
        if retained_v2_case500_path.exists()
        else None
    )
    ordered_keys = [
        (case, offset)
        for case in CASES
        for offset in OFFSETS
        if (case, offset) in summaries and (case, offset) in csv_paths
    ]
    rows: list[dict] = []
    for key in ordered_keys:
        with csv_paths[key].open(encoding="utf-8") as stream:
            current = list(csv.DictReader(stream))
        for row in current:
            row["alias_post_contingency_loading_excess_pu"] = (
                float(row["alias_post_contingency_max_loading_pu"])
                - float(row["full_post_contingency_max_loading_pu"])
            )
            row["hidden_load_shed_mw"] = float(row["full_load_shed_mw"]) - float(row["alias_load_shed_mw"])
            full_post = float(row["full_post_contingency_max_loading_pu"])
            alias_post = float(row["alias_post_contingency_max_loading_pu"])
            full_objective = float(row["full_objective"])
            alias_objective = float(row["alias_objective"])
            row["paired_solver_valid"] = bool(
                math.isfinite(full_objective)
                and math.isfinite(alias_objective)
                and full_objective > 1e-9
                and alias_objective > 1e-9
            )
            row["strict_false_secure"] = (
                row["paired_solver_valid"]
                and full_post <= 1.0001
                and alias_post > 1.0001
            )
            row["exacerbated_existing_overload"] = (
                row["paired_solver_valid"]
                and full_post > 1.0001
                and alias_post > full_post + 1e-5
            )
        rows.extend(current)

    reported_alias_overlimit = [row for row in rows if row["false_secure_dispatch"] == "True"]
    false_secure = [row for row in rows if row["strict_false_secure"]]
    exacerbated = [row for row in rows if row["exacerbated_existing_overload"]]
    invalid_solver_rows = [row for row in rows if not row["paired_solver_valid"]]
    verification = [float(row["gate_verification_us"]) for row in rows]
    state_counts = Counter((row["network"], int(row["state_offset"])) for row in false_secure)
    false_secure_by_network = Counter(row["network"] for row in false_secure)
    gate = dc_confirmatory_gate(list(summaries.values()))
    harmful_starts = sum(int(row["harmful_solver_starts"] or 0) for row in rows)
    prevented = sum(
        row["gate_decision"] != "accept" and int(row["harmful_solver_starts"] or 0) == 0
        for row in false_secure
    )
    n = len(false_secure)

    summary = {
        "protocol": "pcc_v2_dc_scopf_confirmatory_statistics_v1",
        "confirmatory_unit": "network",
        "row_level_effects": "descriptive repeated candidate-outage measurements",
        "coverage": {
            "required_networks": list(CASES),
            "required_states_per_network": 10,
            "completed_states": len(ordered_keys),
            "completed_by_network": {
                case: sum(network == case for network, _offset in ordered_keys) for case in CASES
            },
            "rows": len(rows),
            "selected_terminal_failed_states": sum(
                int(item.get("failed_states", 0)) for item in summaries.values()
            ),
            "superseded_failed_attempts_retained": (
                int(retained_v2_case500.get("failed_states", 0))
                if retained_v2_case500
                and dc_summary_priority(summaries.get(("case500", 0), {})) > 1
                else 0
            ),
        },
        "safety": {
            "strict_false_secure_dispatches": n,
            "reported_alias_overlimit_rows_legacy": len(reported_alias_overlimit),
            "invalid_paired_solver_rows_retained": len(invalid_solver_rows),
            "invalid_paired_solver_rows_by_network": dict(sorted(Counter(
                row["network"] for row in invalid_solver_rows
            ).items())),
            "exacerbated_existing_overload_rows": len(exacerbated),
            "alias_overlimit_without_strict_or_exacerbated_attribution": (
                len(reported_alias_overlimit) - n - len(exacerbated)
            ),
            "unsafe_results_prevented": prevented,
            "prevention_rate_among_false_secure": prevented / n if n else None,
            "harmful_solver_starts": harmful_starts,
            "one_sided_95_clopper_pearson_upper_harmful_start_rate": 1 - 0.05 ** (1 / n) if n and harmful_starts == 0 else None,
            "false_secure_by_network": dict(sorted(false_secure_by_network.items())),
            "false_secure_by_network_state": {
                f"{network}:offset{offset}": count
                for (network, offset), count in sorted(state_counts.items())
            },
        },
        "effects_among_strict_false_secure": {
            "alias_post_contingency_loading_excess_pu": summarize_effect(
                false_secure, "alias_post_contingency_loading_excess_pu"
            ),
            "hidden_load_shed_mw": summarize_effect(false_secure, "hidden_load_shed_mw"),
            "relative_cost_understatement": summarize_effect(false_secure, "relative_cost_understatement"),
        },
        "gate_verification_us": descriptive(verification),
        "superseded_case500_attempt_artifacts": {
            "paths": SUPERSEDED_CASE500_ARTIFACTS,
            "all_retained": all((ROOT / path).is_file() for path in SUPERSEDED_CASE500_ARTIFACTS),
        },
        "gate": gate,
        "ready": bool(
            gate["ready"]
            and n > 0
            and prevented == n
            and harmful_starts == 0
            and len({row["network"] for row in false_secure}) == len(CASES)
        ),
        "failure_policy": "all frozen terminal states and candidate rows retained; no outcome-dependent deletion",
        "classification_policy": (
            "strict false-secure requires a valid positive-objective full/alias pair, "
            "full_post<=1.0001 and alias_post>1.0001; legacy alias-overlimit labels and "
            "invalid solver rows remain in raw files and are reported separately"
        ),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
