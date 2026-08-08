"""Validate exact warm-start row relaxation on failed case500 offset 2."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "cgmes", ROOT / "experiments"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dc_scopf_active_screening import (  # noqa: E402
    active_security_outages,
    bodf_post_contingency_loadings,
)
from highs_constraint_relaxation import (  # noqa: E402
    relax_outage_and_solve,
    restore_rows_and_solve,
)
from run_pcc_v2_dc_scopf_case500_screened import CASE_PATH, strict_solve  # noqa: E402
from run_pcc_v2_dc_scopf_gate import LOAD_SCALES, load_pglib, non_islanding_branches  # noqa: E402


OUTPUT = ROOT / "outputs" / "case500_highs_row_relaxation_offset2_diagnostic"
OMITTED = ("Line", "branch-00407")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    base = load_pglib(CASE_PATH, float(LOAD_SCALES[2]))
    candidates = non_islanding_branches(base)
    full, full_result, _ = strict_solve(
        base,
        candidates,
        "diagnostic:row-relaxation:case500:offset2:full",
        keep_model=True,
    )
    activity = active_security_outages(full)
    omitted_id = f"{OMITTED[0]}:{OMITTED[1]}"
    if not activity[omitted_id]["active"]:
        raise RuntimeError("diagnostic_omitted_candidate_not_active")
    metadata, handle = relax_outage_and_solve(full, OMITTED)
    post = bodf_post_contingency_loadings(full, candidates)
    max_non_omitted = max(
        value for key, value in post.items() if key != omitted_id
    )
    omitted_loading = post[omitted_id]
    restored = restore_rows_and_solve(full, handle)
    restored_relative_difference = abs(
        restored["objective"] - full_result["objective"]
    ) / max(abs(full_result["objective"]), 1e-12)
    summary = {
        "diagnostic": "case500_offset2_highs_warm_start_row_relaxation",
        "load_scale": float(LOAD_SCALES[2]),
        "omitted_candidate": omitted_id,
        "candidate_count": len(candidates),
        "full_objective": full_result["objective"],
        "alias_objective": metadata["objective"],
        "relaxed_rows": metadata["relaxed_rows"],
        "alias_solve_s": metadata["elapsed_s"],
        "max_retained_constraint_violation": metadata[
            "max_retained_constraint_violation"
        ],
        "terminal_max_non_omitted_loading_pu": max_non_omitted,
        "omitted_post_contingency_loading_pu": omitted_loading,
        "restored_full_objective_relative_difference": restored_relative_difference,
        "terminal_all_non_omitted_constraints_feasible": bool(
            max_non_omitted <= 1.000001
        ),
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
