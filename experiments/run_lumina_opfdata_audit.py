"""Audit LUMINA-2M on its native public OPFData dataset entry point."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import torch
from safetensors.torch import load_file

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "model_assets" / "lumina-inference" / "src"))
from lumina_inference.dataset.opf_dataset import OPFDataset
from lumina_inference.modeler import Modeler


def normalize(data):
    if data["shunt"].x.ndim == 1:
        data["shunt"].x = data["shunt"].x.reshape(0, 2)
    for et in data.edge_types:
        data[et].edge_index = data[et].edge_index.to(torch.long)
    return data


def metrics(pred, data):
    bus = data["bus"].y
    gen = data["generator"].y
    gx = data["generator"].x
    gt_cost = (gx[:, 8] * gen[:, 0] ** 2 + gx[:, 9] * gen[:, 0] + gx[:, 10]).sum()
    pcost = (gx[:, 8] * pred["generator"][:, 0] ** 2 + gx[:, 9] * pred["generator"][:, 0] + gx[:, 10]).sum()
    return {
        "V_mae": float((pred["bus"][:, 1] - bus[:, 1]).abs().mean()),
        "theta_mae": float((pred["bus"][:, 0] - bus[:, 0]).abs().mean()),
        "Pg_mae": float((pred["generator"][:, 0] - gen[:, 0]).abs().mean()),
        "Qg_mae": float((pred["generator"][:, 1] - gen[:, 1]).abs().mean()),
        "cost_mape": float((pcost - gt_cost).abs() / gt_cost.abs() * 100),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--case", default="pglib_opf_case14_ieee")
    args = ap.parse_args()
    cfg = json.loads((ROOT / "model_assets" / "LUMINA-2M" / "config.json").read_text(encoding="utf-8"))
    weights = ROOT / "model_assets" / "LUMINA-2M" / "model.safetensors"
    device = torch.device(os.environ.get("H39_DEVICE", "cuda" if torch.cuda.is_available() else "cpu"))
    modeler = Modeler(device, verbose=False)
    modeler.load_model(cfg, load_file(str(weights)))
    dataset = OPFDataset(root=str(ROOT / "model_assets" / "lumina_opfdata"), case_name=args.case, group_id=0, n_jobs=4)
    n = min(args.n, len(dataset))
    rows = []
    t0 = time.perf_counter()
    for i in range(n):
        data = normalize(dataset[i])
        with torch.no_grad():
            pred = modeler.predict_single(data, minmax_scaling=True, validate=True)
        rows.append({"index": i, **metrics(pred, data)})
    elapsed = time.perf_counter() - t0
    out_csv = ROOT / f"lumina_opfdata_{args.case}_{n}_results_20260801.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    summary = {
        "scope": "native LUMINA OPFData public benchmark entry point",
        "case": args.case, "n": n, "device": str(device), "elapsed_seconds": elapsed,
        "checkpoint_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
        "mean": {k: sum(r[k] for r in rows) / n for k in rows[0] if k != "index"},
        "median": {k: sorted(r[k] for r in rows)[n // 2] for k in rows[0] if k != "index"},
        "limitations": ["single public case and group 0", "not H39 lockbox", "no certificate-aware input path"],
    }
    (ROOT / f"lumina_opfdata_{args.case}_{n}_summary_20260801.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
