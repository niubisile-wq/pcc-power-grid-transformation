"""Predeclared heterogeneous N-1 identity-aliasing policy audit.

The experiment follows benchmark_protocol_v3.yaml. It separates three common
fallbacks after feature-only merging destroys the mapping for a named outage:
tripping the aggregate, missing the trip, or applying an oracle proportional
trip. The last policy is a numerical control, not an identity recovery method.
"""
from __future__ import annotations

import copy
import csv
import json
import math
from pathlib import Path

import numpy as np
import pandapower as pp
import pandapower.networks as pn
from scipy.stats import kendalltau, spearmanr


ROOT = Path(__file__).resolve().parent
DATE = "20260803"
OUT_CSV = ROOT / f"nminus1_heterogeneous_policy_results_{DATE}.csv"
OUT_JSON = ROOT / f"nminus1_heterogeneous_policy_summary_{DATE}.json"
LOAD_FACTORS = tuple(round(0.8 + 0.1 * i, 2) for i in range(13))
POLICIES = ("aggregate_trip", "missed_trip", "proportional_trip")


def run_pf(net):
    try:
        pp.runpp(net, init="auto", calculate_voltage_angles=True, numba=False,
                 enforce_q_lims=True, max_iteration=50)
        return "nr"
    except pp.LoadflowNotConverged:
        pp.runpp(net, algorithm="iwamoto_nr", init="flat", max_iteration=150,
                 calculate_voltage_angles=True, numba=False, enforce_q_lims=True)
        return "iwamoto_nr"


def candidate_buses(net, limit=30):
    controlled = set(net.ext_grid.bus.astype(int)) | set(net.gen.bus.astype(int))
    candidates = []
    for bus in net.load.bus.astype(int):
        if int(bus) not in controlled and int(bus) not in candidates:
            candidates.append(int(bus))
    return candidates[:limit]


def local_load(net, bus):
    rows = net.load[(net.load.bus.astype(int) == int(bus)) & net.load.in_service.astype(bool)]
    return float(rows.p_mw.sum()) if len(rows) else 0.0


def stress_network(factory, factor):
    net = factory()
    net.load.loc[:, "p_mw"] *= factor
    net.load.loc[:, "q_mvar"] *= factor
    if len(net.sgen):
        net.sgen.loc[:, "p_mw"] *= factor
        net.sgen.loc[:, "q_mvar"] *= factor
    if len(net.gen):
        net.gen.loc[:, "p_mw"] *= factor
    return net


def asset_power(net, bus):
    loads = [local_load(net, int(b)) for b in candidate_buses(net, limit=30)]
    positive = np.asarray([value for value in loads if value > 0], dtype=float)
    lo = float(positive.min()) if positive.size else 0.0
    hi = float(positive.max()) if positive.size else 1.0
    value = local_load(net, bus)
    percentile = 0.5 if hi <= lo else (value - lo) / (hi - lo)
    heterogeneity = 0.5 + 1.5 * float(np.clip(percentile, 0.0, 1.0))
    total_load = float(net.load.loc[net.load.in_service.astype(bool), "p_mw"].sum())
    return max(1.0, 0.01 * total_load * heterogeneity), heterogeneity


def add_correct_pair(net, bus, p_each):
    common = dict(bus=bus, p_mw=p_each, vm_pu=1.0, min_p_mw=0.0,
                  max_p_mw=2.5 * p_each, min_q_mvar=-2.5 * p_each,
                  max_q_mvar=2.5 * p_each)
    asset_a = pp.create_gen(net, name="identity_asset_A", **common)
    pp.create_gen(net, name="identity_asset_B", **common)
    return asset_a


def add_merged_asset(net, bus, p_each, policy):
    merged = pp.create_gen(
        net, bus=bus, p_mw=2.0 * p_each, vm_pu=1.0,
        min_p_mw=0.0, max_p_mw=5.0 * p_each,
        min_q_mvar=-5.0 * p_each, max_q_mvar=5.0 * p_each,
        name="feature_merged_A_B",
    )
    if policy == "aggregate_trip":
        net.gen.at[merged, "in_service"] = False
    elif policy == "missed_trip":
        pass
    elif policy == "proportional_trip":
        net.gen.at[merged, "p_mw"] = p_each
        net.gen.at[merged, "max_p_mw"] = 2.5 * p_each
        net.gen.at[merged, "min_q_mvar"] = -2.5 * p_each
        net.gen.at[merged, "max_q_mvar"] = 2.5 * p_each
    else:
        raise ValueError(f"unknown policy: {policy}")


