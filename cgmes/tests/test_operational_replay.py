from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


class NaturalOperationalReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.summary = json.loads(
            (ROOT / "results" / "natural_roundtrip_operational_replay_summary.json").read_text()
        )

    def test_reconstruction_limit_is_explicit(self) -> None:
        self.assertFalse(self.summary["evidence"]["raw_source_solver_claim"])
        self.assertFalse(self.summary["gate3_raw_source_solver_evidence"])
        self.assertIn("reconstruction", self.summary["claim_limit"].lower())

    def test_pf_effect_repair_and_oracle_controls(self) -> None:
        converted = self.summary["pf_reference_vs_converted"]
        repaired = self.summary["pf_reference_vs_repaired"]
        oracle = self.summary["pf_reference_vs_parallel_oracle"]
        self.assertEqual(converted["aligned_bus_count"], 11)
        self.assertGreater(converted["max_vm_delta_pu"], 1e-9)
        self.assertLess(repaired["max_vm_delta_pu"], 1e-10)
        self.assertLess(oracle["max_vm_delta_pu"], 1e-10)

    def test_named_contingency_and_candidate_set_change(self) -> None:
        self.assertEqual(
            self.summary["named_l3a_in_converted_status"],
            "not_executable_missing_named_asset",
        )
        self.assertEqual(self.summary["nminus1_reference_candidate_count"], 7)
        self.assertEqual(self.summary["nminus1_converted_candidate_count"], 6)
        self.assertEqual(self.summary["nminus1_candidate_loss_count"], 1)

    def test_acopf_failures_remain_in_denominator(self) -> None:
        replay = pd.read_csv(ROOT / "results" / "natural_roundtrip_operational_replay.csv")
        acopf = replay[replay.task == "AC_OPF"]
        self.assertEqual(len(acopf), 3)
        self.assertTrue(acopf.status.eq("nonconverged").all())
        self.assertFalse(acopf.converged.astype(bool).any())
        self.assertTrue(acopf.opf_cost.isna().all())


if __name__ == "__main__":
    unittest.main()
