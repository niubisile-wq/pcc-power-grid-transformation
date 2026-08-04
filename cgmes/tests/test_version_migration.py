from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


class VersionMigrationTests(unittest.TestCase):
    def test_cgmes2415_to_cgmes3_matrix_preserves_complete_denominator(self) -> None:
        frame = pd.read_csv(
            ROOT / "results" / "version_migration_matrix_results.csv"
        )
        self.assertEqual(len(frame), 128)
        self.assertEqual(frame.case_id.nunique(), 32)
        exports = frame[frame.stage == "export"]
        reimports = frame[frame.stage == "reimport"]
        self.assertEqual(len(exports), 32)
        self.assertEqual(len(reimports), 96)
        self.assertEqual(int(exports.status.eq("success").sum()), 20)
        self.assertEqual(int(exports.status.eq("error").sum()), 12)
        self.assertEqual(int(reimports.status.eq("success").sum()), 40)
        self.assertEqual(int(reimports.status.eq("error").sum()), 20)
        self.assertEqual(
            int(reimports.status.eq("not_attempted_export_failed").sum()), 36
        )
        summary = json.loads(
            (ROOT / "results" / "version_migration_matrix_summary.json").read_text()
        )
        self.assertTrue(summary["complete_denominator"])
        self.assertEqual(summary["recorded_rows"], 128)
        self.assertEqual(
            summary["evidence_role"],
            "development_version_migration_not_final_holdout",
        )

    def test_version_migration_mapping_retains_failed_routes(self) -> None:
        routes = pd.read_csv(
            ROOT / "results" / "version_migration_mapping_routes.csv"
        )
        mapping = pd.read_csv(
            ROOT / "results" / "version_migration_asset_mapping.csv"
        )
        self.assertEqual(len(routes), 32)
        self.assertEqual(int(routes.mapping_status.eq("complete").sum()), 20)
        self.assertEqual(
            int(routes.mapping_status.eq("not_attempted_export_failed").sum()),
            12,
        )
        self.assertEqual(len(mapping), 48548)
        summary = json.loads(
            (ROOT / "results" / "version_migration_mapping_summary.json").read_text()
        )
        self.assertTrue(summary["complete_route_denominator"])
        self.assertEqual(summary["asset_relation_rows"], 48548)

    def test_unified_full_mapping_has_required_contract_columns(self) -> None:
        path = ROOT / "results" / "full_roundtrip_asset_mapping.csv"
        frame = pd.read_csv(path, nrows=5, keep_default_na=False)
        required = {
            "run_id",
            "case_id",
            "toolchain",
            "source_format",
            "target_format",
            "source_snapshot_hash",
            "target_snapshot_hash",
            "source_mrid",
            "target_mrid",
            "mapping_status",
            "mapping_confidence",
            "identity_equivalence_evidence",
            "schema_valid",
            "shacl_valid",
            "conservation_valid",
            "identity_only_valid",
            "full_pcc_valid",
            "adjudication_status",
        }
        self.assertTrue(required.issubset(frame.columns))
        summary = json.loads(
            (ROOT / "results" / "full_roundtrip_asset_mapping_summary.json").read_text()
        )
        self.assertEqual(summary["rows"], 164047)
        self.assertEqual(summary["version_migration_rows"], 48548)
        self.assertEqual(summary["native_pcc_certificate_rows"], 0)
        self.assertEqual(summary["identity_only_accepted_rows"], 87138)

        decisions = pd.read_csv(
            path,
            usecols=["mapping_status", "identity_only_valid"],
            keep_default_na=False,
        )
        self.assertTrue(
            decisions[decisions.mapping_status == "ambiguous"]
            .identity_only_valid.astype(str)
            .str.lower()
            .eq("false")
            .all()
        )


if __name__ == "__main__":
    unittest.main()
