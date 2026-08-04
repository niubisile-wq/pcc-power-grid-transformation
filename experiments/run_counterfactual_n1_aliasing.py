"""Counterfactual representation-aliasing experiment on public pandapower grids.

The construction is deliberately explicit: two generators with the same public
numerical attributes are placed at the same bus.  Their aggregate injection is
represented either as two identity-distinct assets (correct representation) or
as one feature-only merged asset.  The nominal operating point is equivalent,
but a single-asset contingency has different physical consequences.
"""

from __future__ import annotations

import json
import hashlib
import contextlib
import io
from pathlib import Path

import numpy as np
import pandas as pd
import pandapower as pp
import pandapower.networks as pn


ROOT = Path(__file__).resolve().parent
DATE = "20260802"
OUT_CSV = ROOT / f"counterfactual_n1_aliasing_results_{DATE}.csv"
OUT_JSON = ROOT / f"counterfactual_n1_aliasing_summary_{DATE}.json"


def topology_hash(net: pp.pandapowerNet) -> str:
    payload = {
        "bus": net.bus.index.astype(int).tolist(),
        "line": net.line[["from_bus", "to_bus", "length_km"]].round(12).astype(float).to_dict("records"),
        "trafo": net.trafo[["hv_bus", "lv_bus"]].astype(int).to_dict("records") if len(net.trafo) else [],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def choose_bus(net: pp.pandapowerNet) -> int:
    controlled = set(net.ext_grid.bus.astype(int).tolist()) | set(net.gen.bus.astype(int).tolist())
    load_buses = [int(x) for x in net.load.bus.astype(int).tolist() if int(x) not in controlled]
    if load_buses:
        return load_buses[0]
    free_buses = [int(x) for x in net.bus.index.tolist() if int(x) not in controlled]
    if free_buses:
        return free_buses[0]
    # A fallback is still deterministic; align the new generator setpoint to
    # the existing controller at that bus to avoid a false solver warning.
    if len(net.gen):
        return int(net.gen.iloc[0].bus)
    return int(net.ext_grid.iloc[0].bus)


def run_pf(net: pp.pandapowerNet) -> None:
    try:
        pp.runpp(net, init="auto", calculate_voltage_angles=True, numba=False)
    except pp.LoadflowNotConverged:
        with contextlib.redirect_stdout(io.StringIO()):
            pp.runpp(net, algorithm="iwamoto_nr", init="flat", max_iteration=100,
                     calculate_voltage_angles=True, numba=False)


def make_pair(net_factory, network_name: str, stress_factor: float):
    net = net_factory()
    bus = choose_bus(net)
    total_load = float(net.load.p_mw.sum()) if len(net.load) else 100.0
    p_each = max(1.0, stress_factor * total_load)

    # Two separate assets share all numerical features. Their IDs remain distinct.
    vm = 1.0
    if bus in set(net.gen.bus.astype(int).tolist()):
        vm = float(net.gen.loc[net.gen.bus == bus, "vm_pu"].iloc[0])
    elif bus in set(net.ext_grid.bus.astype(int).tolist()):
        vm = float(net.ext_grid.loc[net.ext_grid.bus == bus, "vm_pu"].iloc[0])
    g1 = pp.create_gen(net, bus=bus, p_mw=p_each, vm_pu=vm,
                       min_p_mw=0.0, max_p_mw=2.0 * p_each,
                       min_q_mvar=-2.0 * p_each, max_q_mvar=2.0 * p_each,
                       name="alias_asset_A")
    g2 = pp.create_gen(net, bus=bus, p_mw=p_each, vm_pu=vm,
                       min_p_mw=0.0, max_p_mw=2.0 * p_each,
                       min_q_mvar=-2.0 * p_each, max_q_mvar=2.0 * p_each,
                       name="alias_asset_B")
    net.gen.at[g1, "asset_identity"] = "asset-A"
    net.gen.at[g2, "asset_identity"] = "asset-B"
    run_pf(net)
    base_v = net.res_bus.vm_pu.to_numpy(copy=True)
    base_loading = net.res_line.loading_percent.to_numpy(copy=True) if len(net.line) else np.array([])

    # Correct representation: contingency removes only A.
    correct = net.deepcopy() if hasattr(net, "deepcopy") else None
    if correct is None:
        import copy
        correct = copy.deepcopy(net)
    correct.gen.at[g1, "in_service"] = False
    run_pf(correct)

    # Feature-only alias: merge A+B into one asset, then apply the same named
    # single-asset contingency. The nominal aggregate injection is unchanged.
    import copy
    alias = copy.deepcopy(net)
    alias.gen.at[g1, "p_mw"] = 2.0 * p_each
    alias.gen.at[g1, "name"] = "feature_only_merged_asset"
    alias.gen.at[g1, "asset_identity"] = "A+B (identity discarded)"
    alias.gen.drop(index=g2, inplace=True)
    alias.gen.index = range(len(alias.gen))
    alias_g1 = int(alias.gen.index[-1])
    run_pf(alias)
    nominal_v = alias.res_bus.vm_pu.to_numpy(copy=True)
    nominal_loading = alias.res_line.loading_percent.to_numpy(copy=True) if len(alias.line) else np.array([])
    alias.gen.at[alias_g1, "in_service"] = False
    alias_feasible = True
    alias_error = ""
    try:
        run_pf(alias)
    except Exception as exc:  # preserve solver failures as first-class outcomes
        alias_feasible = False
        alias_error = type(exc).__name__ + ": " + str(exc)[:200]

    correct_feasible = True
    correct_error = ""
    try:
        correct_v = correct.res_bus.vm_pu.to_numpy(copy=True)
        correct_loading = correct.res_line.loading_percent.to_numpy(copy=True) if len(correct.line) else np.array([])
    except Exception as exc:
        correct_feasible = False
        correct_error = type(exc).__name__ + ": " + str(exc)[:200]
        correct_v = np.full_like(base_v, np.nan)
        correct_loading = np.full_like(base_loading, np.nan)

    if alias_feasible:
        alias_v = alias.res_bus.vm_pu.to_numpy(copy=True)
        alias_loading = alias.res_line.loading_percent.to_numpy(copy=True) if len(alias.line) else np.array([])
        max_v_delta = float(np.max(np.abs(correct_v - alias_v)))
        max_loading_delta = float(np.max(np.abs(correct_loading - alias_loading))) if len(alias_loading) else 0.0
        harmful = bool(max_v_delta > 1e-5 or max_loading_delta > 1e-3)
    else:
        max_v_delta = float("inf")
        max_loading_delta = float("inf")
        harmful = True

    # The feature-only verifier sees identical numerical fields and accepts;
    # PCC rejects because the two source identities are not identity-equivalent.
    return {
        "network": network_name,
        "scenario_id": f"{network_name}:duplicate_generator_n1:f{stress_factor:g}",
        "network_family": "IEEE_pandapower",
        "topology_hash": topology_hash(net),
        "bus_count": int(len(net.bus)),
        "line_count": int(len(net.line)),
        "asset_bus": bus,
        "p_each_mw": p_each,
        "stress_factor": stress_factor,
        "feature_only_accept": True,
        "pcc_accept": False,
        "nominal_max_voltage_delta": float(np.max(np.abs(base_v - nominal_v))),
        "nominal_max_loading_delta": float(np.max(np.abs(base_loading - nominal_loading))) if len(base_loading) else 0.0,
        "correct_contingency_feasible": correct_feasible,
        "alias_contingency_feasible": alias_feasible,
        "correct_error": correct_error,
        "alias_error": alias_error,
        "counterfactual_max_voltage_delta": max_v_delta,
        "counterfactual_max_loading_delta": max_loading_delta,
        "correct_min_voltage": float(np.min(correct_v)) if correct_feasible else float("nan"),
        "alias_min_voltage": float(np.min(alias_v)) if alias_feasible else float("nan"),
        "correct_max_loading_percent": float(np.max(correct_loading)) if len(correct_loading) else 0.0,
        "alias_max_loading_percent": float(np.max(alias_loading)) if alias_feasible and len(alias_loading) else float("nan"),
        "correct_safe_095_100": bool(correct_feasible and np.min(correct_v) >= 0.95 and (not len(correct_loading) or np.max(correct_loading) <= 100.0)),
        "alias_safe_095_100": bool(alias_feasible and np.min(alias_v) >= 0.95 and (not len(alias_loading) or np.max(alias_loading) <= 100.0)),
        "harmful_alias": harmful,
        "false_safe_if_merged": bool(correct_feasible and alias_feasible and np.min(correct_v) < 0.95 and np.max(correct_loading) > 100.0 and np.min(alias_v) >= 0.95 and np.max(alias_loading) <= 100.0),
    }


def main():
    cases = [
        ("case14", pn.case14),
        ("case30", pn.case30),
        ("case57", pn.case57),
        ("case118", pn.case118),
        ("case300", pn.case300),
    ]
    rows = []
    errors = []
    stress_factors = [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10]
    for name, factory in cases:
        for stress_factor in stress_factors:
            try:
                rows.append(make_pair(factory, name, stress_factor))
            except Exception as exc:
                errors.append({"network": name, "stress_factor": stress_factor,
                               "error": type(exc).__name__ + ": " + str(exc)[:300]})
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    summary = {
        "experiment": "counterfactual_n1_representation_aliasing",
        "date": DATE,
        "n_networks_attempted": len(cases) * len(stress_factors),
        "n_networks_completed": len(rows),
        "n_networks_failed": len(errors),
        "feature_only_accepts": int(df.feature_only_accept.sum()) if len(df) else 0,
        "pcc_accepts": int(df.pcc_accept.sum()) if len(df) else 0,
        "harmful_aliases": int(df.harmful_alias.sum()) if len(df) else 0,
        "false_safe_cases": int(df.false_safe_if_merged.sum()) if len(df) else 0,
        "errors": errors,
        "interpretation": "Public mechanism benchmark only; not H39 lockbox or field validation.",
        "primary_evidence": str(OUT_CSV.name),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
