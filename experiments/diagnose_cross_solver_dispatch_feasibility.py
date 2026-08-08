from __future__ import annotations

import csv
import json

import numpy as np
from pypower.api import ppoption, rundcpf
from pypower.idx_brch import ANGMAX, ANGMIN, F_BUS, PF, RATE_A, T_BUS
from pypower.idx_bus import PD, QD, VA
from pypower.idx_gen import PG

from run_cross_solver_powermodels import CASES, matrix


def dispatch(text: str) -> np.ndarray:
    values = {int(item.split("=", 1)[0]): float(item.split("=", 1)[1]) for item in text.split(";")}
    return np.asarray([values[index] for index in range(1, max(values) + 1)])


def case_at_scale(path, scale: float) -> dict:
    import re

    text = path.read_text(encoding="utf-8", errors="replace")
    base = re.search(r"mpc\.baseMVA\s*=\s*([0-9.eE+-]+)", text)
    case = {
        "version": "2",
        "baseMVA": float(base.group(1)),
        "bus": np.asarray(matrix(text, "bus"), dtype=float),
        "gen": np.asarray(matrix(text, "gen"), dtype=float),
        "branch": np.asarray(matrix(text, "branch"), dtype=float),
        "gencost": np.asarray(matrix(text, "gencost"), dtype=float),
    }
    case["bus"][:, PD] *= scale
    case["bus"][:, QD] *= scale
    return case


def check(case: dict, generation: np.ndarray) -> dict:
    candidate = {key: value.copy() if hasattr(value, "copy") else value for key, value in case.items()}
    candidate["gen"][:, PG] = generation
    solved = rundcpf(candidate, ppoption(VERBOSE=0, OUT_ALL=0))
    branch = solved[0]["branch"]
    bus = solved[0]["bus"]
    bus_number_to_angle = {int(row[0]): row[VA] for row in bus}
    finite_rate = branch[:, RATE_A] > 0
    rate_excess = np.abs(branch[:, PF]) - branch[:, RATE_A]
    angle = np.asarray([
        bus_number_to_angle[int(row[F_BUS])] - bus_number_to_angle[int(row[T_BUS])]
        for row in branch
    ])
    angle_low_excess = branch[:, ANGMIN] - angle
    angle_high_excess = angle - branch[:, ANGMAX]
    return {
        "dc_pf_success": bool(solved[0]["success"]),
        "slack_adjustment_mw": float(solved[0]["gen"][0, PG] - generation[0]),
        "max_rate_excess_mw": float(max(np.max(rate_excess[finite_rate]), 0.0)),
        "rate_violating_branches": int(np.sum(finite_rate & (rate_excess > 1e-5))),
        "max_angle_excess_deg": float(max(np.max(angle_low_excess), np.max(angle_high_excess), 0.0)),
        "angle_violating_branches": int(np.sum((angle_low_excess > 1e-5) | (angle_high_excess > 1e-5))),
    }


def main() -> None:
    source = CASES["case39"].parents[2] / "outputs" / "cross_solver_validation" / "cross_solver_results.csv"
    with source.open(encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    diagnostics = []
    for row in rows:
        if row["mutually_optimal"] != "True":
            continue
        case = case_at_scale(CASES[row["network"]], float(row["scale"]))
        diagnostics.append({
            "network": row["network"],
            "scale": float(row["scale"]),
            "dispatch": "powermodels",
            **check(case, dispatch(row["generator_dispatch_mw"])),
        })
        diagnostics.append({
            "network": row["network"],
            "scale": float(row["scale"]),
            "dispatch": "pypower",
            **check(case, dispatch(row["pypower_generator_dispatch_mw"])),
        })
    output = source.parent / "dispatch_cross_feasibility_diagnostic.json"
    output.write_text(json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(diagnostics, indent=2))


if __name__ == "__main__":
    main()
