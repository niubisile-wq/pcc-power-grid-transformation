"""Physical solver boundary audit on public pandapower test networks.

This is an executable E4 partial result. It tests PF solvability boundaries
only; it does not test canonicalization or foundation-model outputs.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import pandapower as pp
import pandapower.networks as nw


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "pandapower_boundary_results_20260801.csv"
SUMMARY = ROOT / "pandapower_boundary_summary_20260801.json"
CASES = {
    "case14": nw.case14,
    "case30": nw.case30,
    "case57": nw.case57,
    "case118": nw.case118,
    "case300": nw.case300,
}
MULTIPLIERS = [1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]


def run_case(case_name: str, constructor, multiplier: float) -> dict:
    net = constructor()
    base_p = net.load.p_mw.copy()
    base_q = net.load.q_mvar.copy()
    net.load.loc[:, "p_mw"] = base_p * multiplier
    net.load.loc[:, "q_mvar"] = base_q * multiplier
    start = time.perf_counter()
    error = ""
    converged = False
    iterations = None
    try:
        pp.runpp(net, algorithm="nr", init="flat", max_iteration=100, tolerance_mva=1e-8)
        converged = bool(net.converged)
        if isinstance(getattr(net, "_ppc", None), dict):
            iterations = net._ppc.get("iterations")
    except Exception as exc:  # solver failures are results for this audit
        error = f"{type(exc).__name__}: {exc}"[:500]
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    min_vm = None
    max_line_loading = None
    max_trafo_loading = None
    if converged:
        if len(net.res_bus):
            min_vm = float(net.res_bus.vm_pu.min())
        if len(net.res_line):
            max_line_loading = float(net.res_line.loading_percent.max())
        if len(net.res_trafo):
            max_trafo_loading = float(net.res_trafo.loading_percent.max())
    return {
        "case": case_name,
        "n_bus": int(len(net.bus)),
        "n_line": int(len(net.line)),
        "load_multiplier": multiplier,
        "converged": int(converged),
        "iterations": iterations if iterations is not None else "",
        "min_vm_pu": min_vm,
        "max_line_loading_percent": max_line_loading,
        "max_trafo_loading_percent": max_trafo_loading,
        "runtime_ms": elapsed_ms,
        "error": error,
        "solver": "pandapower.runpp/NR",
        "status": "PASS" if converged else "FAIL_EXPECTED_BOUNDARY",
    }


def main() -> None:
    fields = list(run_case("case14", nw.case14, 1.0).keys())
    rows = []
    for name, constructor in CASES.items():
        for multiplier in MULTIPLIERS:
            rows.append(run_case(name, constructor, multiplier))
    with RESULTS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    by_case = {}
    for name in CASES:
        subset = [r for r in rows if r["case"] == name]
        converged = [r["load_multiplier"] for r in subset if r["converged"]]
        failed = [r["load_multiplier"] for r in subset if not r["converged"]]
        by_case[name] = {
            "n_bus": subset[0]["n_bus"],
            "n_trials": len(subset),
            "converged_multipliers": converged,
            "failed_multipliers": failed,
            "last_converged": max(converged) if converged else None,
            "first_failed": min(failed) if failed else None,
        }
    summary = {
        "audit_type": "public_pandapower_power_flow_boundary",
        "solver": "pandapower.runpp/NR",
        "cases": list(CASES),
        "multipliers": MULTIPLIERS,
        "n_trials": len(rows),
        "by_case": by_case,
        "scope_limit": "PF solvability only; no canonicalization, OPF, or foundation-model evaluation",
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
