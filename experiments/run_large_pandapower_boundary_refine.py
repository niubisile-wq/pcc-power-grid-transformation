"""Refine large-network PF boundaries near the transition region.

This follow-up audit searches lower-load factors for case6495rte and a tighter
transition band for case9241pegase so the boundary is not just coarse.
"""
from __future__ import annotations

import csv
import contextlib
import io
import json
import time
from pathlib import Path

import pandapower as pp
import pandapower.networks as nw

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "large_pandapower_boundary_refine_results_20260802.csv"
SUMMARY = ROOT / "large_pandapower_boundary_refine_summary_20260802.json"

CASES = {
    "case6495rte": nw.case6495rte,
    "case9241pegase": nw.case9241pegase,
}

MULTIPLIERS = {
    "case6495rte": [0.60, 0.70, 0.80, 0.90, 1.00],
    "case9241pegase": [1.00, 1.02, 1.04, 1.05, 1.06, 1.08, 1.10],
}
ALGORITHMS = ["nr", "iwamoto_nr"]


def run_case(case_name: str, constructor, multiplier: float, algorithm: str) -> dict:
    net = constructor()
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
                init="flat",
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
        "case": case_name,
        "n_bus": int(len(net.bus)),
        "n_line": int(len(net.line)),
        "load_multiplier": multiplier,
        "algorithm": algorithm,
        "converged": int(converged),
        "iterations": iterations if iterations is not None else "",
        "min_vm_pu": float(net.res_bus.vm_pu.min()) if converged and len(net.res_bus) else None,
        "max_line_loading_percent": float(net.res_line.loading_percent.max()) if converged and len(net.res_line) else None,
        "runtime_s": elapsed_s,
        "error": error,
    }


def main() -> None:
    rows = []
    for name, constructor in CASES.items():
        for multiplier in MULTIPLIERS[name]:
            for algorithm in ALGORITHMS:
                rows.append(run_case(name, constructor, multiplier, algorithm))

    with RESULTS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "audit_type": "large_public_pandapower_power_flow_boundary_refine",
        "solver": "pandapower.runpp",
        "cases": list(CASES),
        "case_bus_counts": {name: int(CASES[name]().bus.shape[0]) for name in CASES},
        "multipliers": MULTIPLIERS,
        "algorithms": ALGORITHMS,
        "n_trials": len(rows),
        "by_case": {},
        "scope_limit": "PF solvability only; transition-band refinement for large public networks",
    }
    for name in CASES:
        subset = [r for r in rows if r["case"] == name]
        by_alg = {}
        for alg in ALGORITHMS:
            rs = [r for r in subset if r["algorithm"] == alg]
            converged = [r["load_multiplier"] for r in rs if r["converged"]]
            failed = [r["load_multiplier"] for r in rs if not r["converged"]]
            by_alg[alg] = {
                "n_trials": len(rs),
                "converged_multipliers": converged,
                "failed_multipliers": failed,
                "last_converged": max(converged) if converged else None,
                "first_failed": min(failed) if failed else None,
            }
        summary["by_case"][name] = by_alg

    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
