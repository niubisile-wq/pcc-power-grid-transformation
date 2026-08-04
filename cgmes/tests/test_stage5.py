from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rdflib import Graph, Literal, Namespace  # noqa: E402

from validation.run_shacl_worker import (  # noqa: E402
    _apply_shape_declared_datatypes,
    _install_pyshacl_service_keyword_guard_hotfix,
    _select_shapes,
)
from pyshacl.helper.sparql_query_helper import SPARQLQueryHelper  # noqa: E402


class StageFiveTests(unittest.TestCase):
    def test_validation_registry_has_frozen_twenty_model_denominator(self) -> None:
        with (ROOT / "corpus" / "validation_model_registry.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            rows = [
                row
                for row in csv.DictReader(stream)
                if row["included"].lower() == "true"
            ]
        self.assertEqual(len(rows), 20)
        self.assertTrue(all(row["split"] == "internal_validation" for row in rows))
        self.assertTrue(all(row["cgmes_version"] == "3.0.0" for row in rows))
        self.assertTrue(
            all((ROOT / row["package_relative_path"]).is_file() for row in rows)
        )

    def test_cgmes3_direct_import_matrix_is_complete_and_failures_retained(self) -> None:
        frame = pd.read_csv(ROOT / "results" / "stage5_import_matrix_results.csv")
        self.assertEqual(len(frame), 60)
        self.assertEqual(frame.case_id.nunique(), 20)
        self.assertEqual(frame[["case_id", "tool"]].drop_duplicates().shape[0], 60)
        counts = frame.groupby(["tool", "status"]).size().to_dict()
        self.assertEqual(counts[("pandapower", "error")], 20)
        self.assertEqual(counts[("pypowsybl", "error")], 8)
        self.assertEqual(counts[("pypowsybl", "success")], 12)
        self.assertEqual(counts[("veragrid", "success")], 20)
        self.assertEqual(int(frame.timed_out.sum()), 0)

        summary = json.loads(
            (ROOT / "results" / "stage5_import_matrix_summary.json").read_text()
        )
        self.assertEqual(
            summary["evidence_role"],
            "internal_validation_not_untouched_final_holdout",
        )
        self.assertTrue(summary["complete_denominator"])
        self.assertEqual(summary["recorded_attempts"], 60)

    def test_cgmes3_roundtrip_matrix_is_complete_and_failures_retained(self) -> None:
        frame = pd.read_csv(ROOT / "results" / "stage5_roundtrip_matrix_results.csv")
        self.assertEqual(len(frame), 160)
        self.assertEqual(frame.case_id.nunique(), 20)
        self.assertEqual(set(frame.exporter), {"pypowsybl", "veragrid"})
        self.assertEqual(int(frame.status.eq("success").sum()), 32)
        self.assertEqual(int(frame.status.eq("error").sum()), 44)
        self.assertEqual(
            int(frame.status.eq("not_attempted_export_failed").sum()), 84
        )
        exports = frame[frame.stage == "export"]
        self.assertEqual(len(exports), 40)
        self.assertEqual(int(exports.status.eq("success").sum()), 12)
        self.assertEqual(int(exports.status.eq("error").sum()), 28)
        self.assertTrue(
            exports[exports.exporter == "veragrid"].status.eq("error").all()
        )

        summary = json.loads(
            (ROOT / "results" / "stage5_roundtrip_matrix_summary.json").read_text()
        )
        self.assertEqual(
            summary["evidence_role"],
            "internal_validation_not_untouched_final_holdout",
        )
        self.assertTrue(summary["complete_denominator"])
        self.assertEqual(summary["recorded_attempt_rows"], 160)

    def test_cgmes3_official_shacl_denominator_and_timeouts_are_retained(self) -> None:
        frame = pd.read_csv(
            ROOT / "results" / "cgmes_shacl_validation_results.csv",
            keep_default_na=False,
        )
        self.assertEqual(len(frame), 20)
        self.assertEqual(frame.case_id.nunique(), 20)
        self.assertEqual(int(frame.status.eq("success").sum()), 17)
        self.assertEqual(int(frame.status.eq("timeout").sum()), 3)
        successful = frame[frame.status == "success"]
        self.assertTrue(
            successful.shacl_conforms.astype(str).str.lower().eq("false").all()
        )
        self.assertEqual(
            int(
                pd.to_numeric(
                    successful.validation_result_count, errors="coerce"
                ).sum()
            ),
            9549,
        )
        self.assertTrue(
            frame[frame.status == "timeout"]
            .timed_out.astype(str)
            .str.lower()
            .eq("true")
            .all()
        )
        summary = json.loads(
            (ROOT / "results" / "cgmes_shacl_validation_summary.json").read_text()
        )
        self.assertTrue(summary["official_shapes"])
        self.assertTrue(summary["complete_denominator"])
        self.assertEqual(summary["successful_validations"], 17)
        self.assertEqual(summary["nonconforming_artifacts"], 17)
        self.assertEqual(summary["conforming_artifacts"], 0)
        self.assertEqual(summary["timeouts"], 3)

    def test_official_shape_selection_is_profile_matched_and_not_variant_union(self) -> None:
        profiles = {
            "http://iec.ch/TC57/ns/CIM/CoreEquipment-EU/3.0",
            "http://iec.ch/TC57/ns/CIM/EquipmentBoundary-EU/3.0",
            "http://iec.ch/TC57/ns/CIM/Operation-EU/3.0",
            "http://iec.ch/TC57/ns/CIM/ShortCircuit-EU/3.0",
            "http://iec.ch/TC57/ns/CIM/SteadyStateHypothesis-EU/3.0",
            "http://iec.ch/TC57/ns/CIM/StateVariables-EU/3.0",
            "http://iec.ch/TC57/ns/CIM/Topology-EU/3.0",
        }
        paths, policy = _select_shapes(
            ROOT / "corpus" / "extracted" / "cgmes3_profiles", profiles
        )
        names = {path.name for path in paths}
        self.assertGreater(len(names), 20)
        self.assertTrue(any("Header" in name for name in names))
        self.assertTrue(any("AllProfiles" in name for name in names))
        self.assertTrue(any("Equipment-AP" in name for name in names))
        self.assertTrue(any("StateVariables-AP" in name for name in names))
        self.assertTrue(any("SolvedMAS" in name for name in names))
        self.assertFalse(any("NotSolvedMAS" in name for name in names))
        self.assertFalse(any("Implicit-CrossProfile" in name for name in names))
        self.assertTrue(any("Explicit-CrossProfile" in name for name in names))
        self.assertTrue(policy["solved_mas"])

    def test_cimxml_datatype_enrichment_is_in_memory_and_shape_declared(self) -> None:
        cim = Namespace("http://iec.ch/TC57/CIM100#")
        sh = Namespace("http://www.w3.org/ns/shacl#")
        xsd = Namespace("http://www.w3.org/2001/XMLSchema#")
        example = Namespace("urn:test:")
        data = Graph()
        data.add((example.asset, cim["CurveData.y1value"], Literal("-400")))
        shapes = Graph()
        shapes.add((example.shape, sh.path, cim["CurveData.y1value"]))
        shapes.add((example.shape, sh.datatype, xsd.float))
        result = _apply_shape_declared_datatypes(data, shapes)
        values = list(data.objects(example.asset, cim["CurveData.y1value"]))
        self.assertEqual(result["datatype_enriched_literal_count"], 1)
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].datatype, xsd.float)
        self.assertEqual(str(values[0]), "-400")

    def test_service_guard_does_not_mistake_inservice_for_federation(self) -> None:
        _install_pyshacl_service_keyword_guard_hotfix()
        self.assertIsNone(
            SPARQLQueryHelper.has_service_regex.search(
                "$this cim:Equipment.inService true ."
            )
        )
        self.assertIsNotNone(
            SPARQLQueryHelper.has_service_regex.search(
                "SERVICE SILENT <https://example.invalid/sparql> { ?s ?p ?o }"
            )
        )


if __name__ == "__main__":
    unittest.main()
