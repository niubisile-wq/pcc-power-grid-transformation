"""Strict Clarabel 0.11.1 adapter for continuous Linopy LP/QP models."""

from __future__ import annotations

import time

import clarabel
import numpy as np
import scipy.sparse as sp

from linopy.constants import Result, Solution, Status, TerminationCondition


def _clarabel_form(model):
    matrices = model.matrices
    matrix = sp.csc_matrix(matrices.A, dtype=float)
    blocks = []
    rhs_blocks = []
    cones = []
    equal = matrices.sense == "="
    less = matrices.sense == "<"
    greater = matrices.sense == ">"
    if equal.any():
        blocks.append(matrix[equal])
        rhs_blocks.append(matrices.b[equal])
        cones.append(clarabel.ZeroConeT(int(equal.sum())))
    inequalities = []
    inequality_rhs = []
    if less.any():
        inequalities.append(matrix[less])
        inequality_rhs.append(matrices.b[less])
    if greater.any():
        inequalities.append(-matrix[greater])
        inequality_rhs.append(-matrices.b[greater])
    identity = sp.eye(len(matrices.vlabels), format="csc")
    finite_upper = np.isfinite(matrices.ub)
    finite_lower = np.isfinite(matrices.lb)
    if finite_upper.any():
        inequalities.append(identity[finite_upper])
        inequality_rhs.append(matrices.ub[finite_upper])
    if finite_lower.any():
        inequalities.append(-identity[finite_lower])
        inequality_rhs.append(-matrices.lb[finite_lower])
    if inequalities:
        inequality_matrix = sp.vstack(inequalities, format="csc")
        inequality_values = np.concatenate(inequality_rhs).astype(float)
        blocks.append(inequality_matrix)
        rhs_blocks.append(inequality_values)
        cones.append(clarabel.NonnegativeConeT(len(inequality_values)))
    constraint_matrix = sp.vstack(blocks, format="csc")
    rhs = np.concatenate(rhs_blocks).astype(float)
    if matrices.Q is None:
        hessian = sp.csc_matrix((len(matrices.vlabels), len(matrices.vlabels)))
    else:
        hessian = sp.triu(sp.csc_matrix(matrices.Q, dtype=float), format="csc")
    return matrices, hessian, matrices.c.astype(float), constraint_matrix, rhs, cones


def solve_linopy_with_clarabel(network, *, settings_overrides: dict | None = None) -> dict:
    """Solve and assign only a fully converged Clarabel solution."""
    model = network.model
    matrices, hessian, linear, constraint_matrix, rhs, cones = _clarabel_form(model)
    settings = clarabel.DefaultSettings()
    settings.verbose = False
    settings.max_iter = 1000
    settings.tol_gap_abs = 1e-7
    settings.tol_gap_rel = 1e-8
    settings.tol_feas = 1e-8
    for name, value in (settings_overrides or {}).items():
        if not hasattr(settings, name):
            raise ValueError(f"unknown_clarabel_setting:{name}")
        setattr(settings, name, value)
    started = time.perf_counter()
    solution = clarabel.DefaultSolver(
        hessian, linear, constraint_matrix, rhs, cones, settings
    ).solve()
    elapsed = time.perf_counter() - started
    if str(solution.status) != "Solved":
        raise RuntimeError(f"clarabel_not_solved:{solution.status}")
    vector = np.asarray(solution.x, dtype=float)
    lhs = matrices.A @ vector
    violation = np.zeros(len(matrices.b), dtype=float)
    violation[matrices.sense == "="] = np.abs(
        lhs[matrices.sense == "="] - matrices.b[matrices.sense == "="]
    )
    violation[matrices.sense == "<"] = np.maximum(
        lhs[matrices.sense == "<"] - matrices.b[matrices.sense == "<"], 0.0
    )
    violation[matrices.sense == ">"] = np.maximum(
        matrices.b[matrices.sense == ">"] - lhs[matrices.sense == ">"], 0.0
    )
    bound_violation = max(
        float(np.max(np.maximum(matrices.lb - vector, 0.0))),
        float(np.max(np.maximum(vector - matrices.ub, 0.0))),
    )
    max_violation = max(float(np.max(violation)), bound_violation)
    if max_violation > 1e-5:
        raise RuntimeError(f"clarabel_constraint_violation:{max_violation}")

    primal = np.full(int(matrices.vlabels.max()) + 1, np.nan)
    primal[matrices.vlabels] = vector
    # Clarabel returns cone duals in the row order constructed above: equality
    # rows, original <= rows, converted original >= rows, then variable-bound
    # rows.  Linopy needs one dual per original labelled constraint.  Restoring
    # this mapping keeps the exact SCOPF activity screen solver-independent;
    # bound-cone duals are intentionally excluded because they are not Linopy
    # constraint labels.
    cone_dual = np.asarray(solution.z, dtype=float)
    original_dual = np.empty(len(matrices.b), dtype=float)
    equal = matrices.sense == "="
    less = matrices.sense == "<"
    greater = matrices.sense == ">"
    cursor = 0
    equal_count = int(equal.sum())
    less_count = int(less.sum())
    greater_count = int(greater.sum())
    original_dual[equal] = cone_dual[cursor : cursor + equal_count]
    cursor += equal_count
    original_dual[less] = cone_dual[cursor : cursor + less_count]
    cursor += less_count
    original_dual[greater] = -cone_dual[cursor : cursor + greater_count]
    dual = np.full(int(matrices.clabels.max()) + 1, np.nan)
    dual[matrices.clabels] = original_dual
    result = Result(
        status=Status.from_termination_condition(TerminationCondition.optimal),
        solution=Solution(primal, dual, float(solution.obj_val)),
        solver_name="clarabel",
    )
    model.assign_result(result)
    network.optimize.assign_solution()
    network.optimize.post_processing()
    return {
        "status": "ok",
        "condition": "optimal",
        "solver": "Clarabel 0.11.1",
        "objective": float(network.objective),
        "elapsed_s": elapsed,
        "iterations": int(solution.iterations),
        "primal_residual": float(solution.r_prim),
        "dual_residual": float(solution.r_dual),
        "max_constraint_violation": max_violation,
    }
