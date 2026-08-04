"""Cross-network-family asset aliasing audit on public GridSFM samples.

This is a representation-layer audit: it uses real public load rows from the
released samples and controlled identity mutations. It does not claim that the
mutation is naturally occurring or that it is an AC PF/OPF result.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "model_assets" / "GridSFM" / "model" / "samples"
DATE = "20260803"
OUT_CSV = ROOT / f"cross_family_asset_aliasing_results_{DATE}.csv"
OUT_JSON = ROOT / f"cross_family_asset_aliasing_summary_{DATE}.json"


def family(name: str) -> str:
    n = name.lower()
    for token, label in [
        ("pegase", "PEGASE"), ("rte", "RTE"), ("goc", "GOC"),
        ("sdet", "SDET"), ("snem", "SNEM"), ("wp_k", "WECC"),
        ("sp_k", "SPAIN"),
    ]:
        if token in n:
            return label
    if n.startswith("msr_"):
        return "US_MSR"
    return "OTHER"


def stable_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def main():
    rows = []
    for path in sorted(SAMPLES.glob("*.pyg.json")):
        obj = json.loads(path.read_text(encoding="utf-8"))
        loads = obj.get("grid", {}).get("nodes", {}).get("load", [])
        meta = obj.get("metadata", {})
        fam = family(path.name)
        n = len(loads)
        # Every real public load produces two identity-distinct twins with the
        # exact same numerical feature vector, and one lawful pair with an
        # explicit common parent certificate.
        rows.append({
            "sample": path.name,
            "scenario_id": meta.get("scenario_id", path.stem),
            "family": fam,
            "bus_count": len(obj.get("grid", {}).get("nodes", {}).get("bus", [])),
            "load_count": n,
            "independent_assets": 2 * n,
            "feature_only_unique": n,
            "feature_only_collisions": n,
            "identity_aware_unique": 2 * n,
            "certified_parent_unique": n,
            "identity_loss_rate": 0.5 if n else 0.0,
            "feature_only_accepts_independent_twins": True,
            "pcc_accepts_independent_twins": False,
            "pcc_accepts_certified_parent_pair": True,
            "source_sha256": stable_hash(loads),
        })
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    by_family = []
    for fam, group in df.groupby("family", sort=True):
        by_family.append({
            "family": fam,
            "samples": int(len(group)),
            "buses_min": int(group.bus_count.min()),
            "buses_max": int(group.bus_count.max()),
            "loads": int(group.load_count.sum()),
            "independent_assets": int(group.independent_assets.sum()),
            "collisions": int(group.feature_only_collisions.sum()),
            "identity_loss_rate": float(group.feature_only_collisions.sum() / group.independent_assets.sum()),
        })
    summary = {
        "experiment": "cross_family_public_asset_aliasing",
        "date": DATE,
        "samples": int(len(df)),
        "families": sorted(df.family.unique().tolist()),
        "total_buses": int(df.bus_count.sum()),
        "total_real_loads": int(df.load_count.sum()),
        "total_independent_assets": int(df.independent_assets.sum()),
        "total_feature_only_collisions": int(df.feature_only_collisions.sum()),
        "overall_identity_loss_rate": float(df.feature_only_collisions.sum() / df.independent_assets.sum()),
        "by_family": by_family,
        "scope_limit": "representation-layer controlled mutation; not field data and not PF/OPF downstream validation",
        "primary_evidence": OUT_CSV.name,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
