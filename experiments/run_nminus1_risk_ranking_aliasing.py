"""N-1 risk-ranking consequence of identity aliasing on public grids."""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

import numpy as np
import pandapower as pp
import pandapower.networks as pn
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parent
DATE = "20260803"
OUT_CSV = ROOT / f"nminus1_risk_ranking_aliasing_results_{DATE}.csv"
OUT_JSON = ROOT / f"nminus1_risk_ranking_aliasing_summary_{DATE}.json"


def run_pf(net):
    try:
        pp.runpp(net, init="auto", calculate_voltage_angles=True, numba=False)
    except pp.LoadflowNotConverged:
        pp.runpp(net, algorithm="iwamoto_nr", init="flat", max_iteration=100,
                 calculate_voltage_angles=True, numba=False)


def candidate_buses(net, limit=8):
    controlled = set(net.ext_grid.bus.astype(int).tolist()) | set(net.gen.bus.astype(int).tolist())
    out = []
    for bus in net.load.bus.astype(int).tolist():
        if bus not in controlled and bus not in out:
            out.append(int(bus))
    return out[:limit]


def build_pair(factory, bus, factor=0.02):
    net = factory()
    total_load = float(net.load.p_mw.sum()) if len(net.load) else 100.0
    p = max(1.0, factor * total_load)
    g1 = pp.create_gen(net, bus=bus, p_mw=p, vm_pu=1.0, min_p_mw=0.0,
                       max_p_mw=2 * p, min_q_mvar=-2 * p, max_q_mvar=2 * p,
                       name="rank_asset_A")
    g2 = pp.create_gen(net, bus=bus, p_mw=p, vm_pu=1.0, min_p_mw=0.0,
                       max_p_mw=2 * p, min_q_mvar=-2 * p, max_q_mvar=2 * p,
                       name="rank_asset_B")
    return net, g1, g2, p


def score(net):
    min_vm = float(net.res_bus.vm_pu.min())
    max_loading = float(net.res_line.loading_percent.max()) if len(net.res_line) else 0.0
    voltage_deficit = max(0.0, 0.95 - min_vm)
    loading_deficit = max(0.0, max_loading - 100.0) / 100.0
    return {
        "min_vm": min_vm,
        "max_loading": max_loading,
        "risk_score": voltage_deficit + loading_deficit,
        "unsafe": bool(voltage_deficit > 0 or loading_deficit > 0),
    }


def main():
    cases = [("case14", pn.case14), ("case30", pn.case30), ("case57", pn.case57),
             ("case118", pn.case118), ("case300", pn.case300)]
    rows = []
    errors = []
    for name, factory in cases:
        template = factory()
        for bus in candidate_buses(template):
            row = {"network": name, "asset_bus": bus, "correct_converged": False,
                   "alias_converged": False, "correct_error": "", "alias_error": ""}
            try:
                base, g1, g2, p = build_pair(factory, bus)
                correct = copy.deepcopy(base)
                correct.gen.at[g1, "in_service"] = False
                run_pf(correct)
                row.update({"correct_converged": True, "p_each_mw": p, "correct": score(correct)})
            except Exception as exc:
                row["correct_error"] = type(exc).__name__ + ": " + str(exc)[:240]
            try:
                base, g1, g2, p = build_pair(factory, bus)
                alias = copy.deepcopy(base)
                alias.gen.at[g1, "p_mw"] = 2 * p
                alias.gen.at[g2, "in_service"] = False
                alias.gen.at[g1, "in_service"] = False
                run_pf(alias)
                row.update({"alias_converged": True, "alias": score(alias)})
            except Exception as exc:
                row["alias_error"] = type(exc).__name__ + ": " + str(exc)[:240]
            for prefix in ("correct", "alias"):
                result = row.pop(prefix, {})
                for key, value in result.items():
                    row[f"{prefix}_{key}"] = value
            if row["correct_converged"] and row["alias_converged"]:
                row["risk_delta"] = abs(row["correct_risk_score"] - row["alias_risk_score"])
                row["safety_disagreement"] = row["correct_unsafe"] != row["alias_unsafe"]
            else:
                row["risk_delta"] = None
                row["safety_disagreement"] = None
            rows.append(row)

    fields = sorted({key for row in rows for key in row})
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    correlations = []
    for network in sorted({r["network"] for r in rows}):
        valid = [r for r in rows if r["network"] == network and r["correct_converged"] and r["alias_converged"]]
        if len(valid) >= 3:
            correct_scores = [r["correct_risk_score"] for r in valid]
            alias_scores = [r["alias_risk_score"] for r in valid]
            if len(set(correct_scores)) > 1 and len(set(alias_scores)) > 1:
                rho, p = spearmanr(correct_scores, alias_scores)
                correlations.append({"network": network, "n": len(valid), "rankable": True,
                                     "spearman_rho": float(rho), "p_value": float(p)})
            else:
                correlations.append({"network": network, "n": len(valid), "rankable": False,
                                     "spearman_rho": None, "p_value": None,
                                     "reason": "one risk-score vector is constant under the controlled construction"})
    valid_all = [r for r in rows if r["correct_converged"] and r["alias_converged"]]
    summary = {
        "experiment": "nminus1_risk_ranking_aliasing",
        "date": DATE,
        "attempted": len(rows),
        "paired_valid": len(valid_all),
        "correct_converged": sum(r["correct_converged"] for r in rows),
        "alias_converged": sum(r["alias_converged"] for r in rows),
        "nonzero_risk_delta": sum((r["risk_delta"] or 0.0) > 1e-9 for r in valid_all),
        "safety_disagreements": sum(bool(r["safety_disagreement"]) for r in valid_all),
        "max_risk_delta": max((r["risk_delta"] or 0.0) for r in valid_all) if valid_all else None,
        "network_rank_correlations": correlations,
        "limitations": ["public pandapower N-1 mechanism benchmark", "controlled generator-pair construction", "not H39 lockbox or field validation"],
        "primary_evidence": OUT_CSV.name,
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
