from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def load(name: str) -> dict[str, object]:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def main() -> None:
    stage2 = load("stage2_complete_summary.json")
    stage5 = load("stage5_validation_summary.json")
    converted = load("converted_cgmes3_shacl_report_summary.json")
    mapping = load("full_roundtrip_asset_mapping_summary.json")
    baseline = load("baseline_comparison_summary.json")
    replay = load("natural_roundtrip_operational_replay_summary.json")
    statistics = load("confirmatory_statistics_summary.json")
    versions = load("cross_environment/tool_version_summary.json")
    cross_env = load("cross_environment/cross_environment_summary.json")
    serialization = load("serialization_profile_variant_summary.json")

    capability_rows = [
        {
            "requirement": "natural_task_relevant_identity_anomaly",
            "status": "established_with_reconstruction_limit",
            "evidence": "one non-injected L3_a identity loss; N-1 candidate set 7 to 6",
        },
        {
            "requirement": "full_pcc_increment_over_identity_only",
            "status": "bounded_candidate_classification_gain",
            "evidence": "six same-mRID motor-to-generator mutations rejected before task; no safety reversal",
        },
        {
            "requirement": "official_shacl_pass_but_pcc_task_failure",
            "status": "not_established",
            "evidence": converted["critical_pattern_reason"],
        },
        {
            "requirement": "natural_acopf_consequence",
            "status": "not_established",
            "evidence": "all natural replay AC-OPF arms non-convergent; paired-valid=false",
        },
        {
            "requirement": "untouched_final_holdout",
            "status": "unavailable",
            "evidence": "CGMES 3.0 was internal validation; no eligible untouched final holdout existed",
        },
        {
            "requirement": "adjacent_tool_version_probe",
            "status": "complete_same_os",
            "evidence": f"{versions['status_match_rows']}/4 status matches; byte-identical {versions['serialized_byte_identical_rows']}/4",
        },
        {
            "requirement": "cross_os_reproducibility",
            "status": "not_established_infrastructure_failure",
            "evidence": cross_env["infrastructure_failure"],
        },
        {
            "requirement": "formal_public_preregistration",
            "status": "not_established",
            "evidence": "aggregate RUN_LOCK was not created before Stage 5; protocol is a local single-team record",
        },
    ]
    pd.DataFrame(capability_rows).to_csv(
        RESULTS / "final_capability_matrix.csv", index=False
    )

    positioning = (
        "domain_methods_or_interoperability_journal"
        if any(row["status"] in {"unavailable", "not_established", "not_established_infrastructure_failure"} for row in capability_rows)
        else "nature_communications_candidate"
    )
    summary = {
        "evidence_role": "final_single_team_confirmatory_audit",
        "direct_import_attempts": int(stage2["direct_import_attempts"]) + int(stage5["direct_import_attempts"]),
        "direct_import_successes": int(stage2["direct_import_successes"]) + int(stage5["direct_import_successes"]),
        "roundtrip_rows": int(stage2["roundtrip_attempt_rows"]) + int(stage5["roundtrip_rows"]),
        "mapping_relation_rows": int(mapping["rows"]),
        "mapping_identity_only_accepted_rows": int(mapping["identity_only_accepted_rows"]),
        "mapping_additional_review_rows": int(mapping["rows"] - mapping["identity_only_accepted_rows"]),
        "mapping_additional_review_fraction": float(statistics["manual_or_additional_review_fraction"]),
        "baseline_cases": int(baseline["case_count"]),
        "baseline_decisions": int(baseline["decision_count"]),
        "natural_anomaly_count_entering_operational_replay": int(statistics["natural_operational_model_count"]),
        "natural_nminus1_candidate_count_reference": int(replay["nminus1_reference_candidate_count"]),
        "natural_nminus1_candidate_count_converted": int(replay["nminus1_converted_candidate_count"]),
        "natural_common_candidate_spearman": float(replay["nminus1_rank_comparison"]["spearman_common_candidates"]),
        "natural_acopf_paired_valid": bool(replay["acopf_paired_valid"]),
        "source_cgmes3_shacl_artifacts": int(stage5["shacl_artifacts"]),
        "source_cgmes3_shacl_nonconforming": int(stage5["shacl_nonconforming_artifacts"]),
        "source_cgmes3_shacl_timeouts": int(stage5["shacl_timeouts"]),
        "converted_cgmes3_shacl_artifacts": int(converted["recorded_artifacts"]),
        "converted_cgmes3_shacl_outcomes": converted["outcome_counts"],
        "serialization_attempts": int(serialization["attempt_rows"]),
        "tool_version_status_match_rows": int(versions["status_match_rows"]),
        "cross_os_reproducibility_established": bool(cross_env["planned_cross_environment_denominator_complete"]),
        "untouched_final_holdout_available": False,
        "official_shacl_pass_task_failure_established": False,
        "formal_public_preregistration": False,
        "recommended_positioning": positioning,
        "nature_communications_strong_branch_supported": False,
        "decision_reason": (
            "The study establishes a reproducible public-tool interoperability failure and bounded task consequence, "
            "but lacks an untouched final holdout, an official-SHACL-pass/PCC-reject task case, paired-valid natural AC-OPF, "
            "completed cross-OS replication and pre-run aggregate registration."
        ),
    }
    (RESULTS / "confirmatory_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Final single-team confirmatory report",
        "",
        "## Outcome",
        "",
        summary["decision_reason"],
        "",
        "Recommended positioning: **domain methods/interoperability journal**. The strongest Nature Communications branch is not supported by the completed evidence.",
        "",
        "## Complete denominators",
        "",
        f"- Direct import: {summary['direct_import_successes']}/{summary['direct_import_attempts']} raw successes across CGMES 2.4.15 and 3.0.",
        f"- Round-trip matrix rows: {summary['roundtrip_rows']} (raw failures and upstream non-attempts retained).",
        f"- Automated asset relations: {summary['mapping_relation_rows']:,}; {summary['mapping_additional_review_rows']:,} ({summary['mapping_additional_review_fraction']:.1%}) require additional review.",
        f"- Baselines: {summary['baseline_cases']} cases x 8 gates = {summary['baseline_decisions']} decisions.",
        f"- Official source CGMES 3.0 SHACL: {summary['source_cgmes3_shacl_artifacts']} artifacts, {summary['source_cgmes3_shacl_nonconforming']} nonconforming executions and {summary['source_cgmes3_shacl_timeouts']} timeouts.",
        f"- Converted CGMES 3.0 SHACL: {summary['converted_cgmes3_shacl_artifacts']} artifacts; {summary['converted_cgmes3_shacl_outcomes']}.",
        "",
        "## Positive bounded findings",
        "",
        f"- One non-injected official-model route lost named branch L3_a. Under the disclosed official-source-backed reconstruction, the N-1 candidate set changed from {summary['natural_nminus1_candidate_count_reference']} to {summary['natural_nminus1_candidate_count_converted']}; common-candidate Spearman rho was {summary['natural_common_candidate_spearman']:.4f}.",
        "- Full PCC rejected six natural same-mRID asset-type mutations that identity-only validation accepted, avoiding candidate misclassification; no safety reversal was established.",
        f"- Adjacent PyPowSyBl versions matched status in {summary['tool_version_status_match_rows']}/4 frozen route stages, but serialized outputs were not byte-identical.",
        "",
        "## Non-findings and permanent limits",
        "",
        "- No converted artifact both passed the applicable official SHACL profile and supplied native PCC evidence; the critical SHACL-pass/PCC-reject pattern was not established.",
        "- Natural replay AC-OPF was not paired-valid and supports no AC-OPF claim.",
        "- CGMES 3.0 is internal validation, not an untouched final holdout.",
        "- Linux probes were not attempted after Docker failed during base-image resolution; cross-OS reproducibility is not established.",
        "- The aggregate RUN_LOCK is post-run. The protocol must not be described as public preregistration.",
        "- Public test configurations are not an industry-prevalence sample or field-operation evidence.",
        "",
        "## Capability matrix",
        "",
        "See `results/final_capability_matrix.csv` for the machine-readable gate audit.",
    ]
    (RESULTS / "FINAL_CONFIRMATORY_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
