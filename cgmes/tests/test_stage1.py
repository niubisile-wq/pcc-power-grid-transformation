from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


class StageOneTests(unittest.TestCase):
    def test_adjudicated_mapping_has_contract_columns_and_no_unresolved_rows(self) -> None:
        frame = pd.read_csv(ROOT / "results" / "roundtrip_asset_mapping.csv")
        required = {
            "run_id",
            "case_id",
            "toolchain",
            "source_snapshot_hash",
            "target_snapshot_hash",
            "source_mrid",
            "target_mrid",
            "mapping_status",
            "mapping_confidence",
            "common_parent",
            "identity_equivalence_evidence",
            "schema_valid",
            "shacl_valid",
            "conservation_valid",
            "identity_only_valid",
            "full_pcc_valid",
            "adjudication_status",
            "task_scope",
            "gate1_qualifying",
            "notes",
        }
        self.assertTrue(required.issubset(frame.columns))
        self.assertFalse((frame.adjudication_status == "unresolved").any())

    def test_gate1_is_one_specific_noninjected_t1_branch_loss(self) -> None:
        frame = pd.read_csv(ROOT / "results" / "roundtrip_asset_mapping.csv")
        qualifying = frame[frame.gate1_qualifying.astype(bool)]
        self.assertEqual(len(qualifying), 1)
        row = qualifying.iloc[0]
        self.assertEqual(row.case_id, "cgmes24_minigrid_t1")
        self.assertEqual(row.mapping_status, "dropped")
        self.assertEqual(row.source_asset_type, "line")
        self.assertEqual(row.task_scope, "N-1_branch_outage")
        self.assertEqual(
            row.adjudication_status,
            "confirmed_task_relevant_parallel_asset_identity_loss",
        )
        self.assertIn("35df6abe-3087-4c27-a90a-12b5065333f3", row.source_mrid)

    def test_powerflow_denominators_retain_every_failure(self) -> None:
        summary = json.loads(
            (ROOT / "results" / "minimum_roundtrip_powerflow_summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary["attempts"], 18)
        self.assertEqual(sum(summary["outcomes"].values()), 18)
        self.assertEqual(summary["paired_denominator"], 12)
        self.assertEqual(summary["paired_valid"], 4)
        self.assertEqual(summary["paired_valid_by_tool"], {"pandapower": 0, "pypowsybl": 0, "veragrid": 4})

    def test_structural_gate_separates_routes(self) -> None:
        frame = pd.read_csv(ROOT / "results" / "cgmes_structural_validation_results.csv")
        status = {
            (row.case_id, row.artifact_kind): bool(row.structural_gate_valid)
            for row in frame.itertuples()
        }
        for case_id in ("cgmes24_minigrid_t1", "cgmes24_minigrid_t2"):
            self.assertTrue(status[(case_id, "official_source")])
            self.assertTrue(status[(case_id, "veragrid_roundtrip_export")])
            self.assertFalse(status[(case_id, "pypowsybl_roundtrip_export")])

    def test_pypowsybl_route_reimports_but_strict_rdf_parse_fails(self) -> None:
        roundtrip = json.loads(
            (ROOT / "results" / "pypowsybl_roundtrip_summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(roundtrip["successes"], 6)
        self.assertTrue(roundtrip["all_two_models_two_reimports_succeeded"])
        structural = pd.read_csv(ROOT / "results" / "cgmes_structural_validation_results.csv")
        targets = structural[structural.artifact_kind == "pypowsybl_roundtrip_export"]
        self.assertEqual(len(targets), 2)
        self.assertFalse(targets.rdf_parse_valid.astype(bool).any())

    def test_version_matched_official_rdfs_is_hashed_and_not_mislabeled_shacl(self) -> None:
        manifest = json.loads(
            (ROOT / "corpus" / "official_cgmes_corpus_manifest.json").read_text(encoding="utf-8")
        )
        package = next(
            item for item in manifest["packages"]
            if item["corpus_id"] == "entsoe_cgmes_2_4_15_rdfs_04jul2016"
        )
        self.assertEqual(
            package["download_sha256"].upper(),
            "7565DC0EF46ACD13F4FE6DFF30EE85999C3B8169701F171140BE54BAB654729F",
        )
        report = json.loads(
            (ROOT / "results" / "official_rdfs_validation_summary.json").read_text(encoding="utf-8")
        )
        self.assertTrue(report["not_shacl"])


if __name__ == "__main__":
    unittest.main()
