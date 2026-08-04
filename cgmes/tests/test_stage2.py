from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


class StageTwoTests(unittest.TestCase):
    def test_direct_import_denominator_is_complete_and_raw_failures_retained(self) -> None:
        frame = pd.read_csv(ROOT / "results" / "stage2_import_matrix_results.csv")
        self.assertEqual(len(frame), 96)
        self.assertEqual(int((frame.status == "success").sum()), 84)
        self.assertEqual(int((frame.status != "success").sum()), 12)
        self.assertEqual(set(frame.tool), {"pandapower", "pypowsybl", "veragrid"})

    def test_every_direct_failure_recovers_only_with_matched_boundary(self) -> None:
        retry = pd.read_csv(ROOT / "results" / "stage2_boundary_retry_results.csv")
        self.assertEqual(len(retry), 12)
        self.assertTrue(retry.retry_status.eq("success").all())
        self.assertTrue(
            retry.raw_failure_class.eq("missing_boundary_base_voltage_reference").all()
        )
        summary = json.loads((ROOT / "results" / "stage2_import_failure_summary.json").read_text())
        self.assertEqual(summary["boundary_retry_attempts"], 12)
        self.assertTrue(summary["raw_denominator_preserved"])

    def test_eight_baselines_and_four_case_layers_are_present(self) -> None:
        frame = pd.read_csv(ROOT / "results" / "baseline_comparison_results.csv")
        self.assertEqual(frame.case_id.nunique(), 340)
        self.assertEqual(frame.baseline.nunique(), 8)
        self.assertEqual(len(frame), 2720)
        self.assertEqual(
            set(frame.case_layer),
            {
                "lawful_transformation",
                "identity_relation_error",
                "identity_correct_contract_field_error",
                "natural_software_interoperability",
            },
        )

    def test_b2_is_unresolved_not_fake_official_shacl_for_cgmes_2415(self) -> None:
        frame = pd.read_csv(ROOT / "results" / "baseline_comparison_results.csv")
        b2 = frame[frame.baseline == "B2_cgmes_shacl"]
        self.assertTrue(b2.decision.eq("unresolved").all())

    def test_gate2_separation_has_bounded_task_scope_evidence(self) -> None:
        summary = json.loads((ROOT / "results" / "baseline_comparison_summary.json").read_text())
        self.assertEqual(
            summary["gate2_preliminary_identity_only_accept_full_pcc_reject_natural_cases"],
            6,
        )
        self.assertTrue(summary["gate2_downstream_task_effect_verified"])
        self.assertEqual(summary["native_tool_pcc_certificate_count_natural"], 0)
        task = json.loads(
            (ROOT / "results" / "full_pcc_identity_only_task_scope_summary.json").read_text()
        )
        self.assertTrue(task["gate2_met"])
        self.assertEqual(task["misclassified_generator_candidates_avoided_by_pcc"], 6)
        self.assertIn("does not establish a safety", task["numeric_claim_limit"])

    def test_full_roundtrip_matrix_has_complete_preserved_denominator(self) -> None:
        frame = pd.read_csv(ROOT / "results" / "stage2_roundtrip_matrix_results.csv")
        self.assertEqual(len(frame), 256)
        self.assertEqual(frame.case_id.nunique(), 32)
        self.assertEqual(set(frame.exporter), {"veragrid", "pypowsybl"})
        self.assertEqual(int((frame.status == "success").sum()), 202)
        self.assertEqual(int((frame.status == "error").sum()), 45)
        self.assertEqual(
            int((frame.status == "not_attempted_export_failed").sum()), 9
        )
        summary = json.loads(
            (ROOT / "results" / "stage2_roundtrip_matrix_summary.json").read_text()
        )
        self.assertTrue(summary["complete_denominator"])
        self.assertEqual(summary["recorded_attempt_rows"], 256)

    def test_roundtrip_boundary_retry_uses_only_raw_reimport_errors(self) -> None:
        raw = pd.read_csv(ROOT / "results" / "stage2_roundtrip_matrix_results.csv")
        retry = pd.read_csv(
            ROOT / "results" / "stage2_roundtrip_boundary_retry_results.csv"
        )
        raw_reimport_errors = raw[
            (raw.stage == "reimport") & (raw.status == "error")
        ]
        raw_export_errors = raw[
            (raw.stage == "export") & (raw.status == "error")
        ]
        self.assertEqual(len(raw_reimport_errors), 42)
        self.assertEqual(len(raw_export_errors), 3)
        self.assertEqual(len(retry), len(raw_reimport_errors))
        self.assertEqual(int(retry.retry_status.eq("success").sum()), 13)
        self.assertEqual(int(retry.retry_status.eq("error").sum()), 29)
        self.assertTrue(retry.raw_status.eq("error").all())


if __name__ == "__main__":
    unittest.main()
