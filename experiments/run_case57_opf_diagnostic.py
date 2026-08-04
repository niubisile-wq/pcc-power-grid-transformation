"""Check case57 OPF failure across initialization and Q-limit settings."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pandapower as pp

ROOT = Path(__file__).resolve().parent


def main():
    rows = []
    for init in ["dc", "flat"]:
        for q_limits in [True, False]:
            net = pp.networks.case57()
            row = {"init": init, "enforce_q_lims": q_limits, "converged": False, "error": None}
            try:
                pp.runopp(net, verbose=False, calculate_voltage_angles=True, max_iteration=200, delta=1e-8, init=init, enforce_q_lims=q_limits)
                row["converged"] = True
                row["cost"] = float(net.res_cost)
            except Exception as exc:
                row["error"] = type(exc).__name__ + ": " + str(exc)[:180]
            rows.append(row)
    (ROOT / "case57_opf_diagnostic_20260801.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
