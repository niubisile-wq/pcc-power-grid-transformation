"""Validate the strict Clarabel Linopy adapter against PyPSA/HiGHS SCLOPF."""

from __future__ import annotations

import gc
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "cgmes", ROOT / "experiments"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dc_scopf_active_screening import create_security_constrained_model  # noqa: E402
from linopy_clarabel import solve_linopy_with_clarabel  # noqa: E402
from run_pcc_v2_dc_scopf_gate import (  # noqa: E402
    CASE_FILES,
    LOAD_SCALES,
    branch_index,
    load_pglib,
    non_islanding_branches,
)


OUTPUT = ROOT / "outputs" / "clarabel_highs_scopf_validation"
PAIRS = [
    (case, offset)
    for case in ("case39", "case73", "case118")
    for offset in (0, 5, 9)
] + [("case300", 0)]
CLARABEL_SETTINGS_PORTFOLIO = [
    ("default", {}),
    (
        "strong_regularization",
        {
            "static_regularization_constant": 1e-7,
            "dynamic_regularization_delta": 1e-6,
        },
    ),
]


def release(network) -> None:
    if getattr(network, "model", None) is not None:
        network.model.solver_model = None
        del network.model
    del network
    gc.collect()


def main() -> None:
    results = []
    for case, offset in PAIRS:
        path = ROOT / "downloads" / "pglib-opf-v23.07" / CASE_FILES[case]
        scale = float(LOAD_SCALES[offset])
        highs = load_pglib(path, scale)
        candidates = non_islanding_branches(highs)
        status, condition = highs.optimize.optimize_security_constrained(
            branch_outages=branch_index(candidates),
            solver_name="highs",
            log_to_console=False,
            time_limit=300.0,
        )
        if (status, condition) != ("ok", "optimal"):
            raise RuntimeError(f"highs_not_optimal:{case}:{offset}:{status}:{condition}")
        clarabel = None
        metadata = None
        clarabel_errors = []
        clarabel_attempts = 0
        clarabel_settings_profile = None
        for attempt, (settings_profile, settings) in enumerate(
            CLARABEL_SETTINGS_PORTFOLIO, start=1
        ):
            candidate_network = load_pglib(path, scale)
            try:
                create_security_constrained_model(candidate_network, candidates)
                metadata = solve_linopy_with_clarabel(
                    candidate_network, settings_overrides=settings
                )
                clarabel = candidate_network
                clarabel_attempts = attempt
                clarabel_settings_profile = settings_profile
                break
            except Exception as exc:
                clarabel_errors.append({
                    "settings_profile": settings_profile,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                release(candidate_network)
        if clarabel is None or metadata is None:
            raise RuntimeError(
                f"clarabel_settings_portfolio_failed:{case}:{offset}:"
                + json.dumps(clarabel_errors)
            )
        highs_dispatch = highs.generators_t.p.loc["now"]
        clarabel_dispatch = clarabel.generators_t.p.loc["now"]
        objective_relative_difference = abs(clarabel.objective - highs.objective) / max(
            abs(highs.objective), 1e-12
        )
        dispatch_absolute_difference = float(
            (clarabel_dispatch - highs_dispatch).abs().max()
        )
        aggregate_generation_absolute_difference = abs(
            float(clarabel_dispatch.sum()) - float(highs_dispatch.sum())
        )
        highs_load_shed = float(highs_dispatch.filter(like="shed-").clip(lower=0.0).sum())
        clarabel_load_shed = float(
            clarabel_dispatch.filter(like="shed-").clip(lower=0.0).sum()
        )
        aggregate_load_shed_absolute_difference = abs(
            clarabel_load_shed - highs_load_shed
        )
        objective_feasibility_equivalent = bool(
            objective_relative_difference <= 1e-6
            and metadata["max_constraint_violation"] <= 1e-5
            and aggregate_generation_absolute_difference <= 1e-4
            and aggregate_load_shed_absolute_difference <= 1e-4
        )
        results.append({
            "network": case,
            "state_offset": offset,
            "load_scale": scale,
            "candidate_count": len(candidates),
            "highs_objective": float(highs.objective),
            "clarabel_objective": float(clarabel.objective),
            "objective_relative_difference": objective_relative_difference,
            "maximum_dispatch_absolute_difference_mw": dispatch_absolute_difference,
            "aggregate_generation_absolute_difference_mw": aggregate_generation_absolute_difference,
            "highs_load_shed_mw": highs_load_shed,
            "clarabel_load_shed_mw": clarabel_load_shed,
            "aggregate_load_shed_absolute_difference_mw": aggregate_load_shed_absolute_difference,
            "clarabel_elapsed_s": metadata["elapsed_s"],
            "clarabel_iterations": metadata["iterations"],
            "clarabel_attempts": clarabel_attempts,
            "clarabel_settings_profile": clarabel_settings_profile,
            "clarabel_prior_errors": clarabel_errors,
            "clarabel_max_constraint_violation": metadata["max_constraint_violation"],
            "component_dispatch_identity_within_1e_4_mw": bool(
                dispatch_absolute_difference <= 1e-4
            ),
            "objective_feasibility_equivalent": objective_feasibility_equivalent,
            "within_tolerance": objective_feasibility_equivalent,
        })
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / "checkpoint.json").write_text(
            json.dumps({"pairs": results}, indent=2) + "\n", encoding="utf-8"
        )
        release(highs)
        release(clarabel)
    summary = {
        "protocol": "clarabel_portfolio_vs_highs_scopf_optimal_face_validation_v3",
        "pairs": len(results),
        "networks": sorted({item["network"] for item in results}),
        "maximum_objective_relative_difference": max(
            item["objective_relative_difference"] for item in results
        ),
        "maximum_dispatch_absolute_difference_mw": max(
            item["maximum_dispatch_absolute_difference_mw"] for item in results
        ),
        "maximum_aggregate_generation_absolute_difference_mw": max(
            item["aggregate_generation_absolute_difference_mw"] for item in results
        ),
        "maximum_aggregate_load_shed_absolute_difference_mw": max(
            item["aggregate_load_shed_absolute_difference_mw"] for item in results
        ),
        "maximum_clarabel_constraint_violation": max(
            item["clarabel_max_constraint_violation"] for item in results
        ),
        "results": results,
        "objective_feasibility_equivalent_pairs": sum(
            item["objective_feasibility_equivalent"] for item in results
        ),
        "component_dispatch_identity_pairs": sum(
            item["component_dispatch_identity_within_1e_4_mw"] for item in results
        ),
        "component_dispatch_difference_interpretation": (
            "descriptive optimal-face diagnostic; not required for convex optimum equivalence"
        ),
        "ready": bool(
            len(results) == 10
            and all(item["objective_feasibility_equivalent"] for item in results)
        ),
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
