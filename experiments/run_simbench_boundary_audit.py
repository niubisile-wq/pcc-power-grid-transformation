"""Independent SimBench load-scaling boundary audit with pandapower."""
from __future__ import annotations

import copy
import csv
import contextlib
import json
import io
import time
from pathlib import Path

import pandapower as pp
import simbench as sb

ROOT = Path(__file__).resolve().parent
CODE = "1-HVMVLV-urban-all-0-sw"


def main():
    base = sb.get_simbench_net(CODE)
    rows = []
    factors = [round(1.0 + 0.01 * i, 2) for i in range(0, 341)]
    for algorithm in ["nr", "iwamoto_nr"]:
        for factor in factors:
            net = copy.deepcopy(base)
            net.load["p_mw"] *= factor
            net.load["q_mvar"] *= factor
            t0 = time.perf_counter()
            row = {"code": CODE, "algorithm": algorithm, "factor": factor, "converged": False, "runtime_s": None, "min_vm_pu": None, "max_line_loading_percent": None, "error": None}
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    pp.runpp(net, algorithm=algorithm, init="dc", calculate_voltage_angles=True, max_iteration=80, tolerance_mva=1e-8, trafo_model="t")
                row["converged"] = True
                row["min_vm_pu"] = float(net.res_bus.vm_pu.min())
                row["max_line_loading_percent"] = float(net.res_line.loading_percent.max()) if len(net.res_line) else None
            except Exception as exc:
                row["error"] = type(exc).__name__ + ": " + str(exc)[:180]
            row["runtime_s"] = time.perf_counter() - t0
            rows.append(row)

    out_csv = ROOT / "simbench_boundary_results_20260801.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    summary = {"code": CODE, "buses": len(base.bus), "loads": len(base.load), "lines": len(base.line), "algorithms": {}}
    for alg in ["nr", "iwamoto_nr"]:
        rs = [r for r in rows if r["algorithm"] == alg]
        ok = [r for r in rs if r["converged"]]
        summary["algorithms"][alg] = {"last_converged": max(r["factor"] for r in ok) if ok else None, "first_failed": min(r["factor"] for r in rs if not r["converged"]) if any(not r["converged"] for r in rs) else None, "n_converged": len(ok), "n_failed": len(rs) - len(ok)}
    (ROOT / "simbench_boundary_summary_20260801.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
