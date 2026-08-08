from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "epsr_manuscript_tables"


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def load_optional(relative: str) -> dict | None:
    path = ROOT / relative
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def main() -> None:
    ladder = load("outputs/pcc_v2_semantic_baseline_ladder/summary.json")
    stats = load("outputs/pcc_v2_application_statistics/summary.json")
    dc_dashboard = load("outputs/epsr_evidence_dashboard/epsr_evidence_dashboard.json")
    dc_stats = load_optional("outputs/pcc_v2_dc_scopf_statistics/summary.json")
    dual = load("outputs/cross_solver_dcmp_validation/cross_solver_dcmp_summary.json")
    dual_negative = load("outputs/cross_solver_validation/cross_solver_summary.json")
    holdout = load("outputs/cgmes_untouched_holdout/holdout_summary.json")
    qocdc = load("outputs/qocdc_414_applicable_subset/summary.json")
    separation = load("outputs/cgmes_apl111_pcc_separation/separation_summary.json")
    taxonomy = load("outputs/pcc_decision_reason_taxonomy/summary.json")
    external = load("outputs/external_tool_blind_roundtrip/summary.json")

    baseline_rows = []
    for baseline, metric in ladder["metrics"].items():
        baseline_rows.append([
            baseline,
            f"{metric['lawful_accepts']}/{ladder['lawful_n']}",
            f"{metric['harmful_accepts']}/{ladder['harmful_n']}",
            f"{metric['harmful_acceptance_rate']:.3f}",
        ])

    n1 = stats["n1"]
    opf = stats["opf"]
    application_rows = [
        [
            "AC N-1",
            f"{n1['paired_valid']}/{n1['attempted']}",
            n1["unsafe_results_prevented"],
            n1["harmful_solver_starts"],
            f"{n1['counterfactual_max_loading_delta_percent_points']['median']:.3f} percentage points",
            f"[{n1['counterfactual_max_loading_delta_percent_points']['hierarchical_cluster_bootstrap_median_95'][0]:.3f}, {n1['counterfactual_max_loading_delta_percent_points']['hierarchical_cluster_bootstrap_median_95'][1]:.3f}]",
            f"{n1['counterfactual_max_loading_delta_percent_points']['exact_one_sided_network_sign_p']:.8f}",
        ],
        [
            "AC OPF",
            f"{opf['paired_valid']}/{opf['attempted']}",
            opf["unsafe_results_prevented"],
            opf["harmful_solver_starts"],
            f"{100 * opf['relative_cost_regret']['median']:.2f}%",
            f"[{100 * opf['relative_cost_regret']['hierarchical_cluster_bootstrap_median_95'][0]:.2f}%, {100 * opf['relative_cost_regret']['hierarchical_cluster_bootstrap_median_95'][1]:.2f}%]",
            f"{opf['relative_cost_regret']['exact_one_sided_network_sign_p']:.5f}",
        ],
    ]
    if dc_stats:
        dc_effect = dc_stats["effects_among_strict_false_secure"]["alias_post_contingency_loading_excess_pu"]
        dc_safety = dc_stats["safety"]
        label = "DC SCOPF" if dc_stats["ready"] else "DC SCOPF (interim; gate open)"
        application_rows.append([
            label,
            f"{dc_stats['coverage']['completed_states']}/50 states",
            dc_safety["unsafe_results_prevented"],
            dc_safety["harmful_solver_starts"],
            f"{dc_effect['median']:.3f} p.u. loading excess",
            f"[{dc_effect['hierarchical_cluster_bootstrap_median_95'][0]:.3f}, {dc_effect['hierarchical_cluster_bootstrap_median_95'][1]:.3f}]",
            f"{dc_effect['exact_one_sided_network_sign_p']:.5f}",
        ])

    solver_rows = [
        ["Unaligned PowerModels DCP negative control", dual_negative["status_pairs"], dual_negative["mutually_optimal_pairs"], f"{dual_negative['status_agreement_rate']:.3f}", f"{dual_negative['objective_agreement_rate_among_mutually_optimal']:.3f}", f"{dual_negative['generation_agreement_rate_among_mutually_optimal']:.3f}", f"{dual_negative['max_objective_relative_error']:.3e}"],
        ["Transformer-aware PowerModels DCMP + HiGHS", dual["status_pairs"], dual["mutually_optimal_pairs"], f"{dual['status_agreement_rate']:.3f}", f"{dual['objective_agreement_rate_among_mutually_optimal']:.3f}", f"{dual['generation_agreement_rate_among_mutually_optimal']:.3f}", f"{dual['max_objective_relative_error']:.3e}"],
    ]

    shacl = holdout["official_shacl"]
    import_result = holdout["pypowsybl_import"]
    standards_rows = [
        ["Official Svedala APL control", "APL 1.1.1 SHACL", separation["official_shacl_conforms"], separation["official_shacl_results"], "Reported separately from PCC"],
        ["QoCDC development control", "QoCDC 4.1.4 subset L1-L4", qocdc["positive_control"]["passed"], qocdc["implemented_check_count"], "Full QoCDC claim forbidden"],
        ["Untouched PowSyBl bundle", "APL 1.1.1 merged-graph run", shacl["shacl_conforms"], shacl["validation_result_count"], "Task-semantic/import holdout; no APL-conformance claim"],
        ["Untouched PowSyBl bundle", f"pypowsybl {import_result['tool_version']} import", import_result["status"], import_result["nonempty_element_total"], "59 reported elements across six tables"],
    ]

    readiness_rows = [
        [name, "ready" if gate["ready"] else "open", gate["evidence"]]
        for name, gate in dc_dashboard["gates"].items()
    ]
    readiness_rows.extend(
        [name, "ready" if gate["ready"] else "open", gate["evidence"]]
        for name, gate in dc_dashboard.get("enhancement_gates", {}).items()
    )

    decision_rows = [
        [row["source"], row["decision"], row["count"]]
        for row in taxonomy["decision_counts"]
    ]
    top_reason_rows = [
        [row["source"], row["decision"], row["reason"], row["count"], row["operator_action"]]
        for row in taxonomy["top_reasons"][:8]
    ]

    text = "\n\n".join([
        "# Machine-generated EPSR manuscript tables",
        "Generated from result JSON files. Do not edit numeric cells manually.",
        "## Table 1. Ordered semantic baseline ladder\n\n" + markdown_table(
            ["Baseline", "Lawful accepted", "Harmful accepted", "Harmful acceptance rate"], baseline_rows
        ),
        "## Table 2. Operational consequence and prevention\n\n" + markdown_table(
            ["Task", "Paired-valid / attempted", "Prevented", "Harmful starts", "Median effect", "Cluster-bootstrap 95% CI", "Network sign p"], application_rows
        ),
        "## Table 3. Independent solver reproduction\n\n" + markdown_table(
            ["Stack/formulation", "Status pairs", "Mutually optimal", "Status agreement", "Objective agreement", "Generation agreement", "Max objective relative error"], solver_rows
        ),
        "## Table 4. Standards and untouched-source controls\n\n" + markdown_table(
            ["Artifact", "Check", "Outcome", "Results/elements", "Claim boundary"], standards_rows
        ),
        "## Table 5. PCC decision reason taxonomy\n\n"
        + f"Rows seen: {taxonomy['rows_seen']}; rows with reasons: {taxonomy['rows_with_reasons']}; unique reasons: {taxonomy['unique_reasons']}; external lawful exact acceptance: {external['lawful_exact_roundtrips_accepted']}/{external['lawful_exact_roundtrips']}.\n\n"
        + markdown_table(["Source", "Decision", "Count"], decision_rows)
        + "\n\nTop operator-facing reasons:\n\n"
        + markdown_table(["Source", "Decision", "Reason", "Count", "Operator action"], top_reason_rows),
        "## Supplementary audit table. Evidence readiness\n\n" + markdown_table(
            ["Evidence family", "Status", "Machine evidence"], readiness_rows
        ),
    ])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "epsr_manuscript_tables.md").write_text(text + "\n", encoding="utf-8")
    (OUTPUT / "table_source_snapshot.json").write_text(json.dumps({
        "dashboard": dc_dashboard,
        "dual_solver": dual,
        "holdout_ready": holdout["ready"],
        "taxonomy": taxonomy,
        "external_blind_roundtrip": external,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT / "epsr_manuscript_tables.md")


if __name__ == "__main__":
    main()
