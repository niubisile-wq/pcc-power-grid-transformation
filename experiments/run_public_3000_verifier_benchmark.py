"""Benchmark verifier and certificate construction on the public 3,000 lockbox."""
from __future__ import annotations

import copy
import csv
import gc
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandapower as pp
import psutil

from h39_canonicalizer import ACCEPT, REJECT_INCONSISTENT, Canonicalizer, canonical_json, digest

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "public_3000_verifier_benchmark_results_20260802.csv"
SUMMARY = ROOT / "public_3000_verifier_benchmark_summary_20260802.json"

CASES = [
    ("case14", pp.networks.case14()),
    ("case30", pp.networks.case30()),
    ("case57", pp.networks.case57()),
]
N_PER_CASE = 1000
REPEATS = 8
SEED = 20260801


def signed_cert(canon: Canonicalizer, certificate: dict) -> dict:
    unsigned = {k: v for k, v in certificate.items() if k != "signature"}
    certificate["signature"] = canon.private_key.sign(canonical_json(unsigned).encode("utf-8")).hex()
    return certificate


def quantiles(values: list[float], *, scale: float = 1.0) -> dict[str, float]:
    arr = np.asarray(values, dtype=float)
    return {
        "p50": float(np.percentile(arr, 50) * scale),
        "p95": float(np.percentile(arr, 95) * scale),
        "p99": float(np.percentile(arr, 99) * scale),
        "min": float(arr.min() * scale),
        "max": float(arr.max() * scale),
        "mean": float(arr.mean() * scale),
    }


def build_scenario(case_name: str, base, base_loads, scenario_index: int, case_offset: int) -> dict:
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
    canon = Canonicalizer(snapshot)

    ids = list(assets)
    source = ids[0]
    target_ids = [source + ":part0", source + ":part1"]
    source_asset = assets[source]
    split_values = {
        target_ids[0]: {"p_mw": source_asset["p_mw"] / 2, "q_mvar": source_asset["q_mvar"] / 2},
        target_ids[1]: {"p_mw": source_asset["p_mw"] / 2, "q_mvar": source_asset["q_mvar"] / 2},
    }

    split_t0 = time.perf_counter()
    lawful_split = canon.issue_split(source, target_ids, values=split_values)
    split_build_s = time.perf_counter() - split_t0

    if len(ids) < 2:
        raise RuntimeError("scenario does not have enough assets for merge benchmark")
    source_ids = ids[:2]
    target_id = source + ":merged"
    merge_values = {
        "p_mw": sum(assets[s]["p_mw"] for s in source_ids),
        "q_mvar": sum(assets[s]["q_mvar"] for s in source_ids),
    }
    proof = digest({"snapshot": canon.snapshot_hash, "source_ids": sorted(source_ids), "target_id": target_id})
    merge_t0 = time.perf_counter()
    lawful_merge = canon.issue_merge(source_ids, target_id, values=merge_values, identity_equivalence_proof=proof)
    merge_build_s = time.perf_counter() - merge_t0

    illegal_merge = dict(lawful_merge)
    illegal_merge["relation_type"] = "feature_only_merge"
    illegal_merge = signed_cert(canon, illegal_merge)

    return {
        "scenario_id": f"public-{case_name}-{scenario_index:04d}",
        "case": case_name,
        "n_bus": len(net.bus),
        "n_load": len(net.load),
        "snapshot": snapshot,
        "canon": canon,
        "lawful_split": lawful_split,
        "lawful_merge": lawful_merge,
        "feature_only_merge": illegal_merge,
        "split_build_s": split_build_s,
        "merge_build_s": merge_build_s,
        "lawful_split_bytes": len(canonical_json(lawful_split).encode("utf-8")),
        "lawful_merge_bytes": len(canonical_json(lawful_merge).encode("utf-8")),
        "feature_only_merge_bytes": len(canonical_json(illegal_merge).encode("utf-8")),
    }


