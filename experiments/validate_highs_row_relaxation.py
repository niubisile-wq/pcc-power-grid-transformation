"""Compare warm-start row relaxation with direct leave-one-out SCOPF."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "cgmes", ROOT / "experiments"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dc_scopf_active_screening import active_security_outages  # noqa: E402
from highs_constraint_relaxation import (  # noqa: E402
    relax_outage_and_solve,
    restore_rows_and_solve,
)
from run_pcc_v2_dc_scopf_gate import (  # noqa: E402
    CASE_FILES,
    branch_index,
    load_pglib,
    non_islanding_branches,
)


OUTPUT = ROOT / "outputs" / "highs_row_relaxation_validation"


def main() -> None:
    case = "case39"
    path = ROOT / "downloads" / "pglib-opf-v23.07" / CASE_FILES[case]
    base = load_pglib(path, 0.9)
    candidates = non_islanding_branches(base)
    full = load_pglib(path, 0.9)
    status, condition = full.optimize.optimize_security_constrained(
        branch_outages=branch_index(candidates),
        solver_name="highs",
        log_to_console=False,
        time_limit=300.0,
    )
    if (status, condition) != ("ok", "optimal"):
        raise RuntimeError("full_model_not_optimal")
    full_objective = float(full.objective)
    activity = active_security_outages(full)
    active = [key for key, item in activity.items() if item["active"]]
    if not active:
        raise RuntimeError("no_active_outage_for_validation")
    omitted_id = active[0]
    omitted = tuple(omitted_id.split(":", 1))
    metadata, handle = relax_outage_and_solve(full, omitted)
    relaxed_dispatch = full.generators_t.p.loc["now"].copy()
    direct = load_pglib(path, 0.9)
    retained = [candidate for candidate in candidates if candidate != omitted]
    direct_status, direct_condition = direct.optimize.optimize_security_constrained(
        branch_outages=branch_index(retained),
        solver_name="highs",
        log_to_console=False,
        time_limit=300.0,
    )
    if (direct_status, direct_condition) != ("ok", "optimal"):
        raise RuntimeError("direct_alias_not_optimal")
    objective_relative_difference = abs(full.objective - direct.objective) / max(
        abs(direct.objective), 1e-12
    )
    dispatch_max_absolute_difference = float(
        (relaxed_dispatch - direct.generators_t.p.loc["now"]).abs().max()
    )
    restored = restore_rows_and_solve(full, handle)
    restored_objective_relative_difference = abs(full.objective - full_objective) / max(
        abs(full_objective), 1e-12
    )
    summary = {
        "protocol": "highs_warm_start_row_relaxation_validation_v1",
        "network": case,
        "load_scale": 0.9,
        "omitted_candidate": omitted_id,
        "relaxed_rows": metadata["relaxed_rows"],
        "direct_objective": float(direct.objective),
        "relaxed_objective": metadata["objective"],
        "objective_relative_difference": objective_relative_difference,
        "dispatch_max_absolute_difference_mw": dispatch_max_absolute_difference,
        "max_retained_constraint_violation": metadata["max_retained_constraint_violation"],
        "restored_objective_relative_difference": restored_objective_relative_difference,
        "relaxed_solve_s": metadata["elapsed_s"],
        "restored_solve_s": restored["elapsed_s"],
        "ready": bool(
            objective_relative_difference <= 1e-8
            and dispatch_max_absolute_difference <= 1e-4
            and metadata["max_retained_constraint_violation"] <= 1e-5
            and restored_objective_relative_difference <= 1e-8
        ),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
