"""Exact warm-started HiGHS leave-one-out solves for PyPSA SCOPF models."""

from __future__ import annotations

import time

import numpy as np

from linopy.constants import Result, Solution, Status, TerminationCondition


def outage_security_row_indices(network, omitted: tuple[str, str]) -> list[int]:
    """Map all security-constraint labels for one outage to HiGHS row indices."""
    component, name = omitted
    outage_dim = component + "-outage"
    labels = []
    for constraint_name, constraint in network.model.constraints.items():
        if "security-for" not in constraint_name or outage_dim not in constraint.labels.dims:
            continue
        selected = np.asarray(
            constraint.labels.sel({outage_dim: name}).values, dtype=int
        ).ravel()
        labels.extend(int(value) for value in selected if value >= 0)
    labels = sorted(set(labels))
    if not labels:
        raise RuntimeError(f"no_security_rows_for_outage:{component}:{name}")
    label_to_row = {
        int(label): row
        for row, label in enumerate(network.model.matrices.clabels)
    }
    missing = [label for label in labels if label not in label_to_row]
    if missing:
        raise RuntimeError("security_constraint_labels_missing_from_solver_rows")
    return sorted(label_to_row[label] for label in labels)


def _assign_highs_solution(network, *, excluded_rows: set[int]) -> dict:
    model = network.model
    highs = model.solver_model
    status = highs.modelStatusToString(highs.getModelStatus())
    if status != "Optimal":
        raise RuntimeError(f"highs_not_optimal_after_row_relaxation:{status}")
    solution = highs.getSolution()
    vector = np.asarray(solution.col_value, dtype=float)
    matrices = model.matrices
    lhs = matrices.A @ vector
    included = np.ones(len(matrices.b), dtype=bool)
    if excluded_rows:
        included[np.fromiter(excluded_rows, dtype=int)] = False
    violation = np.zeros(len(matrices.b), dtype=float)
    equal = (matrices.sense == "=") & included
    less = (matrices.sense == "<") & included
    greater = (matrices.sense == ">") & included
    violation[equal] = np.abs(lhs[equal] - matrices.b[equal])
    violation[less] = np.maximum(lhs[less] - matrices.b[less], 0.0)
    violation[greater] = np.maximum(matrices.b[greater] - lhs[greater], 0.0)
    bound_violation = max(
        float(np.max(np.maximum(matrices.lb - vector, 0.0))),
        float(np.max(np.maximum(vector - matrices.ub, 0.0))),
    )
    max_violation = max(float(np.max(violation)), bound_violation)
    if max_violation > 1e-5:
        raise RuntimeError(f"highs_relaxed_model_constraint_violation:{max_violation}")
    primal = np.full(int(matrices.vlabels.max()) + 1, np.nan)
    primal[matrices.vlabels] = vector
    result = Result(
        status=Status.from_termination_condition(TerminationCondition.optimal),
        solution=Solution(primal, np.array([]), float(highs.getObjectiveValue())),
        solver_name="highs",
    )
    model.assign_result(result)
    network.optimize.assign_solution()
    network.optimize.post_processing()
    return {
        "status": "ok",
        "condition": "optimal",
        "solver": "HiGHS 1.11.0 warm-start row relaxation",
        "objective": float(network.objective),
        "max_retained_constraint_violation": max_violation,
    }


def relax_outage_and_solve(network, omitted: tuple[str, str]) -> tuple[dict, dict]:
    """Relax exactly one outage group in an already solved full SCOPF model."""
    highs = network.model.solver_model
    rows = outage_security_row_indices(network, omitted)
    lp = highs.getLp()
    original_lower = [float(lp.row_lower_[row]) for row in rows]
    original_upper = [float(lp.row_upper_[row]) for row in rows]
    infinity = float(highs.getInfinity())
    for row in rows:
        highs.changeRowBounds(row, -infinity, infinity)
    started = time.perf_counter()
    highs.run()
    metadata = _assign_highs_solution(network, excluded_rows=set(rows))
    metadata["elapsed_s"] = time.perf_counter() - started
    metadata["relaxed_rows"] = len(rows)
    handle = {
        "rows": rows,
        "lower": original_lower,
        "upper": original_upper,
    }
    return metadata, handle


def restore_rows_and_solve(network, handle: dict) -> dict:
    """Restore a relaxed outage group and return to the full SCOPF optimum."""
    highs = network.model.solver_model
    for row, lower, upper in zip(handle["rows"], handle["lower"], handle["upper"]):
        highs.changeRowBounds(int(row), float(lower), float(upper))
    started = time.perf_counter()
    highs.run()
    metadata = _assign_highs_solution(network, excluded_rows=set())
    metadata["elapsed_s"] = time.perf_counter() - started
    return metadata
