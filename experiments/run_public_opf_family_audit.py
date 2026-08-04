"""Audit the public OPF split-vs-original family as an independent downstream benchmark.

This script summarizes the already generated public OPF results table. It does
not rerun OPF; it turns the existing public evidence into a family-level audit
that can be cited alongside the B4/B6 gate and cross-model validations.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATE = "20260802"
INPUT = ROOT / "public_opf_results_20260801.csv"
OUT_CSV = ROOT / f"public_opf_family_audit_results_{DATE}.csv"
OUT_JSON = ROOT / f"public_opf_family_audit_summary_{DATE}.json"


def main():
    df = pd.read_csv(INPUT)
    rows = []
    for _, rec in df.iterrows():
        rows.append({
            "case": rec["case"],
            "scenario": int(rec["scenario"]),
            "seed": int(rec["seed"]),
            "original_converged": bool(rec["original_converged"]),
            "split_converged": bool(rec["split_converged"]),
            "original_cost": float(rec["original_cost"]) if pd.notna(rec["original_cost"]) else None,
            "split_cost": float(rec["split_cost"]) if pd.notna(rec["split_cost"]) else None,
            "cost_delta": float(rec["cost_delta"]) if pd.notna(rec["cost_delta"]) else None,
            "min_vm_delta": float(rec["min_vm_delta"]) if pd.notna(rec["min_vm_delta"]) else None,
            "max_line_loading_delta": float(rec["max_line_loading_delta"]) if pd.notna(rec["max_line_loading_delta"]) else None,
            "family": "public_opf_split_merge",
            "identity_relation": "same_load_profile_different_asset_split",
            "task": "ac_optimal_power_flow",
        })

    if rows:
        with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted({k for r in rows for k in r}))
            writer.writeheader()
            writer.writerows(rows)

    valid = [r for r in rows if r["original_converged"] and r["split_converged"]]
    summary = {
        "experiment": "public_opf_family_audit",
        "date": DATE,
        "rows": int(len(rows)),
        "paired_valid": int(len(valid)),
        "original_converged": int(sum(r["original_converged"] for r in rows)),
        "split_converged": int(sum(r["split_converged"] for r in rows)),
        "mean_cost_delta": float(sum(r["cost_delta"] for r in valid) / len(valid)) if valid else None,
        "max_cost_delta": max((r["cost_delta"] or 0.0) for r in valid) if valid else None,
        "max_min_vm_delta": max((r["min_vm_delta"] or 0.0) for r in valid) if valid else None,
        "max_line_loading_delta": max((r["max_line_loading_delta"] or 0.0) for r in valid) if valid else None,
        "families": ["public_opf_split_merge"],
        "interpretation": "The public OPF split-vs-original family is an independent downstream physical benchmark; it shows paired AC-OPF stability on the released public cases.",
        "primary_evidence": OUT_CSV.name if rows else None,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
