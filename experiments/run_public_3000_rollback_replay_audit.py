"""Audit rollback and replay behavior on the public 3,000 lockbox substitute."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandapower as pp

from h39_contract_reference import ACCEPT, REJECT_INCONSISTENT, canonical_json, reference_signature, snapshot_hash, verify_certificate

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "public_3000_rollback_replay_audit_results_20260803.csv"
SUMMARY = ROOT / "public_3000_rollback_replay_audit_summary_20260803.json"

CASES = [
    ("case14", pp.networks.case14()),
    ("case30", pp.networks.case30()),
    ("case57", pp.networks.case57()),
]
N_PER_CASE = 1000
SEED = 20260801


def make_cert(snapshot: dict, source_id: str, target_ids: list[str], relation: str, task: str = "PF", version: str = "h39-v1") -> dict:
    cert = {
        "source_ids": [source_id],
        "target_ids": list(target_ids),
        "relation_type": relation,
        "conservation_payload": {"p_mw": "sum", "q_mvar": "sum"},
        "provenance_hash": snapshot_hash(snapshot),
        "contract_version": version,
        "authorized_tasks": [task],
        "composition_chain": ["public-ieee", "load-witness"],
        "chain_digest": hashlib.sha256(canonical_json(["public-ieee", "load-witness"]).encode("utf-8")).hexdigest(),
        "signature": None,
    }
    cert["signature"] = reference_signature(cert)
    return cert


def quantiles(values: list[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=float)
    return {
        "p50": float(np.percentile(arr, 50) * 1000.0),
        "p95": float(np.percentile(arr, 95) * 1000.0),
        "p99": float(np.percentile(arr, 99) * 1000.0),
        "mean": float(arr.mean() * 1000.0),
        "min": float(arr.min() * 1000.0),
        "max": float(arr.max() * 1000.0),
    }


def main() -> None:
    rows = []
    verify_times = {"baseline": [], "replay": [], "rollback": []}
    for case_index, (case_name, base) in enumerate(CASES):
        base_loads = base.load[["bus", "p_mw", "q_mvar"]].copy()
        for j in range(N_PER_CASE):
            rng = np.random.default_rng(SEED + case_index * 1_000_000 + j)
            net = copy.deepcopy(base)
            if len(net.load):
                multipliers = rng.uniform(0.80, 1.20, len(net.load))
                net.load["p_mw"] = base_loads["p_mw"].to_numpy() * multipliers
                net.load["q_mvar"] = base_loads["q_mvar"].to_numpy() * multipliers
            assets = {}
            for i, item in net.load.iterrows():
                assets[f"{case_name}:load:{i}"] = {
                    "asset_type": "load",
                    "bus": int(item.bus),
                    "p_mw": float(item.p_mw),
                    "q_mvar": float(item.q_mvar),
                    "identity": f"public-{case_name}-{j:04d}:load:{i}",
                }
            snapshot = {"schema": "public-ieee-lockbox-v1", "scenario_id": f"public-{case_name}-{j:04d}", "assets": assets}
            source_id = next(iter(assets))
            target_ids = [source_id + ":part0", source_id + ":part1"]
            source_asset = assets[source_id]
            split_values = {
                target_ids[0]: {"p_mw": source_asset["p_mw"] / 2, "q_mvar": source_asset["q_mvar"] / 2},
                target_ids[1]: {"p_mw": source_asset["p_mw"] / 2, "q_mvar": source_asset["q_mvar"] / 2},
            }
            # Build a lawful split certificate.
            lawful = make_cert(snapshot, source_id, target_ids, "lawful_split")
            # Mutate the same certificate through a version rollback.
            rollback = dict(lawful)
            rollback["contract_version"] = "h39-v0"
            rollback["signature"] = reference_signature(rollback)
            # Replay is the exact same certificate, re-verified without state.
            replay = dict(lawful)

            t0 = time.perf_counter()
            base_result = verify_certificate(snapshot, lawful, expected_version="h39-v1", requested_task="PF")
            verify_times["baseline"].append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            replay_result = verify_certificate(snapshot, replay, expected_version="h39-v1", requested_task="PF")
            verify_times["replay"].append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            rollback_result = verify_certificate(snapshot, rollback, expected_version="h39-v1", requested_task="PF")
            verify_times["rollback"].append(time.perf_counter() - t0)

            rows.append({
                "scenario_id": f"public-{case_name}-{j:04d}",
                "case": case_name,
                "baseline_decision": base_result.decision,
                "replay_decision": replay_result.decision,
                "rollback_decision": rollback_result.decision,
                "baseline_reason": ";".join(base_result.reasons),
                "replay_reason": ";".join(replay_result.reasons),
                "rollback_reason": ";".join(rollback_result.reasons),
                "replay_is_same_cert": 1,
                "rollback_version": rollback["contract_version"],
            })

    with RESULTS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "audit_type": "public_3000_rollback_replay_audit",
        "verifier": "h39_contract_reference.verify_certificate",
        "scenario_count": len(rows),
        "case_counts": {case: sum(r["case"] == case for r in rows) for case, _ in CASES},
        "baseline_accepts": sum(r["baseline_decision"] == ACCEPT for r in rows),
        "replay_accepts": sum(r["replay_decision"] == ACCEPT for r in rows),
        "rollback_accepts": sum(r["rollback_decision"] == ACCEPT for r in rows),
        "rollback_block_rate": sum(r["rollback_decision"] != ACCEPT for r in rows) / len(rows),
        "replay_accept_rate": sum(r["replay_decision"] == ACCEPT for r in rows) / len(rows),
        "verification_latency_ms": {
            "baseline": quantiles(verify_times["baseline"]),
            "replay": quantiles(verify_times["replay"]),
            "rollback": quantiles(verify_times["rollback"]),
        },
        "limitations": [
            "public IEEE/pandapower substitute, not H39 original lockbox",
            "stateless verifier; replay acceptance shows absence of a cache, not an implementation bug",
            "rollback is a contract-level version check, not a full provenance-chain replay cache",
        ],
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
