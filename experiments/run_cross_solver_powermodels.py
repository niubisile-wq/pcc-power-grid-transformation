from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path

import numpy as np
from pypower.api import ppoption, rundcopf
from pypower.idx_bus import PD, QD

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "cross_solver_validation"
JULIA_PROJECT = ROOT / "julia" / "cross_solver"
JULIA_SCRIPT = JULIA_PROJECT / "run_powermodels_dc_opf.jl"
CASES = {
    "case39": ROOT / "downloads" / "pglib-opf-v23.07" / "pglib_opf_case39_epri.m",
    "case73": ROOT / "downloads" / "pglib-opf-v23.07" / "pglib_opf_case73_ieee_rts.m",
    "case118": ROOT / "downloads" / "pglib-opf-v23.07" / "pglib_opf_case118_ieee.m",
}
SCALES = (0.9, 1.0, 1.1)


def matrix(text: str, name: str) -> list[list[float]]:
    uncommented = re.sub(r"%.*$", "", text, flags=re.MULTILINE)
    match = re.search(rf"mpc\.{name}\s*=\s*\[(.*?)\];", uncommented, flags=re.DOTALL)
    if not match:
        raise ValueError(f"matrix_missing:{name}")
    return [
        [float(value) for value in raw.split()]
        for raw in match.group(1).split(";")
        if raw.strip()
    ]


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix().split(":", 1)[1]
    return f"/mnt/{drive}{rest}"


def solve_pypower(path: Path, scale: float) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    base_match = re.search(r"mpc\.baseMVA\s*=\s*([0-9.eE+-]+)", text)
    if not base_match:
        raise ValueError("base_mva_missing")
    case = {
        "version": "2",
        "baseMVA": float(base_match.group(1)),
        "bus": np.asarray(matrix(text, "bus"), dtype=float),
        "gen": np.asarray(matrix(text, "gen"), dtype=float),
        "branch": np.asarray(matrix(text, "branch"), dtype=float),
        "gencost": np.asarray(matrix(text, "gencost"), dtype=float),
    }
    case["bus"][:, PD] *= scale
    case["bus"][:, QD] *= scale
    result = rundcopf(case, ppoption(VERBOSE=0, OUT_ALL=0))
    return {
        "success": bool(result["success"]),
        "objective": float(result["f"]),
        "total_generation_mw": float(np.sum(result["gen"][:, 1])),
        "generator_dispatch_mw": ";".join(
            f"{index + 1}={value:.12g}"
            for index, value in enumerate(result["gen"][:, 1])
        ),
    }


def main() -> None:
    missing = [str(path) for path in CASES.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(missing)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    input_path = OUTPUT / "powermodels_inputs.tsv"
    julia_output = OUTPUT / "powermodels_results.tsv"
    python_rows: dict[tuple[str, float], dict] = {}
    with input_path.open("w", encoding="utf-8", newline="") as stream:
        for network, path in CASES.items():
            for scale in SCALES:
                stream.write(f"{network}\t{wsl_path(path)}\t{scale}\n")
                python_rows[(network, scale)] = solve_pypower(path, scale)
    command = [
        "wsl", "-d", "Ubuntu-24.04", "--",
        "/root/.local/bin/julia",
        f"--project={wsl_path(JULIA_PROJECT)}",
        wsl_path(JULIA_SCRIPT),
        wsl_path(input_path),
        wsl_path(julia_output),
    ]
    subprocess.run(command, check=True, cwd=ROOT)
    with julia_output.open(encoding="utf-8") as stream:
        julia_rows = list(csv.DictReader(stream, delimiter="\t"))
    rows = []
    for julia in julia_rows:
        key = (julia["network"], float(julia["scale"]))
        python = python_rows[key]
        julia_status = julia["termination_status"].upper()
        julia_optimal = julia_status in {"OPTIMAL", "LOCALLY_SOLVED"}
        mutually_optimal = python["success"] and julia_optimal
        julia_objective = float(julia["objective"])
        julia_generation = float(julia["total_generation_mw"])
        objective_relative_error = None
        generation_relative_error = None
        if mutually_optimal:
            objective_relative_error = abs(python["objective"] - julia_objective) / max(abs(python["objective"]), 1.0)
            generation_relative_error = abs(python["total_generation_mw"] - julia_generation) / max(abs(python["total_generation_mw"]), 1.0)
        objective_agreement = mutually_optimal and objective_relative_error <= 1e-5
        generation_agreement = mutually_optimal and generation_relative_error <= 1e-6
        rows.append({
            **julia,
            "pypower_success": python["success"],
            "pypower_objective": python["objective"],
            "pypower_total_generation_mw": python["total_generation_mw"],
            "pypower_generator_dispatch_mw": python["generator_dispatch_mw"],
            "status_agreement": python["success"] == julia_optimal,
            "mutually_optimal": mutually_optimal,
            "objective_relative_error": objective_relative_error,
            "generation_relative_error": generation_relative_error,
            "objective_agreement": objective_agreement if mutually_optimal else None,
            "generation_agreement": generation_agreement if mutually_optimal else None,
        })
    with (OUTPUT / "cross_solver_results.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    comparable = [row for row in rows if row["mutually_optimal"]]
    unexplained = sum(
        (not row["status_agreement"])
        or (
            row["mutually_optimal"]
            and not (row["objective_agreement"] and row["generation_agreement"])
        )
        for row in rows
    )
    summary = {
        "protocol": "cross_solver_powermodels_v1",
        "status_pairs": len(rows),
        "mutually_optimal_pairs": len(comparable),
        "status_agreement_rate": sum(row["status_agreement"] for row in rows) / len(rows),
        "objective_agreement_rate_among_mutually_optimal": sum(row["objective_agreement"] for row in comparable) / len(comparable) if comparable else None,
        "generation_agreement_rate_among_mutually_optimal": sum(row["generation_agreement"] for row in comparable) / len(comparable) if comparable else None,
        "max_objective_relative_error": max((row["objective_relative_error"] for row in comparable), default=None),
        "max_generation_relative_error": max((row["generation_relative_error"] for row in comparable), default=None),
        "unexplained_differences": unexplained,
        "julia_version": rows[0]["julia_version"],
        "powermodels_version": rows[0]["powermodels_version"],
        "ipopt_version": rows[0]["ipopt_version"],
        "ready": len(rows) == 9 and len(comparable) >= 8 and unexplained == 0,
    }
    (OUTPUT / "cross_solver_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
