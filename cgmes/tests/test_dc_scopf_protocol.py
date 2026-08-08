from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


EXPERIMENTS = Path(__file__).resolve().parents[2] / "experiments"
if str(EXPERIMENTS) not in sys.path:
    sys.path.insert(0, str(EXPERIMENTS))

from build_epsr_evidence_dashboard import (  # noqa: E402
    dc_confirmatory_gate,
    dc_summary_priority,
    official_separation_gate,
    qocdc_subset_gate,
)
from dc_scopf_active_screening import bodf_post_contingency_loadings  # noqa: E402
try:
    from run_pcc_v2_dc_scopf_gate import (  # noqa: E402
        LOADER_REVISION,
        RESULT_SCHEMA,
        branch_index,
        load_pglib,
        non_islanding_branches,
        post_contingency_loading,
    )
    HAS_DC_ENVIRONMENT = True
except ModuleNotFoundError as exc:
    if exc.name != "pypsa":
        raise
    HAS_DC_ENVIRONMENT = False
    LOADER_REVISION = "pglib-pypsa-transformer-explicit-v2"
    RESULT_SCHEMA = "pcc-v2-dc-scopf-result-v2"


class DCSCOPFProtocolTests(unittest.TestCase):
    @unittest.skipUnless(HAS_DC_ENVIRONMENT, "requires isolated PyPSA DC-SCOPF environment")
    def test_matpower_transformer_tap_and_phase_shift_are_explicit(self) -> None:
        case = """\
mpc.baseMVA = 100;
mpc.bus = [1 3 0 0 0 0 1 1 0 230 1 1.1 0.9; 2 1 10 0 0 0 1 1 0 230 1 1.1 0.9; 3 1 5 0 0 0 1 1 0 230 1 1.1 0.9];
mpc.gen = [1 20 0 100 -100 1 100 1 100 0];
mpc.branch = [1 2 0.01 0.10 0 100 100 100 1.05 7 1 -360 360; 2 3 0.01 0.10 0 100 100 100 0 0 1 -360 360; 3 1 0.01 0.10 0 100 100 100 0 0 1 -360 360];
mpc.gencost = [2 0 0 2 10 0];
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.m"
            path.write_text(case, encoding="utf-8")
            network = load_pglib(path, 1.0)
        self.assertEqual(len(network.transformers), 1)
        self.assertEqual(len(network.lines), 2)
        transformer = network.transformers.iloc[0]
        self.assertAlmostEqual(float(transformer.tap_ratio), 1.05)
        self.assertAlmostEqual(float(transformer.phase_shift), 7.0)
        self.assertIn(("Transformer", "branch-00000"), non_islanding_branches(network))

    @unittest.skipUnless(HAS_DC_ENVIRONMENT, "requires isolated PyPSA DC-SCOPF environment")
    def test_branch_outages_are_tuple_typed_for_pypsa_regression(self) -> None:
        outages = [("Line", "branch-1"), ("Transformer", "branch-2")]
        self.assertIsInstance(branch_index(outages), tuple)
        self.assertEqual(branch_index(outages), tuple(outages))

    def test_dashboard_requires_exact_five_by_ten_coverage(self) -> None:
        summaries = []
        for case in ("case39", "case73", "case118", "case300", "case500"):
            for offset in range(10):
                summaries.append(
                    {
                        "loader_revision": LOADER_REVISION,
                        "result_schema": RESULT_SCHEMA,
                        "candidate_mode": "all",
                        "cases_requested": [case],
                        "states_per_case_requested": 1,
                        "state_offset": offset,
                        "rows": 1,
                        "failed_states": 0,
                        "false_secure_dispatches": 1,
                        "unsafe_results_prevented": 1,
                        "harmful_solver_starts": 0,
                    }
                )
        self.assertTrue(dc_confirmatory_gate(summaries)["ready"])
        summaries.pop()
        self.assertFalse(dc_confirmatory_gate(summaries)["ready"])

    def test_dashboard_fails_closed_on_failure_or_solver_start(self) -> None:
        summary = {
            "loader_revision": LOADER_REVISION,
            "result_schema": RESULT_SCHEMA,
            "candidate_mode": "all",
            "cases_requested": ["case39"],
            "states_per_case_requested": 1,
            "state_offset": 0,
            "rows": 1,
            "failed_states": 1,
            "false_secure_dispatches": 0,
            "unsafe_results_prevented": 0,
            "harmful_solver_starts": 1,
        }
        self.assertFalse(dc_confirmatory_gate([summary])["ready"])

    def test_case500_screened_schema_has_explicit_priority(self) -> None:
        summary = {
            "cases_requested": ["case500"],
            "loader_revision": LOADER_REVISION,
            "result_schema": "pcc-v2-dc-scopf-result-v3",
            "protocol_version": "pcc_v2_native_dc_scopf_case500_screened_v3",
            "screening_exact_convex_reduction": True,
        }
        self.assertEqual(dc_summary_priority(summary), 2)
        summary["screening_exact_convex_reduction"] = False
        self.assertEqual(dc_summary_priority(summary), 0)

    def test_case500_top1_clarabel_schema_supersedes_prior_revisions(self) -> None:
        summary = {
            "cases_requested": ["case500"],
            "loader_revision": LOADER_REVISION,
            "result_schema": "pcc-v2-dc-scopf-result-v6",
            "protocol_version": "pcc_v2_native_dc_scopf_case500_clarabel_top1_cg_v6",
            "screening_exact_convex_reduction": True,
            "restricted_master_solver": "Clarabel 0.11.1",
            "terminal_all_non_omitted_constraints_feasible": True,
        }
        self.assertEqual(dc_summary_priority(summary), 5)
        summary["restricted_master_solver"] = "unvalidated"
        self.assertEqual(dc_summary_priority(summary), 0)

    def test_case500_hybrid_exact_schema_has_highest_priority(self) -> None:
        summary = {
            "cases_requested": ["case500"],
            "loader_revision": LOADER_REVISION,
            "result_schema": "pcc-v2-dc-scopf-result-v7",
            "protocol_version": "pcc_v2_native_dc_scopf_case500_hybrid_exact_v7",
            "screening_exact_convex_reduction": True,
            "restricted_master_solver": "Clarabel 0.11.1 with exact HiGHS fallback",
            "terminal_all_non_omitted_constraints_feasible": True,
        }
        self.assertEqual(dc_summary_priority(summary), 6)
        summary["terminal_all_non_omitted_constraints_feasible"] = False
        self.assertEqual(dc_summary_priority(summary), 0)

    def test_case500_clarabel_portfolio_schema_supersedes_hybrid_v7(self) -> None:
        summary = {
            "cases_requested": ["case500"],
            "loader_revision": LOADER_REVISION,
            "result_schema": "pcc-v2-dc-scopf-result-v8",
            "protocol_version": "pcc_v2_native_dc_scopf_case500_clarabel_portfolio_v8",
            "screening_exact_convex_reduction": True,
            "restricted_master_solver": (
                "Clarabel 0.11.1 settings portfolio with exact HiGHS fallback"
            ),
            "terminal_all_non_omitted_constraints_feasible": True,
        }
        self.assertEqual(dc_summary_priority(summary), 7)
        summary["terminal_all_non_omitted_constraints_feasible"] = False
        self.assertEqual(dc_summary_priority(summary), 0)

    def test_case500_full_clarabel_schema_supersedes_portfolio_v8(self) -> None:
        summary = {
            "cases_requested": ["case500"],
            "loader_revision": LOADER_REVISION,
            "result_schema": "pcc-v2-dc-scopf-result-v10",
            "protocol_version": "pcc_v2_native_dc_scopf_case500_full_clarabel_v10",
            "screening_exact_convex_reduction": True,
            "full_solver": "Clarabel 0.11.1 settings portfolio",
            "restricted_master_solver": (
                "Clarabel 0.11.1 settings portfolio with exact HiGHS fallback"
            ),
            "terminal_all_non_omitted_constraints_feasible": True,
        }
        self.assertEqual(dc_summary_priority(summary), 8)
        summary["terminal_all_non_omitted_constraints_feasible"] = False
        self.assertEqual(dc_summary_priority(summary), 0)

    def test_case500_tight_dual_schema_has_highest_priority(self) -> None:
        summary = {
            "cases_requested": ["case500"],
            "loader_revision": LOADER_REVISION,
            "result_schema": "pcc-v2-dc-scopf-result-v11",
            "protocol_version": "pcc_v2_native_dc_scopf_case500_tight_dual_v11",
            "screening_exact_convex_reduction": True,
            "full_solver": "Clarabel 0.11.1 tight settings portfolio",
            "restricted_master_solver": (
                "Clarabel 0.11.1 settings portfolio with exact HiGHS fallback"
            ),
            "terminal_all_non_omitted_constraints_feasible": True,
        }
        self.assertEqual(dc_summary_priority(summary), 9)
        summary["full_solver"] = "unvalidated"
        self.assertEqual(dc_summary_priority(summary), 0)

    @unittest.skipUnless(HAS_DC_ENVIRONMENT, "requires isolated PyPSA DC-SCOPF environment")
    def test_vectorized_bodf_matches_explicit_post_contingency_lpf(self) -> None:
        case = """\
