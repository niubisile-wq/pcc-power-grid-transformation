"""Unified PF boundary sweep on public IEEE pandapower cases.

This adds a broad, reproducible robustness view across several public
networks without claiming any H39-original evidence. The goal is to provide
another clean public-substitute stress map that can be cited in the
experimental story.
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import time
from pathlib import Path

import pandapower as pp
import pandapower.networks as pn

ROOT = Path(__file__).resolve().parent
DATE = "20260803"
OUT_CSV = ROOT / f"public_family_boundary_sweep_results_{DATE}.csv"
OUT_JSON = ROOT / f"public_family_boundary_sweep_summary_{DATE}.json"

CASES = [
    ("case14", pn.case14),
    ("case30", pn.case30),
    ("case57", pn.case57),
    ("case118", pn.case118),
    ("case300", pn.case300),
]

# Broad but still cheap enough to run locally.
MULTIPLIERS = [round(x, 3) for x in [0.50, 0.60, 0.70, 0.80, 0.90, 1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.35, 1.40, 1.50]]
ALGORITHMS = ["nr", "iwamoto_nr"]


def run_pf(net, algorithm: str) -> dict:
    start = time.perf_counter()
    error = ""
    converged = False
    iterations = ""
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            pp.runpp(
                net,
                algorithm=algorithm,
                init="flat",
                max_iteration=120,
                tolerance_mva=1e-8,
                calculate_voltage_angles=True,
            )
        converged = bool(net.converged)
        if isinstance(getattr(net, "_ppc", None), dict):
            iterations = net._ppc.get("iterations", "")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
    elapsed_s = time.perf_counter() - start
    return {
        "converged": int(converged),
        "iterations": iterations,
        "runtime_s": elapsed_s,
        "min_vm_pu": float(net.res_bus.vm_pu.min()) if converged and len(net.res_bus) else None,
        "max_line_loading_percent": float(net.res_line.loading_percent.max()) if converged and len(net.res_line) else None,
        "error": error,
    }


def main() -> None:
    rows = []
    for case_name, factory in CASES:
        for multiplier in MULTIPLIERS:
            for algorithm in ALGORITHMS:
                net = factory()
                if len(net.load):
                    net.load.loc[:, "p_mw"] *= multiplier
                    net.load.loc[:, "q_mvar"] *= multiplier
                result = run_pf(net, algorithm)
                rows.append({
                    "case": case_name,
                    "n_bus": int(len(net.bus)),
                    "n_line": int(len(net.line)),
                    "load_multiplier": multiplier,
                    "algorithm": algorithm,
                    **result,
                })

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "audit_type": "public_family_boundary_sweep",
        "solver": "pandapower.runpp",
        "cases": [name for name, _ in CASES],
        "case_bus_counts": {name: int(factory().bus.shape[0]) for name, factory in CASES},
        "algorithms": ALGORITHMS,
        "multipliers": MULTIPLIERS,
        "n_trials": len(rows),
        "by_case": {},
        "scope_limit": "public PF boundary only; no claim about original H39 assets",
    }
    for case_name, _ in CASES:
        subset = [r for r in rows if r["case"] == case_name]
        by_alg = {}
        for algorithm in ALGORITHMS:
            rs = [r for r in subset if r["algorithm"] == algorithm]
            converged = [r["load_multiplier"] for r in rs if r["converged"]]
            failed = [r["load_multiplier"] for r in rs if not r["converged"]]
            by_alg[algorithm] = {
                "n_trials": len(rs),
                "converged_count": len(converged),
                "failed_count": len(failed),
                "last_converged": max(converged) if converged else None,
                "first_failed": min(failed) if failed else None,
            }
        summary["by_case"][case_name] = by_alg

    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
