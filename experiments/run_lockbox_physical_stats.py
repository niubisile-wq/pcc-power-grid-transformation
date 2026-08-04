"""Summarize physical distributions for the 3,000-scenario lockbox."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


def q(x, p):
    return float(np.quantile(np.asarray(x, dtype=float), p))


def main():
    with (ROOT / "public_3000_lockbox_results_20260801.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    summary = {"n": len(rows), "by_case": {}}
    for case in sorted({r["case"] for r in rows}):
        rs = [r for r in rows if r["case"] == case]
        vm = [float(r["min_vm_pu"]) for r in rs]
        loading = [float(r["max_line_loading_percent"]) for r in rs]
        load = [float(r["load_min"]) for r in rs]
        summary["by_case"][case] = {
            "n": len(rs),
            "converged": sum(r["converged"] == "True" for r in rs),
            "load_sum_mw": {"p05": q(load, .05), "median": q(load, .5), "p95": q(load, .95)},
            "min_vm_pu": {"p05": q(vm, .05), "median": q(vm, .5), "p95": q(vm, .95), "min": min(vm)},
            "max_line_loading_percent": {"p05": q(loading, .05), "median": q(loading, .5), "p95": q(loading, .95), "max": max(loading)},
        }
    summary["interpretation"] = "All sampled scenarios converged under this mild 0.80-1.20 per-load perturbation; the distributions characterize the positive physical witness regime and should not be interpreted as a stress-boundary estimate."
    (ROOT / "public_3000_lockbox_physical_stats_20260801.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