mpc.baseMVA = 100;
mpc.bus = [1 3 0 0 0 0 1 1 0 230 1 1.1 0.9; 2 1 10 0 0 0 1 1 0 230 1 1.1 0.9; 3 1 5 0 0 0 1 1 0 230 1 1.1 0.9];
mpc.gen = [1 20 0 100 -100 1 100 1 100 0];
mpc.branch = [1 2 0.01 0.10 0 100 100 100 1.05 0 1 -360 360; 2 3 0.01 0.10 0 100 100 100 0 0 1 -360 360; 3 1 0.01 0.10 0 100 100 100 0 0 1 -360 360];
mpc.gencost = [2 0 0 2 10 0];
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.m"
            path.write_text(case, encoding="utf-8")
            network = load_pglib(path, 1.0)
        candidates = non_islanding_branches(network)
        status, condition = network.optimize.optimize_security_constrained(
            branch_outages=branch_index(candidates), solver_name="highs", log_to_console=False
        )
        self.assertEqual((status, condition), ("ok", "optimal"))
        predicted = bodf_post_contingency_loadings(network, candidates)
        dispatch = {str(key): float(value) for key, value in network.generators_t.p.loc["now"].items()}
        for outage in candidates:
            actual = post_contingency_loading(network, dispatch, outage)
            self.assertAlmostEqual(predicted[f"{outage[0]}:{outage[1]}"], actual, places=8)

    def test_official_separation_requires_both_standard_pass_and_pcc_fail_closed(self) -> None:
        summary = {
            "ready": True,
            "official_shacl_status": "success",
            "official_shacl_conforms": True,
            "official_shacl_results": 0,
            "target_byte_identical": True,
            "pcc_decision": "reject",
            "task_asset_count": 8,
            "solver_starts": 0,
        }
        self.assertTrue(official_separation_gate(summary)["ready"])
        summary["pcc_decision"] = "accept"
        self.assertFalse(official_separation_gate(summary)["ready"])
        summary["pcc_decision"] = "reject"
        summary["official_shacl_conforms"] = False
        self.assertFalse(official_separation_gate(summary)["ready"])

    def test_qocdc_gate_requires_scoped_claim_and_negative_controls(self) -> None:
        summary = {
            "protocol": "qocdc_4_1_4_applicable_subset_v1",
            "claim_scope": "applicable_subset_only_not_full_QoCDC_compliance",
            "implemented_levels": [1, 2, 3, 4],
            "not_implemented_levels": [5, 6, 7, 8],
            "implemented_check_count": 15,
            "positive_control": {"passed": True},
            "negative_controls_detected": True,
            "ready": True,
        }
        self.assertTrue(qocdc_subset_gate(summary)["ready"])
        summary["claim_scope"] = "full_QoCDC_compliance"
        self.assertFalse(qocdc_subset_gate(summary)["ready"])
        summary["claim_scope"] = "applicable_subset_only_not_full_QoCDC_compliance"
        summary["negative_controls_detected"] = False
        self.assertFalse(qocdc_subset_gate(summary)["ready"])


if __name__ == "__main__":
    unittest.main()
