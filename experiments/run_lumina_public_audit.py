"""Run LUMINA-2M on public GridSFM/OPFData-format samples.

The model and inference package are public.  Results are a public baseline,
not H39 lockbox evidence.  The optional three-view section reuses the
controlled load split/merge witness used in the GridSFM audit.
"""
from __future__ import annotations

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
LUMINA_SRC = ROOT / "model_assets" / "lumina-inference" / "src"
SAMPLES = ROOT / "model_assets" / "GridSFM" / "model" / "samples"
sys.path.insert(0, str(LUMINA_SRC))

from lumina_inference import load_from_json_file
from lumina_inference.modeler import Modeler


def gt_metrics(pred, data):
    bus_gt = data["bus"].y
    gen_gt = data["generator"].y
    bus_mae = (pred["bus"] - bus_gt).abs()
    gen_mae = (pred["generator"] - gen_gt).abs()
    gen_x = data["generator"].x
    # GridSFM/OPFData generator columns: cp2=8, cp1=9, cp0=10.
    gt_cost = (gen_x[:, 8] * gen_gt[:, 0] ** 2 + gen_x[:, 9] * gen_gt[:, 0] + gen_x[:, 10]).sum()
    pred_cost = (gen_x[:, 8] * pred["generator"][:, 0] ** 2 + gen_x[:, 9] * pred["generator"][:, 0] + gen_x[:, 10]).sum()
    return {
        "V_mae": float(bus_mae[:, 1].mean()),
        "theta_mae": float(bus_mae[:, 0].mean()),
        "Pg_mae": float(gen_mae[:, 0].mean()),
        "Qg_mae": float(gen_mae[:, 1].mean()),
        "cost_mape": float((pred_cost - gt_cost).abs() / gt_cost.abs() * 100),
    }


def split_data(data):
    d = data.clone()
    i = 0
    bus = int(d["load", "load_link", "bus"].edge_index[1, i])
    row = d["load"].x[i].clone() / 2
    d["load"].x[i] = row
    d["load"].x = torch.cat([d["load"].x, row[None]], dim=0)
    new = d["load"].x.size(0) - 1
    d["load", "load_link", "bus"].edge_index = torch.cat([d["load", "load_link", "bus"].edge_index, torch.tensor([[new], [bus]])], 1)
    d["bus", "load_link", "load"].edge_index = torch.cat([d["bus", "load_link", "load"].edge_index, torch.tensor([[bus], [new]])], 1)
    return d


def invalid_merge(data):
    d = split_data(data)
    a, b = 0, d["load"].x.size(0) - 1
    d["load"].x[a] += d["load"].x[b]
    keep = torch.ones(d["load"].x.size(0), dtype=torch.bool)
    keep[b] = False
    d["load"].x = d["load"].x[keep]
    for et in [("load", "load_link", "bus"), ("bus", "load_link", "load")]:
        store = d[et]
        axis = 0 if et[0] == "load" else 1
        ids = store.edge_index[axis]
        good = ids != b
        ei = store.edge_index[:, good].clone()
        ei[axis][ei[axis] > b] -= 1
        store.edge_index = ei
    return d


def run(modeler, data):
    # Some public samples encode an empty shunt table as a one-dimensional
    # empty list; normalize that representation without changing semantics.
    if data["shunt"].x.ndim == 1:
        data["shunt"].x = data["shunt"].x.reshape(0, 2)
    for edge_type in data.edge_types:
        data[edge_type].edge_index = data[edge_type].edge_index.to(torch.long)
    with torch.no_grad():
        return modeler.predict_single(data, minmax_scaling=True, validate=True)


def main():
    cfg_path = ROOT / "model_assets" / "LUMINA-2M" / "config.json"
    weights = ROOT / "model_assets" / "LUMINA-2M" / "model.safetensors"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    device = torch.device(os.environ.get("H39_DEVICE", "cuda" if torch.cuda.is_available() else "cpu"))
    modeler = Modeler(device, verbose=False)
    modeler.load_model(cfg, load_file(str(weights)))

    samples = sorted(SAMPLES.glob("*.pyg.json"))
    official_rows = []
    t0 = time.perf_counter()
    for p in samples:
        d = load_from_json_file(str(p), require_solution=True)
        pred = run(modeler, d)
        official_rows.append({"case": p.stem.replace(".pyg", ""), "variant": "official", "certificate_status": "REFERENCE", **gt_metrics(pred, d)})
    official_seconds = time.perf_counter() - t0

    ablation_rows = []
    t1 = time.perf_counter()
    for p in samples:
        base = load_from_json_file(str(p), require_solution=True)
        for name, make, status in [("official", lambda x: x.clone(), "REFERENCE"), ("certified_split", split_data, "ACCEPT"), ("feature_only_merge", invalid_merge, "REJECT_INCONSISTENT")]:
            d = make(base)
            pred = run(modeler, d)
            ablation_rows.append({"case": p.stem.replace(".pyg", ""), "variant": name, "certificate_status": status, **gt_metrics(pred, base)})
    ablation_seconds = time.perf_counter() - t1

    def write(path, rows):
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)

    write(ROOT / "lumina_public_results_20260801.csv", official_rows)
    write(ROOT / "lumina_representation_ablation_20260801.csv", ablation_rows)

    def agg(rows):
        out = {}
        for v in sorted({r["variant"] for r in rows}):
            rs = [r for r in rows if r["variant"] == v]
            out[v] = {"n": len(rs), **{k: sum(r[k] for r in rs) / len(rs) for k in ["V_mae", "theta_mae", "Pg_mae", "Qg_mae", "cost_mape"]}, "certificate_statuses": sorted({r["certificate_status"] for r in rs})}
        return out

    summary = {
        "scope": "public LUMINA-2M v0.1.2 baseline on GridSFM shipped OPFData-format samples",
        "checkpoint_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
        "device": str(device),
        "official_n": len(official_rows),
        "official_seconds": official_seconds,
        "official_mean": agg(official_rows),
        "ablation_n_cases": len(samples),
        "ablation_seconds": ablation_seconds,
        "ablation": agg(ablation_rows),
        "limitations": ["samples and labels are public GridSFM repository artifacts", "not H39 independent lockbox", "certificate fields are sidecar only and not consumed by LUMINA", "no CGMES/SimBench or LUMINA-specific OPFDataset split"],
    }
    (ROOT / "lumina_public_summary_20260801.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
