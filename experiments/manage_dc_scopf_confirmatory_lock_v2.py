from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_epsr_evidence_dashboard import dc_confirmatory_gate


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "pcc_v2_dc_scopf_gate"
CASE500_OUTPUT = ROOT / "outputs" / "pcc_v2_dc_scopf_case500_clarabel_portfolio"
LOCK = ROOT / "protocols" / "dc_scopf_confirmatory_lock_v2.json"
CASES = {
    "case39": "pglib_opf_case39_epri.m",
    "case73": "pglib_opf_case73_ieee_rts.m",
    "case118": "pglib_opf_case118_ieee.m",
    "case300": "pglib_opf_case300_ieee.m",
    "case500": "pglib_opf_case500_goc.m",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def expected_files() -> list[Path]:
    files = [
        ROOT / "protocols" / "dc_scopf_protocol_v1.yaml",
        ROOT / "protocols" / "dc_scopf_case500_screening_amendment_v2.yaml",
        ROOT / "protocols" / "dc_scopf_case500_constraint_generation_v3.yaml",
        ROOT / "protocols" / "dc_scopf_case500_clarabel_adjudication_v4.yaml",
        ROOT / "protocols" / "dc_scopf_case500_top1_constraint_generation_v5.yaml",
        ROOT / "protocols" / "dc_scopf_case500_hybrid_exact_solver_v7.yaml",
        ROOT / "protocols" / "dc_scopf_case500_clarabel_portfolio_v8.yaml",
        ROOT / "protocols" / "dc_scopf_case500_base_clarabel_v9.yaml",
        ROOT / "protocols" / "dc_scopf_case500_full_clarabel_v10.yaml",
        ROOT / "protocols" / "dc_scopf_case500_tight_dual_v11.yaml",
        ROOT / "protocols" / "dc_scopf_clarabel_optimal_face_validation_v6.yaml",
        ROOT / "protocols" / "dc_scopf_clarabel_portfolio_validation_v9.yaml",
        ROOT / "requirements-pcc-v2.txt",
        ROOT / "experiments" / "run_pcc_v2_dc_scopf_gate.py",
        ROOT / "experiments" / "run_dc_scopf_confirmatory_batches.ps1",
        ROOT / "experiments" / "run_dc_scopf_confirmatory_statistics.py",
        ROOT / "experiments" / "dc_scopf_active_screening.py",
        ROOT / "experiments" / "linopy_clarabel.py",
        ROOT / "experiments" / "diagnose_case500_clarabel_top1.py",
        ROOT / "experiments" / "highs_constraint_relaxation.py",
        ROOT / "experiments" / "validate_highs_row_relaxation.py",
        ROOT / "experiments" / "diagnose_case500_clarabel_settings_offset2.py",
        ROOT / "experiments" / "diagnose_case500_clarabel_strong_top1_offset2.py",
        ROOT / "experiments" / "diagnose_case500_highs_row_relaxation_offset2.py",
        ROOT / "experiments" / "diagnose_case500_clarabel_portfolio_offset1.py",
        ROOT / "experiments" / "validate_clarabel_highs_scopf.py",
        ROOT / "experiments" / "validate_dc_scopf_active_screening.py",
        ROOT / "experiments" / "run_pcc_v2_dc_scopf_case500_screened.py",
        ROOT / "experiments" / "run_case500_screened_batches.ps1",
        ROOT / "experiments" / "build_case500_screened_evidence.py",
        ROOT / "experiments" / "build_epsr_evidence_dashboard.py",
        ROOT / "experiments" / "build_epsr_manuscript_tables.py",
        ROOT / "experiments" / "build_dc_scopf_mechanism_atlas.py",
        ROOT / "experiments" / "build_pcc_decision_reason_taxonomy.py",
        ROOT / "experiments" / "select_external_tool_blind_corpus.py",
        ROOT / "experiments" / "run_external_tool_blind_roundtrip.py",
        ROOT / "experiments" / "run_external_tool_consequence_adjudication.py",
        ROOT / "protocols" / "external_tool_blind_roundtrip_v1.yaml",
    ]
    files.extend(ROOT / "downloads" / "pglib-opf-v23.07" / name for name in CASES.values())
    for case in CASES:
        if case == "case500":
            continue
        for offset in range(10):
            prefix = OUTPUT / f"dc_scopf_gate_all_{case}_offset{offset}_1states"
            files.extend([
                prefix.with_name(prefix.name + "_summary.json"),
                prefix.with_name(prefix.name + "_results.csv"),
                prefix.with_name(prefix.name + "_evidence.csv"),
                prefix.with_name(prefix.name + "_checkpoint.json"),
            ])
    for offset in range(10):
        prefix = CASE500_OUTPUT / f"dc_scopf_gate_all_case500_offset{offset}_1states_v11"
        files.extend([
            prefix.with_name(prefix.name + "_summary.json"),
            prefix.with_name(prefix.name + "_results.csv"),
            prefix.with_name(prefix.name + "_evidence.csv"),
            prefix.with_name(prefix.name + "_checkpoint.json"),
        ])
    files.extend([
        OUTPUT / "dc_scopf_gate_all_case500_offset0_1states_summary.json",
        OUTPUT / "dc_scopf_gate_all_case500_offset0_1states_checkpoint.json",
        ROOT / "outputs" / "case500_scopf_diagnostic" / "summary.json",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_screened" / "aborted_v3_exact_alias_timeout_attempts.jsonl",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_screened" / "aborted_v3_exact_alias_timeout_offset0_checkpoint.json",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_constraint_generation" / "aborted_v4_highs_cg_timeout_attempts.jsonl",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_constraint_generation" / "aborted_v4_highs_cg_timeout_offset0_checkpoint.json",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_clarabel" / "aborted_v5_clarabel_add_all_numerical_error_attempts.jsonl",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_clarabel" / "aborted_v5_clarabel_add_all_offset0_checkpoint.json",
        ROOT / "outputs" / "case500_clarabel_top1_diagnostic" / "summary.json",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_clarabel_top1" / "aborted_v6_offset2_clarabel_top1_attempts.jsonl",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_clarabel_top1" / "aborted_v6_offset2_clarabel_top1_checkpoint.json",
        ROOT / "outputs" / "case500_clarabel_settings_offset2_diagnostic" / "summary.json",
        ROOT / "outputs" / "case500_clarabel_strong_top1_offset2_diagnostic" / "summary.json",
        ROOT / "outputs" / "highs_row_relaxation_validation" / "summary.json",
        ROOT / "outputs" / "case500_highs_row_relaxation_offset2_diagnostic" / "summary.json",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_hybrid_exact" / "aborted_v7_offset1_hybrid_attempts.jsonl",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_hybrid_exact" / "aborted_v7_offset1_hybrid_checkpoint.json",
        ROOT / "outputs" / "case500_clarabel_portfolio_offset1_diagnostic" / "summary.json",
        ROOT / "outputs" / "dc_scopf_active_screening_validation" / "summary.json",
        ROOT / "outputs" / "clarabel_highs_scopf_validation" / "summary.json",
        ROOT / "outputs" / "clarabel_highs_scopf_validation" / "failed_dispatch_identity_summary_v1.json",
        ROOT / "outputs" / "clarabel_highs_scopf_validation" / "failed_dispatch_identity_checkpoint_v1.json",
        ROOT / "outputs" / "clarabel_highs_scopf_validation" / "failed_optimal_face_rerun_checkpoint_attempt1.json",
        ROOT / "outputs" / "clarabel_highs_scopf_validation" / "failed_optimal_face_rerun_stderr_attempt1.log",
        ROOT / "outputs" / "clarabel_highs_scopf_validation" / "failed_optimal_face_rerun_checkpoint_attempt2.json",
        ROOT / "outputs" / "clarabel_highs_scopf_validation" / "failed_optimal_face_rerun_stderr_attempt2.log",
        CASE500_OUTPUT / "solver_attempts.jsonl",
        CASE500_OUTPUT / "evidence_build_summary.json",
    ])
    files.extend([
        ROOT / "outputs" / "pcc_v2_dc_scopf_statistics" / "summary.json",
        ROOT / "outputs" / "epsr_evidence_dashboard" / "epsr_evidence_dashboard.json",
        ROOT / "outputs" / "epsr_manuscript_tables" / "epsr_manuscript_tables.md",
        ROOT / "outputs" / "epsr_manuscript_tables" / "table_source_snapshot.json",
    ])
    files.extend([
        ROOT / "outputs" / "dc_scopf_mechanism_atlas" / "summary.json",
        ROOT / "outputs" / "dc_scopf_mechanism_atlas" / "false_secure_by_network_state.csv",
        ROOT / "outputs" / "dc_scopf_mechanism_atlas" / "false_secure_by_component.csv",
        ROOT / "outputs" / "dc_scopf_mechanism_atlas" / "top_loading_excess_cases.csv",
        ROOT / "outputs" / "dc_scopf_mechanism_atlas" / "top_hidden_load_shed_cases.csv",
        ROOT / "outputs" / "dc_scopf_mechanism_atlas" / "top_cost_understatement_cases.csv",
        ROOT / "outputs" / "pcc_decision_reason_taxonomy" / "summary.json",
        ROOT / "outputs" / "pcc_decision_reason_taxonomy" / "decision_counts.csv",
        ROOT / "outputs" / "pcc_decision_reason_taxonomy" / "reason_counts.csv",
        ROOT / "outputs" / "pcc_decision_reason_taxonomy" / "reason_examples.csv",
        ROOT / "outputs" / "external_tool_blind_roundtrip" / "challenge_manifest.json",
        ROOT / "outputs" / "external_tool_blind_roundtrip" / "route_artifacts_manifest.json",
        ROOT / "outputs" / "external_tool_blind_roundtrip" / "pcc_receipts.jsonl",
        ROOT / "outputs" / "external_tool_blind_roundtrip" / "pcc_receipts.csv",
        ROOT / "outputs" / "external_tool_blind_roundtrip" / "consequence_labels.jsonl",
        ROOT / "outputs" / "external_tool_blind_roundtrip" / "consequence_labels.csv",
        ROOT / "outputs" / "external_tool_blind_roundtrip" / "consequence_summary.json",
        ROOT / "outputs" / "external_tool_blind_roundtrip" / "summary.json",
        ROOT / "cgmes" / "corpus" / "external_blind_roundtrip_v1" / "selection_manifest.json",
    ])
    files.extend(sorted((ROOT / "cgmes" / "corpus" / "external_blind_roundtrip_v1").glob("*.zip")))
    files.extend(sorted((ROOT / "outputs" / "external_tool_blind_roundtrip" / "route_artifacts").glob("*.zip")))
    return files


def terminal_summaries() -> list[dict]:
    summaries = []
    for case in CASES:
        if case == "case500":
            continue
        for offset in range(10):
            path = OUTPUT / f"dc_scopf_gate_all_{case}_offset{offset}_1states_summary.json"
            if path.is_file():
                summaries.append(json.loads(path.read_text(encoding="utf-8")))
    for offset in range(10):
        path = CASE500_OUTPUT / f"dc_scopf_gate_all_case500_offset{offset}_1states_v11_summary.json"
        if path.is_file():
            summaries.append(json.loads(path.read_text(encoding="utf-8")))
    return summaries


def create() -> None:
    gate = dc_confirmatory_gate(terminal_summaries())
    if not gate["ready"]:
        raise SystemExit(f"refuse_lock_incomplete_dc_gate:{gate['evidence']}")
    missing = [relative(path) for path in expected_files() if not path.is_file()]
    if missing:
        raise SystemExit("refuse_lock_missing_files:" + ",".join(missing))
    payload = {
        "lock_version": "dc-scopf-confirmatory-lock-v2",
        "created_only_after_exact_5x10_gate": True,
        "gate_evidence_at_lock": gate["evidence"],
        "file_count": len(expected_files()),
        "sha256": {relative(path): sha256(path) for path in expected_files()},
    }
    LOCK.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


def verify() -> None:
    if not LOCK.is_file():
        raise SystemExit("dc_scopf_confirmatory_lock_v2_missing")
    payload = json.loads(LOCK.read_text(encoding="utf-8"))
    checks = {}
    for name, expected in payload["sha256"].items():
        path = ROOT / name
        actual = sha256(path) if path.is_file() else None
        checks[name] = {"exists": path.is_file(), "expected": expected, "actual": actual, "match": actual == expected}
    result = {
        "lock_version": payload["lock_version"],
        "checked_files": len(checks),
        "all_match": all(item["match"] for item in checks.values()),
        "checks": checks,
    }
    print(json.dumps(result, indent=2))
    if not result["all_match"]:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args()
    create() if args.create else verify()


if __name__ == "__main__":
    main()
