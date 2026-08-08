"""Adjudicate Clarabel numerical settings on the failed offset-2 master."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "cgmes", ROOT / "experiments"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dc_scopf_active_screening import (  # noqa: E402
    active_security_outages,
    create_security_constrained_model,
)
from linopy_clarabel import solve_linopy_with_clarabel  # noqa: E402
from run_pcc_v2_dc_scopf_case500_screened import CASE_PATH, release_model, strict_solve  # noqa: E402
from run_pcc_v2_dc_scopf_gate import LOAD_SCALES, load_pglib, non_islanding_branches  # noqa: E402


OUTPUT = ROOT / "outputs" / "case500_clarabel_settings_offset2_diagnostic"
OMITTED_ID = "Line:branch-00407"
ADDED_ID = "Line:branch-00492"
VARIANTS = [
    ("default", {}),
    ("drop_explicit_zeros", {"input_sparse_dropzeros": True}),
    ("presolve_disabled", {"presolve_enable": False}),
    ("equilibration_disabled", {"equilibrate_enable": False}),
    (
        "stronger_regularization",
        {
            "static_regularization_constant": 1e-7,
            "dynamic_regularization_delta": 1e-6,
        },
    ),
]


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    base = load_pglib(CASE_PATH, float(LOAD_SCALES[2]))
    candidates = non_islanding_branches(base)
    candidate_by_id = {
        f"{component}:{name}": (component, name) for component, name in candidates
    }
    full, full_result, _ = strict_solve(
        base, candidates, "diagnostic:clarabel-settings:case500:offset2:full", keep_model=True
    )
    activity = active_security_outages(full)
    active_ids = {key for key, item in activity.items() if item["active"]}
    enforced_ids = (active_ids - {OMITTED_ID}) | {ADDED_ID}
    release_model(full)
    enforced = [candidate_by_id[key] for key in sorted(enforced_ids)]
    results = []
    for name, overrides in VARIANTS:
        network = copy.deepcopy(base)
        started = time.perf_counter()
        try:
            create_security_constrained_model(network, enforced)
            metadata = solve_linopy_with_clarabel(
                network, settings_overrides=overrides
            )
            result = {
                "variant": name,
                "settings_overrides": overrides,
                "solved": True,
                "metadata": metadata,
                "wall_s": time.perf_counter() - started,
            }
        except Exception as exc:
            result = {
                "variant": name,
                "settings_overrides": overrides,
                "solved": False,
                "error": f"{type(exc).__name__}: {exc}",
                "wall_s": time.perf_counter() - started,
            }
        results.append(result)
        print(json.dumps(result), flush=True)
        release_model(network)
    summary = {
        "diagnostic": "case500_offset2_clarabel_failed_master_settings",
        "load_scale": float(LOAD_SCALES[2]),
        "omitted_candidate": OMITTED_ID,
        "added_candidate": ADDED_ID,
        "active_ids": sorted(active_ids),
        "enforced_ids": sorted(enforced_ids),
        "full_objective": full_result["objective"],
        "results": results,
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
