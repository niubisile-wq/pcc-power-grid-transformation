"""Build a fail-closed EPSR evidence-readiness dashboard from result summaries."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "epsr_evidence_dashboard"
DC_CASES = {"case39", "case73", "case118", "case300", "case500"}
DC_OFFSETS = set(range(10))
DC_LOADER_REVISION = "pglib-pypsa-transformer-explicit-v2"
DC_RESULT_SCHEMA = "pcc-v2-dc-scopf-result-v2"
DC_CASE500_RESULT_SCHEMA = "pcc-v2-dc-scopf-result-v3"
DC_CASE500_CG_RESULT_SCHEMA = "pcc-v2-dc-scopf-result-v4"
DC_CASE500_CLARABEL_RESULT_SCHEMA = "pcc-v2-dc-scopf-result-v5"
DC_CASE500_TOP1_RESULT_SCHEMA = "pcc-v2-dc-scopf-result-v6"
DC_CASE500_HYBRID_RESULT_SCHEMA = "pcc-v2-dc-scopf-result-v7"
DC_CASE500_PORTFOLIO_RESULT_SCHEMA = "pcc-v2-dc-scopf-result-v8"
DC_CASE500_FULL_CLARABEL_RESULT_SCHEMA = "pcc-v2-dc-scopf-result-v10"
DC_CASE500_TIGHT_DUAL_RESULT_SCHEMA = "pcc-v2-dc-scopf-result-v11"


def dc_summary_priority(summary: dict) -> int:
    cases = summary.get("cases_requested", [])
    if (
        cases == ["case500"]
        and summary.get("loader_revision") == DC_LOADER_REVISION
        and summary.get("result_schema") == DC_CASE500_TIGHT_DUAL_RESULT_SCHEMA
        and summary.get("protocol_version")
        == "pcc_v2_native_dc_scopf_case500_tight_dual_v11"
        and summary.get("screening_exact_convex_reduction") is True
        and summary.get("full_solver")
        == "Clarabel 0.11.1 tight settings portfolio"
        and summary.get("restricted_master_solver")
        == "Clarabel 0.11.1 settings portfolio with exact HiGHS fallback"
        and summary.get("terminal_all_non_omitted_constraints_feasible") is True
    ):
        return 9
    if (
        cases == ["case500"]
        and summary.get("loader_revision") == DC_LOADER_REVISION
        and summary.get("result_schema") == DC_CASE500_FULL_CLARABEL_RESULT_SCHEMA
        and summary.get("protocol_version")
        == "pcc_v2_native_dc_scopf_case500_full_clarabel_v10"
        and summary.get("screening_exact_convex_reduction") is True
        and summary.get("full_solver") == "Clarabel 0.11.1 settings portfolio"
        and summary.get("restricted_master_solver")
        == "Clarabel 0.11.1 settings portfolio with exact HiGHS fallback"
        and summary.get("terminal_all_non_omitted_constraints_feasible") is True
    ):
        return 8
    if (
        cases == ["case500"]
        and summary.get("loader_revision") == DC_LOADER_REVISION
        and summary.get("result_schema") == DC_CASE500_PORTFOLIO_RESULT_SCHEMA
        and summary.get("protocol_version")
        == "pcc_v2_native_dc_scopf_case500_clarabel_portfolio_v8"
        and summary.get("screening_exact_convex_reduction") is True
        and summary.get("restricted_master_solver")
        == "Clarabel 0.11.1 settings portfolio with exact HiGHS fallback"
        and summary.get("terminal_all_non_omitted_constraints_feasible") is True
    ):
        return 7
    if (
        cases == ["case500"]
        and summary.get("loader_revision") == DC_LOADER_REVISION
        and summary.get("result_schema") == DC_CASE500_HYBRID_RESULT_SCHEMA
        and summary.get("protocol_version")
        == "pcc_v2_native_dc_scopf_case500_hybrid_exact_v7"
        and summary.get("screening_exact_convex_reduction") is True
        and summary.get("restricted_master_solver")
        == "Clarabel 0.11.1 with exact HiGHS fallback"
        and summary.get("terminal_all_non_omitted_constraints_feasible") is True
    ):
        return 6
    if (
        cases == ["case500"]
        and summary.get("loader_revision") == DC_LOADER_REVISION
        and summary.get("result_schema") == DC_CASE500_TOP1_RESULT_SCHEMA
        and summary.get("protocol_version")
        == "pcc_v2_native_dc_scopf_case500_clarabel_top1_cg_v6"
        and summary.get("screening_exact_convex_reduction") is True
        and summary.get("restricted_master_solver") == "Clarabel 0.11.1"
        and summary.get("terminal_all_non_omitted_constraints_feasible") is True
    ):
        return 5
    if (
        cases == ["case500"]
        and summary.get("loader_revision") == DC_LOADER_REVISION
        and summary.get("result_schema") == DC_CASE500_CLARABEL_RESULT_SCHEMA
        and summary.get("protocol_version")
        == "pcc_v2_native_dc_scopf_case500_clarabel_cg_v5"
        and summary.get("screening_exact_convex_reduction") is True
        and summary.get("restricted_master_solver") == "Clarabel 0.11.1"
    ):
        return 4
    if (
        cases == ["case500"]
        and summary.get("loader_revision") == DC_LOADER_REVISION
        and summary.get("result_schema") == DC_CASE500_CG_RESULT_SCHEMA
        and summary.get("protocol_version")
        == "pcc_v2_native_dc_scopf_case500_constraint_generation_v4"
        and summary.get("screening_exact_convex_reduction") is True
    ):
        return 3
    if (
        cases == ["case500"]
        and summary.get("loader_revision") == DC_LOADER_REVISION
        and summary.get("result_schema") == DC_CASE500_RESULT_SCHEMA
        and summary.get("protocol_version") == "pcc_v2_native_dc_scopf_case500_screened_v3"
        and summary.get("screening_exact_convex_reduction") is True
    ):
        return 2
    if (
        summary.get("loader_revision") == DC_LOADER_REVISION
        and summary.get("result_schema") == DC_RESULT_SCHEMA
    ):
        return 1
    return 0


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def load_optional(relative: str) -> dict | None:
    path = ROOT / relative
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def dc_confirmatory_gate(summaries: list[dict]) -> dict:
    """Aggregate singleton checkpoints without double-counting reruns."""
    states: dict[tuple[str, int], dict] = {}
    for summary in summaries:
        priority = dc_summary_priority(summary)
        if not priority:
            continue
        if summary.get("candidate_mode") != "all":
            continue
        cases = summary.get("cases_requested", [])
        if len(cases) != 1 or summary.get("states_per_case_requested") != 1:
            continue
        key = (str(cases[0]), int(summary.get("state_offset", -1)))
        if key not in states or priority > dc_summary_priority(states[key]):
            states[key] = summary

    coverage = {case: {offset for current, offset in states if current == case} for case in DC_CASES}
    complete_coverage = all(coverage[case] == DC_OFFSETS for case in DC_CASES)
    selected = list(states.values())
    supported = [item for item in summaries if dc_summary_priority(item)]
    failures = sum(int(item.get("failed_states", 0)) for item in selected)
    superseded_failures = max(
        0,
        sum(int(item.get("failed_states", 0)) for item in supported) - failures,
    )
    rows = sum(int(item.get("rows", 0)) for item in selected)
    reported_alias_overlimit = sum(
        int(item.get("false_secure_dispatches", 0)) for item in selected
    )
    prevented = sum(int(item.get("unsafe_results_prevented", 0)) for item in selected)
    solver_starts = sum(int(item.get("harmful_solver_starts", 0)) for item in selected)
    nonempty = all(
        int(states[(case, offset)].get("rows", 0)) > 0
        for case in DC_CASES
        for offset in DC_OFFSETS
        if (case, offset) in states
    )
    ready = (
        complete_coverage
        and nonempty
        and failures == 0
        and solver_starts == 0
        and prevented == reported_alias_overlimit
    )
    coverage_text = ", ".join(f"{case}:{len(coverage[case])}/10" for case in sorted(DC_CASES))
    return {
        "ready": ready,
        "evidence": (
            f"coverage [{coverage_text}]; rows={rows}; failures={failures}; "
            f"reported-alias-overlimit={reported_alias_overlimit}; "
            f"prevented={prevented}; solver-starts={solver_starts}; "
            f"superseded-failures-retained={superseded_failures}"
        ),
        "selected_terminal_failures": failures,
        "superseded_failures_retained": superseded_failures,
    }


def official_separation_gate(summary: dict | None) -> dict:
    ready = bool(
        summary
        and summary.get("ready") is True
        and summary.get("official_shacl_status") == "success"
        and summary.get("official_shacl_conforms") is True
        and summary.get("target_byte_identical") is True
        and summary.get("pcc_decision") in {"reject", "unresolved"}
        and int(summary.get("solver_starts", -1)) == 0
    )
    if not summary:
        evidence = "no APL 1.1.1 SHACL-pass/PCC-fail-closed separation result"
    else:
        evidence = (
            f"SHACL conforms={summary.get('official_shacl_conforms')}; "
            f"SHACL results={summary.get('official_shacl_results')}; "
            f"PCC={summary.get('pcc_decision')}; "
            f"task-assets={summary.get('task_asset_count')}; "
            f"solver-starts={summary.get('solver_starts')}"
        )
    return {"ready": ready, "evidence": evidence}


def qocdc_subset_gate(summary: dict | None) -> dict:
    ready = bool(
        summary
        and summary.get("protocol") == "qocdc_4_1_4_applicable_subset_v1"
        and summary.get("claim_scope") == "applicable_subset_only_not_full_QoCDC_compliance"
        and summary.get("implemented_levels") == [1, 2, 3, 4]
        and summary.get("not_implemented_levels") == [5, 6, 7, 8]
        and summary.get("positive_control", {}).get("passed") is True
        and summary.get("negative_controls_detected") is True
        and summary.get("ready") is True
    )
    if not summary:
        evidence = "no QoCDC 4.1.4 applicable-subset result"
    else:
        evidence = (
            f"implemented-levels={summary.get('implemented_levels')}; "
            f"checks={summary.get('implemented_check_count')}; "
            f"positive-pass={summary.get('positive_control', {}).get('passed')}; "
            f"negative-controls-detected={summary.get('negative_controls_detected')}; "
            "full-compliance-claim=false"
        )
    return {"ready": ready, "evidence": evidence}


def dc_mechanism_gate(summary: dict | None) -> dict:
    ready = bool(
        summary
        and summary.get("ready") is True
        and summary.get("rows") == 12340
        and summary.get("strict_false_secure_dispatches") == 369
        and summary.get("strict_prevented") == 369
        and summary.get("strict_harmful_solver_starts") == 0
        and summary.get("invalid_solver_pairs_retained") == 38
        and summary.get("exacerbated_existing_overload_rows") == 50
    )
    if not summary:
        evidence = "no DC-SCOPF mechanism atlas"
    else:
        evidence = (
            f"rows={summary.get('rows')}; strict={summary.get('strict_false_secure_dispatches')}; "
            f"states-with-strict={summary.get('states_with_strict_false_secure')}; "
            f"line/transformer={summary.get('by_component')}; "
            f"retained-invalid={summary.get('invalid_solver_pairs_retained')}; "
            f"retained-exacerbated={summary.get('exacerbated_existing_overload_rows')}"
        )
    return {"ready": ready, "evidence": evidence}


def pcc_taxonomy_gate(summary: dict | None) -> dict:
    ready = bool(
        summary
        and summary.get("ready") is True
        and summary.get("rows_seen", 0) > 0
        and summary.get("unique_reasons", 0) >= 5
    )
    if not summary:
        evidence = "no PCC decision reason taxonomy"
    else:
        evidence = (
            f"rows={summary.get('rows_seen')}; rows-with-reasons={summary.get('rows_with_reasons')}; "
            f"unique-reasons={summary.get('unique_reasons')}"
        )
    return {"ready": ready, "evidence": evidence}


def external_roundtrip_gate(summary: dict | None) -> dict:
    ready = bool(
        summary
        and summary.get("success_criteria", {}).get("harmful_solver_starts_zero") is True
        and summary.get("success_criteria", {}).get("lawful_exact_acceptance_rate_one") is True
        and summary.get("success_criteria", {}).get("at_least_one_external_tool_generated_task_relevant_anomaly") is True
        and summary.get("success_criteria", {}).get("at_least_one_operationally_consequential_anomaly") is True
    )
    if not summary:
        evidence = "no external-tool blind roundtrip result"
    else:
        evidence = (
            f"bundles={summary.get('selected_bundles')}; route-successes={summary.get('route_successes')}; "
            f"receipts={summary.get('receipt_count')}; lawful-accept-rate={summary.get('lawful_exact_acceptance_rate')}; "
            f"task-anomalies={summary.get('external_tool_generated_task_relevant_anomalies')}; "
            f"harmful-starts={summary.get('harmful_solver_starts')}; "
            f"operational-consequence-attempted={summary.get('operational_consequence_attempted')}; "
            f"paired-valid-consequence={summary.get('paired_valid_consequence_evaluated')}; "
            f"operational-consequence-evaluated={summary.get('operational_consequence_evaluated')}"
        )
    return {
        "ready": ready,
        "evidence": evidence,
        "claim_use": summary.get("claim_use") if summary else "not available",
    }


def main() -> None:
    semantic = load("outputs/pcc_v2_attack_matrix/attack_matrix_summary.json")
    semantic_ladder = load_optional("outputs/pcc_v2_semantic_baseline_ladder/summary.json")
    n1 = load("outputs/pcc_v2_n1_gate/pcc_v2_n1_gate_summary.json")
    opf = load("outputs/pcc_v2_opf_gate/pcc_v2_opf_gate_summary.json")
    application_stats = load_optional("outputs/pcc_v2_application_statistics/summary.json")
    scaling = load("outputs/pcc_v2_scaling/pcc_v2_scaling_summary.json")
    separation = load_optional(
        "outputs/cgmes_apl111_pcc_separation/separation_summary.json"
    )
    qocdc = load_optional("outputs/qocdc_414_applicable_subset/summary.json")
    dc_summaries = []
    for directory in (
        ROOT / "outputs" / "pcc_v2_dc_scopf_gate",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_screened",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_constraint_generation",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_clarabel",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_clarabel_top1",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_hybrid_exact",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_clarabel_portfolio",
    ):
        for path in sorted(directory.glob("dc_scopf_gate_all_*_summary.json")):
            summary = json.loads(path.read_text(encoding="utf-8"))
            dc_summaries.append(summary)
    dc_gate = dc_confirmatory_gate(dc_summaries)
    dc_statistics = load_optional("outputs/pcc_v2_dc_scopf_statistics/summary.json")
    dc_screening_validation = load_optional(
        "outputs/dc_scopf_active_screening_validation/summary.json"
    )
    clarabel_validation = load_optional(
        "outputs/clarabel_highs_scopf_validation/summary.json"
    )
    dc_gate["ready"] = bool(
        dc_gate["ready"]
        and dc_statistics
        and dc_statistics.get("ready") is True
        and dc_screening_validation
        and dc_screening_validation.get("ready") is True
        and dc_screening_validation.get("states_validated") == 40
        and dc_screening_validation.get("strict_false_secure_recall") == 1.0
        and clarabel_validation
        and clarabel_validation.get("ready") is True
        and clarabel_validation.get("pairs") == 10
        and clarabel_validation.get("protocol")
        == "clarabel_portfolio_vs_highs_scopf_optimal_face_validation_v3"
        and clarabel_validation.get("objective_feasibility_equivalent_pairs") == 10
        and dc_statistics.get("safety", {}).get("prevention_rate_among_false_secure") == 1.0
        and dc_statistics.get("safety", {}).get("harmful_solver_starts") == 0
        and dc_statistics.get("superseded_case500_attempt_artifacts", {}).get(
            "all_retained"
        ) is True
    )
    if dc_statistics:
        safety = dc_statistics.get("safety", {})
        dc_gate["evidence"] += (
            f"; stats-ready={dc_statistics.get('ready')}; "
            f"strict-false-secure={safety.get('strict_false_secure_dispatches')}; "
            f"zero-event-upper95={safety.get('one_sided_95_clopper_pearson_upper_harmful_start_rate')}"
        )
    if dc_screening_validation:
        dc_gate["evidence"] += (
            f"; screening-validation={dc_screening_validation.get('states_validated')}/40; "
            f"screening-recall={dc_screening_validation.get('strict_false_secure_recall')}"
        )
    if clarabel_validation:
        dc_gate["evidence"] += (
            f"; clarabel-highs={clarabel_validation.get('pairs')}/10; "
            f"clarabel-objective-maxrel="
            f"{clarabel_validation.get('maximum_objective_relative_difference')}; "
            f"clarabel-feasible-equivalent="
            f"{clarabel_validation.get('objective_feasibility_equivalent_pairs')}/10; "
            f"component-dispatch-identity="
            f"{clarabel_validation.get('component_dispatch_identity_pairs')}/10"
        )
    dual_unaligned = load_optional("outputs/cross_solver_validation/cross_solver_summary.json")
    dual = load_optional("outputs/cross_solver_dcmp_validation/cross_solver_dcmp_summary.json")
    holdout = load_optional("outputs/cgmes_untouched_holdout/holdout_summary.json")
    dc_mechanism = load_optional("outputs/dc_scopf_mechanism_atlas/summary.json")
    pcc_taxonomy = load_optional("outputs/pcc_decision_reason_taxonomy/summary.json")
    external_roundtrip = load_optional("outputs/external_tool_blind_roundtrip/summary.json")
    gates = {
        "semantic_confirmatory": {
            "ready": bool(
                semantic["go_no_go"] == "GO"
                and semantic_ladder
                and semantic_ladder.get("ready") is True
                and semantic_ladder.get("harmful_n") == semantic["harmful_n"]
                and semantic_ladder.get("metrics", {}).get("B5_full_PCC_v2", {}).get("harmful_accepts") == 0
            ),
            "evidence": (
                f"{semantic['harmful_n']} harmful; full-PCC accepted={semantic['v2_harmful_accepts']}; "
                f"signed-artifact accepted={semantic_ladder.get('metrics', {}).get('B1_signed_artifact_v1', {}).get('harmful_accepts') if semantic_ladder else 'missing'}; "
                f"lawful={semantic['lawful_n']}"
            ),
        },
        "ac_n1_gate": {
            "ready": bool(
                n1["completed"] >= 50
                and n1["harmful_solver_starts"] == 0
                and application_stats
                and application_stats.get("ready") is True
            ),
            "evidence": (
                f"{n1['completed']} completed; {n1['unsafe_results_prevented']} prevented; "
                f"{n1['failed']} failures retained; network-sign-p="
                f"{application_stats.get('n1', {}).get('counterfactual_max_loading_delta_percent_points', {}).get('exact_one_sided_network_sign_p') if application_stats else 'missing'}"
            ),
        },
        "ac_opf_gate": {
            "ready": bool(
                opf["paired_valid"] >= 20
                and opf["harmful_solver_starts"] == 0
                and application_stats
                and application_stats.get("ready") is True
                and application_stats.get("opf", {}).get("paired_valid", 0) >= 25
                and application_stats.get("opf", {}).get("relative_cost_regret", {}).get("exact_one_sided_network_sign_p", 1.0) < 0.05
            ),
            "evidence": (
                f"{application_stats.get('opf', {}).get('paired_valid') if application_stats else 'missing'} paired-valid; "
                f"median regret={application_stats.get('opf', {}).get('relative_cost_regret', {}).get('median') if application_stats else 'missing'}; "
                f"paired-networks={application_stats.get('opf', {}).get('paired_networks') if application_stats else 'missing'}; "
                f"network-sign-p={application_stats.get('opf', {}).get('relative_cost_regret', {}).get('exact_one_sided_network_sign_p') if application_stats else 'missing'}"
            ),
        },
        "dc_scopf_confirmatory": dc_gate,
        "scaling": {
            "ready": bool(scaling["all_targets_met"]),
            "evidence": f"largest={scaling['sizes'][-1]['asset_count']}; p95={scaling['sizes'][-1]['p95_ms']:.3f} ms",
        },
        "official_shacl_pcc_separation": official_separation_gate(separation),
        "qocdc_4_1_4_applicable_subset": qocdc_subset_gate(qocdc),
        "dual_solver_cross_environment": {
            "ready": bool(
                dual
                and dual.get("ready") is True
                and dual.get("status_pairs") == 9
                and dual.get("mutually_optimal_pairs", 0) >= 8
                and dual.get("status_agreement_rate", 0) == 1.0
                and dual.get("objective_agreement_rate_among_mutually_optimal", 0) == 1.0
                and dual.get("generation_agreement_rate_among_mutually_optimal", 0) == 1.0
            ),
            "evidence": (
                f"status-pairs={dual.get('status_pairs', 0)}; mutually-optimal={dual.get('mutually_optimal_pairs', 0)}; "
                f"status-agreement={dual.get('status_agreement_rate', 0):.4f}; "
                f"objective-agreement={dual.get('objective_agreement_rate_among_mutually_optimal', 0):.4f}; "
                f"unexplained={dual.get('unexplained_differences', 0)}; "
                f"unaligned-DCP-objective-agreement={dual_unaligned.get('objective_agreement_rate_among_mutually_optimal', 'missing') if dual_unaligned else 'missing'}"
                if dual else "Julia/PowerModels confirmatory results not present"
            ),
        },
        "untouched_cgmes_holdout": {
            "ready": bool(
                holdout
                and holdout.get("frozen_before_inspection") is True
                and holdout.get("official_shacl_reported_separately") is True
                and holdout.get("pcc_reported_separately") is True
                and holdout.get("pypowsybl_import_reported_separately") is True
                and holdout.get("ready") is True
                and holdout.get("pcc", {}).get("lawful_complete_proof", {}).get("decision") == "accept"
                and holdout.get("pcc", {}).get("lawful_complete_proof", {}).get("solver_starts") == 1
                and holdout.get("pcc", {}).get("harmful_missing_proof", {}).get("decision") != "accept"
                and holdout.get("pcc", {}).get("harmful_missing_proof", {}).get("solver_starts") == 0
            ),
            "evidence": (
                f"artifacts={holdout.get('artifacts', 0)}; frozen-before-inspection="
                f"{holdout.get('frozen_before_inspection', False)}"
                if holdout else "no frozen untouched CGMES holdout result"
            ),
        },
    }
    report = {
        "dashboard_version": "epsr-evidence-readiness-v1",
        "target_journal": "Electric Power Systems Research",
        "ready_gates": sum(item["ready"] for item in gates.values()),
        "total_gates": len(gates),
        "submission_ready": all(item["ready"] for item in gates.values()),
        "gates": gates,
        "enhancement_gates": {
            "dc_scopf_mechanism_atlas": dc_mechanism_gate(dc_mechanism),
            "pcc_decision_reason_taxonomy": pcc_taxonomy_gate(pcc_taxonomy),
            "external_tool_blind_roundtrip": external_roundtrip_gate(external_roundtrip),
        },
        "policy": "A missing or incomplete evidence family is not promoted to ready.",
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "epsr_evidence_dashboard.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
