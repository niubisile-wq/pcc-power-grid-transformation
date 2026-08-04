"""Audit conservation-tolerance boundary on the public 3,000 lockbox substitute."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandapower as pp

from h39_canonicalizer import ACCEPT, Canonicalizer, canonical_json, digest

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "public_3000_conservation_boundary_audit_results_20260803.csv"
SUMMARY = ROOT / "public_3000_conservation_boundary_audit_summary_20260803.json"

CASES = [
    ("case14", pp.networks.case14()),
    ("case30", pp.networks.case30()),
    ("case57", pp.networks.case57()),
]
N_PER_CASE = 1000
SEED = 20260801
DELTAS = [0.0, 5e-13, 1e-12, 1.5e-12, 2e-12, 1e-11]


def build_snapshot(case_name: str, base, base_loads, scenario_index: int, case_offset: int):
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


def make_split(canon: Canonicalizer, assets: dict, source_id: str, delta: float) -> dict:
    source_asset = assets[source_id]
    target_ids = [f"{source_id}:part0", f"{source_id}:part1"]
    split_values = {
        target_ids[0]: {"p_mw": source_asset["p_mw"] / 2 + delta, "q_mvar": source_asset["q_mvar"] / 2 + delta},
        target_ids[1]: {"p_mw": source_asset["p_mw"] / 2, "q_mvar": source_asset["q_mvar"] / 2},
    }
    return canon.issue_split(source_id, target_ids, values=split_values)


def make_merge(canon: Canonicalizer, assets: dict, source_ids: list[str], delta: float) -> dict:
    target_id = source_ids[0] + ":merged"
    proof = digest({"snapshot": canon.snapshot_hash, "source_ids": sorted(source_ids), "target_id": target_id})
    p_total = sum(assets[s]["p_mw"] for s in source_ids)
    q_total = sum(assets[s]["q_mvar"] for s in source_ids)
    return canon.issue_merge(
        source_ids,
        target_id,
        values={"p_mw": p_total + delta, "q_mvar": q_total + delta},
        identity_equivalence_proof=proof,
    )


def main() -> None:
    rows = []
    timings = {"split": [], "merge": []}
    for case_offset, (case_name, base) in enumerate(CASES):
        base_loads = base.load[["bus", "p_mw", "q_mvar"]].copy()
        for j in range(N_PER_CASE):
            snapshot, canon, assets = build_snapshot(case_name, base, base_loads, j, case_offset)
            ids = list(assets)
            if len(ids) < 2:
                continue
            source = ids[0]
            merge_sources = ids[:2]

            for delta in DELTAS:
                t0 = time.perf_counter()
                split_decision = "REJECT"
                split_reason = ""
                try:
                    cert = make_split(canon, assets, source, delta)
                    split_decision = canon.verify(cert, requested_task="PF").status
                except Exception as exc:
                    split_reason = f"{type(exc).__name__}:{exc}"
                timings["split"].append(time.perf_counter() - t0)

                t0 = time.perf_counter()
                merge_decision = "REJECT"
                merge_reason = ""
                try:
                    cert = make_merge(canon, assets, merge_sources, delta)
                    merge_decision = canon.verify(cert, requested_task="PF").status
                except Exception as exc:
                    merge_reason = f"{type(exc).__name__}:{exc}"
                timings["merge"].append(time.perf_counter() - t0)

                rows.append({
                    "scenario_id": f"public-{case_name}-{j:04d}",
                    "case": case_name,
                    "delta": delta,
                    "split_decision": split_decision,
                    "merge_decision": merge_decision,
                    "split_reason": split_reason,
                    "merge_reason": merge_reason,
                })

    with RESULTS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    def block_rates(kind: str) -> dict[str, float]:
        out = {}
        for delta in DELTAS:
            subset = [r for r in rows if r["delta"] == delta]
            accepted = sum(r[f"{kind}_decision"] == ACCEPT for r in subset)
            out[str(delta)] = accepted / len(subset)
        return out

    summary = {
        "audit_type": "public_3000_conservation_boundary_audit",
        "verifier": "h39_canonicalizer.Canonicalizer.issue_split / issue_merge",
        "scenario_count": len(rows) // len(DELTAS),
        "case_counts": {case: sum(r["case"] == case for r in rows if r["delta"] == 0.0 and r["split_decision"]) for case, _ in CASES},
        "deltas": DELTAS,
        "split_accept_rate_by_delta": block_rates("split"),
        "merge_accept_rate_by_delta": block_rates("merge"),
        "latency_ms": {
            "split": {
                "p50": float(np.percentile(np.asarray(timings["split"], dtype=float), 50) * 1000.0),
                "p95": float(np.percentile(np.asarray(timings["split"], dtype=float), 95) * 1000.0),
                "p99": float(np.percentile(np.asarray(timings["split"], dtype=float), 99) * 1000.0),
            },
            "merge": {
                "p50": float(np.percentile(np.asarray(timings["merge"], dtype=float), 50) * 1000.0),
                "p95": float(np.percentile(np.asarray(timings["merge"], dtype=float), 95) * 1000.0),
                "p99": float(np.percentile(np.asarray(timings["merge"], dtype=float), 99) * 1000.0),
            },
        },
        "limitations": [
            "public IEEE/pandapower substitute, not H39 original lockbox",
            "tests the canonicalizer's conservation tolerance, not downstream model inference",
            "delta grid is discrete, so the exact float threshold is bracketed rather than analytically solved",
        ],
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
