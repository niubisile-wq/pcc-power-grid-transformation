"""Audit unit mismatch and serialization-equivalence behavior on the public 3,000 lockbox substitute."""
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
RESULTS = ROOT / "public_3000_unit_serialization_audit_results_20260803.csv"
SUMMARY = ROOT / "public_3000_unit_serialization_audit_summary_20260803.json"

CASES = [
    ("case14", pp.networks.case14()),
    ("case30", pp.networks.case30()),
    ("case57", pp.networks.case57()),
]
N_PER_CASE = 1000
SEED = 20260801
UNIT_SCALE_FACTORS = [1.0, 1000.0, 0.001]


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


def make_lawful_split(canon: Canonicalizer, assets: dict, source_id: str) -> dict:
    source_asset = assets[source_id]
    target_ids = [f"{source_id}:part0", f"{source_id}:part1"]
    split_values = {
        target_ids[0]: {"p_mw": source_asset["p_mw"] / 2, "q_mvar": source_asset["q_mvar"] / 2},
        target_ids[1]: {"p_mw": source_asset["p_mw"] / 2, "q_mvar": source_asset["q_mvar"] / 2},
    }
    return canon.issue_split(source_id, target_ids, values=split_values)


def make_lawful_merge(canon: Canonicalizer, assets: dict, source_ids: list[str]) -> dict:
    target_id = source_ids[0] + ":merged"
    proof = digest({"snapshot": canon.snapshot_hash, "source_ids": sorted(source_ids), "target_id": target_id})
    merge_values = {
        "p_mw": sum(assets[s]["p_mw"] for s in source_ids),
        "q_mvar": sum(assets[s]["q_mvar"] for s in source_ids),
    }
    return canon.issue_merge(source_ids, target_id, values=merge_values, identity_equivalence_proof=proof)


def reorder_dict(cert: dict) -> dict:
    items = list(cert.items())
    items.reverse()
    return dict(items)


