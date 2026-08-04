"""Check AC-PF invariance after a legal same-bus load split."""
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
# The full 300-per-case sweep exceeded the local CPU time budget because it
# performs two independent AC PF solves per scenario.  Keep this executable
# mechanism audit intentionally small and explicit; the 3,000-scenario lockbox
# already covers the larger semantic/PF matrix.
N_PER_CASE = 30
SEED = 20260801


def solve(net):
    pp.runpp(net, algorithm="nr", init="dc", calculate_voltage_angles=True, max_iteration=50, tolerance_mva=1e-8)


def main():
    rows = []
    t0 = time.perf_counter()
    for offset, (case, constructor) in enumerate(CASES):
        for j in range(N_PER_CASE):
            rng = np.random.default_rng(SEED + offset * 1_000_000 + j)
            original = constructor()
            if len(original.load):
                mult = rng.uniform(.8, 1.2, len(original.load))
                original.load["p_mw"] *= mult
                original.load["q_mvar"] *= mult
            split = copy.deepcopy(original)
            load_idx = int(split.load.index[0])
            bus = int(split.load.loc[load_idx, "bus"])
            p = float(split.load.loc[load_idx, "p_mw"]) / 2
            q = float(split.load.loc[load_idx, "q_mvar"]) / 2
            split.load.loc[load_idx, "p_mw"] = p
            split.load.loc[load_idx, "q_mvar"] = q
            pp.create_load(split, bus=bus, p_mw=p, q_mvar=q, name="certified_split_part")
            row = {"case": case, "scenario": j, "converged_original": False, "converged_split": False, "max_vm_delta_pu": None, "max_line_loading_delta_percent": None, "split_load_bus": bus}
            try:
                solve(original); row["converged_original"] = True
                solve(split); row["converged_split"] = True
                row["max_vm_delta_pu"] = float(np.max(np.abs(original.res_bus.vm_pu.to_numpy() - split.res_bus.vm_pu.to_numpy())))
                row["max_line_loading_delta_percent"] = float(np.max(np.abs(original.res_line.loading_percent.to_numpy() - split.res_line.loading_percent.to_numpy()))) if len(original.res_line) else 0.0
            except Exception as exc:
                row["error"] = type(exc).__name__ + ": " + str(exc)[:160]
            rows.append(row)
    out = ROOT / "physical_split_invariance_results_20260801.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    valid = [r for r in rows if r["converged_original"] and r["converged_split"]]
    summary = {"n": len(rows), "n_valid_pairs": len(valid), "elapsed_seconds": time.perf_counter() - t0, "max_vm_delta_pu": max(r["max_vm_delta_pu"] for r in valid), "max_line_loading_delta_percent": max(r["max_line_loading_delta_percent"] for r in valid), "by_case": {case: {"n": sum(r["case"] == case for r in rows), "valid": sum(r["case"] == case and r in valid for r in rows)} for case, _ in CASES}, "limitations": ["same-bus load split only", "public IEEE/pandapower substitute", "does not prove OPF or model-level invariance"]}
    (ROOT / "physical_split_invariance_summary_20260801.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
