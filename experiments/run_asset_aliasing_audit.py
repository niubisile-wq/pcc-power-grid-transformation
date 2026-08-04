"""Asset-granularity aliasing audit on public pandapower asset tables.

The experiment uses real public network asset rows but a controlled duplicate
mutation. It measures the representation failure mode; it is not a full
canonicalizer or an OPF experiment.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import pandapower.networks as nw


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "asset_aliasing_results_20260801.csv"
SUMMARY = ROOT / "asset_aliasing_summary_20260801.json"
CASES = {"case14": nw.case14, "case30": nw.case30, "case57": nw.case57, "case118": nw.case118, "case300": nw.case300}


def load_assets(constructor):
    net = constructor()
    assets = []
    for idx, row in net.load.iterrows():
        assets.append({
            "stable_id": f"load:{idx}",
            "parent_id": f"load:{idx}",
            "asset_type": "load",
            "bus": int(row.bus),
            "p_mw": round(float(row.p_mw), 8),
            "q_mvar": round(float(row.q_mvar), 8),
        })
    return assets


def main():
    fields = [
        "case", "n_buses", "n_original_loads", "n_independent_assets",
        "n_lawful_split_assets", "feature_only_unique", "feature_only_collisions",
        "identity_aware_unique", "certified_parent_unique", "identity_loss_rate",
        "scope",
    ]
    rows = []
    for case, constructor in CASES.items():
        original = load_assets(constructor)
        independent = []
        lawful = []
        for asset in original:
            for part in ("a", "b"):
                child = dict(asset)
                child["stable_id"] = f"{asset['stable_id']}::{part}"
                child["parent_id"] = asset["parent_id"]
                independent.append(child)
                lawful.append(child)

        feature_groups = defaultdict(list)
        for asset in independent:
            key = (asset["asset_type"], asset["bus"], asset["p_mw"], asset["q_mvar"])
            feature_groups[key].append(asset["stable_id"])
        feature_unique = len(feature_groups)
        feature_collisions = sum(max(0, len(ids) - 1) for ids in feature_groups.values())
        identity_unique = len({a["stable_id"] for a in independent})
        certified_parent_unique = len({a["parent_id"] for a in lawful})
        rows.append({
            "case": case,
            "n_buses": int(constructor().bus.shape[0]),
            "n_original_loads": len(original),
            "n_independent_assets": len(independent),
            "n_lawful_split_assets": len(lawful),
            "feature_only_unique": feature_unique,
            "feature_only_collisions": feature_collisions,
            "identity_aware_unique": identity_unique,
            "certified_parent_unique": certified_parent_unique,
            "identity_loss_rate": feature_collisions / len(independent) if independent else 0.0,
            "scope": "real public asset rows + controlled duplicate mutation",
        })

    with RESULTS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "audit_type": "public_asset_aliasing_controlled_mutation",
        "cases": list(CASES),
        "total_original_loads": sum(r["n_original_loads"] for r in rows),
        "total_independent_assets": sum(r["n_independent_assets"] for r in rows),
        "total_feature_only_collisions": sum(r["feature_only_collisions"] for r in rows),
        "total_identity_aware_unique": sum(r["identity_aware_unique"] for r in rows),
        "total_certified_parent_unique": sum(r["certified_parent_unique"] for r in rows),
        "scope_limit": "controlled aliasing demonstration; no PF/OPF or production certificate implementation",
        "by_case": rows,
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
