"""Test deterministic Clarabel settings on offset-1 branch-00081 master 2."""

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

from dc_scopf_active_screening import create_security_constrained_model  # noqa: E402
from linopy_clarabel import solve_linopy_with_clarabel  # noqa: E402
from run_pcc_v2_dc_scopf_case500_screened import CASE_PATH, release_model  # noqa: E402
from run_pcc_v2_dc_scopf_gate import LOAD_SCALES, load_pglib  # noqa: E402


OUTPUT = ROOT / "outputs" / "case500_clarabel_portfolio_offset1_diagnostic"
ENFORCED = [
    ("Line", "branch-00029"),
    ("Line", "branch-00034"),
    ("Line", "branch-00407"),
]
VARIANTS = [
    ("default", {}),
    (
        "strong_v7",
        {
            "static_regularization_constant": 1e-7,
            "dynamic_regularization_delta": 1e-6,
        },
    ),
    (
        "stronger_1e6",
        {
            "static_regularization_constant": 1e-6,
            "dynamic_regularization_delta": 1e-5,
        },
    ),
    (
        "stronger_1e5",
        {
            "static_regularization_constant": 1e-5,
            "dynamic_regularization_delta": 1e-4,
        },
    ),
]


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    base = load_pglib(CASE_PATH, float(LOAD_SCALES[1]))
    results = []
    for name, settings in VARIANTS:
        network = copy.deepcopy(base)
        started = time.perf_counter()
        try:
            create_security_constrained_model(network, ENFORCED)
            metadata = solve_linopy_with_clarabel(
                network, settings_overrides=settings
            )
            result = {
                "variant": name,
                "settings_overrides": settings,
                "solved": True,
                "metadata": metadata,
                "wall_s": time.perf_counter() - started,
            }
        except Exception as exc:
            result = {
                "variant": name,
                "settings_overrides": settings,
                "solved": False,
                "error": f"{type(exc).__name__}: {exc}",
                "wall_s": time.perf_counter() - started,
            }
        results.append(result)
        print(json.dumps(result), flush=True)
        release_model(network)
    summary = {
        "diagnostic": "case500_offset1_branch00081_master2_clarabel_settings_portfolio",
        "load_scale": float(LOAD_SCALES[1]),
        "omitted_candidate": "Line:branch-00081",
        "enforced_outages": [f"{component}:{name}" for component, name in ENFORCED],
        "results": results,
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
