"""Diagnose top-one exact constraint generation on the hardest case500 alias."""

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
    strict_solve_clarabel,
)
from run_pcc_v2_dc_scopf_gate import load_pglib, non_islanding_branches  # noqa: E402


OUTPUT = ROOT / "outputs" / "case500_clarabel_top1_diagnostic"
OMITTED_ID = "Line:branch-00407"
MAX_ITERATIONS = 100


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    base = load_pglib(CASE_PATH, 0.9)
    candidates = non_islanding_branches(base)
    candidate_by_id = {
        f"{component}:{name}": (component, name) for component, name in candidates
    }
    full, full_result, _ = strict_solve(
        base, candidates, "diagnostic:case500:offset0:full", keep_model=True
    )
    activity = active_security_outages(full)
    active_ids = {key for key, item in activity.items() if item["active"]}
    enforced_ids = active_ids - {OMITTED_ID}
    release_model(full)

    iterations = []
    terminal_network = None
    terminal_result = None
    for iteration in range(1, MAX_ITERATIONS + 1):
        enforced = [candidate_by_id[key] for key in sorted(enforced_ids)]
        network, result, attempts = strict_solve_clarabel(
            base, enforced, f"diagnostic:case500:offset0:{OMITTED_ID}:master{iteration}"
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
        }
        iterations.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
        if not violations:
            terminal_network = network
            terminal_result = result
            break
        if not new_violations:
            release_model(network)
            raise RuntimeError("top1_constraint_generation_stalled")
        added_id = max(new_violations.items(), key=lambda item: item[1])[0]
        record["added_outage"] = added_id
        enforced_ids.add(added_id)
        release_model(network)

    if terminal_network is None or terminal_result is None:
        raise RuntimeError("top1_constraint_generation_iteration_limit")
    summary = {
        "diagnostic": "case500_clarabel_top1_exact_constraint_generation",
        "load_scale": 0.9,
        "omitted_candidate": OMITTED_ID,
        "candidate_count": len(candidates),
        "initial_active_count": len(active_ids),
        "full_objective": full_result["objective"],
        "terminal_objective": terminal_result["objective"],
        "terminal_enforced_outages": len(enforced_ids),
        "terminal_all_non_omitted_constraints_feasible": True,
        "separation_tolerance": SEPARATION_TOLERANCE,
        "iterations": iterations,
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    release_model(terminal_network)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
