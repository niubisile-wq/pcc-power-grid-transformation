"""Frozen 22-network, six-family PCC v2 semantic attack matrix."""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
import platform
import sys
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "cgmes", ROOT / "experiments"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_pcc_v2_semantic_benchmark import (  # noqa: E402
    CASES as ORIGINAL_CASES,
    download_case,
    parse_branches,
    source_snapshot,
    zero_event_upper_95,
)
from validation.evidence_schema import EvidenceRow, validate_evidence_mapping  # noqa: E402
from validation.pcc_contract import PCCVerifier, issue_certificate  # noqa: E402
from validation.pcc_v2 import (  # noqa: E402
    ACCEPT,
    PCCV2Verifier,
    TaskContract,
    digest,
    issue_v2_certificate,
)


CASES = [
    *ORIGINAL_CASES,
    "pglib_opf_case118_ieee.m",
    "pglib_opf_case300_ieee.m",
    "pglib_opf_case6470_rte.m",
    "pglib_opf_case9241_pegase.m",
]
ATTACK_FAMILIES = (
    "task_asset_drop",
    "independent_merge",
    "wrong_one_to_many",
    "target_id_reuse",
    "endpoint_parameter_swap",
    "source_snapshot_mismatch",
)
LAWFUL_PER_NETWORK = 30
ATTACKS_PER_FAMILY_NETWORK = 10
OUTPUT = ROOT / "outputs" / "pcc_v2_attack_matrix"


def _relation(source_ids: list[str], target_ids: list[str], kind: str = "rename") -> dict:
    return {
        "source_ids": source_ids,
        "target_ids": target_ids,
        "relation_type": kind,
        "authoritative_evidence": {"kind": "signed_converter_trace"},
        "intervention_map": {source_id: list(target_ids) for source_id in source_ids},
    }


def _trace(source_ids: list[str], target_ids: list[str], kind: str = "rename") -> list[dict]:
    return [
        {
            "source_id": source_id,
            "target_ids": list(target_ids),
            "relation_type": kind,
            "authoritative": True,
            "evidence_kind": "signed_converter_trace",
        }
        for source_id in source_ids
    ]


