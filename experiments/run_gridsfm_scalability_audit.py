"""CPU scalability audit on the 53 public GridSFM samples."""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

import psutil
import torch

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "model_assets" / "GridSFM" / "model"
sys.path.insert(0, str(MODEL_DIR))
from gridsfm import batch_data_list, load_model, load_pyg_json, prepare_for_inference


def quantile(values, q):
    return float(sorted(values)[min(len(values) - 1, int(round((len(values) - 1) * q)))])


def main():
    samples = sorted((MODEL_DIR / "samples").glob("*.pyg.json"))
    model = load_model(str(MODEL_DIR / "checkpoints" / "gridsfm_open_v1.1.pt"), device="cpu")
    process = psutil.Process(os.getpid())
    rows = []
    for path in samples:
        data = load_pyg_json(path)
        buses = int(data["bus"].x.size(0))
        t0 = time.perf_counter()
        prepared = prepare_for_inference(data)
        prep = time.perf_counter() - t0
        t1 = time.perf_counter()
        batch = batch_data_list([prepared])
        with torch.no_grad():
            out = model(batch)
        forward = time.perf_counter() - t1
        rows.append({"case": path.stem.replace(".pyg", ""), "buses": buses, "prep_s": prep, "forward_s": forward, "total_s": prep + forward, "rss_mb": process.memory_info().rss / 1024**2, "torch_version": torch.__version__, "device": "cpu"})

    out_csv = ROOT / "gridsfm_scalability_results_20260801.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    summary = {"scope": "public GridSFM-Open per-graph scalability audit", "n": len(rows), "device": "cpu", "torch_version": torch.__version__, "all": {k: {"p50": quantile([r[k] for r in rows], .50), "p95": quantile([r[k] for r in rows], .95), "p99": quantile([r[k] for r in rows], .99)} for k in ["prep_s", "forward_s", "total_s", "rss_mb"]}}
    for lo, hi in [(0, 1000), (1000, 3000), (3000, 10000), (10000, 20000)]:
        group = [r for r in rows if lo <= r["buses"] < hi]
        if group:
            summary[f"buses_{lo}_{hi}"] = {"n": len(group), "min_buses": min(r["buses"] for r in group), "max_buses": max(r["buses"] for r in group), "prep_p50_s": quantile([r["prep_s"] for r in group], .5), "forward_p50_s": quantile([r["forward_s"] for r in group], .5), "total_p95_s": quantile([r["total_s"] for r in group], .95)}
    (ROOT / "gridsfm_scalability_summary_20260801.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
