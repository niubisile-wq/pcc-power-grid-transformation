from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


class FinalizationTests(unittest.TestCase):
    def test_converted_shacl_denominator_and_taxonomy_are_complete(self) -> None:
        frame = pd.read_csv(
            RESULTS / "converted_cgmes3_shacl_validation_results.csv",
            keep_default_na=False,
        )
        summary = json.loads(
            (RESULTS / "converted_cgmes3_shacl_report_summary.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(len(frame), 32)
        self.assertEqual(frame.artifact_id.nunique(), 32)
        self.assertTrue(summary["complete_denominator"])
        self.assertEqual(
            summary["outcome_counts"],
            {
                "shacl_nonconforming": 4,
                "strict_rdf_parse_duplicate_id": 25,
                "validation_timeout": 3,
            },
        )
        self.assertFalse(
            summary["critical_pattern_shacl_passes_but_pcc_rejects_established"]
        )

    def test_unified_mapping_includes_target_validation_statuses(self) -> None:
        summary = json.loads(
            (RESULTS / "full_roundtrip_asset_mapping_summary.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(summary["rows"], 164047)
        self.assertEqual(sum(summary["target_shacl_status_counts"].values()), 164047)
        self.assertEqual(summary["native_pcc_certificate_rows"], 0)
        self.assertEqual(summary["full_pcc_fail_closed_rows"], 164047)

    def test_completed_environment_and_version_probes_have_pre_attempt_locks(self) -> None:
        locks = (
            RESULTS
            / "cross_environment"
            / "windows_py312"
            / "cross_environment_probe_lock.json",
            RESULTS
            / "cross_environment"
            / "windows_py312"
            / "tool_version"
            / "tool_version_probe_lock.json",
            RESULTS
            / "cross_environment"
            / "windows_py312_pypowsybl112"
            / "tool_version"
            / "tool_version_probe_lock.json",
        )
        for path in locks:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["created_before_attempts"], path)

    def test_cross_os_nonattempt_is_not_counted_as_tool_failure(self) -> None:
        summary = json.loads(
            (
                RESULTS
                / "cross_environment"
                / "cross_environment_summary.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(summary["available_environment_denominators_complete"])
        self.assertFalse(summary["planned_cross_environment_denominator_complete"])
        self.assertEqual(
            summary["environment_availability"]["linux_py311"],
            "not_attempted_environment_unavailable",
        )
        self.assertIn("Docker", summary["infrastructure_failure"])

    def test_final_positioning_retains_permanent_claim_limits(self) -> None:
        summary = json.loads(
            (RESULTS / "confirmatory_summary.json").read_text(encoding="utf-8")
        )
        self.assertFalse(summary["untouched_final_holdout_available"])
        self.assertFalse(summary["official_shacl_pass_task_failure_established"])
        self.assertFalse(summary["natural_acopf_paired_valid"])
        self.assertFalse(summary["formal_public_preregistration"])
        self.assertEqual(
            summary["recommended_positioning"],
            "domain_methods_or_interoperability_journal",
        )


if __name__ == "__main__":
    unittest.main()
