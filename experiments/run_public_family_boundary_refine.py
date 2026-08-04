"""Refine the PF transition bands for the most interesting public cases.

This focuses on the cases that showed a clear transition in the broad sweep:
case57 near 1.5x loading and case300 near the baseline regime.
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
OUT_CSV = ROOT / f"public_family_boundary_refine_results_{DATE}.csv"
OUT_JSON = ROOT / f"public_family_boundary_refine_summary_{DATE}.json"

CASES = {
    "case57": {
        "factory": pn.case57,
        "multipliers": [round(x, 3) for x in [1.20, 1.25, 1.30, 1.35, 1.40, 1.45, 1.50, 1.55, 1.60]],
    },
    "case300": {
        "factory": pn.case300,
        "multipliers": [round(x, 3) for x in [0.90, 0.95, 1.00, 1.05, 1.10]],
    },
}
ALGORITHMS = ["nr", "iwamoto_nr"]


def run_pf(net, algorithm: str) -> dict:
    start = time.perf_counter()
    error = ""
    converged = False
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            pp.runpp(
                net,
                algorithm=algorithm,
                init="flat",
                max_iteration=150,
                tolerance_mva=1e-8,
                calculate_voltage_angles=True,
            )
        converged = bool(net.converged)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
    return {
        "converged": int(converged),
        "runtime_s": time.perf_counter() - start,
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
        "audit_type": "public_family_boundary_refine",
        "solver": "pandapower.runpp",
        "cases": list(CASES),
        "algorithms": ALGORITHMS,
        "n_trials": len(rows),
        "by_case": {},
        "scope_limit": "public PF boundary refinement only; no H39-original claims",
    }
    for case_name, spec in CASES.items():
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
