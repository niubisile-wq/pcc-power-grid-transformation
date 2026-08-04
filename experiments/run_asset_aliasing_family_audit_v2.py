"""Family-level audit for the public asset-aliasing controlled mutation benchmark."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATE = "20260802"
INPUT = ROOT / "asset_aliasing_results_20260801.csv"
OUT_CSV = ROOT / f"asset_aliasing_family_audit_results_{DATE}.csv"
OUT_JSON = ROOT / f"asset_aliasing_family_audit_summary_{DATE}.json"


def main():
    df = pd.read_csv(INPUT)
    rows = []
    for _, rec in df.iterrows():
        rows.append({
            "case": rec["case"],
            "n_buses": int(rec["n_buses"]),
            "n_original_loads": int(rec["n_original_loads"]),
            "n_independent_assets": int(rec["n_independent_assets"]),
            "n_lawful_split_assets": int(rec["n_lawful_split_assets"]),
            "feature_only_unique": int(rec["feature_only_unique"]),
            "feature_only_collisions": int(rec["feature_only_collisions"]),
            "identity_aware_unique": int(rec["identity_aware_unique"]),
            "certified_parent_unique": int(rec["certified_parent_unique"]),
            "identity_loss_rate": float(rec["identity_loss_rate"]),
            "family": "asset_aliasing_controlled_mutation",
            "identity_relation": "same_numeric_fields_different_asset_identity",
        })

    if rows:
        with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted({k for r in rows for k in r}))
            writer.writeheader()
            writer.writerows(rows)

    frame = pd.DataFrame(rows)
    summary = {
        "experiment": "asset_aliasing_family_audit",
        "date": DATE,
        "cases": int(len(frame)),
        "case_names": frame["case"].tolist() if len(frame) else [],
        "total_original_loads": int(frame["n_original_loads"].sum()) if len(frame) else 0,
        "total_independent_assets": int(frame["n_independent_assets"].sum()) if len(frame) else 0,
        "total_feature_only_collisions": int(frame["feature_only_collisions"].sum()) if len(frame) else 0,
        "total_identity_aware_unique": int(frame["identity_aware_unique"].sum()) if len(frame) else 0,
        "total_certified_parent_unique": int(frame["certified_parent_unique"].sum()) if len(frame) else 0,
        "mean_identity_loss_rate": float(frame["identity_loss_rate"].mean()) if len(frame) else 0.0,
        "max_identity_loss_rate": float(frame["identity_loss_rate"].max()) if len(frame) else 0.0,
        "family": "asset_aliasing_controlled_mutation",
        "scope_limit": "controlled duplicate mutation on public asset rows; no PF/OPF downstream evaluation",
        "primary_evidence": OUT_CSV.name if rows else None,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
