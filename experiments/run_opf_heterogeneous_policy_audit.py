"""Expanded public AC-OPF audit under predeclared identity-loss policies."""
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
OUT_CSV = ROOT / f"opf_heterogeneous_policy_results_{DATE}.csv"
OUT_JSON = ROOT / f"opf_heterogeneous_policy_summary_{DATE}.json"
LOAD_FACTORS = (0.9, 1.0, 1.1, 1.2, 1.3)
POLICIES = ("aggregate_trip", "missed_trip", "proportional_trip")


def candidate_buses(net, limit=4):
    controlled = set(net.ext_grid.bus.astype(int)) | set(net.gen.bus.astype(int))
    buses = []
    for bus in net.load.bus.astype(int):
        if int(bus) not in controlled and int(bus) not in buses:
            buses.append(int(bus))
    return buses[:limit]


def stress_network(factory, factor):
    net = factory()
    net.load.loc[:, "p_mw"] *= factor
    net.load.loc[:, "q_mvar"] *= factor
    if len(net.sgen):
        net.sgen.loc[:, "p_mw"] *= factor
        net.sgen.loc[:, "q_mvar"] *= factor
    return net


def local_load(net, bus):
    rows = net.load[(net.load.bus.astype(int) == int(bus)) & net.load.in_service.astype(bool)]
    return float(rows.p_mw.sum()) if len(rows) else 0.0


def asset_power(net, bus):
    values = np.asarray([local_load(net, b) for b in candidate_buses(net, 4)], dtype=float)
    positive = values[values > 0]
    lo = float(positive.min()) if positive.size else 0.0
    hi = float(positive.max()) if positive.size else 1.0
    value = local_load(net, bus)
    percentile = 0.5 if hi <= lo else (value - lo) / (hi - lo)
    heterogeneity = 0.5 + 1.5 * float(np.clip(percentile, 0.0, 1.0))
    total = float(net.load.loc[net.load.in_service.astype(bool), "p_mw"].sum())
    return max(1.0, 0.01 * total * heterogeneity), heterogeneity


def add_correct_assets(net, bus, p_each):
    asset_a = pp.create_sgen(net, bus=bus, p_mw=p_each, q_mvar=0.0,
                             name="identity_asset_A", controllable=False)
    pp.create_sgen(net, bus=bus, p_mw=p_each, q_mvar=0.0,
                   name="identity_asset_B", controllable=False)
    net.sgen.at[asset_a, "in_service"] = False


def add_alias_asset(net, bus, p_each, policy):
    p = {"aggregate_trip": 0.0, "missed_trip": 2.0 * p_each,
         "proportional_trip": p_each}[policy]
    pp.create_sgen(net, bus=bus, p_mw=p, q_mvar=0.0,
                   name="feature_merged_A_B", controllable=False)


def solve_opf(net):
    errors = []
    for init in ("pf", "flat"):
        trial = copy.deepcopy(net)
        try:
            pp.runopp(trial, verbose=False, calculate_voltage_angles=True,
                      init=init, max_iteration=200, delta=1e-8)
            min_vm = float(trial.res_bus.vm_pu.min())
            max_vm = float(trial.res_bus.vm_pu.max())
            max_loading = float(trial.res_line.loading_percent.max()) if len(trial.res_line) else 0.0
            return {
                "converged": True,
                "init": init,
                "cost": float(trial.res_cost),
                "min_vm_pu": min_vm,
                "max_vm_pu": max_vm,
                "max_loading_percent": max_loading,
                "unsafe": bool(min_vm < 0.95 or max_vm > 1.05 or max_loading > 100.0),
                "error": "",
            }
        except Exception as exc:
            errors.append(f"{init}:{type(exc).__name__}:{str(exc)[:180]}")
    return {"converged": False, "init": "", "error": " | ".join(errors)}


def flatten(prefix, values):
    return {f"{prefix}_{key}": value for key, value in values.items()}


def main():
    cases = [
        ("case9", pn.case9),
        ("case14", pn.case14),
        ("case24_ieee_rts", pn.case24_ieee_rts),
        ("case30", pn.case30),
        ("case39", pn.case39),
        ("case57", pn.case57),
        ("case89pegase", pn.case89pegase),
        ("case118", pn.case118),
        ("case145", pn.case145),
        ("case_illinois200", pn.case_illinois200),
    ]
    rows = []
    for network, factory in cases:
        buses = candidate_buses(factory(), 4)
        for factor in LOAD_FACTORS:
            for bus in buses:
                stressed = stress_network(factory, factor)
                p_each, heterogeneity = asset_power(stressed, bus)
                correct = copy.deepcopy(stressed)
                add_correct_assets(correct, bus, p_each)
                correct_result = solve_opf(correct)
                for policy in POLICIES:
                    alias = copy.deepcopy(stressed)
                    add_alias_asset(alias, bus, p_each, policy)
                    alias_result = solve_opf(alias)
                    row = {
                        "network": network,
                        "load_factor": factor,
                        "asset_bus": bus,
                        "p_each_mw": p_each,
                        "heterogeneity_multiplier": heterogeneity,
                        "alias_policy": policy,
                    }
                    row.update(flatten("correct", correct_result))
                    row.update(flatten("alias", alias_result))
                    if correct_result["converged"] and alias_result["converged"]:
                        row["signed_cost_regret"] = alias_result["cost"] - correct_result["cost"]
                        row["absolute_cost_regret"] = abs(row["signed_cost_regret"])
                        row["min_vm_delta_pu"] = alias_result["min_vm_pu"] - correct_result["min_vm_pu"]
                        row["max_loading_delta_percent"] = alias_result["max_loading_percent"] - correct_result["max_loading_percent"]
                        row["security_disagreement"] = alias_result["unsafe"] != correct_result["unsafe"]
                    rows.append(row)

    fields = sorted({key for row in rows for key in row})
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    by_policy = {}
    for policy in POLICIES:
        attempted = [r for r in rows if r["alias_policy"] == policy]
        valid = [r for r in attempted if r["correct_converged"] and r["alias_converged"]]
        by_policy[policy] = {
            "attempted": len(attempted),
            "paired_valid": len(valid),
            "paired_convergence_rate": len(valid) / len(attempted) if attempted else None,
            "nonzero_cost_regret": sum(r.get("absolute_cost_regret", 0.0) > 1e-8 for r in valid),
            "median_absolute_cost_regret": float(np.median([r["absolute_cost_regret"] for r in valid])) if valid else None,
            "max_absolute_cost_regret": max((r["absolute_cost_regret"] for r in valid), default=None),
            "security_disagreements": sum(bool(r["security_disagreement"]) for r in valid),
            "max_abs_min_vm_delta_pu": max((abs(r["min_vm_delta_pu"]) for r in valid), default=None),
            "max_abs_loading_delta_percent": max((abs(r["max_loading_delta_percent"]) for r in valid), default=None),
        }
    valid_all = [r for r in rows if r["correct_converged"] and r["alias_converged"]]
    summary = {
        "experiment": "opf_heterogeneous_policy_audit",
        "protocol": "benchmark_protocol_v4_opf.yaml",
        "date": DATE,
        "public_networks": [name for name, _ in cases],
        "load_factors": list(LOAD_FACTORS),
        "candidate_limit_per_network": 4,
        "attempted_policy_pairs": len(rows),
        "paired_valid": len(valid_all),
        "by_policy": by_policy,
        "primary_evidence": OUT_CSV.name,
        "limitations": [
            "controlled public-data counterfactual",
            "fixed-injection added assets",
            "single AC-OPF implementation with two initialization attempts",
        ],
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
