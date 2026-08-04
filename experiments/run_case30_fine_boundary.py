"""Fine load-boundary scan for the public pandapower case30 network."""

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
RESULTS = ROOT / "case30_fine_boundary_results_20260801.csv"
SUMMARY = ROOT / "case30_fine_boundary_summary_20260801.json"
MULTIPLIERS = [round(3.50 + 0.01 * i, 3) for i in range(51)]
ALGORITHMS = ["nr", "iwamoto_nr"]


def one(multiplier: float, algorithm: str) -> dict:
    net = nw.case30()
    net.load.loc[:, "p_mw"] *= multiplier
    net.load.loc[:, "q_mvar"] *= multiplier
    start = time.perf_counter()
    error = ""
    converged = False
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            pp.runpp(
                net,
                algorithm=algorithm,
                init="flat",
                max_iteration=200,
                tolerance_mva=1e-8,
            )
        converged = bool(net.converged)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
    runtime_ms = (time.perf_counter() - start) * 1000.0
    return {
        "case": "case30",
        "load_multiplier": multiplier,
        "algorithm": algorithm,
        "converged": int(converged),
        "runtime_ms": runtime_ms,
        "min_vm_pu": float(net.res_bus.vm_pu.min()) if converged else "",
        "max_line_loading_percent": float(net.res_line.loading_percent.max()) if converged else "",
        "error": error,
    }


def main() -> None:
    rows = [one(multiplier, algorithm) for algorithm in ALGORITHMS for multiplier in MULTIPLIERS]
    with RESULTS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    by_algorithm = {}
    for algorithm in ALGORITHMS:
        subset = [r for r in rows if r["algorithm"] == algorithm]
        ok = [r["load_multiplier"] for r in subset if r["converged"]]
        bad = [r["load_multiplier"] for r in subset if not r["converged"]]
        by_algorithm[algorithm] = {
            "last_converged": max(ok) if ok else None,
            "first_failed": min(bad) if bad else None,
            "converged_count": len(ok),
            "failed_count": len(bad),
        }
    summary = {
        "audit_type": "public_case30_fine_boundary",
        "network": "pandapower.networks.case30",
        "multipliers": MULTIPLIERS,
        "algorithms": ALGORITHMS,
        "n_trials": len(rows),
        "by_algorithm": by_algorithm,
        "scope_limit": "PF solver boundary only; not evidence for canonicalization or foundation-model claims",
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