def main() -> None:
    rows = []
    timings = {"unit_split": [], "unit_merge": [], "serialization": []}
    for case_offset, (case_name, base) in enumerate(CASES):
        base_loads = base.load[["bus", "p_mw", "q_mvar"]].copy()
        for j in range(N_PER_CASE):
            snapshot, canon, assets = build_snapshot(case_name, base, base_loads, j, case_offset)
            ids = list(assets)
            if len(ids) < 2:
                continue
            source = ids[0]
            merge_sources = ids[:2]

            lawful_split = make_lawful_split(canon, assets, source)
            lawful_merge = make_lawful_merge(canon, assets, merge_sources)

            # Unit mismatch: scale only one side by a factor that breaks unit consistency.
            for scale in UNIT_SCALE_FACTORS:
                t0 = time.perf_counter()
                unit_split_status = "REJECT"
                unit_split_reason = ""
                try:
                    source_asset = assets[source]
                    target_ids = [f"{source}:u0:{scale}", f"{source}:u1:{scale}"]
                    split_values = {
                        target_ids[0]: {"p_mw": source_asset["p_mw"] / 2 * scale, "q_mvar": source_asset["q_mvar"] / 2 * scale},
                        target_ids[1]: {"p_mw": source_asset["p_mw"] / 2, "q_mvar": source_asset["q_mvar"] / 2},
                    }
                    cert = canon.issue_split(source, target_ids, values=split_values)
                    unit_split_status = canon.verify(cert, requested_task="PF").status
                except Exception as exc:
                    unit_split_reason = f"{type(exc).__name__}:{exc}"
                timings["unit_split"].append(time.perf_counter() - t0)

                t0 = time.perf_counter()
                unit_merge_status = "REJECT"
                unit_merge_reason = ""
                try:
                    target_id = source + f":u_merge:{scale}"
                    proof = digest({"snapshot": canon.snapshot_hash, "source_ids": sorted(merge_sources), "target_id": target_id})
                    p_total = sum(assets[s]["p_mw"] for s in merge_sources)
                    q_total = sum(assets[s]["q_mvar"] for s in merge_sources)
                    cert = canon.issue_merge(
                        merge_sources,
                        target_id,
                        values={"p_mw": p_total * scale, "q_mvar": q_total * scale},
                        identity_equivalence_proof=proof,
                    )
                    unit_merge_status = canon.verify(cert, requested_task="PF").status
                except Exception as exc:
                    unit_merge_reason = f"{type(exc).__name__}:{exc}"
                timings["unit_merge"].append(time.perf_counter() - t0)

                rows.append({
                    "scenario_id": f"public-{case_name}-{j:04d}",
                    "case": case_name,
                    "test_kind": "unit_mismatch",
                    "scale": scale,
                    "split_status": unit_split_status,
                    "merge_status": unit_merge_status,
                    "split_reason": unit_split_reason,
                    "merge_reason": unit_merge_reason,
                })

            # Serialization equivalence: same logical cert, different JSON round-trips.
            for variant_name, variant in [
                ("ordered", reorder_dict(lawful_split)),
                ("pretty_roundtrip", json.loads(json.dumps(lawful_split, indent=2, ensure_ascii=False))),
                ("ascii_roundtrip", json.loads(json.dumps(lawful_split, indent=2, ensure_ascii=True))),
            ]:
                t0 = time.perf_counter()
                decision = canon.verify(variant, requested_task="PF")
                timings["serialization"].append(time.perf_counter() - t0)
                rows.append({
                    "scenario_id": f"public-{case_name}-{j:04d}",
                    "case": case_name,
                    "test_kind": "serialization_equivalence",
                    "scale": 1.0,
                    "variant": variant_name,
                    "split_status": decision.status,
                    "merge_status": "",
                    "split_reason": ";".join(decision.reasons),
                    "merge_reason": "",
                })

    fieldnames = sorted({key for row in rows for key in row})
    with RESULTS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    unit_rows = [r for r in rows if r["test_kind"] == "unit_mismatch"]
    ser_rows = [r for r in rows if r["test_kind"] == "serialization_equivalence"]
    summary = {
        "audit_type": "public_3000_unit_serialization_audit",
        "verifier": "h39_canonicalizer.Canonicalizer.issue_split / issue_merge / verify",
        "scenario_count": len(rows),
        "case_counts": {case: sum(r["case"] == case for r in unit_rows) for case, _ in CASES},
        "unit_mismatch": {
            str(scale): {
                "split_accept_rate": sum(r["scale"] == scale and r["split_status"] == ACCEPT for r in unit_rows) / sum(r["scale"] == scale for r in unit_rows),
                "merge_accept_rate": sum(r["scale"] == scale and r["merge_status"] == ACCEPT for r in unit_rows) / sum(r["scale"] == scale for r in unit_rows),
            }
            for scale in UNIT_SCALE_FACTORS
        },
        "serialization_equivalence": {
            variant: {
                "accept_rate": sum(r.get("variant") == variant and r["split_status"] == ACCEPT for r in ser_rows) / sum(r.get("variant") == variant for r in ser_rows),
            }
            for variant in ["ordered", "pretty_roundtrip", "ascii_roundtrip"]
        },
        "latency_ms": {
            "unit_split": {
                "p50": float(np.percentile(np.asarray(timings["unit_split"], dtype=float), 50) * 1000.0),
                "p95": float(np.percentile(np.asarray(timings["unit_split"], dtype=float), 95) * 1000.0),
                "p99": float(np.percentile(np.asarray(timings["unit_split"], dtype=float), 99) * 1000.0),
            },
            "unit_merge": {
                "p50": float(np.percentile(np.asarray(timings["unit_merge"], dtype=float), 50) * 1000.0),
                "p95": float(np.percentile(np.asarray(timings["unit_merge"], dtype=float), 95) * 1000.0),
                "p99": float(np.percentile(np.asarray(timings["unit_merge"], dtype=float), 99) * 1000.0),
            },
            "serialization": {
                "p50": float(np.percentile(np.asarray(timings["serialization"], dtype=float), 50) * 1000.0),
                "p95": float(np.percentile(np.asarray(timings["serialization"], dtype=float), 95) * 1000.0),
                "p99": float(np.percentile(np.asarray(timings["serialization"], dtype=float), 99) * 1000.0),
            },
        },
        "limitations": [
            "public IEEE/pandapower substitute, not H39 original lockbox",
            "unit mismatch is exercised as a contract-level scale perturbation, not a full external unit ontology",
            "serialization equivalence checks canonicalization invariance on the public schema",
        ],
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
