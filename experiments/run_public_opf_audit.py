"""Run a small, real public OPF audit and legal load-split comparison."""
from __future__ import annotations

import copy
import csv
import json
import time
from pathlib import Path

import numpy as np
import pandapower as pp

ROOT = Path(__file__).resolve().parent
CASES = [("case14", pp.networks.case14), ("case30", pp.networks.case30), ("case57", pp.networks.case57)]
N_PER_CASE = 20
SEED = 20260801


def perturb(net, seed):
    rng = np.random.default_rng(seed)
    if len(net.load):
        m = rng.uniform(.90, 1.10, len(net.load))
        net.load["p_mw"] *= m
        net.load["q_mvar"] *= m


def add_legal_split(net):
    d = copy.deepcopy(net)
    i = int(d.load.index[0])
    bus = int(d.load.loc[i, "bus"])
    p = float(d.load.loc[i, "p_mw"]) / 2
    q = float(d.load.loc[i, "q_mvar"]) / 2
    d.load.loc[i, "p_mw"] = p
    d.load.loc[i, "q_mvar"] = q
    pp.create_load(d, bus=bus, p_mw=p, q_mvar=q, name="certified_split_part")
    return d


def solve(net):
    t0 = time.perf_counter()
    pp.runopp(net, verbose=False, calculate_voltage_angles=True, max_iteration=100, delta=1e-8)
    return time.perf_counter() - t0


def main():
    rows = []
    for offset, (case, constructor) in enumerate(CASES):
        for j in range(N_PER_CASE):
            seed = SEED + offset * 1_000_000 + j
            original = constructor(); perturb(original, seed)
            split = add_legal_split(original)
            row = {"case": case, "scenario": j, "seed": seed, "original_converged": False, "split_converged": False, "original_cost": None, "split_cost": None, "cost_delta": None, "min_vm_delta": None, "max_line_loading_delta": None, "original_time_s": None, "split_time_s": None, "error": None}
            try:
                row["original_time_s"] = solve(original); row["original_converged"] = True; row["original_cost"] = float(original.res_cost)
            except Exception as exc:
                row["error"] = "original:" + type(exc).__name__ + ":" + str(exc)[:140]
            try:
                row["split_time_s"] = solve(split); row["split_converged"] = True; row["split_cost"] = float(split.res_cost)
            except Exception as exc:
                row["error"] = (row["error"] or "") + " split:" + type(exc).__name__ + ":" + str(exc)[:140]
            if row["original_converged"] and row["split_converged"]:
                row["cost_delta"] = abs(row["original_cost"] - row["split_cost"])
                row["min_vm_delta"] = float(np.max(np.abs(original.res_bus.vm_pu.to_numpy() - split.res_bus.vm_pu.to_numpy())))
                row["max_line_loading_delta"] = float(np.max(np.abs(original.res_line.loading_percent.to_numpy() - split.res_line.loading_percent.to_numpy()))) if len(original.res_line) else 0.0
            rows.append(row)
    out = ROOT / "public_opf_results_20260801.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    valid = [r for r in rows if r["original_converged"] and r["split_converged"]]
    summary = {"n": len(rows), "by_case": {}, "paired_valid": len(valid), "max_cost_delta": max((r["cost_delta"] or 0.0) for r in valid), "max_min_vm_delta": max((r["min_vm_delta"] or 0.0) for r in valid), "max_line_loading_delta": max((r["max_line_loading_delta"] or 0.0) for r in valid), "limitations": ["public pandapower OPF substitute", "case57 may fail under native voltage/cost constraints", "not H39 lockbox or GridSFM/LUMINA OPF evaluation"]}
    for case, _ in CASES:
        rs = [r for r in rows if r["case"] == case]
        summary["by_case"][case] = {"n": len(rs), "original_converged": sum(r["original_converged"] for r in rs), "split_converged": sum(r["split_converged"] for r in rs), "paired_valid": sum(r in valid for r in rs)}
    (ROOT / "public_opf_summary_20260801.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