def main() -> None:
    process = psutil.Process()
    prep_records = []
    for case_offset, (case_name, base) in enumerate(CASES):
        base_loads = base.load[["bus", "p_mw", "q_mvar"]].copy()
        for j in range(N_PER_CASE):
            prep_records.append(build_scenario(case_name, base, base_loads, j, case_offset))

    gc.collect()
    peak_rss = process.memory_info().rss
    verify_times = {"lawful_split": [], "feature_only_merge": []}
    build_times = {"lawful_split": [], "lawful_merge": []}
    rows = []

    for repeat in range(REPEATS):
        for rec in prep_records:
            canon = rec["canon"]
            build_times["lawful_split"].append(rec["split_build_s"])
            build_times["lawful_merge"].append(rec["merge_build_s"])

            t0 = time.perf_counter()
            decision_split = canon.verify(rec["lawful_split"], requested_task="PF")
            dt_split = time.perf_counter() - t0
            rss = process.memory_info().rss
            peak_rss = max(peak_rss, rss)
            verify_times["lawful_split"].append(dt_split)
            rows.append({
                "scenario_id": rec["scenario_id"],
                "case": rec["case"],
                "repeat": repeat,
                "verify_kind": "lawful_split",
                "decision": decision_split.status,
                "latency_s": dt_split,
                "rss_mb": rss / (1024 * 1024),
                "certificate_bytes": rec["lawful_split_bytes"],
                "build_split_s": rec["split_build_s"],
                "build_merge_s": rec["merge_build_s"],
            })

            t0 = time.perf_counter()
            decision_merge = canon.verify(rec["feature_only_merge"], requested_task="PF")
            dt_merge = time.perf_counter() - t0
            rss = process.memory_info().rss
            peak_rss = max(peak_rss, rss)
            verify_times["feature_only_merge"].append(dt_merge)
            rows.append({
                "scenario_id": rec["scenario_id"],
                "case": rec["case"],
                "repeat": repeat,
                "verify_kind": "feature_only_merge",
                "decision": decision_merge.status,
                "latency_s": dt_merge,
                "rss_mb": rss / (1024 * 1024),
                "certificate_bytes": rec["feature_only_merge_bytes"],
                "build_split_s": rec["split_build_s"],
                "build_merge_s": rec["merge_build_s"],
            })

    with RESULTS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "benchmark_type": "public_3000_verifier_benchmark",
        "verifier": "h39_canonicalizer.Canonicalizer.verify",
        "construction": {
            "lawful_split_ms": quantiles(build_times["lawful_split"], scale=1000.0),
            "lawful_merge_ms": quantiles(build_times["lawful_merge"], scale=1000.0),
        },
        "verification": {
            "lawful_split": {
                **quantiles(verify_times["lawful_split"], scale=1000.0),
                "accepts": sum(r["verify_kind"] == "lawful_split" and r["decision"] == ACCEPT for r in rows),
                "rejects": sum(r["verify_kind"] == "lawful_split" and r["decision"] != ACCEPT for r in rows),
            },
            "feature_only_merge": {
                **quantiles(verify_times["feature_only_merge"], scale=1000.0),
                "accepts": sum(r["verify_kind"] == "feature_only_merge" and r["decision"] == ACCEPT for r in rows),
                "rejects": sum(r["verify_kind"] == "feature_only_merge" and r["decision"] != ACCEPT for r in rows),
            },
        },
        "certificate_bytes": {
            "lawful_split": quantiles([r["certificate_bytes"] for r in rows if r["verify_kind"] == "lawful_split"]),
            "feature_only_merge": quantiles([r["certificate_bytes"] for r in rows if r["verify_kind"] == "feature_only_merge"]),
        },
        "peak_rss_mb": float(peak_rss / (1024 * 1024)),
        "repeats": REPEATS,
        "scenario_count": len(prep_records),
        "case_counts": {case: sum(r["case"] == case for r in prep_records) for case, _ in CASES},
        "total_calls": len(rows),
        "limitations": [
            "public IEEE/pandapower substitute, not H39 original lockbox",
            "protocol-level verifier benchmark, not downstream model inference",
            "certificate sizes reflect the public substitute schema",
        ],
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