def metrics(net):
    vm = net.res_bus.vm_pu.to_numpy(dtype=float)
    loading = (net.res_line.loading_percent.to_numpy(dtype=float)
               if len(net.res_line) else np.zeros(1, dtype=float))
    min_vm = float(np.min(vm))
    max_vm = float(np.max(vm))
    max_loading = float(np.max(loading))
    unsafe_voltage = bool(min_vm < 0.95 or max_vm > 1.05)
    unsafe_loading = bool(max_loading > 100.0)
    # Continuous ranking endpoint. It is non-zero below hard limits and rises
    # smoothly as voltages move away from nominal or branch loading increases.
    risk = float(np.mean((vm - 1.0) ** 2) + np.mean((loading / 100.0) ** 2))
    return {
        "min_vm_pu": min_vm,
        "max_vm_pu": max_vm,
        "max_loading_percent": max_loading,
        "risk_score": risk,
        "unsafe_voltage": unsafe_voltage,
        "unsafe_loading": unsafe_loading,
        "unsafe": bool(unsafe_voltage or unsafe_loading),
    }


def flatten(prefix, values):
    return {f"{prefix}_{key}": value for key, value in values.items()}


def wilson(successes, total, z=1.959963984540054):
    if total == 0:
        return [None, None]
    p = successes / total
    denom = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denom
    half = z * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total)) / denom
    return [max(0.0, centre - half), min(1.0, centre + half)]


def top_k_overlap(correct, alias, k):
    k = min(k, len(correct))
    if k == 0:
        return None
    c = set(np.argsort(-np.asarray(correct))[:k].tolist())
    a = set(np.argsort(-np.asarray(alias))[:k].tolist())
    return len(c & a) / k


def ndcg(correct, alias):
    if not correct:
        return None
    relevance = np.asarray(correct, dtype=float)
    span = float(relevance.max() - relevance.min())
    scaled = np.ones_like(relevance) if span <= 0 else (relevance - relevance.min()) / span
    predicted_order = np.argsort(-np.asarray(alias, dtype=float))
    ideal_order = np.argsort(-relevance)
    discounts = 1.0 / np.log2(np.arange(len(relevance), dtype=float) + 2.0)
    dcg = float(np.sum((2.0 ** scaled[predicted_order] - 1.0) * discounts))
    ideal = float(np.sum((2.0 ** scaled[ideal_order] - 1.0) * discounts))
    return dcg / ideal if ideal > 0 else 1.0


def rank_summary(rows):
    groups = []
    keys = sorted({(r["network"], float(r["load_factor"]), r["alias_policy"]) for r in rows})
    for network, factor, policy in keys:
        valid = [r for r in rows if r["network"] == network
                 and float(r["load_factor"]) == factor
                 and r["alias_policy"] == policy
                 and r["correct_converged"] and r["alias_converged"]]
        correct = [float(r["correct_risk_score"]) for r in valid]
        alias = [float(r["alias_risk_score"]) for r in valid]
        rankable = len(valid) >= 3 and len(set(correct)) > 1 and len(set(alias)) > 1
        item = {"network": network, "load_factor": factor, "alias_policy": policy,
                "n": len(valid), "rankable": rankable,
                "top_1_overlap": top_k_overlap(correct, alias, 1),
                "top_5_overlap": top_k_overlap(correct, alias, 5),
                "top_10_overlap": top_k_overlap(correct, alias, 10),
                "ndcg": ndcg(correct, alias)}
        if rankable:
            rho, rho_p = spearmanr(correct, alias)
            tau, tau_p = kendalltau(correct, alias)
            item.update({"spearman_rho": float(rho), "spearman_p": float(rho_p),
                         "kendall_tau": float(tau), "kendall_p": float(tau_p)})
        else:
            item.update({"spearman_rho": None, "spearman_p": None,
                         "kendall_tau": None, "kendall_p": None,
                         "non_rankable_reason": "fewer_than_3_or_constant_vector"})
        groups.append(item)
    return groups


