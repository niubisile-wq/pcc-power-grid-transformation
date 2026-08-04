"""Audit chain-order tampering on the public 3,000 lockbox substitute."""
from __future__ import annotations

import copy
import csv
import json
import time
from pathlib import Path

import numpy as np
import pandapower as pp

from h39_canonicalizer import ACCEPT, Canonicalizer, canonical_json

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "public_3000_chain_order_audit_results_20260803.csv"
SUMMARY = ROOT / "public_3000_chain_order_audit_summary_20260803.json"

CASES = [
    ("case14", pp.networks.case14()),
    ("case30", pp.networks.case30()),
    ("case57", pp.networks.case57()),
]
N_PER_CASE = 1000
SEED = 20260801


def quantiles(values: list[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=float)
    return {
        "p50_ms": float(np.percentile(arr, 50) * 1000.0),
        "p95_ms": float(np.percentile(arr, 95) * 1000.0),
        "p99_ms": float(np.percentile(arr, 99) * 1000.0),
        "mean_ms": float(arr.mean() * 1000.0),
        "min_ms": float(arr.min() * 1000.0),
        "max_ms": float(arr.max() * 1000.0),
    }


def build_snapshot(case_name: str, base, base_loads, scenario_index: int, case_offset: int) -> tuple[dict, Canonicalizer, dict]:
    rng = np.random.default_rng(SEED + case_offset * 1_000_000 + scenario_index)
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
            "identity": f"public-{case_name}-{scenario_index:04d}:load:{i}",
        }
    snapshot = {"schema": "public-ieee-lockbox-v1", "scenario_id": f"public-{case_name}-{scenario_index:04d}", "assets": assets}
    return snapshot, Canonicalizer(snapshot), assets


def main() -> None:
    rows = []
    verify_times = {"lawful": [], "chain_order_tamper": []}
    for case_offset, (case_name, base) in enumerate(CASES):
        base_loads = base.load[["bus", "p_mw", "q_mvar"]].copy()
        for j in range(N_PER_CASE):
            snapshot, canon, assets = build_snapshot(case_name, base, base_loads, j, case_offset)
            ids = list(assets)
            source = ids[0]
            target_ids = [source + ":part0", source + ":part1"]
            source_asset = assets[source]
            split_values = {
                target_ids[0]: {"p_mw": source_asset["p_mw"] / 2, "q_mvar": source_asset["q_mvar"] / 2},
                target_ids[1]: {"p_mw": source_asset["p_mw"] / 2, "q_mvar": source_asset["q_mvar"] / 2},
            }
            lawful = canon.issue_split(source, target_ids, values=split_values)
            tampered = dict(lawful)
            tampered["composition_chain"] = list(reversed(tampered["composition_chain"]))
            tampered["chain_digest"] = canonical_json(tampered["composition_chain"])
            tampered["signature"] = canon.private_key.sign(canonical_json({k: v for k, v in tampered.items() if k != "signature"}).encode("utf-8")).hex()

            t0 = time.perf_counter()
            lawful_result = canon.verify(lawful, requested_task="PF")
            verify_times["lawful"].append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            tamper_result = canon.verify(tampered, requested_task="PF")
            verify_times["chain_order_tamper"].append(time.perf_counter() - t0)

            rows.append({
                "scenario_id": f"public-{case_name}-{j:04d}",
                "case": case_name,
                "lawful_decision": lawful_result.status,
                "chain_order_tamper_decision": tamper_result.status,
                "lawful_reason": ";".join(lawful_result.reasons),
                "chain_order_tamper_reason": ";".join(tamper_result.reasons),
                "tamper_type": "reverse_composition_chain",
                "tampered_chain": "|".join(reversed(lawful["composition_chain"])),
            })

    with RESULTS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "audit_type": "public_3000_chain_order_audit",
        "verifier": "h39_canonicalizer.Canonicalizer.verify",
        "scenario_count": len(rows),
        "case_counts": {case: sum(r["case"] == case for r in rows) for case, _ in CASES},
        "lawful_accepts": sum(r["lawful_decision"] == ACCEPT for r in rows),
        "chain_order_tamper_accepts": sum(r["chain_order_tamper_decision"] == ACCEPT for r in rows),
        "chain_order_tamper_block_rate": sum(r["chain_order_tamper_decision"] != ACCEPT for r in rows) / len(rows),
        "latency_ms": {
            "lawful": quantiles(verify_times["lawful"]),
            "chain_order_tamper": quantiles(verify_times["chain_order_tamper"]),
        },
        "limitations": [
            "public IEEE/pandapower substitute, not H39 original lockbox",
            "order tamper is a digest-level contract test, not a stateful replay cache",
            "composition-chain order sensitivity is exercised on the public canonicalizer schema",
        ],
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
