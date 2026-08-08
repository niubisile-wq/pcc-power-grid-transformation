"""Diagnose the retained case500/offset0 HiGHS internal solver error.

This script writes to a separate diagnostic directory and never modifies the
confirmatory result files.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "cgmes", ROOT / "experiments"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_pcc_v2_dc_scopf_gate import (  # noqa: E402
    branch_index,
    load_pglib,
    non_islanding_branches,
)


def main() -> None:
    output = ROOT / "outputs" / "case500_scopf_diagnostic"
    output.mkdir(parents=True, exist_ok=True)
    case = ROOT / "downloads" / "pglib-opf-v23.07" / "pglib_opf_case500_goc.m"
    network = load_pglib(case, 0.9)
    network.determine_network_topology()
    candidates = non_islanding_branches(network)

    bodf = []
    selected_finite = True
    for sub_network in network.sub_networks.obj:
        branches = sub_network.branches_i()
        sub_network.calculate_BODF()
        matrix = np.asarray(sub_network.BODF)
        selected = branches.get_indexer(branches.intersection(branch_index(candidates)))
        selected = selected[selected >= 0]
        selected_finite = selected_finite and bool(np.isfinite(matrix[:, selected]).all())
        bodf.append({
            "sub_network": str(sub_network.name),
            "branches": len(branches),
            "nonfinite_full_matrix": int((~np.isfinite(matrix)).sum()),
            "selected_columns": len(selected),
            "selected_columns_all_finite": bool(np.isfinite(matrix[:, selected]).all()),
        })

    started = time.perf_counter()
    status = condition = legacy_status = None
    error = None
    try:
        status, condition = network.optimize.optimize_security_constrained(
            branch_outages=branch_index(candidates),
            solver_name="highs",
            log_to_console=False,
            log_fn=output / "highs_case500_offset0.log",
            time_limit=300.0,
        )
        solver_model = getattr(network.model, "solver_model", None)
        if solver_model is not None:
            legacy_status = solver_model.modelStatusToString(solver_model.getModelStatus())
    except Exception as exc:  # diagnostic must preserve native exception detail
        error = f"{type(exc).__name__}: {exc}"
    summary = {
        "protocol": "case500_scopf_internal_error_diagnostic_v1",
        "confirmatory_files_modified": False,
        "network": "case500",
        "state_offset": 0,
        "load_scale": 0.9,
        "buses": len(network.buses),
        "passive_branches": len(network.lines) + len(network.transformers),
        "candidate_count": len(candidates),
        "selected_bodf_columns_all_finite": selected_finite,
        "bodf": bodf,
        "status": status,
        "condition": condition,
        "highs_model_status": legacy_status,
        "error": error,
        "elapsed_s": time.perf_counter() - started,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