def main():
    cases = [("case14", pn.case14), ("case30", pn.case30),
             ("case57", pn.case57), ("case118", pn.case118),
             ("case300", pn.case300)]
    rows = []
    for network, factory in cases:
        buses = candidate_buses(factory(), limit=30)
        for factor in LOAD_FACTORS:
            for bus in buses:
                stressed = stress_network(factory, factor)
                p_each, heterogeneity = asset_power(stressed, bus)
                correct_values = {}
                correct_converged = False
                correct_error = ""
                correct_solver = ""
                try:
                    correct = copy.deepcopy(stressed)
                    asset_a = add_correct_pair(correct, bus, p_each)
                    correct.gen.at[asset_a, "in_service"] = False
                    correct_solver = run_pf(correct)
                    correct_values = metrics(correct)
                    correct_converged = True
                except Exception as exc:
                    correct_error = f"{type(exc).__name__}: {str(exc)[:300]}"

                for policy in POLICIES:
                    row = {
                        "network": network,
                        "load_factor": factor,
                        "asset_bus": bus,
                        "p_each_mw": p_each,
                        "heterogeneity_multiplier": heterogeneity,
                        "alias_policy": policy,
                        "correct_converged": correct_converged,
                        "correct_solver": correct_solver,
                        "correct_error": correct_error,
                        "alias_converged": False,
                        "alias_solver": "",
                        "alias_error": "",
                    }
                    row.update(flatten("correct", correct_values))
                    try:
                        alias = copy.deepcopy(stressed)
                        add_merged_asset(alias, bus, p_each, policy)
                        row["alias_solver"] = run_pf(alias)
                        row.update(flatten("alias", metrics(alias)))
                        row["alias_converged"] = True
                    except Exception as exc:
                        row["alias_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"

                    if row["correct_converged"] and row["alias_converged"]:
                        row["risk_delta"] = float(row["alias_risk_score"] - row["correct_risk_score"])
                        row["abs_risk_delta"] = abs(row["risk_delta"])
                        row["min_vm_delta_pu"] = float(row["alias_min_vm_pu"] - row["correct_min_vm_pu"])
                        row["max_loading_delta_percent"] = float(row["alias_max_loading_percent"] - row["correct_max_loading_percent"])
                        row["security_disagreement"] = bool(row["alias_unsafe"] != row["correct_unsafe"])
                        row["false_safe"] = bool(row["correct_unsafe"] and not row["alias_unsafe"])
                        row["false_alarm"] = bool(not row["correct_unsafe"] and row["alias_unsafe"])
                        row["pcc_prevented_disagreement"] = row["security_disagreement"]
                    rows.append(row)

    fields = sorted({key for row in rows for key in row})
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    valid = [r for r in rows if r["correct_converged"] and r["alias_converged"]]
    by_policy = {}
    for policy in POLICIES:
        subset = [r for r in valid if r["alias_policy"] == policy]
        false_safe = sum(bool(r["false_safe"]) for r in subset)
        false_alarm = sum(bool(r["false_alarm"]) for r in subset)
        disagreements = sum(bool(r["security_disagreement"]) for r in subset)
        by_policy[policy] = {
            "paired_valid": len(subset),
            "false_safe": false_safe,
            "false_safe_rate": false_safe / len(subset) if subset else None,
            "false_safe_wilson_95_ci": wilson(false_safe, len(subset)),
            "false_alarm": false_alarm,
            "false_alarm_rate": false_alarm / len(subset) if subset else None,
            "false_alarm_wilson_95_ci": wilson(false_alarm, len(subset)),
            "security_disagreements": disagreements,
            "security_disagreement_rate": disagreements / len(subset) if subset else None,
            "security_disagreement_wilson_95_ci": wilson(disagreements, len(subset)),
            "median_abs_risk_delta": float(np.median([r["abs_risk_delta"] for r in subset])) if subset else None,
            "max_abs_risk_delta": max((r["abs_risk_delta"] for r in subset), default=None),
        }

    ranks = rank_summary(rows)
    rankable = [item for item in ranks if item["rankable"]]
    summary = {
        "experiment": "nminus1_heterogeneous_policy_audit",
        "protocol": "benchmark_protocol_v3.yaml",
        "date": DATE,
        "public_networks": [name for name, _ in cases],
        "load_factors": list(LOAD_FACTORS),
        "candidate_limit_per_network": 30,
        "candidate_count": sum(len(candidate_buses(factory(), 30)) for _, factory in cases),
        "attempted_policy_pairs": len(rows),
        "paired_valid": len(valid),
        "by_policy": by_policy,
        "rank_groups": ranks,
        "rankable_groups": len(rankable),
        "median_rankable_spearman": float(np.median([x["spearman_rho"] for x in rankable])) if rankable else None,
        "median_rankable_kendall": float(np.median([x["kendall_tau"] for x in rankable])) if rankable else None,
        "primary_evidence": OUT_CSV.name,
        "limitations": [
            "controlled public-data counterfactual, not natural collision prevalence",
            "alias policies are predeclared operational fallbacks after identity loss",
            "proportional trip is an oracle numerical control, not identity recovery",
        ],
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "rank_groups"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
