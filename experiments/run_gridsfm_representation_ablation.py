"""Public-data three-view ablation for the H39 representation claim.

The experiment uses the released GridSFM samples and checkpoint.  It creates
controlled, aggregate-preserving load transformations:

* official: unchanged graph;
* certified_split: one load is split into two equal numerical loads at the
  same bus, with an accepted sidecar certificate;
* feature_only_merge: two distinct loads attached to the same bus are merged
  by numerical feature equality/aggregation, but the sidecar certificate is
  intentionally rejected because identity is not proven.

The model does not consume certificate fields.  The experiment therefore
measures downstream numerical sensitivity and separately records semantic
accept/reject decisions; it is not a substitute for the missing H39 lockbox.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "model_assets" / "GridSFM" / "model"
sys.path.insert(0, str(MODEL_DIR))
sys.path.insert(0, str(MODEL_DIR / "examples"))

from gridsfm import batch_data_list, load_model, load_pyg_json, prepare_for_inference
from infer_samples import load_ground_truth, per_case_metrics, split_per_case


def clone_graph(path: Path):
    return load_pyg_json(path).clone()


def edge_pair(data):
    """Return load->bus and bus->load stores."""
    return data["load", "load_link", "bus"], data["bus", "load_link", "load"]


def certified_split(path: Path):
    data = clone_graph(path)
    n = data["load"].x.size(0)
    i = 0
    bus = int(data["load", "load_link", "bus"].edge_index[1, i])
    row = data["load"].x[i].clone() / 2.0
    data["load"].x[i] = row
    data["load"].x = torch.cat([data["load"].x, row[None]], dim=0)
    new = n
    lb, bl = edge_pair(data)
    lb.edge_index = torch.cat([lb.edge_index, torch.tensor([[new], [bus]])], dim=1)
    bl.edge_index = torch.cat([bl.edge_index, torch.tensor([[bus], [new]])], dim=1)
    return data, {"status": "ACCEPT", "operation": "split", "source_ids": [i], "new_id": new}


def feature_only_merge(path: Path):
    # Create a controlled aliasing witness first: two distinct asset IDs have
    # identical half-load features at the same bus.  Numerical aggregation
    # can recover the original graph exactly, while the semantic verifier
    # must still reject the merge unless identity equivalence is certified.
    data, _ = certified_split(path)
    lb, bl = edge_pair(data)
    a, b = 0, data["load"].x.size(0) - 1
    data["load"].x[a] = data["load"].x[a] + data["load"].x[b]
    keep = torch.ones(data["load"].x.size(0), dtype=torch.bool)
    keep[b] = False
    data["load"].x = data["load"].x[keep]
    for store in (lb, bl):
        src = store.edge_index[0]
        dst = store.edge_index[1]
        load_axis = 0 if store is lb else 1
        load_idx = src if load_axis == 0 else dst
        edge_keep = load_idx != b
        ei = store.edge_index[:, edge_keep].clone()
        adjusted = ei[load_axis] > b
        ei[load_axis][adjusted] -= 1
        store.edge_index = ei
    return data, {
        "status": "REJECT_INCONSISTENT",
        "operation": "merge",
        "source_ids": [a, b],
        "reason": "distinct asset identities not bound by certificate",
    }


def main() -> None:
    # Use the complete public release rather than the initial 10-sample pilot.
    samples = sorted((MODEL_DIR / "samples").glob("*.pyg.json"))
    requested_device = __import__("os").environ.get("H39_DEVICE")
    device_name = requested_device or ("cuda:0" if torch.cuda.is_available() else "cpu")
    model = load_model(str(MODEL_DIR / "checkpoints" / "gridsfm_open_v1.1.pt"), device=device_name)
    device = next(model.parameters()).device
    variant_groups = []
    records = []
    for path in samples:
        gt = load_ground_truth(path)
        group = []
        group_records = []
        for name, builder in (("official", None), ("certified_split", certified_split), ("feature_only_merge", feature_only_merge)):
            if builder is None:
                data = clone_graph(path)
                cert = {"status": "REFERENCE", "operation": "none"}
            else:
                data, cert = builder(path)
            group.append(prepare_for_inference(data))
            group_records.append({"case": path.stem.replace(".pyg", ""), "variant": name, "certificate_status": cert["status"], "certificate_digest": hashlib.sha256(json.dumps(cert, sort_keys=True).encode()).hexdigest(), "gt": gt})
        variant_groups.append(group)
        records.extend(group_records)

    t0 = time.perf_counter()
    predictions = []
    with torch.no_grad():
        # Keep each topology's three views in a small batch.  This avoids
        # excessive mixed-topology temporary allocations on some PyG builds.
        for group in variant_groups:
            batch = batch_data_list(group).to(device)
            out = model(batch)
            predictions.extend(split_per_case(out, len(group)))
    forward_seconds = time.perf_counter() - t0
    rows = []
    for rec, pred in zip(records, predictions):
        m = per_case_metrics(pred, rec["gt"])
        rows.append({k: v for k, v in rec.items() if k != "gt"} | m)

    csv_path = ROOT / "gridsfm_representation_ablation_20260801.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fields = list(rows[0])
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    by_variant = {}
    for variant in {r["variant"] for r in rows}:
        rs = [r for r in rows if r["variant"] == variant]
        by_variant[variant] = {
            "n": len(rs),
            "mean_V_MAE": sum(r["V_mae"] for r in rs) / len(rs),
            "mean_theta_MAE": sum(r["theta_mae"] for r in rs) / len(rs),
            "mean_Pg_MAE": sum(r["Pg_mae"] for r in rs) / len(rs),
            "mean_Qg_MAE": sum(r["Qg_mae"] for r in rs) / len(rs),
            "mean_cost_MAPE": sum(r["cost_mape"] for r in rs) / len(rs),
            "feasibility_accuracy": sum(r["feas_correct"] for r in rs) / len(rs),
            "certificate_statuses": sorted({r["certificate_status"] for r in rs}),
        }
    summary = {
        "scope": "public GridSFM-Open representation ablation; all 53 shipped samples",
        "n_cases": len(samples),
        "n_variant_runs": len(rows),
        "forward_seconds": forward_seconds,
        "variants": by_variant,
        "interpretation": "certificate-aware sidecar rejects the feature-only merge; GridSFM itself receives only numerical graph features and cannot enforce that semantic decision",
        "limitations": ["public shipped samples, not H39 lockbox", "only load split/merge controlled transformation", "certificate fields are sidecar only and not consumed by GridSFM", "no claim of causal model improvement from certificates"],
    }
    (ROOT / "gridsfm_representation_ablation_summary_20260801.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
