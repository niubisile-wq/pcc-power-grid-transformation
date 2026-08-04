"""Extreme low/high load search for case6495rte.

This probes whether the large public network has any solvable band below 0.2x
or above 1.0x after the earlier boundary runs failed in the 0.6x-1.0x region.
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import time
from pathlib import Path

import pandapower as pp
import pandapower.networks as nw

ROOT = Path(__file__).resolve().parent
DATE = "20260803"
OUT_CSV = ROOT / f"case6495_extreme_search_results_{DATE}.csv"
OUT_JSON = ROOT / f"case6495_extreme_search_summary_{DATE}.json"

MULTIPLIERS = [round(x, 3) for x in list([0.01 * i for i in range(1, 20)]) + [1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30]]
ALGORITHMS = ["nr", "iwamoto_nr"]


def run_case(multiplier: float, algorithm: str) -> dict:
    net = nw.case6495rte()
    if len(net.load):
        net.load.loc[:, "p_mw"] *= multiplier
        net.load.loc[:, "q_mvar"] *= multiplier
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
    return {
        "converged": int(converged),
        "iterations": iterations,
        "runtime_s": time.perf_counter() - start,
        "min_vm_pu": float(net.res_bus.vm_pu.min()) if converged and len(net.res_bus) else None,
        "max_line_loading_percent": float(net.res_line.loading_percent.max()) if converged and len(net.res_line) else None,
        "error": error,
    }


def main() -> None:
    rows = []
    for multiplier in MULTIPLIERS:
        for algorithm in ALGORITHMS:
            rows.append({
                "case": "case6495rte",
                "n_bus": int(nw.case6495rte().bus.shape[0]),
                "n_line": int(nw.case6495rte().line.shape[0]),
                "load_multiplier": multiplier,
                "algorithm": algorithm,
                **run_case(multiplier, algorithm),
            })

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "audit_type": "case6495rte_extreme_search",
        "solver": "pandapower.runpp",
        "case": "case6495rte",
        "algorithms": ALGORITHMS,
        "multipliers": MULTIPLIERS,
        "n_trials": len(rows),
        "by_algorithm": {},
        "scope_limit": "extreme low/high load search only; public PF boundary evidence",
    }
    for algorithm in ALGORITHMS:
        rs = [r for r in rows if r["algorithm"] == algorithm]
        converged = [r["load_multiplier"] for r in rs if r["converged"]]
        failed = [r["load_multiplier"] for r in rs if not r["converged"]]
        summary["by_algorithm"][algorithm] = {
            "n_trials": len(rs),
            "converged_count": len(converged),
            "failed_count": len(failed),
            "last_converged": max(converged) if converged else None,
            "first_failed": min(failed) if failed else None,
        }

    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
