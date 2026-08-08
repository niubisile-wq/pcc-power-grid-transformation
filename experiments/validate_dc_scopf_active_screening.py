"""Validate exact active-outage screening against completed exhaustive states."""

from __future__ import annotations

import argparse
import csv
import gc
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "cgmes", ROOT / "experiments"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dc_scopf_active_screening import active_security_outages  # noqa: E402
from run_pcc_v2_dc_scopf_gate import (  # noqa: E402
    CASE_FILES,
    LOAD_SCALES,
    branch_index,
    load_pglib,
    non_islanding_branches,
)


INPUT = ROOT / "outputs" / "pcc_v2_dc_scopf_gate"
OUTPUT = ROOT / "outputs" / "dc_scopf_active_screening_validation"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", nargs="+", choices=CASE_FILES)
    args = parser.parse_args()
    requested = set(args.cases or CASE_FILES)
    states = []
    for path in sorted(INPUT.glob("dc_scopf_gate_all_*_summary.json")):
        summary = json.loads(path.read_text(encoding="utf-8"))
        cases = summary.get("cases_requested", [])
        if (
            len(cases) != 1
            or cases[0] not in requested
            or summary.get("loader_revision") != "pglib-pypsa-transformer-explicit-v2"
            or summary.get("result_schema") != "pcc-v2-dc-scopf-result-v2"
            or summary.get("candidate_mode") != "all"
            or summary.get("failed_states") != 0
            or summary.get("completed_state_denominator") != 1
        ):
            continue
        csv_path = path.with_name(path.name.replace("_summary.json", "_results.csv"))
        if csv_path.exists():
            states.append((cases[0], int(summary["state_offset"]), csv_path))

    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = []
    for case, offset, csv_path in states:
        rows = read_rows(csv_path)
        network = load_pglib(
            ROOT / "downloads" / "pglib-opf-v23.07" / CASE_FILES[case],
            float(LOAD_SCALES[offset]),
        )
        candidates = non_islanding_branches(network)
        status, condition = network.optimize.optimize_security_constrained(
            branch_outages=branch_index(candidates),
            solver_name="highs",
            log_to_console=False,
            time_limit=300.0,
        )
        if status != "ok" or condition != "optimal":
            raise RuntimeError(f"full_scopf_not_optimal:{case}:{offset}:{status}:{condition}")
        activity = active_security_outages(network)
        active = {key for key, value in activity.items() if value["active"]}
        strict = {
            row["omitted_candidate"]
            for row in rows
            if float(row["full_objective"]) > 1e-9
            and float(row["alias_objective"]) > 1e-9
            and float(row["full_post_contingency_max_loading_pu"]) <= 1.0001
            and float(row["alias_post_contingency_max_loading_pu"]) > 1.0001
        }
        legacy = {row["omitted_candidate"] for row in rows if row["false_secure_dispatch"] == "True"}
        result = {
            "network": case,
            "state_offset": offset,
            "load_scale": float(LOAD_SCALES[offset]),
            "candidate_count": len(candidates),
            "active_count": len(active),
            "strict_false_secure_count": len(strict),
            "legacy_alias_overlimit_count": len(legacy),
            "strict_false_secure_missing_from_active": sorted(strict - active),
            "strict_recall": len(strict & active) / len(strict) if strict else 1.0,
            "active_candidates": sorted(active),
        }
        results.append(result)
        (OUTPUT / "checkpoint.json").write_text(
            json.dumps({"states": results}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        network.model.solver_model = None
        del network.model
        del network
        gc.collect()

    strict_total = sum(item["strict_false_secure_count"] for item in results)
    missing = sum(len(item["strict_false_secure_missing_from_active"]) for item in results)
    summary = {
        "protocol": "dc_scopf_active_constraint_screening_validation_v1",
        "parent_amendment": "protocols/dc_scopf_case500_screening_amendment_v2.yaml",
        "states_validated": len(results),
        "networks_validated": sorted({item["network"] for item in results}),
        "strict_false_secure_events": strict_total,
        "strict_false_secure_events_recovered": strict_total - missing,
        "strict_false_secure_recall": (strict_total - missing) / strict_total if strict_total else 1.0,
        "state_results": results,
        "ready": bool(
            len(results) == 10 * len(requested)
            and {item["network"] for item in results} == requested
            and missing == 0
        ),
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
