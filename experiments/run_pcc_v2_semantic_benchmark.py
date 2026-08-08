"""Frozen public-network semantic benchmark for PCC v1 versus PCC v2.

The experiment uses branch records from public PGLib-OPF cases.  It does not
claim that the generated loss is a naturally observed prevalence estimate.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
CGMES = ROOT / "cgmes"
if str(CGMES) not in sys.path:
    sys.path.insert(0, str(CGMES))

from validation.pcc_contract import PCCVerifier, issue_certificate  # noqa: E402
from validation.pcc_v2 import (  # noqa: E402
    ACCEPT,
    PCCV2Verifier,
    TaskContract,
    issue_v2_certificate,
)
from validation.proof_guided_repair import ProofGuidedRepairer  # noqa: E402


CASES = [
    "pglib_opf_case73_ieee_rts.m",
    "pglib_opf_case162_ieee_dtc.m",
    "pglib_opf_case1888_rte.m",
    "pglib_opf_case1951_rte.m",
    "pglib_opf_case2848_rte.m",
    "pglib_opf_case89_pegase.m",
    "pglib_opf_case1354_pegase.m",
    "pglib_opf_case2869_pegase.m",
    "pglib_opf_case179_goc.m",
    "pglib_opf_case500_goc.m",
    "pglib_opf_case793_goc.m",
    "pglib_opf_case588_sdet.m",
    "pglib_opf_case2853_sdet.m",
    "pglib_opf_case4661_sdet.m",
    "pglib_opf_case197_snem.m",
    "pglib_opf_case1803_snem.m",
    "pglib_opf_case240_pserc.m",
    "pglib_opf_case200_activ.m",
]
BASE_URL = "https://raw.githubusercontent.com/power-grid-lib/pglib-opf/v23.07/"
CACHE = ROOT / "downloads" / "pglib-opf-v23.07"
OUTPUT = ROOT / "outputs" / "pcc_v2_semantic_benchmark"
N_ASSETS = 16


def download_case(name: str) -> tuple[Path, str]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists():
        request = Request(BASE_URL + name, headers={"User-Agent": "PCC-v2-benchmark"})
        with urlopen(request, timeout=60) as response:
            data = response.read()
        path.write_bytes(data)
    data = path.read_bytes()
    return path, hashlib.sha256(data).hexdigest()


def parse_branches(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"mpc\.branch\s*=\s*\[(.*?)\];", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"branch_matrix_missing:{path.name}")
    rows: list[dict[str, object]] = []
    for raw in match.group(1).split(";"):
        raw = raw.split("%", 1)[0].strip()
        if not raw:
            continue
        values = raw.split()
        if len(values) < 11:
            continue
        rows.append(
            {
                "asset_type": "line",
                "from_bus": values[0],
                "to_bus": values[1],
                "r_pu": float(values[2]),
                "x_pu": float(values[3]),
                "rate_a": float(values[5]),
                "outage_capable": True,
                "p_mw": 0.0,
                "q_mvar": 0.0,
            }
        )
    if len(rows) < N_ASSETS:
        raise ValueError(f"insufficient_branches:{path.name}:{len(rows)}")
    return rows[:N_ASSETS]


def source_snapshot(branches: list[dict[str, object]]) -> dict[str, object]:
    return {"assets": {f"branch-{i:03d}": dict(row) for i, row in enumerate(branches)}}


def transformed_fixture(source: dict[str, object], dropped: int | None):
    target_assets = {}
    relations = []
    trace = []
    source_ids = list(source["assets"])
    target_ids = [f"canonical-{i:03d}" for i in range(len(source_ids))]
    for index, (source_id, target_id) in enumerate(zip(source_ids, target_ids)):
        if index == dropped:
            continue
        target_assets[target_id] = dict(source["assets"][source_id])
        relation = {
            "source_ids": [source_id],
            "target_ids": [target_id],
            "relation_type": "rename",
            "authoritative_evidence": {"kind": "signed_converter_trace"},
            "intervention_map": {source_id: [target_id]},
        }
        relations.append(relation)
        trace.append(
            {
                "source_id": source_id,
                "target_ids": [target_id],
                "relation_type": "rename",
                "authoritative": True,
                "evidence_kind": "signed_converter_trace",
            }
        )
    return {"assets": target_assets}, relations, trace, source_ids, target_ids


def zero_event_upper_95(n: int) -> float | None:
    return None if n <= 0 else 1.0 - 0.05 ** (1.0 / n)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    v1 = PCCVerifier(
        contract_version="pcc-cgmes-v1",
        trusted_issuers={"native-adapter": key.public_key()},
        stateful_replay_protection=False,
    )
    v2 = PCCV2Verifier(
        trusted_issuers={"native-adapter": key.public_key()},
        stateful_replay_protection=False,
    )
    rows = []
    downloads = []

    for case_name in CASES:
        path, sha256 = download_case(case_name)
        downloads.append({"case": case_name, "sha256": sha256})
        source = source_snapshot(parse_branches(path))
        for scenario in range(N_ASSETS):
            for label, dropped in (("lawful", None), ("harmful_drop", scenario)):
                target, relations, trace, source_ids, target_ids = transformed_fixture(source, dropped)
                task = TaskContract(
                    task_id="all-branch-n1",
                    task_kind="N1_AC",
                    source_assets=tuple(source_ids),
                    target_assets=tuple(target_ids),
                    intervention_type="outage",
                    required_attributes=("asset_type", "from_bus", "to_bus", "r_pu", "x_pu"),
                    tolerances={"r_pu": 1e-12, "x_pu": 1e-12},
                )
                existing_source = source_ids[0]
                existing_target = target_ids[0]
                if dropped == 0:
                    existing_source = source_ids[1]
                    existing_target = target_ids[1]
                v1_cert = issue_certificate(
                    source,
                    target,
                    source_ids=[existing_source],
                    target_ids=[existing_target],
                    relation_type="exact",
                    authorized_tasks=["N-1"],
                    issuer="native-adapter",
                    private_key=key,
                    certificate_id=f"v1:{case_name}:{label}:{scenario}",
                    transformation_id=f"v1:{case_name}:{label}:{scenario}",
                )
                v1_decision = v1.verify(source, target, v1_cert, requested_task="N-1")
                v2_cert = issue_v2_certificate(
                    source,
                    target,
                    task_contract=task,
                    relations=relations,
                    converter_trace=trace,
                    issuer="native-adapter",
                    private_key=key,
                    certificate_id=f"v2:{case_name}:{label}:{scenario}",
                    transformation_id=f"v2:{case_name}:{label}:{scenario}",
                    issued_at="2026-08-06T00:00:00Z",
                    nonce=f"{case_name}:{label}:{scenario}",
                )
                started = time.perf_counter_ns()
                v2_decision = v2.verify(
                    source,
                    target,
                    v2_cert,
                    requested_task="N1_AC",
                    converter_trace=trace,
                )
                verify_us = (time.perf_counter_ns() - started) / 1000.0
                repair_status = "not_applicable"
                repaired_verification = "not_applicable"
                if dropped is not None:
                    dropped_source = source_ids[dropped]
                    dropped_target = target_ids[dropped]
                    repair_trace = [
                        *trace,
                        {
                            "source_id": dropped_source,
                            "target_ids": [dropped_target],
                            "relation_type": "rename",
                            "authoritative": True,
                            "evidence_kind": "signed_converter_trace",
                            "reversible": True,
                            "reconstructed_assets": {
                                dropped_target: dict(source["assets"][dropped_source])
                            },
                        },
                    ]
                    repaired = ProofGuidedRepairer().repair(
                        source, target, task, relations, repair_trace
                    )
                    repair_status = repaired.status
                    if repaired.status == ACCEPT:
                        repaired_cert = issue_v2_certificate(
                            source,
                            repaired.target_snapshot,
                            task_contract=task,
                            relations=repaired.relations,
                            converter_trace=repair_trace,
                            issuer="native-adapter",
                            private_key=key,
                            certificate_id=f"v2-repaired:{case_name}:{scenario}",
                            transformation_id=f"v2-repaired:{case_name}:{scenario}",
                            issued_at="2026-08-06T00:00:00Z",
                            nonce=f"repaired:{case_name}:{scenario}",
                        )
                        repaired_verification = v2.verify(
                            source,
                            repaired.target_snapshot,
                            repaired_cert,
                            requested_task="N1_AC",
                            converter_trace=repair_trace,
                        ).status
                rows.append(
                    {
                        "case": case_name,
                        "scenario": scenario,
                        "class": label,
                        "v1_decision": v1_decision.status,
                        "v1_reasons": ";".join(v1_decision.reasons),
                        "v2_decision": v2_decision.status,
                        "v2_reasons": ";".join(v2_decision.reasons),
                        "v2_counterexamples": json.dumps(v2_decision.counterexamples, sort_keys=True),
                        "v2_verify_us": verify_us,
                        "v2_certificate_bytes": len(json.dumps(v2_cert, sort_keys=True).encode("utf-8")),
                        "repair_status": repair_status,
                        "repaired_verification": repaired_verification,
                    }
                )

    results_path = OUTPUT / "pcc_v2_semantic_results.csv"
    with results_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    harmful = [row for row in rows if row["class"] == "harmful_drop"]
    lawful = [row for row in rows if row["class"] == "lawful"]
    v1_harmful_accepts = sum(row["v1_decision"] == "accept" for row in harmful)
    v2_harmful_accepts = sum(row["v2_decision"] == ACCEPT for row in harmful)
    v2_lawful_accepts = sum(row["v2_decision"] == ACCEPT for row in lawful)
    v1_rate = v1_harmful_accepts / len(harmful)
    v2_rate = v2_harmful_accepts / len(harmful)
    lawful_rate = v2_lawful_accepts / len(lawful)
    repair_successes = sum(
        row["repair_status"] == ACCEPT and row["repaired_verification"] == ACCEPT
        for row in harmful
    )
    repair_rate = repair_successes / len(harmful)
    latencies = [float(row["v2_verify_us"]) for row in rows]
    certificate_sizes = [int(row["v2_certificate_bytes"]) for row in rows]
    go = (
        v2_harmful_accepts == 0
        and lawful_rate >= 0.99
        and (v1_rate - v2_rate) >= 0.20
        and repair_rate >= 0.95
    )
    summary = {
        "protocol": "pcc_v2_task_semantic_confirmatory_v1",
        "network_count": len(CASES),
        "harmful_n": len(harmful),
        "lawful_n": len(lawful),
        "v1_harmful_accepts": v1_harmful_accepts,
        "v1_unsafe_release_rate": v1_rate,
        "v2_harmful_accepts": v2_harmful_accepts,
        "v2_unsafe_release_rate": v2_rate,
        "v2_zero_event_one_sided_upper_95": zero_event_upper_95(len(harmful)) if v2_harmful_accepts == 0 else None,
        "v2_lawful_accepts": v2_lawful_accepts,
        "v2_lawful_acceptance_rate": lawful_rate,
        "absolute_unsafe_release_reduction": v1_rate - v2_rate,
        "repair_successes": repair_successes,
        "repair_success_rate": repair_rate,
        "verification_latency_us": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": max(latencies),
        },
        "certificate_bytes": {
            "p50": percentile([float(value) for value in certificate_sizes], 0.50),
            "p95": percentile([float(value) for value in certificate_sizes], 0.95),
            "max": max(certificate_sizes),
        },
        "go_no_go": "GO" if go else "NO_GO",
        "downloads": downloads,
        "scope": "controlled public-network task-semantic benchmark; not natural prevalence",
    }
    (OUTPUT / "pcc_v2_semantic_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
