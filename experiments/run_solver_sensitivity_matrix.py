"""Solver sensitivity matrix for selected public pandapower cases.

This audit varies algorithm, initialization, and load multiplier on a small
set of cases that already showed interesting boundary behavior. The goal is to
make numerical stability and transition sensitivity explicit in one table.
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
OUT_CSV = ROOT / f"solver_sensitivity_matrix_results_{DATE}.csv"
OUT_JSON = ROOT / f"solver_sensitivity_matrix_summary_{DATE}.json"

CASES = {
    "case57": {
        "factory": pn.case57,
        "multipliers": [0.95, 1.0, 1.05, 1.10, 1.20, 1.30, 1.40, 1.45],
    },
    "case300": {
        "factory": pn.case300,
        "multipliers": [0.90, 1.0, 1.05, 1.10],
    },
    "case9241pegase": {
        "factory": pn.case9241pegase,
        "multipliers": [1.00, 1.02, 1.04, 1.06, 1.08],
    },
}
ALGORITHMS = ["nr", "iwamoto_nr", "bfsw"]
INITS = ["flat", "dc", "auto"]


def run_case(factory, multiplier: float, algorithm: str, init: str) -> dict:
    net = factory()
    if len(net.load):
        net.load.loc[:, "p_mw"] *= multiplier
        net.load.loc[:, "q_mvar"] *= multiplier
    start = time.perf_counter()
    error = ""
    converged = False
    iterations = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            pp.runpp(
                net,
                algorithm=algorithm,
                init=init,
                max_iteration=120,
                tolerance_mva=1e-8,
                calculate_voltage_angles=True,
            )
        converged = bool(net.converged)
        if isinstance(getattr(net, "_ppc", None), dict):
            iterations = net._ppc.get("iterations")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
    elapsed_s = time.perf_counter() - start
    return {
        "converged": int(converged),
        "iterations": iterations if iterations is not None else "",
        "runtime_s": elapsed_s,
        "min_vm_pu": float(net.res_bus.vm_pu.min()) if converged and len(net.res_bus) else None,
        "max_line_loading_percent": float(net.res_line.loading_percent.max()) if converged and len(net.res_line) else None,
        "error": error,
    }


def main() -> None:
    rows = []
    for case_name, spec in CASES.items():
        factory = spec["factory"]
        for multiplier in spec["multipliers"]:
            for algorithm in ALGORITHMS:
                for init in INITS:
                    result = run_case(factory, multiplier, algorithm, init)
                    rows.append({
                        "case": case_name,
                        "n_bus": int(factory().bus.shape[0]),
                        "n_line": int(factory().line.shape[0]),
                        "load_multiplier": multiplier,
                        "algorithm": algorithm,
                        "init": init,
                        **result,
                    })

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "audit_type": "solver_sensitivity_matrix",
        "solver": "pandapower.runpp",
        "cases": list(CASES),
        "algorithms": ALGORITHMS,
        "inits": INITS,
        "n_trials": len(rows),
        "by_case": {},
        "scope_limit": "public PF solver sensitivity only; not H39-original evidence",
    }
    for case_name in CASES:
        subset = [r for r in rows if r["case"] == case_name]
        by_alg = {}
        for algorithm in ALGORITHMS:
            rs = [r for r in subset if r["algorithm"] == algorithm]
            by_init = {}
            for init in INITS:
                rsi = [r for r in rs if r["init"] == init]
                converged = [r["load_multiplier"] for r in rsi if r["converged"]]
                failed = [r["load_multiplier"] for r in rsi if not r["converged"]]
                by_init[init] = {
                    "n_trials": len(rsi),
                    "converged_count": len(converged),
                    "failed_count": len(failed),
                    "last_converged": max(converged) if converged else None,
                    "first_failed": min(failed) if failed else None,
                }
            by_alg[algorithm] = by_init
        summary["by_case"][case_name] = by_alg

    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
