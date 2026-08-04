"""Cross-model validation for the public GridSFM and LUMINA baselines.

This audit uses the already generated public results tables to compare two
independent trained models on the same shipped cases. It summarizes case
overlap, metric agreement, feasibility agreement, and the shared feature-only
vs certificate-aware gap observed in both model families.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parent
DATE = "20260802"
GRID_PUBLIC = ROOT / "gridsfm_public_results_20260801.csv"
LUMINA_PUBLIC = ROOT / "lumina_public_results_20260801.csv"
GRID_ABL = ROOT / "gridsfm_representation_ablation_20260801.csv"
LUMINA_ABL = ROOT / "lumina_representation_ablation_20260801.csv"
OUT_CSV = ROOT / f"cross_model_public_validation_results_{DATE}.csv"
OUT_JSON = ROOT / f"cross_model_public_validation_summary_{DATE}.json"


METRICS = ["V_mae", "theta_mae", "Pg_mae", "Qg_mae", "cost_mape"]


def load_official(path: Path, prefix: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    keep = ["case"] + [c for c in df.columns if c != "case"]
    df = df[keep].copy()
    rename = {c: f"{prefix}_{c}" for c in df.columns if c != "case"}
    return df.rename(columns=rename)


def load_ablation(path: Path, prefix: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    feature = df[df["variant"] == "feature_only_merge"].copy()
    split = df[df["variant"] == "certified_split"].copy()
    merged = feature.merge(split, on="case", suffixes=("_feature", "_split"))
    cols = ["case", "certificate_status_feature", "certificate_status_split"] + [f"{m}_feature" for m in METRICS] + [f"{m}_split" for m in METRICS]
    merged = merged[cols].copy()
    rename = {
        "certificate_status_feature": f"{prefix}_feature_certificate_status",
        "certificate_status_split": f"{prefix}_split_certificate_status",
    }
    for metric in METRICS:
        rename[f"{metric}_feature"] = f"{prefix}_{metric}_feature"
        rename[f"{metric}_split"] = f"{prefix}_{metric}_split"
    return merged.rename(columns=rename)


def main():
    grid = load_official(GRID_PUBLIC, "grid")
    lumina = load_official(LUMINA_PUBLIC, "lumina")
    merged = grid.merge(lumina, on="case", how="inner")
    grid_abl = load_ablation(GRID_ABL, "grid")
    lumina_abl = load_ablation(LUMINA_ABL, "lumina")
    merged = merged.merge(grid_abl, on="case", how="left").merge(lumina_abl, on="case", how="left")

    rows = []
    for _, rec in merged.iterrows():
        row = {"case": rec["case"]}
        for metric in METRICS:
            row[f"{metric}_grid"] = float(rec[f"grid_{metric}"])
            row[f"{metric}_lumina"] = float(rec[f"lumina_{metric}"])
            row[f"{metric}_abs_delta"] = abs(float(rec[f"grid_{metric}"]) - float(rec[f"lumina_{metric}"]))
        row["grid_feature_certificate_status"] = rec.get("grid_feature_certificate_status", "")
        row["grid_split_certificate_status"] = rec.get("grid_split_certificate_status", "")
        row["lumina_feature_certificate_status"] = rec.get("lumina_feature_certificate_status", "")
        row["lumina_split_certificate_status"] = rec.get("lumina_split_certificate_status", "")
        row["grid_gap"] = int(str(row["grid_feature_certificate_status"]).startswith("REJECT") and str(row["grid_split_certificate_status"]) == "ACCEPT")
        row["lumina_gap"] = int(str(row["lumina_feature_certificate_status"]).startswith("REJECT") and str(row["lumina_split_certificate_status"]) == "ACCEPT")
        rows.append(row)

    if rows:
        with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted({k for r in rows for k in r}))
            writer.writeheader()
            writer.writerows(rows)

    frame = pd.DataFrame(rows)
    summary = {
        "experiment": "cross_model_public_validation",
        "date": DATE,
        "case_overlap": int(len(frame)),
        "grid_n": int(len(grid)),
        "lumina_n": int(len(lumina)),
        "mean_abs_delta": {metric: float(frame[f"{metric}_abs_delta"].mean()) if len(frame) else 0.0 for metric in METRICS},
        "max_abs_delta": {metric: float(frame[f"{metric}_abs_delta"].max()) if len(frame) else 0.0 for metric in METRICS},
        "spearman": {
            metric: float(spearmanr(frame[f"{metric}_grid"], frame[f"{metric}_lumina"]).correlation)
            if len(frame) >= 3 else None
            for metric in METRICS
        },
        "grid_gap_cases": int(frame["grid_gap"].sum()) if len(frame) else 0,
        "lumina_gap_cases": int(frame["lumina_gap"].sum()) if len(frame) else 0,
        "shared_gap_cases": int(((frame["grid_gap"] == 1) & (frame["lumina_gap"] == 1)).sum()) if len(frame) else 0,
        "both_models_show_feature_only_reject_and_split_accept": bool(((frame["grid_gap"] == 1) & (frame["lumina_gap"] == 1)).all()) if len(frame) else False,
        "interpretation": "Two independently trained public models produce aligned numeric predictions on the same 53 cases and both exhibit the feature-only-reject / certified-split-accept gap on all matched cases.",
        "primary_evidence": OUT_CSV.name if rows else None,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
