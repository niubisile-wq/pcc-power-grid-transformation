from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "outputs" / "cross_solver_validation"
OUTPUT = ROOT / "outputs" / "cross_solver_dcmp_validation"
PROJECT = ROOT / "julia" / "cross_solver"
SCRIPT = PROJECT / "run_powermodels_dcmp_highs_opf.jl"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive.rstrip(':').lower()}{resolved.as_posix().split(':', 1)[1]}"


def optimal(status: str) -> bool:
    return status.upper() in {"OPTIMAL", "LOCALLY_SOLVED"}


def relative(left: float, right: float) -> float:
    return abs(left - right) / max(abs(left), 1.0)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    input_path = V1 / "powermodels_inputs.tsv"
    independent_path = OUTPUT / "powermodels_dcmp_highs_results.tsv"
    subprocess.run([
        "wsl", "-d", "Ubuntu-24.04", "--", "/root/.local/bin/julia",
        f"--project={wsl_path(PROJECT)}", wsl_path(SCRIPT),
        wsl_path(input_path), wsl_path(independent_path),
    ], check=True, cwd=ROOT)
    with (V1 / "cross_solver_results.csv").open(encoding="utf-8") as stream:
        reference = {(row["network"], row["scale"]): row for row in csv.DictReader(stream)}
    with independent_path.open(encoding="utf-8") as stream:
        independent = list(csv.DictReader(stream, delimiter="\t"))
    rows = []
    for row in independent:
        old = reference[(row["network"], row["scale"])]
        independent_optimal = optimal(row["termination_status"])
        reference_optimal = old["pypower_success"] == "True"
        mutually_optimal = independent_optimal and reference_optimal
        objective_error = relative(float(old["pypower_objective"]), float(row["objective"])) if mutually_optimal else None
        generation_error = relative(float(old["pypower_total_generation_mw"]), float(row["total_generation_mw"])) if mutually_optimal else None
        rows.append({
            **row,
            "pypower_status": "optimal" if reference_optimal else "nonoptimal",
            "pypower_objective": old["pypower_objective"],
            "pypower_total_generation_mw": old["pypower_total_generation_mw"],
            "status_agreement": independent_optimal == reference_optimal,
            "mutually_optimal": mutually_optimal,
            "objective_relative_error": objective_error,
            "generation_relative_error": generation_error,
            "objective_agreement": objective_error <= 1e-5 if mutually_optimal else None,
            "generation_agreement": generation_error <= 1e-6 if mutually_optimal else None,
        })
    with (OUTPUT / "cross_solver_dcmp_results.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    comparable = [row for row in rows if row["mutually_optimal"]]
    unexplained = sum(
        not row["status_agreement"]
        or (row["mutually_optimal"] and not (row["objective_agreement"] and row["generation_agreement"]))
        for row in rows
    )
    summary = {
        "protocol": "cross_solver_powermodels_dcmp_v2",
        "status_pairs": len(rows),
        "mutually_optimal_pairs": len(comparable),
        "status_agreement_rate": sum(row["status_agreement"] for row in rows) / len(rows),
        "objective_agreement_rate_among_mutually_optimal": sum(row["objective_agreement"] for row in comparable) / len(comparable),
        "generation_agreement_rate_among_mutually_optimal": sum(row["generation_agreement"] for row in comparable) / len(comparable),
        "max_objective_relative_error": max(row["objective_relative_error"] for row in comparable),
        "max_generation_relative_error": max(row["generation_relative_error"] for row in comparable),
        "unexplained_differences": unexplained,
        "julia_version": rows[0]["julia_version"],
        "powermodels_version": rows[0]["powermodels_version"],
        "highs_version": rows[0]["highs_version"],
        "formulation": rows[0]["formulation"],
        "ready": len(rows) == 9 and len(comparable) >= 8 and unexplained == 0,
    }
    (OUTPUT / "cross_solver_dcmp_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