def transform(source: dict, family: str, seed: int) -> tuple[dict, list[dict], list[dict]]:
    source_ids = list(source["assets"])
    selected = seed % len(source_ids)
    neighbour = (selected + 1) % len(source_ids)
    target_assets: dict[str, dict] = {}
    relations: list[dict] = []
    trace: list[dict] = []
    handled: set[int] = set()

    for index, source_id in enumerate(source_ids):
        if index in handled:
            continue
        base_target = f"target-{seed:02d}-{index:03d}"
        if family == "task_asset_drop" and index == selected:
            handled.add(index)
            continue
        if family == "independent_merge" and index == selected:
            other_id = source_ids[neighbour]
            merged = f"target-{seed:02d}-merged"
            target_assets[merged] = copy.deepcopy(source["assets"][source_id])
            relations.append(_relation([source_id, other_id], [merged], "merge"))
            trace.extend(_trace([source_id, other_id], [merged], "merge"))
            handled.update({selected, neighbour})
            continue
        if family == "wrong_one_to_many" and index == selected:
            targets = [base_target + "-a", base_target + "-b"]
            for target_id in targets:
                target_assets[target_id] = copy.deepcopy(source["assets"][source_id])
            relations.append(_relation([source_id], targets, "exact"))
            trace.extend(_trace([source_id], targets, "exact"))
            handled.add(index)
            continue
        if family == "target_id_reuse" and index == selected:
            other_id = source_ids[neighbour]
            shared = f"target-{seed:02d}-shared"
            target_assets[shared] = copy.deepcopy(source["assets"][source_id])
            relations.append(_relation([source_id], [shared]))
            relations.append(_relation([other_id], [shared]))
            trace.extend(_trace([source_id], [shared]))
            trace.extend(_trace([other_id], [shared]))
            handled.update({selected, neighbour})
            continue

        target_assets[base_target] = copy.deepcopy(source["assets"][source_id])
        if family == "endpoint_parameter_swap" and index == selected:
            other = source["assets"][source_ids[neighbour]]
            target_assets[base_target]["from_bus"] = other["from_bus"]
            target_assets[base_target]["to_bus"] = other["to_bus"]
            target_assets[base_target]["r_pu"] = float(source["assets"][source_id]["r_pu"]) + 0.125
        relations.append(_relation([source_id], [base_target]))
        trace.extend(_trace([source_id], [base_target]))
        handled.add(index)

    return {"assets": target_assets}, relations, trace


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    v1 = PCCVerifier(
        contract_version="pcc-cgmes-v1",
        trusted_issuers={"confirmatory-adapter": key.public_key()},
        stateful_replay_protection=False,
    )
    v2 = PCCV2Verifier(
        trusted_issuers={"confirmatory-adapter": key.public_key()},
        stateful_replay_protection=False,
    )
    environment = f"{platform.system()}-python-{platform.python_version()}"
    evidence_rows: list[dict] = []
    result_rows: list[dict] = []
    downloads: list[dict] = []

    for case_name in CASES:
        case_path, sha256 = download_case(case_name)
        downloads.append({"case": case_name, "sha256": sha256})
        source = source_snapshot(parse_branches(case_path))
        scenarios = [
            ("lawful", "none", index) for index in range(LAWFUL_PER_NETWORK)
        ] + [
            ("harmful", family, index)
            for family in ATTACK_FAMILIES
            for index in range(ATTACKS_PER_FAMILY_NETWORK)
        ]
        for transform_class, family, seed in scenarios:
            scenario_id = f"{case_name}:{family}:{seed:02d}"
            target, relations, trace = transform(source, family, seed)
            verification_source = copy.deepcopy(source)
            if family == "source_snapshot_mismatch":
                selected_id = list(verification_source["assets"])[seed % len(source["assets"])]
                verification_source["assets"][selected_id]["source_version"] = "unexpected-v2"
            task = TaskContract(
                task_id=scenario_id,
                task_kind="N1_AC",
                source_assets=tuple(source["assets"]),
                target_assets=tuple(target["assets"]),
                intervention_type="outage",
                required_attributes=("asset_type", "from_bus", "to_bus", "r_pu", "x_pu"),
                tolerances={"r_pu": 1e-12, "x_pu": 1e-12},
            )
            existing_source = next(iter(relations[0]["source_ids"]))
            existing_target = next(iter(relations[0]["target_ids"]))
            v1_cert = issue_certificate(
                verification_source,
                target,
                source_ids=[existing_source],
                target_ids=[existing_target],
                relation_type="exact",
                authorized_tasks=["N-1"],
                issuer="confirmatory-adapter",
                private_key=key,
                certificate_id="v1:" + scenario_id,
                transformation_id="v1:" + scenario_id,
            )
            v1_decision = v1.verify(
                verification_source, target, v1_cert, requested_task="N-1"
            )
            v2_cert = issue_v2_certificate(
                source,
                target,
                task_contract=task,
                relations=relations,
                converter_trace=trace,
                issuer="confirmatory-adapter",
                private_key=key,
                certificate_id="v2:" + scenario_id,
                transformation_id="v2:" + scenario_id,
                issued_at="2026-08-06T00:00:00Z",
                nonce=scenario_id,
            )
            started = time.perf_counter_ns()
            v2_decision = v2.verify(
                verification_source,
                target,
                v2_cert,
                requested_task="N1_AC",
                converter_trace=trace,
            )
            verification_us = (time.perf_counter_ns() - started) / 1000.0
            result_rows.append(
                {
                    "scenario_id": scenario_id,
                    "network": case_name,
                    "transform_class": transform_class,
                    "attack_family": family,
                    "v1_decision": v1_decision.status,
                    "v1_reasons": ";".join(v1_decision.reasons),
                    "v2_decision": v2_decision.status,
                    "v2_reasons": ";".join(v2_decision.reasons),
                    "v2_verification_us": verification_us,
                }
            )
            common = dict(
                experiment_id="pcc-v2-six-family-confirmatory-v1",
                scenario_id=scenario_id,
                network=case_name,
                data_split="frozen_public_confirmatory",
                environment=environment,
                solver="none-semantic-verification",
                task_kind="N1_AC",
                state_id="base",
                transform_class=transform_class,
                attack_family=family,
                solver_status="not_run",
                solver_started=False,
                source_hash=digest(verification_source),
                target_hash=digest(target),
                consequence_observed=False,
                unsafe_result_prevented=False,
            )
            for baseline, decision, reasons, certificate, latency in (
                ("pcc_v1", v1_decision.status, v1_decision.reasons, v1_cert, None),
                ("pcc_v2", v2_decision.status, v2_decision.reasons, v2_cert, verification_us),
            ):
                row = EvidenceRow(
                    **common,
                    baseline=baseline,
                    decision=decision,
                    certificate_hash=digest(certificate),
                    reasons=tuple(reasons),
                    verification_us=latency,
                ).to_dict()
                validate_evidence_mapping(row)
                evidence_rows.append(row)

    with (OUTPUT / "attack_matrix_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result_rows[0]))
        writer.writeheader()
        writer.writerows(result_rows)
    with (OUTPUT / "evidence_rows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(evidence_rows[0]))
        writer.writeheader()
        writer.writerows(evidence_rows)

    harmful = [row for row in result_rows if row["transform_class"] == "harmful"]
    lawful = [row for row in result_rows if row["transform_class"] == "lawful"]
    v2_harmful_accepts = sum(row["v2_decision"] == ACCEPT for row in harmful)
    v2_lawful_accepts = sum(row["v2_decision"] == ACCEPT for row in lawful)
    latency = [float(row["v2_verification_us"]) for row in result_rows]
    by_family = {
        family: {
            "n": sum(row["attack_family"] == family for row in harmful),
            "accept": sum(
                row["attack_family"] == family and row["v2_decision"] == ACCEPT
                for row in harmful
            ),
            "reject": sum(
                row["attack_family"] == family and row["v2_decision"] == "reject"
                for row in harmful
            ),
            "unresolved": sum(
                row["attack_family"] == family and row["v2_decision"] == "unresolved"
                for row in harmful
            ),
        }
        for family in ATTACK_FAMILIES
    }
    summary = {
        "protocol": "pcc-v2-six-family-confirmatory-v1",
        "network_count": len(CASES),
        "lawful_n": len(lawful),
        "harmful_n": len(harmful),
        "v1_harmful_accepts": sum(row["v1_decision"] == ACCEPT for row in harmful),
        "v2_harmful_accepts": v2_harmful_accepts,
        "v2_unsafe_release_rate": v2_harmful_accepts / len(harmful),
        "v2_zero_event_one_sided_upper_95": (
            zero_event_upper_95(len(harmful)) if v2_harmful_accepts == 0 else None
        ),
        "v2_lawful_accepts": v2_lawful_accepts,
        "v2_lawful_acceptance_rate": v2_lawful_accepts / len(lawful),
        "by_attack_family": by_family,
        "verification_latency_us": {
            "p50": percentile(latency, 0.50),
            "p95": percentile(latency, 0.95),
            "p99": percentile(latency, 0.99),
            "max": max(latency),
        },
        "evidence_row_count": len(evidence_rows),
        "downloads": downloads,
        "go_no_go": "GO" if v2_harmful_accepts == 0 and v2_lawful_accepts / len(lawful) >= 0.99 else "NO_GO",
        "scope": "controlled semantic attacks on public network records; not field prevalence",
    }
    (OUTPUT / "attack_matrix_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
