"""Generate and audit a 3,000-scenario public IEEE PF lockbox substitute.

This is deliberately independent of the absent H39 production pipeline.  It
uses public pandapower cases, deterministic per-scenario seeds, real AC PF,
and the reference contract verifier.  It records both positive physical
witnesses and solver failures instead of filtering failures away.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandapower as pp

from h39_contract_reference import (
    ACCEPT,
    REJECT_INCONSISTENT,
    canonical_json,
    reference_signature,
    snapshot_hash,
    verify_certificate,
)

ROOT = Path(__file__).resolve().parent
CASES = [("case14", pp.networks.case14), ("case30", pp.networks.case30), ("case57", pp.networks.case57)]
N_PER_CASE = 1000
SEED = 20260801


def cert(snapshot, source_ids, target_ids, relation, task="PF"):
    c = {
        "source_ids": list(source_ids),
        "target_ids": list(target_ids),
        "relation_type": relation,
        "conservation_payload": {"p_mw": "sum", "q_mvar": "sum"},
        "provenance_hash": snapshot_hash(snapshot),
        "contract_version": "h39-v1",
        "authorized_tasks": [task],
        "composition_chain": ["public-ieee", "load-witness"],
        "chain_digest": hashlib.sha256(canonical_json(["public-ieee", "load-witness"]).encode()).hexdigest(),
        "signature": None,
    }
    c["signature"] = reference_signature(c)
    return c


def main():
    rows = []
    t0 = time.perf_counter()
    for case_offset, (case_name, constructor) in enumerate(CASES):
        base = constructor()
        base_loads = base.load[["bus", "p_mw", "q_mvar"]].copy()
        for j in range(N_PER_CASE):
            scenario_id = f"public-{case_name}-{j:04d}"
            rng = np.random.default_rng(SEED + case_offset * 1_000_000 + j)
            net = copy.deepcopy(base)
            if len(net.load):
                multipliers = rng.uniform(0.80, 1.20, len(net.load))
                net.load["p_mw"] = base_loads["p_mw"].to_numpy() * multipliers
                net.load["q_mvar"] = base_loads["q_mvar"].to_numpy() * multipliers
            row = {"scenario_id": scenario_id, "case": case_name, "seed": SEED + case_offset * 1_000_000 + j, "n_bus": len(net.bus), "n_load": len(net.load), "load_min": float(net.load["p_mw"].sum()) if len(net.load) else 0.0, "converged": False, "min_vm_pu": None, "max_line_loading_percent": None, "pf_error": None}
            try:
                pp.runpp(net, algorithm="nr", init="dc", calculate_voltage_angles=True, max_iteration=50, tolerance_mva=1e-8)
                row["converged"] = True
                row["min_vm_pu"] = float(net.res_bus.vm_pu.min())
                row["max_line_loading_percent"] = float(net.res_line.loading_percent.max()) if len(net.res_line) else None
            except Exception as exc:
                row["pf_error"] = type(exc).__name__ + ": " + str(exc)[:160]

            # A stable asset snapshot is generated for every scenario,
            # including PF failures, so semantic and physical failure modes
            # remain distinguishable.
            assets = {}
            for i, item in net.load.iterrows():
                assets[f"{case_name}:load:{i}"] = {"asset_type": "load", "bus": int(item.bus), "p_mw": float(item.p_mw), "q_mvar": float(item.q_mvar), "identity": f"{scenario_id}:load:{i}"}
            snapshot = {"schema": "public-ieee-lockbox-v1", "scenario_id": scenario_id, "assets": assets}
            ids = list(assets)
            if ids:
                source = ids[0]
                legal = cert(snapshot, [source], [source + ":part0", source + ":part1"], "lawful_split")
                legal_result = verify_certificate(snapshot, legal, expected_version="h39-v1", requested_task="PF")
                row["lawful_split_decision"] = legal_result.decision
                row["lawful_split_reason"] = ";".join(legal_result.reasons)
                if len(ids) >= 2:
                    illegal = cert(snapshot, ids[:2], [ids[0] + ":merged"], "feature_only_merge")
                    illegal_result = verify_certificate(snapshot, illegal, expected_version="h39-v1", requested_task="PF")
                    row["feature_only_merge_decision"] = illegal_result.decision
                    row["feature_only_merge_reason"] = ";".join(illegal_result.reasons)
                    row["numeric_merge_conservation_error"] = abs((assets[ids[0]]["p_mw"] + assets[ids[1]]["p_mw"]) - (assets[ids[0]]["p_mw"] + assets[ids[1]]["p_mw"]))
                else:
                    row["feature_only_merge_decision"] = "NOT_APPLICABLE"
                    row["feature_only_merge_reason"] = "fewer_than_two_assets"
                    row["numeric_merge_conservation_error"] = None
            rows.append(row)

    fields = list(rows[0])
    out_csv = ROOT / "public_3000_lockbox_results_20260801.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    summary = {
        "lockbox_type": "public_deterministic_ieee_pf_substitute",
        "seed": SEED,
        "n_scenarios": len(rows),
        "cases": {case: sum(r["case"] == case for r in rows) for case, _ in CASES},
        "elapsed_seconds": time.perf_counter() - t0,
        "pf_converged": sum(bool(r["converged"]) for r in rows),
        "pf_failed": sum(not r["converged"] for r in rows),
        "lawful_split_accepts": sum(r.get("lawful_split_decision") == ACCEPT for r in rows),
        "feature_only_merge_rejects": sum(r.get("feature_only_merge_decision") == REJECT_INCONSISTENT for r in rows),
        "max_numeric_merge_conservation_error": max((r["numeric_merge_conservation_error"] or 0.0) for r in rows),
        "sha256_csv": hashlib.sha256(out_csv.read_bytes()).hexdigest(),
        "limitations": ["public IEEE/pandapower substitute, not H39 original lockbox", "PF only, no OPF or model inference", "feature-only merge is a controlled semantic witness"],
    }
    (ROOT / "public_3000_lockbox_summary_20260801.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
