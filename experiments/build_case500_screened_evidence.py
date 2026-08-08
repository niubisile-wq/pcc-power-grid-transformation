"""Build normalized EvidenceRow files for screened case500 result CSVs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "cgmes") not in sys.path:
    sys.path.insert(0, str(ROOT / "cgmes"))

from validation.evidence_schema import EvidenceRow  # noqa: E402


INPUT = ROOT / "outputs" / "pcc_v2_dc_scopf_case500_clarabel_portfolio"
SEPARATION_TOLERANCE = 1.000001


def as_bool(value: str) -> bool:
    return value.lower() == "true"


def main() -> None:
    reports = []
    for path in sorted(INPUT.glob("dc_scopf_gate_all_case500_offset*_1states_v11_results.csv")):
        with path.open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        evidence = []
        for row in rows:
            evidence.append(
                EvidenceRow(
                    experiment_id="pcc-v2-case500-clarabel-portfolio-exact-dc-scopf-v11",
                    scenario_id=(
                        f"{row['network']}:{float(row['load_scale']):.4f}:"
                        f"{row['omitted_candidate']}"
                    ),
                    network=row["network"],
                    data_split="public_pglib_operational_confirmatory",
                    environment=row["environment_id"],
                    solver=row["solver_stack"],
                    task_kind="DC_SCOPF",
                    state_id=f"load-{float(row['load_scale']):.4f}",
                    transform_class="harmful",
                    attack_family="contingency_candidate_omission",
                    baseline="pcc_v2",
                    decision=row["gate_decision"],
                    solver_status=row["gate_solver_status"],
                    solver_started=int(row["harmful_solver_starts"]) > 0,
                    source_hash=row["source_hash"],
                    target_hash=row["target_hash"],
                    certificate_hash=row["certificate_hash"],
                    consequence_observed=as_bool(row["strict_false_secure_dispatch"]),
                    unsafe_result_prevented=as_bool(row["unsafe_result_prevented"]),
                    reasons=tuple(row["gate_reasons"].split(";")),
                    verification_us=float(row["gate_verification_us"]),
                    metrics={
                        "candidate_count": int(row["candidate_count"]),
                        "full_post_contingency_max_loading_pu": float(row["full_post_contingency_max_loading_pu"]),
                        "alias_post_contingency_max_loading_pu": float(row["alias_post_contingency_max_loading_pu"]),
                        "relative_cost_understatement": float(row["relative_cost_understatement"]),
                        "full_load_shed_mw": float(row["full_load_shed_mw"]),
                        "alias_load_shed_mw": float(row["alias_load_shed_mw"]),
                        "screening_max_abs_dual": float(row["screening_max_abs_dual"]),
                        "screening_min_abs_slack": float(row["screening_min_abs_slack"]),
                        "constraint_generation_terminal_max_non_omitted_loading_pu": (
                            float(row["constraint_generation_terminal_max_non_omitted_loading_pu"])
                            if row["constraint_generation_terminal_max_non_omitted_loading_pu"]
                            else None
                        ),
                    },
                ).to_dict()
            )
        output = path.with_name(path.name.replace("_results.csv", "_evidence.csv"))
        if evidence:
            with output.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(evidence[0]))
                writer.writeheader()
                writer.writerows(evidence)
        reports.append({"results": path.name, "evidence": output.name, "rows": len(evidence)})
        active_terminal = [
            float(row["constraint_generation_terminal_max_non_omitted_loading_pu"])
            for row in rows
            if row["screening_class"].startswith("active_exact_")
            and row["constraint_generation_terminal_max_non_omitted_loading_pu"]
        ]
        summary_path = path.with_name(path.name.replace("_results.csv", "_summary.json"))
        if summary_path.is_file():
            state_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            state_summary["terminal_non_omitted_loading_max_pu"] = (
                max(active_terminal) if active_terminal else None
            )
            state_summary["terminal_all_non_omitted_constraints_feasible"] = bool(
                active_terminal
                and all(value <= SEPARATION_TOLERANCE for value in active_terminal)
            )
            summary_path.write_text(
                json.dumps(state_summary, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            reports[-1]["terminal_all_non_omitted_constraints_feasible"] = state_summary[
                "terminal_all_non_omitted_constraints_feasible"
            ]
    summary = {
        "protocol": "case500_screened_evidence_builder_v3",
        "files": reports,
        "total_rows": sum(item["rows"] for item in reports),
        "ready": bool(
            len(reports) == 10
            and all(
                item["rows"] == 582
                and item.get("terminal_all_non_omitted_constraints_feasible") is True
                for item in reports
            )
        ),
    }
    (INPUT / "evidence_build_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
