"""AC-OPF downstream consequence of feature-only asset aliasing."""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

import numpy as np
import pandapower as pp
import pandapower.networks as pn


ROOT = Path(__file__).resolve().parent
DATE = "20260803"
OUT_CSV = ROOT / f"counterfactual_opf_aliasing_results_{DATE}.csv"
OUT_JSON = ROOT / f"counterfactual_opf_aliasing_summary_{DATE}.json"


def choose_bus(net):
    controlled = set(net.ext_grid.bus.astype(int).tolist()) | set(net.gen.bus.astype(int).tolist())
    candidates = [int(x) for x in net.load.bus.astype(int).tolist() if int(x) not in controlled]
    if candidates:
        return candidates[0]
    return int(net.bus.index[0])


def build_pair(factory, factor):
    net = factory()
    bus = choose_bus(net)
    total_load = float(net.load.p_mw.sum()) if len(net.load) else 100.0
    p = max(1.0, factor * total_load)
    g1 = pp.create_gen(net, bus=bus, p_mw=p, vm_pu=1.0, min_p_mw=0.0,
                       max_p_mw=2 * p, min_q_mvar=-2 * p, max_q_mvar=2 * p,
                       name="asset_A")
    g2 = pp.create_gen(net, bus=bus, p_mw=p, vm_pu=1.0, min_p_mw=0.0,
                       max_p_mw=2 * p, min_q_mvar=-2 * p, max_q_mvar=2 * p,
                       name="asset_B")
    pp.create_poly_cost(net, g1, "gen", cp1_eur_per_mw=1.0, cp0_eur=0.0)
    pp.create_poly_cost(net, g2, "gen", cp1_eur_per_mw=1.0, cp0_eur=0.0)
    return net, g1, g2, bus, p


def solve_opp(net):
    pp.runopp(net, verbose=False, calculate_voltage_angles=True, max_iteration=100, delta=1e-8)
    return {
        "cost": float(net.res_cost),
        "min_vm": float(net.res_bus.vm_pu.min()),
        "max_loading": float(net.res_line.loading_percent.max()) if len(net.res_line) else 0.0,
        "safe": bool(net.res_bus.vm_pu.min() >= 0.95 and (not len(net.res_line) or net.res_line.loading_percent.max() <= 100.0)),
    }


def main():
    cases = [("case14", pn.case14), ("case30", pn.case30), ("case57", pn.case57)]
    factors = [0.005, 0.01, 0.02, 0.03, 0.05]
    rows = []
    for name, factory in cases:
        for factor in factors:
            row = {"network": name, "stress_factor": factor, "correct_converged": False,
                   "alias_converged": False, "correct_error": "", "alias_error": ""}
            try:
                base, g1, g2, bus, p = build_pair(factory, factor)
                row.update({"asset_bus": bus, "p_each_mw": p})
                correct = copy.deepcopy(base)
                correct.gen.at[g1, "in_service"] = False
                row.update({"correct": solve_opp(correct), "correct_converged": True})
            except Exception as exc:
                row["correct_error"] = type(exc).__name__ + ": " + str(exc)[:240]
            try:
                base, g1, g2, bus, p = build_pair(factory, factor)
                alias = copy.deepcopy(base)
                alias.gen.at[g1, "p_mw"] = 2 * p
                alias.gen.at[g2, "in_service"] = False
                alias.gen.at[g1, "in_service"] = False
                row.update({"alias": solve_opp(alias), "alias_converged": True})
            except Exception as exc:
                row["alias_error"] = type(exc).__name__ + ": " + str(exc)[:240]
            # Flatten nested result fields for a machine-readable table.
            for prefix in ("correct", "alias"):
                result = row.pop(prefix, {})
                for key, value in result.items():
                    row[f"{prefix}_{key}"] = value
            if row["correct_converged"] and row["alias_converged"]:
                row["cost_regret_abs"] = abs(row["correct_cost"] - row["alias_cost"])
                row["min_vm_delta"] = abs(row["correct_min_vm"] - row["alias_min_vm"])
                row["max_loading_delta"] = abs(row["correct_max_loading"] - row["alias_max_loading"])
                row["safety_disagreement"] = row["correct_safe"] != row["alias_safe"]
            else:
                row["cost_regret_abs"] = None
                row["min_vm_delta"] = None
                row["max_loading_delta"] = None
                row["safety_disagreement"] = None
            rows.append(row)
    fields = sorted({key for row in rows for key in row})
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    valid = [r for r in rows if r["correct_converged"] and r["alias_converged"]]
    summary = {
        "experiment": "counterfactual_ac_opf_aliasing",
        "date": DATE,
        "attempted": len(rows),
        "paired_valid": len(valid),
        "correct_converged": sum(r["correct_converged"] for r in rows),
        "alias_converged": sum(r["alias_converged"] for r in rows),
        "safety_disagreements": sum(bool(r["safety_disagreement"]) for r in valid),
        "max_cost_regret_abs": max((r["cost_regret_abs"] or 0.0) for r in valid) if valid else None,
        "max_min_vm_delta": max((r["min_vm_delta"] or 0.0) for r in valid) if valid else None,
        "max_loading_delta": max((r["max_loading_delta"] or 0.0) for r in valid) if valid else None,
        "limitations": ["public pandapower OPF mechanism benchmark", "not H39 lockbox", "not field validation"],
        "primary_evidence": OUT_CSV.name,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
