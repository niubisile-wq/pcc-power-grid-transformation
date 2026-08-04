"""Census for naturally occurring asset-signature collisions in public GridSFM samples.

This script does not synthesize twins. It only scans released samples, hashes the
observed graph/asset signatures, and reports duplicate signatures across distinct
public samples and source variants.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "model_assets" / "GridSFM" / "model" / "samples"
DATE = "20260802"
OUT_CSV = ROOT / f"natural_asset_alias_census_results_{DATE}.csv"
OUT_JSON = ROOT / f"natural_asset_alias_census_summary_{DATE}.json"


def stable_hash(value) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonicalize(value):
    if isinstance(value, dict):
        return {str(k): canonicalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, list):
        return [canonicalize(v) for v in value]
    if isinstance(value, tuple):
        return [canonicalize(v) for v in value]
    if hasattr(value, "item"):
        try:
            return canonicalize(value.item())
        except Exception:
            pass
    return value


def sample_signature(obj) -> str:
    grid = obj.get("grid", {})
    nodes = grid.get("nodes", {})
    signature_payload = {
        "bus": canonicalize(nodes.get("bus", [])),
        "gen": canonicalize(nodes.get("gen", [])),
        "load": canonicalize(nodes.get("load", [])),
        "edges": canonicalize(grid.get("edges", {})),
        "bus_id_map": canonicalize(obj.get("bus_id_map")),
        "gen_id_map": canonicalize(obj.get("gen_id_map")),
        "load_id_map": canonicalize(obj.get("load_id_map")),
        "gen_bus_map": canonicalize(obj.get("gen_bus_map")),
        "load_bus_map": canonicalize(obj.get("load_bus_map")),
        "source_variant": obj.get("source_variant"),
        "system_load_factor": obj.get("system_load_factor"),
        "n_gens_killed": obj.get("n_gens_killed"),
        "n_lines_derated": obj.get("n_lines_derated"),
        "n_buses_vsqueezed": obj.get("n_buses_vsqueezed"),
        "objective": obj.get("objective"),
        "termination_status": obj.get("termination_status"),
    }
    return stable_hash(signature_payload)


def main():
    rows = []
    groups = defaultdict(list)
    for path in sorted(SAMPLES.glob("*.pyg.json")):
        obj = json.loads(path.read_text(encoding="utf-8"))
        meta = obj.get("metadata", {})
        sig = sample_signature(obj)
        row = {
            "sample": path.name,
            "scenario_id": meta.get("scenario_id", obj.get("scenario_id")),
            "source_variant": obj.get("source_variant"),
            "system_load_factor": obj.get("system_load_factor"),
            "n_gens_killed": obj.get("n_gens_killed"),
            "n_lines_derated": obj.get("n_lines_derated"),
            "n_buses_vsqueezed": obj.get("n_buses_vsqueezed"),
            "feasible": obj.get("feasible"),
            "signature_hash": sig,
        }
        rows.append(row)
        groups[sig].append(row)

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) + ["collision_group_size"] if rows else [])
        if rows:
            writer.writeheader()
            for row in rows:
                row = dict(row)
                row["collision_group_size"] = len(groups[row["signature_hash"]])
                writer.writerow(row)

    collision_groups = [items for items in groups.values() if len(items) > 1]
    collision_rows = sum(len(items) for items in collision_groups)
    distinct_samples = len(rows)
    summary = {
        "experiment": "natural_asset_alias_census",
        "date": DATE,
        "sample_count": distinct_samples,
        "signature_count": len(groups),
        "natural_collision_group_count": len(collision_groups),
        "natural_collision_sample_count": collision_rows,
        "natural_collision_rate": float(collision_rows / distinct_samples) if distinct_samples else 0.0,
        "max_collision_group_size": max((len(items) for items in collision_groups), default=1),
        "collision_groups": [
            {
                "signature_hash": items[0]["signature_hash"],
                "group_size": len(items),
                "samples": [item["sample"] for item in items],
                "source_variants": sorted({str(item["source_variant"]) for item in items}),
                "scenario_ids": sorted({str(item["scenario_id"]) for item in items}),
            }
            for items in collision_groups
        ],
        "scope_limit": "public sample census only; no synthesized twins and no PF/OPF downstream intervention",
        "primary_evidence": OUT_CSV.name,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
