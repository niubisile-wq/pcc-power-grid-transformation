"""Resumable exact-screened case500 DC-SCOPF confirmatory runner."""

from __future__ import annotations

import argparse
import copy
import csv
import gc
import json
import math
from pathlib import Path
import sys
import time

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "cgmes", ROOT / "experiments"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dc_scopf_active_screening import (  # noqa: E402
    active_security_outages,
    bodf_post_contingency_loadings,
    create_security_constrained_model,
)
from linopy_clarabel import solve_linopy_with_clarabel  # noqa: E402
from highs_constraint_relaxation import (  # noqa: E402
    relax_outage_and_solve,
    restore_rows_and_solve,
)
from run_pcc_v2_dc_scopf_gate import (  # noqa: E402
    ENVIRONMENT_ID,
    LOAD_SCALES,
    branch_index,
    branch_loading,
    experiment_key,
    load_pglib,
    non_islanding_branches,
    post_contingency_loading,
    semantic_bundle,
    sha256_file,
)
from validation.execution_gate import ExecutionGate  # noqa: E402
from validation.pcc_v2 import PCCV2Verifier, TaskContract, issue_v2_certificate  # noqa: E402


CASE = "case500"
CASE_FILE = "pglib_opf_case500_goc.m"
CASE_PATH = ROOT / "downloads" / "pglib-opf-v23.07" / CASE_FILE
OUTPUT = ROOT / "outputs" / "pcc_v2_dc_scopf_case500_clarabel_portfolio"
PROTOCOL_VERSION = "pcc_v2_native_dc_scopf_case500_tight_dual_v11"
RESULT_SCHEMA = "pcc-v2-dc-scopf-result-v11"
LOADER_REVISION = "pglib-pypsa-transformer-explicit-v2"
CASE500_ENVIRONMENT_ID = ENVIRONMENT_ID + "-clarabel-0.11.1-portfolio-exact"
MAX_ATTEMPTS = 3
MAX_CONSTRAINT_GENERATION_ITERATIONS = 100
SEPARATION_TOLERANCE = 1.000001
CLARABEL_STRONG_SETTINGS = {
    "static_regularization_constant": 1e-7,
    "dynamic_regularization_delta": 1e-6,
}
CLARABEL_SETTINGS_PORTFOLIO = [
    ("default", {}),
    ("strong_regularization", CLARABEL_STRONG_SETTINGS),
]
CLARABEL_TIGHT_SETTINGS = {
    "tol_gap_abs": 1e-9,
    "tol_gap_rel": 1e-10,
    "tol_feas": 1e-9,
    "max_iter": 2000,
}
CLARABEL_TIGHT_STRONG_SETTINGS = {
    **CLARABEL_TIGHT_SETTINGS,
    **CLARABEL_STRONG_SETTINGS,
}
CLARABEL_FULL_SETTINGS_PORTFOLIO = [
    ("tight_default", CLARABEL_TIGHT_SETTINGS),
    ("tight_strong_regularization", CLARABEL_TIGHT_STRONG_SETTINGS),
]


