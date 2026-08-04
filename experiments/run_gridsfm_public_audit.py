"""Run the released GridSFM-Open checkpoint on its 53 shipped samples.

This is a public-model baseline audit for the H39 protocol.  It is not an
H39 certificate result: the shipped samples are GridSFM's own benchmark and
the script only records the model's numerical predictions and reference
metrics.
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "model_assets" / "GridSFM" / "model"
sys.path.insert(0, str(MODEL_DIR))
sys.path.insert(0, str(MODEL_DIR / "examples"))

import torch
from gridsfm import batch_data_list, load_model, load_pyg_json, prepare_for_inference
from infer_samples import load_ground_truth, per_case_metrics, split_per_case


def main() -> None:
    samples = sorted((MODEL_DIR / "samples").glob("*.pyg.json"))
    checkpoint = MODEL_DIR / "checkpoints" / "gridsfm_open_v1.1.pt"
    if not samples or not checkpoint.exists():
        raise SystemExit("GridSFM samples or checkpoint missing")

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    model = load_model(str(checkpoint), device=device)
    t0 = time.perf_counter()
    prepared = [prepare_for_inference(load_pyg_json(p)) for p in samples]
    ground_truth = [load_ground_truth(p) for p in samples]
    prep_seconds = time.perf_counter() - t0
    t1 = time.perf_counter()
    batch = batch_data_list(prepared).to(device)
    with torch.no_grad():
        output = model(batch)
    forward_seconds = time.perf_counter() - t1
    predictions = split_per_case(output, len(samples))
    rows = []
    for path, pred, gt in zip(samples, predictions, ground_truth):
        m = per_case_metrics(pred, gt)
        rows.append({"case": path.stem.replace(".pyg", ""), **m})

    out_csv = ROOT / "gridsfm_public_results_20260801.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    def mean(key):
        vals = [float(r[key]) for r in rows if r[key] is not None]
        return sum(vals) / len(vals) if vals else None

    summary = {
        "scope": "public GridSFM-Open v1.1 shipped-sample baseline",
        "checkpoint_sha256": __import__("hashlib").sha256(checkpoint.read_bytes()).hexdigest(),
        "n_samples": len(rows),
        "device": device,
        "prep_seconds": prep_seconds,
        "forward_seconds": forward_seconds,
        "mean_V_MAE_pu": mean("V_mae"),
        "mean_theta_MAE_rad": mean("theta_mae"),
        "mean_Pg_MAE_pu": mean("Pg_mae"),
        "mean_Qg_MAE_pu": mean("Qg_mae"),
        "mean_cost_MAPE_percent": mean("cost_mape"),
        "max_cost_MAPE_percent": max(float(r["cost_mape"]) for r in rows if r["cost_mape"] is not None),
        "feasibility_accuracy": sum(r["feas_correct"] for r in rows) / len(rows),
        "limitations": [
            "The samples and labels are shipped with the public GridSFM repository.",
            "This is not an H39 certificate-aware, lockbox, or independent OOD evaluation.",
            "The GridSFM README states that cases below 500 buses are out of distribution; those cases are not in this sample set.",
        ],
    }
    (ROOT / "gridsfm_public_summary_20260801.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
