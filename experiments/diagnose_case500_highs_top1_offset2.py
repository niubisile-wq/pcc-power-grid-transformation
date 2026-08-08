"""Test exact top-one constraint generation with HiGHS on case500 offset 2."""

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
from run_pcc_v2_dc_scopf_case500_screened import (  # noqa: E402
    CASE_PATH,
    SEPARATION_TOLERANCE,
    release_model,
    strict_solve,
)
from run_pcc_v2_dc_scopf_gate import (  # noqa: E402
    LOAD_SCALES,
    load_pglib,
    non_islanding_branches,
)


OUTPUT = ROOT / "outputs" / "case500_highs_top1_offset2_diagnostic"
OMITTED_ID = "Line:branch-00407"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    base = load_pglib(CASE_PATH, float(LOAD_SCALES[2]))
    candidates = non_islanding_branches(base)
    candidate_by_id = {
        f"{component}:{name}": (component, name) for component, name in candidates
    }
    full, full_result, _ = strict_solve(
        base, candidates, "diagnostic:highs:case500:offset2:full", keep_model=True
    )
    activity = active_security_outages(full)
    active_ids = {key for key, item in activity.items() if item["active"]}
    enforced_ids = active_ids - {OMITTED_ID}
    release_model(full)
    iterations = []
    terminal = None
    for iteration in range(1, 21):
        enforced = [candidate_by_id[key] for key in sorted(enforced_ids)]
        network, result, attempts = strict_solve(
            base,
            enforced,
            f"diagnostic:highs:case500:offset2:{OMITTED_ID}:master{iteration}",
        )
        post = bodf_post_contingency_loadings(network, candidates)
        eligible = {key: value for key, value in post.items() if key != OMITTED_ID}
        violations = {
            key: value
            for key, value in eligible.items()
            if value > SEPARATION_TOLERANCE
        }
        new_violations = {
            key: value for key, value in violations.items() if key not in enforced_ids
        }
        worst_id, worst_value = max(eligible.items(), key=lambda item: item[1])
        record = {
            "iteration": iteration,
            "enforced_outages": len(enforced_ids),
            "objective": result["objective"],
            "attempts": attempts,
            "violation_count": len(violations),
            "new_violation_count": len(new_violations),
            "worst_outage": worst_id,
            "worst_loading_pu": worst_value,
            "added_outage": None,
        }
        if not violations:
            terminal = record
            iterations.append(record)
            print(json.dumps(record), flush=True)
            break
        if not new_violations:
            raise RuntimeError("highs_top1_constraint_generation_stalled")
        added_id = max(new_violations, key=lambda key: (post[key], key))
        record["added_outage"] = added_id
        iterations.append(record)
        print(json.dumps(record), flush=True)
        enforced_ids.add(added_id)
    if terminal is None:
        raise RuntimeError("highs_top1_constraint_generation_iteration_limit")
    summary = {
        "diagnostic": "case500_offset2_highs_top1_exact_constraint_generation",
        "load_scale": float(LOAD_SCALES[2]),
        "omitted_candidate": OMITTED_ID,
        "candidate_count": len(candidates),
        "initial_active_count": len(active_ids),
        "full_objective": full_result["objective"],
        "terminal_all_non_omitted_constraints_feasible": True,
        "separation_tolerance": SEPARATION_TOLERANCE,
        "iterations": iterations,
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
