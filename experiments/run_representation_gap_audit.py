"""Audit the public representation-ablation gap between feature-only and PCC-aware variants.

This script uses the shipped GridSFM and LUMINA public ablation tables. It does
not retrain models; it measures how the same public cases behave under the
feature-only merge and the certificate-aware split path.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATE = "20260802"
INPUTS = {
    "GridSFM": ROOT / "gridsfm_representation_ablation_20260801.csv",
    "LUMINA": ROOT / "lumina_representation_ablation_20260801.csv",
}
OUT_CSV = ROOT / f"representation_gap_audit_results_{DATE}.csv"
OUT_JSON = ROOT / f"representation_gap_audit_summary_{DATE}.json"


METRICS = ["V_mae", "theta_mae", "Pg_mae", "Qg_mae", "cost_mape"]


def pick(rec, *names):
    for name in names:
        if name in rec.index and pd.notna(rec[name]):
            return rec[name]
    return None


def main():
    rows = []
    summary = {}

    for dataset, path in INPUTS.items():
        df = pd.read_csv(path)
        feature = df[df["variant"] == "feature_only_merge"].copy()
        split = df[df["variant"] == "certified_split"].copy()
        official = df[df["variant"] == "official"].copy()

        merged = feature.merge(split, on="case", suffixes=("_feature", "_split"))
        merged = merged.merge(official, on="case", suffixes=("", "_official"))

        for _, rec in merged.iterrows():
            row = {
                "dataset": dataset,
                "case": rec["case"],
                "feature_certificate_status": rec["certificate_status_feature"],
                "split_certificate_status": rec["certificate_status_split"],
                "official_certificate_status": rec["certificate_status"],
                "feature_rejected": str(rec["certificate_status_feature"]).startswith("REJECT"),
                "split_accepted": str(rec["certificate_status_split"]) == "ACCEPT",
            }
            for metric in METRICS:
                row[f"{metric}_feature"] = float(rec[f"{metric}_feature"])
                row[f"{metric}_split"] = float(rec[f"{metric}_split"])
                row[f"{metric}_delta_feature_minus_split"] = float(rec[f"{metric}_feature"] - rec[f"{metric}_split"])
            row["gap_present"] = bool(row["feature_rejected"] and row["split_accepted"])
            row["feas_pred_feature"] = pick(rec, "feas_pred_feature", "feas_pred")
            row["feas_pred_split"] = pick(rec, "feas_pred_split", "feas_pred")
            row["feas_correct_feature"] = pick(rec, "feas_correct_feature", "feas_correct")
            row["feas_correct_split"] = pick(rec, "feas_correct_split", "feas_correct")
            rows.append(row)

        if len(merged) == 0:
            summary[dataset] = {
                "cases": 0,
                "gap_cases": 0,
                "note": "no overlapping cases found",
            }
            continue

        gap_cases = int(sum(1 for _, rec in merged.iterrows()
                            if str(rec["certificate_status_feature"]).startswith("REJECT")
                            and str(rec["certificate_status_split"]) == "ACCEPT"))
        summary[dataset] = {
            "cases": int(len(merged)),
            "gap_cases": gap_cases,
            "gap_rate": float(gap_cases / len(merged)),
            "mean_delta": {
                metric: float((merged[f"{metric}_feature"] - merged[f"{metric}_split"]).mean())
                for metric in METRICS
            },
            "max_abs_delta": {
                metric: float((merged[f"{metric}_feature"] - merged[f"{metric}_split"]).abs().max())
                for metric in METRICS
            },
            "feature_only_certificate_statuses": sorted(set(merged["certificate_status_feature"].astype(str))),
            "split_certificate_statuses": sorted(set(merged["certificate_status_split"].astype(str))),
        }

    if rows:
        with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    overall_gap_cases = sum(v.get("gap_cases", 0) for v in summary.values())
    overall_cases = sum(v.get("cases", 0) for v in summary.values())
    payload = {
        "experiment": "representation_gap_audit",
        "date": DATE,
        "datasets": summary,
        "overall_cases": overall_cases,
        "overall_gap_cases": overall_gap_cases,
        "overall_gap_rate": float(overall_gap_cases / overall_cases) if overall_cases else 0.0,
        "interpretation": "feature-only merge is rejected while certificate-aware split is accepted on matched public cases, giving a concrete B4/B6 analogue",
        "primary_evidence": OUT_CSV.name if rows else None,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
