"""Fine-grained PF boundary microcurve for selected public cases.

This script zooms in around the transition bands already identified in prior
audits. It is intentionally narrow and deterministic so it can produce a
clean continuous curve for the paper's boundary figure.
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
OUT_CSV = ROOT / f"boundary_microcurve_results_{DATE}.csv"
OUT_JSON = ROOT / f"boundary_microcurve_summary_{DATE}.json"

CASES = {
    "case57": {
        "factory": pn.case57,
        "multipliers": [round(x, 3) for x in [1.36, 1.37, 1.38, 1.39, 1.40, 1.41, 1.42, 1.43, 1.44, 1.45, 1.46]],
    },
    "case300": {
        "factory": pn.case300,
        "multipliers": [round(x, 3) for x in [0.94, 0.96, 0.98, 1.00, 1.02, 1.04]],
    },
    "case9241pegase": {
        "factory": pn.case9241pegase,
        "multipliers": [round(x, 3) for x in [1.04, 1.05, 1.06, 1.07, 1.08, 1.09]],
    },
}
ALGORITHMS = ["nr", "iwamoto_nr"]


def run_case(factory, multiplier: float, algorithm: str) -> dict:
    net = factory()
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
                max_iteration=150,
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
    for case_name, spec in CASES.items():
        factory = spec["factory"]
        for multiplier in spec["multipliers"]:
            for algorithm in ALGORITHMS:
                rows.append({
                    "case": case_name,
                    "n_bus": int(factory().bus.shape[0]),
                    "n_line": int(factory().line.shape[0]),
                    "load_multiplier": multiplier,
                    "algorithm": algorithm,
                    **run_case(factory, multiplier, algorithm),
                })

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "audit_type": "boundary_microcurve",
        "solver": "pandapower.runpp",
        "cases": list(CASES),
        "algorithms": ALGORITHMS,
        "n_trials": len(rows),
        "by_case": {},
        "scope_limit": "fine public PF transition curve only; not H39-original evidence",
    }
    for case_name in CASES:
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
