"""Inject a public measured aggregate load profile into a public benchmark grid.

This is deliberately labelled as ``real-profile + benchmark-topology``.  It is
not a claim that the German profile belongs to the SimBench topology.
"""
from __future__ import annotations

import copy
import contextlib
import csv
import io
import json
import hashlib
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pandapower as pp
import simbench as sb

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / "model_assets" / "real_time_series" / "opsd_time_series_60min_singleindex_2020-10-06.csv"
CODE = "1-HVMVLV-urban-all-0-sw"
N_SNAPSHOTS = 200
SEED = 20260801


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    if not PROFILE.exists():
        raise FileNotFoundError(PROFILE)
    data = pd.read_csv(PROFILE, usecols=["utc_timestamp", "DE_load_actual_entsoe_transparency"])
    data["utc_timestamp"] = pd.to_datetime(data["utc_timestamp"], utc=True)
    data = data.dropna(subset=["DE_load_actual_entsoe_transparency"]).copy()
    data = data[data["DE_load_actual_entsoe_transparency"] > 0].reset_index(drop=True)
    raw = data["DE_load_actual_entsoe_transparency"].astype(float)
    median = float(raw.median())
    data["raw_relative_to_median"] = raw / median
    # The topology is not Germany's; clipping only prevents a foreign aggregate
    # profile from pushing an unrelated benchmark outside its solvable envelope.
    data["injected_factor"] = data["raw_relative_to_median"].clip(0.75, 1.25)
    rng = np.random.default_rng(SEED)
    idx = np.sort(rng.choice(len(data), size=min(N_SNAPSHOTS, len(data)), replace=False))
    chosen = data.iloc[idx].copy()

    base = sb.get_simbench_net(CODE)
    rows = []
    for _, rec in chosen.iterrows():
        net = copy.deepcopy(base)
        factor = float(rec["injected_factor"])
        net.load["p_mw"] *= factor
        net.load["q_mvar"] *= factor
        t0 = time.perf_counter()
        row = {
            "timestamp": rec["utc_timestamp"].isoformat(),
            "germany_load_mw": float(rec["DE_load_actual_entsoe_transparency"]),
            "relative_to_germany_median": float(rec["raw_relative_to_median"]),
            "injected_factor": factor,
            "converged": False,
            "min_vm_pu": None,
            "max_line_loading_percent": None,
            "runtime_s": None,
            "error": None,
        }
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                pp.runpp(net, algorithm="nr", init="dc", calculate_voltage_angles=True,
                         max_iteration=80, tolerance_mva=1e-8, trafo_model="t")
            row["converged"] = True
            row["min_vm_pu"] = float(net.res_bus.vm_pu.min())
            row["max_line_loading_percent"] = float(net.res_line.loading_percent.max()) if len(net.res_line) else None
        except Exception as exc:
            row["error"] = type(exc).__name__ + ": " + str(exc)[:180]
        row["runtime_s"] = time.perf_counter() - t0
        rows.append(row)

    out_csv = ROOT / "real_profile_injection_results_20260801.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    ok = [r for r in rows if r["converged"]]
    summary = {
        "dataset": "Open Power System Data time_series 60min, version 2020-10-06",
        "dataset_url": "https://data.open-power-system-data.org/time_series/2020-10-06/time_series_60min_singleindex.csv",
        "dataset_sha256": sha256(PROFILE),
        "profile_field": "DE_load_actual_entsoe_transparency",
        "profile_rows_after_missing_drop": len(data),
        "profile_start": data["utc_timestamp"].min().isoformat(),
        "profile_end": data["utc_timestamp"].max().isoformat(),
        "germany_load_median_mw": median,
        "germany_load_min_mw": float(raw.min()),
        "germany_load_max_mw": float(raw.max()),
        "benchmark": {"simbench_code": CODE, "buses": len(base.bus), "loads": len(base.load), "lines": len(base.line)},
        "sampling": {"seed": SEED, "requested": N_SNAPSHOTS, "used": len(rows), "factor_clip": [0.75, 1.25]},
        "convergence": {"n_converged": len(ok), "n_failed": len(rows) - len(ok), "rate": len(ok) / len(rows) if rows else 0.0},
        "converged_min_vm_pu": {"min": float(min(r["min_vm_pu"] for r in ok)) if ok else None, "median": float(np.median([r["min_vm_pu"] for r in ok])) if ok else None},
        "converged_max_line_loading_percent": {"max": float(max(r["max_line_loading_percent"] for r in ok)) if ok else None, "median": float(np.median([r["max_line_loading_percent"] for r in ok])) if ok else None},
        "interpretation": "real aggregate German operating profile injected into an unrelated public SimBench benchmark topology; not field validation of that topology",
    }
    (ROOT / "real_profile_injection_summary_20260801.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
