from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "cross_solver_validation"
PROJECT = ROOT / "julia" / "cross_solver"
SCRIPT = PROJECT / "run_powermodels_highs_dc_opf.jl"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive.rstrip(':').lower()}{resolved.as_posix().split(':', 1)[1]}"


def optimal(status: str) -> bool:
    return status.upper() in {"OPTIMAL", "LOCALLY_SOLVED"}


def relative(left: float, right: float) -> float:
    return abs(left - right) / max(abs(left), 1.0)


def main() -> None:
    input_path = OUTPUT / "powermodels_inputs.tsv"
    v1_path = OUTPUT / "cross_solver_results.csv"
    highs_path = OUTPUT / "powermodels_highs_results.tsv"
    subprocess.run([
        "wsl", "-d", "Ubuntu-24.04", "--", "/root/.local/bin/julia",
        f"--project={wsl_path(PROJECT)}", wsl_path(SCRIPT),
        wsl_path(input_path), wsl_path(highs_path),
    ], check=True, cwd=ROOT)
    with v1_path.open(encoding="utf-8") as stream:
        v1 = {(row["network"], row["scale"]): row for row in csv.DictReader(stream)}
    with highs_path.open(encoding="utf-8") as stream:
        highs = list(csv.DictReader(stream, delimiter="\t"))
    rows = []
    for row in highs:
        old = v1[(row["network"], row["scale"])]
        highs_optimal = optimal(row["termination_status"])
        pypower_optimal = old["pypower_success"] == "True"
        ipopt_optimal = optimal(old["termination_status"])
        mutually_optimal = highs_optimal and pypower_optimal and ipopt_optimal
        record = {
            **row,
            "pypower_status": "optimal" if pypower_optimal else "nonoptimal",
            "ipopt_status": old["termination_status"],
            "three_stack_status_agreement": highs_optimal == pypower_optimal == ipopt_optimal,
            "mutually_optimal": mutually_optimal,
            "pypower_objective": old["pypower_objective"],
            "ipopt_objective": old["objective"],
            "highs_vs_pypower_objective_relative_error": None,
            "highs_vs_ipopt_objective_relative_error": None,
            "highs_vs_pypower_generation_relative_error": None,
        }
        if mutually_optimal:
            record["highs_vs_pypower_objective_relative_error"] = relative(float(old["pypower_objective"]), float(row["objective"]))
            record["highs_vs_ipopt_objective_relative_error"] = relative(float(old["objective"]), float(row["objective"]))
            record["highs_vs_pypower_generation_relative_error"] = relative(float(old["pypower_total_generation_mw"]), float(row["total_generation_mw"]))
        rows.append(record)
    with (OUTPUT / "highs_adjudication_results.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    comparable = [row for row in rows if row["mutually_optimal"]]
    summary = {
        "protocol": "cross_solver_highs_adjudication_v1",
        "status_pairs": len(rows),
        "three_stack_status_agreement_rate": sum(row["three_stack_status_agreement"] for row in rows) / len(rows),
        "mutually_optimal_pairs": len(comparable),
        "highs_vs_pypower_objective_agreement_rate": sum(row["highs_vs_pypower_objective_relative_error"] <= 1e-5 for row in comparable) / len(comparable),
        "highs_vs_pypower_max_objective_relative_error": max(row["highs_vs_pypower_objective_relative_error"] for row in comparable),
        "highs_vs_ipopt_max_objective_relative_error": max(row["highs_vs_ipopt_objective_relative_error"] for row in comparable),
        "highs_vs_pypower_max_generation_relative_error": max(row["highs_vs_pypower_generation_relative_error"] for row in comparable),
        "julia_version": rows[0]["julia_version"],
        "powermodels_version": rows[0]["powermodels_version"],
        "highs_version": rows[0]["highs_version"],
    }
    (OUTPUT / "highs_adjudication_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