def append_attempt(record: dict) -> None:
    with (OUTPUT / "solver_attempts.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def capture_result(network, elapsed_s: float, status: str, condition: str) -> dict:
    dispatch = {
        str(key): float(value)
        for key, value in network.generators_t.p.loc["now"].items()
    }
    return {
        "status": status,
        "condition": condition,
        "solver": "HiGHS 1.11.0",
        "objective": float(network.objective),
        "elapsed_s": elapsed_s,
        "dispatch": dispatch,
        "load_shed_mw": float(
            network.generators_t.p.loc["now"].filter(like="shed-").clip(lower=0.0).sum()
        ),
    }


def strict_solve(base, outages, solve_id: str, *, keep_model: bool = False):
    errors = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        network = copy.deepcopy(base)
        started = time.perf_counter()
        status = condition = legacy = None
        try:
            status, condition = network.optimize.optimize_security_constrained(
                branch_outages=branch_index(outages),
                solver_name="highs",
                log_to_console=False,
                time_limit=300.0,
            )
            solver_model = getattr(network.model, "solver_model", None)
            if solver_model is not None:
                legacy = solver_model.modelStatusToString(solver_model.getModelStatus())
            elapsed = time.perf_counter() - started
            objective = float(network.objective) if status == "ok" else None
            valid = bool(
                status == "ok"
                and condition == "optimal"
                and objective is not None
                and math.isfinite(objective)
                and objective > 1e-9
            )
            append_attempt({
                "solve_id": solve_id,
                "attempt": attempt,
                "status": status,
                "condition": condition,
                "highs_model_status": legacy,
                "objective": objective,
                "elapsed_s": elapsed,
                "valid": valid,
            })
            if valid:
                result = capture_result(network, elapsed, status, condition)
                if not keep_model:
                    if network.model is not None:
                        network.model.solver_model = None
                        del network.model
                    gc.collect()
                return network, result, attempt
            errors.append(f"attempt{attempt}:{status}:{condition}:{legacy}:{objective}")
        except Exception as exc:
            elapsed = time.perf_counter() - started
            errors.append(f"attempt{attempt}:{type(exc).__name__}:{exc}")
            append_attempt({
                "solve_id": solve_id,
                "attempt": attempt,
                "status": status,
                "condition": condition,
                "highs_model_status": legacy,
                "elapsed_s": elapsed,
                "valid": False,
                "error": f"{type(exc).__name__}: {exc}",
            })
        try:
            if network.model is not None:
                network.model.solver_model = None
                del network.model
        except Exception:
            pass
        del network
        gc.collect()
    raise RuntimeError("strict_solver_attempts_exhausted:" + "|".join(errors))


def release_model(network) -> None:
    if getattr(network, "model", None) is not None:
        network.model.solver_model = None
        del network.model
    gc.collect()


def strict_solve_clarabel(
    base,
    outages,
    solve_id: str,
    *,
    settings_overrides: dict | None = None,
    settings_portfolio: list[tuple[str, dict]] | None = None,
):
    errors = []
    portfolio = settings_portfolio or [("custom", settings_overrides or {})]
    for attempt, (settings_profile, current_settings) in enumerate(portfolio, start=1):
        network = copy.deepcopy(base)
        try:
            create_security_constrained_model(network, outages)
            metadata = solve_linopy_with_clarabel(
                network, settings_overrides=current_settings
            )
            metadata["settings_profile"] = settings_profile
            result = capture_result(
                network,
                metadata["elapsed_s"],
                metadata["status"],
                metadata["condition"],
            )
            result.update(metadata)
            append_attempt({
                "solve_id": solve_id,
                "attempt": attempt,
                "settings_profile": settings_profile,
                "solver": metadata["solver"],
                "status": metadata["status"],
                "condition": metadata["condition"],
                "objective": metadata["objective"],
                "elapsed_s": metadata["elapsed_s"],
                "iterations": metadata["iterations"],
                "primal_residual": metadata["primal_residual"],
                "dual_residual": metadata["dual_residual"],
                "max_constraint_violation": metadata["max_constraint_violation"],
                "valid": True,
            })
            return network, result, attempt
        except Exception as exc:
            errors.append(f"attempt{attempt}:{type(exc).__name__}:{exc}")
            append_attempt({
                "solve_id": solve_id,
                "attempt": attempt,
                "settings_profile": settings_profile,
                "solver": "Clarabel 0.11.1",
                "valid": False,
                "error": f"{type(exc).__name__}: {exc}",
            })
            release_model(network)
            del network
    raise RuntimeError("clarabel_attempts_exhausted:" + "|".join(errors))


def solve_alias_by_constraint_generation(
    base,
    all_candidates,
    omitted,
    initial_active_ids: set[str],
    solve_id: str,
):
    candidate_by_id = {
        f"{component}:{name}": (component, name) for component, name in all_candidates
    }
    omitted_id = f"{omitted[0]}:{omitted[1]}"
    enforced_ids = set(initial_active_ids) - {omitted_id}
    total_attempts = 0
    iterations = []
    for iteration in range(1, MAX_CONSTRAINT_GENERATION_ITERATIONS + 1):
        enforced = [candidate_by_id[key] for key in sorted(enforced_ids)]
        network, result, attempts = strict_solve_clarabel(
            base,
            enforced,
            f"{solve_id}:master{iteration}",
            settings_portfolio=CLARABEL_SETTINGS_PORTFOLIO,
        )
        total_attempts += attempts
        post = bodf_post_contingency_loadings(network, all_candidates)
        violations = sorted(
            key
            for key, value in post.items()
            if key != omitted_id and value > SEPARATION_TOLERANCE
        )
        new_violations = sorted(set(violations) - enforced_ids)
        record = {
            "solve_id": solve_id,
            "kind": "constraint_generation_separation",
            "iteration": iteration,
            "enforced_outages": len(enforced_ids),
            "violations": violations,
            "new_violations": new_violations,
            "max_non_omitted_loading_pu": max(
                value for key, value in post.items() if key != omitted_id
            ),
            "objective": result["objective"],
            "settings_profile": result["settings_profile"],
            "added_outages": [],
        }
        if not violations:
            append_attempt(record)
            iterations.append(record)
            return network, result, total_attempts, iterations, enforced_ids
        if not new_violations:
            append_attempt(record)
            iterations.append(record)
            release_model(network)
            raise RuntimeError(
                "constraint_generation_stalled_with_violations:" + ",".join(violations)
            )
        added_id = max(
            new_violations,
            key=lambda key: (post[key], key),
        )
        record["added_outages"] = [added_id]
        append_attempt(record)
        iterations.append(record)
        enforced_ids.add(added_id)
        release_model(network)
        del network
    raise RuntimeError("constraint_generation_iteration_limit")


def write_checkpoint(path: Path, rows: list[dict], failures: list[dict], metadata: dict) -> None:
    path.write_text(
        json.dumps({**metadata, "rows": rows, "failures": failures}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_state(offset: int, force: bool = False) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    prefix = OUTPUT / f"dc_scopf_gate_all_case500_offset{offset}_1states_v11"
    checkpoint_path = prefix.with_name(prefix.name + "_checkpoint.json")
    summary_path = prefix.with_name(prefix.name + "_summary.json")
    results_path = prefix.with_name(prefix.name + "_results.csv")
    if summary_path.exists() and not force:
        prior = json.loads(summary_path.read_text(encoding="utf-8"))
        if prior.get("completed_state_denominator") == 1 and prior.get("failed_states") == 0:
            print(f"SKIP complete case500 offset={offset}")
            return

    rows: list[dict] = []
    failures: list[dict] = []
    if checkpoint_path.exists() and not force:
        prior = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if prior.get("result_schema") == RESULT_SCHEMA:
            rows = prior.get("rows", [])
            failures = prior.get("failures", [])
    completed = {row["omitted_candidate"] for row in rows}
    load_scale = float(LOAD_SCALES[offset])
    input_hash = sha256_file(CASE_PATH)
    base = load_pglib(CASE_PATH, load_scale)
    candidates = non_islanding_branches(base)
    candidate_ids = [f"{component}:{name}" for component, name in candidates]
    metadata = {
        "protocol_version": PROTOCOL_VERSION,
        "result_schema": RESULT_SCHEMA,
        "loader_revision": LOADER_REVISION,
        "network": CASE,
        "state_offset": offset,
        "load_scale": load_scale,
        "candidate_count": len(candidates),
    }

    base_network, base_result, base_attempts = strict_solve_clarabel(
        base,
        [],
        f"{CASE}:offset{offset}:base:v11",
        settings_portfolio=CLARABEL_SETTINGS_PORTFOLIO,
    )
    pre_loading = branch_loading(base_network, candidates).fillna(0.0).sort_values()
    release_model(base_network)
    del base_network
    full_network, full_result, full_attempts = strict_solve_clarabel(
        base,
        candidates,
        f"{CASE}:offset{offset}:full:v11",
        settings_portfolio=CLARABEL_FULL_SETTINGS_PORTFOLIO,
    )
    activity = active_security_outages(full_network)
    full_post_by_outage = bodf_post_contingency_loadings(full_network, candidates)
    active = {key for key, item in activity.items() if item["active"]}
    if set(candidate_ids) - set(activity):
        raise RuntimeError("screening_activity_missing_candidates")
    key = experiment_key()

    for index, omitted in enumerate(pre_loading.index):
        omitted_id = f"{omitted[0]}:{omitted[1]}"
        if omitted_id in completed:
            continue
        try:
            omitted_frame = base.lines if omitted[0] == "Line" else base.transformers
            omitted_row = omitted_frame.loc[omitted[1]]
            exact_alias_solver_path = "inactive_full_optimum_reused"
            fallback_used = False
            fallback_relaxed_rows = 0
            fallback_max_retained_constraint_violation = None
            fallback_restored_full_objective_relative_difference = None
            if omitted_id in active:
                full_post = post_contingency_loading(base, full_result["dispatch"], omitted)
                try:
                    alias_network, alias_result, alias_attempts, cg_iterations, cg_enforced = (
                        solve_alias_by_constraint_generation(
                            base,
                            candidates,
                            omitted,
                            active,
                            f"{CASE}:offset{offset}:alias:{omitted_id}:v11",
                        )
                    )
                    alias_post = post_contingency_loading(
                        base, alias_result["dispatch"], omitted
                    )
                    terminal_max_non_omitted = cg_iterations[-1][
                        "max_non_omitted_loading_pu"
                    ]
                    release_model(alias_network)
                    del alias_network
                    screening_class = "active_exact_clarabel_portfolio_top1"
                    exact_alias_solver_path = "clarabel_settings_portfolio_top1"
                    alias_status = alias_result["status"]
                    alias_condition = alias_result["condition"]
                except Exception as primary_exc:
                    append_attempt({
                        "solve_id": f"{CASE}:offset{offset}:alias:{omitted_id}:v11",
                        "kind": "deterministic_highs_direct_exact_fallback",
                        "primary_error": f"{type(primary_exc).__name__}: {primary_exc}",
                    })
                    remaining = [item for item in candidates if item != omitted]
                    alias_network, alias_result, direct_attempts = strict_solve(
                        base,
                        remaining,
                        f"{CASE}:offset{offset}:alias:{omitted_id}:v11:highs-direct",
                        keep_model=True,
                    )
                    alias_post_by_outage = bodf_post_contingency_loadings(
                        alias_network, candidates
                    )
                    terminal_max_non_omitted = max(
                        value
                        for candidate_id, value in alias_post_by_outage.items()
                        if candidate_id != omitted_id
                    )
                    alias_post = post_contingency_loading(
                        base, alias_result["dispatch"], omitted
                    )
                    if terminal_max_non_omitted > SEPARATION_TOLERANCE:
                        raise RuntimeError(
                            "fallback_terminal_non_omitted_constraint_violation:"
                            f"{terminal_max_non_omitted}"
                        )
                    release_model(alias_network)
                    del alias_network
                    alias_attempts = len(CLARABEL_SETTINGS_PORTFOLIO) + direct_attempts
                    cg_iterations = []
                    cg_enforced = set()
                    screening_class = "active_exact_highs_direct_fallback"
                    exact_alias_solver_path = "highs_fresh_exact_leave_one_out"
                    fallback_used = True
                    fallback_relaxed_rows = 0
                    fallback_max_retained_constraint_violation = max(
                        0.0, terminal_max_non_omitted - 1.0
                    )
                    fallback_restored_full_objective_relative_difference = None
                    alias_status = alias_result["status"]
                    alias_condition = alias_result["condition"]
            else:
                alias_result = full_result
                alias_attempts = 0
                full_post = full_post_by_outage[omitted_id]
                alias_post = full_post
                screening_class = "inactive_full_optimum_reused"
                alias_status = "reused"
                alias_condition = "optimal_by_convex_slack_theorem"
                cg_iterations = []
                cg_enforced = set()
                terminal_max_non_omitted = None

            source, harmful_target, harmful_relations, harmful_trace = semantic_bundle(
                candidate_ids, omitted_id
            )
            task = TaskContract(
                task_id=f"{CASE}:{load_scale:.4f}:{omitted_id}",
                task_kind="DC_SCOPF",
                source_assets=tuple(candidate_ids),
                target_assets=tuple("target-" + branch_id for branch_id in candidate_ids),
                intervention_type="constraint",
                required_attributes=("asset_type",),
            )
            cert = issue_v2_certificate(
                source,
                harmful_target,
                task_contract=task,
                relations=harmful_relations,
                converter_trace=harmful_trace,
                issuer="pypsa-adapter",
                private_key=key,
                certificate_id="harmful:" + task.task_id,
                transformation_id="harmful:" + task.task_id,
                issued_at="2026-08-06T00:00:00Z",
                nonce="harmful:" + task.task_id,
            )
            solver_calls = []

            def forbidden_solver(_snapshot):
                solver_calls.append(task.task_id)
                raise AssertionError("harmful solver must not start")

            gate = ExecutionGate(
                PCCV2Verifier(trusted_issuers={"pypsa-adapter": key.public_key()})
            ).execute(
                source,
                harmful_target,
                cert,
                requested_task="DC_SCOPF",
                converter_trace=harmful_trace,
                solver=forbidden_solver,
            )
            strict_false_secure = bool(full_post <= 1.0001 and alias_post > 1.0001)
            rows.append({
                "result_schema": RESULT_SCHEMA,
                "protocol_version": PROTOCOL_VERSION,
                "loader_revision": LOADER_REVISION,
                "environment_id": CASE500_ENVIRONMENT_ID,
                "solver_stack": "PyPSA/Clarabel portfolio with exact HiGHS fallback",
                "input_hash": input_hash,
                "network": CASE,
                "state_offset": offset,
                "load_scale": load_scale,
                "loading_rank": f"q{index / max(len(candidates) - 1, 1):.3f}",
                "omitted_candidate": omitted_id,
                "branch_component": omitted[0],
                "branch_id": omitted[1],
                "tap_ratio": float(omitted_row.get("tap_ratio", 1.0)),
                "phase_shift": float(omitted_row.get("phase_shift", 0.0)),
                "candidate_count": len(candidates),
                "pre_contingency_loading_pu": float(pre_loading.loc[omitted]),
                "base_objective": base_result["objective"],
                "full_objective": full_result["objective"],
                "alias_objective": alias_result["objective"],
                "full_load_shed_mw": full_result["load_shed_mw"],
                "alias_load_shed_mw": alias_result["load_shed_mw"],
                "relative_cost_understatement": max(
                    0.0,
                    (full_result["objective"] - alias_result["objective"])
                    / max(abs(full_result["objective"]), 1e-12),
                ),
                "full_post_contingency_max_loading_pu": full_post,
                "alias_post_contingency_max_loading_pu": alias_post,
                "false_secure_dispatch": strict_false_secure,
                "strict_false_secure_dispatch": strict_false_secure,
                "gate_decision": gate.receipt.decision,
                "gate_reasons": ";".join(gate.receipt.reasons),
                "gate_verification_us": gate.receipt.verification_us,
                "gate_solver_status": gate.receipt.solver_status,
                "source_hash": gate.receipt.source_input_hash,
                "target_hash": gate.receipt.target_input_hash,
                "certificate_hash": gate.receipt.certificate_hash,
                "harmful_solver_starts": len(solver_calls),
                "unsafe_result_prevented": bool(strict_false_secure and not solver_calls),
                "full_solver_s": full_result["elapsed_s"],
                "alias_solver_s": alias_result["elapsed_s"] if alias_attempts else 0.0,
                "base_solver_attempts": base_attempts,
                "full_solver_attempts": full_attempts,
                "alias_solver_attempts": alias_attempts,
                "full_solver_status": full_result["status"],
                "full_solver_condition": full_result["condition"],
                "full_solver_engine": full_result["solver"],
                "alias_solver_status": alias_status,
                "alias_solver_condition": alias_condition,
                "alias_solver_engine": alias_result["solver"],
                "alias_solver_settings_profile": alias_result.get(
                    "settings_profile", exact_alias_solver_path
                ),
                "screening_class": screening_class,
                "constraint_generation_iterations": len(cg_iterations),
                "constraint_generation_final_enforced_outages": len(cg_enforced),
                "constraint_generation_added_outages": json.dumps(sorted(
                    set().union(*(set(item["added_outages"]) for item in cg_iterations))
                    if cg_iterations else set()
                )),
                "constraint_generation_terminal_max_non_omitted_loading_pu": (
                    terminal_max_non_omitted
                ),
                "exact_alias_solver_path": exact_alias_solver_path,
                "fallback_used": fallback_used,
                "fallback_relaxed_security_rows": fallback_relaxed_rows,
                "fallback_max_retained_constraint_violation": (
                    fallback_max_retained_constraint_violation
                ),
                "fallback_restored_full_objective_relative_difference": (
                    fallback_restored_full_objective_relative_difference
                ),
                "post_check_method": (
                    "explicit_remove_and_lpf"
                    if omitted_id in active
                    else "pypsa_bodf_security_equation"
                ),
                "screening_max_abs_dual": activity[omitted_id]["max_abs_dual"],
                "screening_min_abs_slack": activity[omitted_id]["min_abs_slack"],
            })
            write_checkpoint(checkpoint_path, rows, failures, metadata)
        except Exception as exc:
            failure = {
                "network": CASE,
                "state_offset": offset,
                "load_scale": load_scale,
                "omitted_candidate": omitted_id,
                "included_in_denominator": True,
                "error": f"{type(exc).__name__}: {str(exc)[:500]}",
            }
            failures.append(failure)
            write_checkpoint(checkpoint_path, rows, failures, metadata)
            raise

    release_model(full_network)
    fields = list(rows[0])
    with results_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    strict_rows = [row for row in rows if row["strict_false_secure_dispatch"]]
    terminal_constraint_checks = [
        float(row["constraint_generation_terminal_max_non_omitted_loading_pu"])
        for row in rows
        if row["screening_class"] in {
            "active_exact_clarabel_portfolio_top1",
            "active_exact_highs_direct_fallback",
        }
    ]
    summary = {
        "experiment": "pcc_v2_native_pypsa_clarabel_dc_scopf_case500",
        "result_schema": RESULT_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "loader_revision": LOADER_REVISION,
        "environment_id": CASE500_ENVIRONMENT_ID,
        "full_solver": "Clarabel 0.11.1 tight settings portfolio",
        "restricted_master_solver": "Clarabel 0.11.1 settings portfolio with exact HiGHS fallback",
        "screening_protocol": "protocols/dc_scopf_case500_tight_dual_v11.yaml",
        "screening_exact_convex_reduction": True,
        "cases_requested": [CASE],
        "states_per_case_requested": 1,
        "state_offset": offset,
        "candidate_mode": "all",
        "rows": len(rows),
        "requested_state_denominator": 1,
        "completed_state_denominator": int(len(rows) == len(candidates) and not failures),
        "failed_states": int(bool(failures) or len(rows) != len(candidates)),
        "candidate_count": len(candidates),
        "active_exact_constraint_generation": sum(row["screening_class"] == "active_exact_clarabel_portfolio_top1" for row in rows),
        "active_exact_highs_direct_fallback": sum(
            row["screening_class"] == "active_exact_highs_direct_fallback"
            for row in rows
        ),
        "inactive_optimum_reused": sum(row["screening_class"] == "inactive_full_optimum_reused" for row in rows),
        "false_secure_dispatches": len(strict_rows),
        "strict_false_secure_dispatches": len(strict_rows),
        "harmful_solver_starts": sum(int(row["harmful_solver_starts"]) for row in rows),
        "unsafe_results_prevented": sum(bool(row["unsafe_result_prevented"]) for row in rows),
        "prevention_rate_among_false_secure": (
            sum(bool(row["unsafe_result_prevented"]) for row in rows) / len(strict_rows)
            if strict_rows else None
        ),
        "terminal_non_omitted_loading_max_pu": (
            max(terminal_constraint_checks) if terminal_constraint_checks else None
        ),
        "terminal_all_non_omitted_constraints_feasible": bool(
            terminal_constraint_checks
            and all(value <= SEPARATION_TOLERANCE for value in terminal_constraint_checks)
        ),
        "failures": failures,
        "scope": "all graph-nonislanding case500 candidates with exact convex active-constraint screening",
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-offset", type=int, required=True, choices=range(10))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run_state(args.state_offset, args.force)


if __name__ == "__main__":
    main()
