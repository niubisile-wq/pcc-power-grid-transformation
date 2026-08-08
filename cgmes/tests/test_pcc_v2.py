from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from validation.execution_gate import ExecutionGate
from validation.evidence_schema import EvidenceRow, validate_evidence_mapping
from validation.pcc_v2 import (
    ACCEPT,
    REJECT,
    UNRESOLVED,
    PCCV2Verifier,
    TaskContract,
    issue_v2_certificate,
)
from validation.proof_guided_repair import ProofGuidedRepairer

EXPERIMENTS = Path(__file__).resolve().parents[2] / "experiments"
if str(EXPERIMENTS) not in sys.path:
    sys.path.insert(0, str(EXPERIMENTS))
from run_pcc_v2_attack_matrix import ATTACK_FAMILIES, transform  # noqa: E402


class PCCV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = Ed25519PrivateKey.generate()
        self.source = {
            "assets": {
                "line-a": {
                    "asset_type": "line",
                    "from_bus": "b1",
                    "to_bus": "b2",
                    "outage_capable": True,
                },
                "line-b": {
                    "asset_type": "line",
                    "from_bus": "b1",
                    "to_bus": "b2",
                    "outage_capable": True,
                },
            }
        }
        self.target = {
            "assets": {
                "line-x": {
                    "asset_type": "line",
                    "from_bus": "b1",
                    "to_bus": "b2",
                    "outage_capable": True,
                },
                "line-y": {
                    "asset_type": "line",
                    "from_bus": "b1",
                    "to_bus": "b2",
                    "outage_capable": True,
                },
            }
        }
        self.task = TaskContract(
            task_id="n1-all-branches",
            task_kind="N1_AC",
            source_assets=("line-a", "line-b"),
            target_assets=("line-x", "line-y"),
            intervention_type="outage",
            required_attributes=("asset_type", "from_bus", "to_bus"),
        )
        self.trace = [
            {
                "source_id": "line-a",
                "target_ids": ["line-x"],
                "relation_type": "rename",
                "authoritative": True,
                "evidence_kind": "native_backlink",
            },
            {
                "source_id": "line-b",
                "target_ids": ["line-y"],
                "relation_type": "rename",
                "authoritative": True,
                "evidence_kind": "native_backlink",
            },
        ]
        self.relations = [
            {
                "source_ids": ["line-a"],
                "target_ids": ["line-x"],
                "relation_type": "rename",
                "authoritative_evidence": {"kind": "native_backlink"},
                "intervention_map": {"line-a": ["line-x"]},
            },
            {
                "source_ids": ["line-b"],
                "target_ids": ["line-y"],
                "relation_type": "rename",
                "authoritative_evidence": {"kind": "native_backlink"},
                "intervention_map": {"line-b": ["line-y"]},
            },
        ]

    def certificate(self, relations=None, target=None, trace=None, nonce="nonce-1"):
        return issue_v2_certificate(
            self.source,
            target or self.target,
            task_contract=self.task,
            relations=self.relations if relations is None else relations,
            converter_trace=self.trace if trace is None else trace,
            issuer="native-adapter",
            private_key=self.key,
            certificate_id="cert-v2-1",
            transformation_id="transform-v2-1",
            issued_at="2026-08-06T00:00:00Z",
            nonce=nonce,
        )

    def verifier(self):
        return PCCV2Verifier(trusted_issuers={"native-adapter": self.key.public_key()})

    def test_complete_task_semantics_accept(self) -> None:
        decision = self.verifier().verify(
            self.source,
            self.target,
            self.certificate(),
            requested_task="N1_AC",
            converter_trace=self.trace,
        )
        self.assertEqual(decision.status, ACCEPT)

    def test_missing_converter_trace_is_unresolved(self) -> None:
        decision = self.verifier().verify(
            self.source, self.target, self.certificate(), requested_task="N1_AC"
        )
        self.assertEqual(decision.status, UNRESOLVED)
        self.assertIn("converter_trace_missing", decision.reasons)

    def test_independent_task_assets_cannot_merge(self) -> None:
        merged_target = {
            "assets": {
                "line-z": {
                    "asset_type": "line",
                    "from_bus": "b1",
                    "to_bus": "b2",
                    "outage_capable": True,
                }
            }
        }
        merged_task = TaskContract(
            task_id="n1-all-branches",
            task_kind="N1_AC",
            source_assets=("line-a", "line-b"),
            target_assets=("line-z",),
            intervention_type="outage",
            required_attributes=("asset_type",),
        )
        relations = [{
            "source_ids": ["line-a", "line-b"],
            "target_ids": ["line-z"],
            "relation_type": "merge",
            "authoritative_evidence": {"kind": "native_backlink"},
            "intervention_map": {"line-a": ["line-z"], "line-b": ["line-z"]},
        }]
        trace = [{
            "source_id": "line-a",
            "target_ids": ["line-z"],
            "relation_type": "merge",
            "authoritative": True,
            "evidence_kind": "native_backlink",
        }]
        cert = issue_v2_certificate(
            self.source,
            merged_target,
            task_contract=merged_task,
            relations=relations,
            converter_trace=trace,
            issuer="native-adapter",
            private_key=self.key,
            certificate_id="merge",
            transformation_id="merge",
            issued_at="2026-08-06T00:00:00Z",
            nonce="merge",
        )
        decision = self.verifier().verify(
            self.source, merged_target, cert, requested_task="N1_AC", converter_trace=trace
        )
        self.assertEqual(decision.status, REJECT)
        self.assertIn("independent_task_assets_merged", decision.reasons)

    def test_independent_relations_cannot_reuse_target_identity(self) -> None:
        target = {"assets": {"line-x": copy.deepcopy(self.target["assets"]["line-x"])}}
        task = TaskContract(
            task_id="all-lines-n1",
            task_kind="N1_AC",
            source_assets=("line-a", "line-b"),
            target_assets=("line-x",),
            intervention_type="outage",
            required_attributes=("asset_type",),
        )
        relations = [
            {
                "source_ids": [source_id],
                "target_ids": ["line-x"],
                "relation_type": "rename",
                "authoritative_evidence": {"kind": "native_backlink"},
                "intervention_map": {source_id: ["line-x"]},
            }
            for source_id in task.source_assets
        ]
        trace = [
            {
                "source_id": source_id,
                "target_ids": ["line-x"],
                "relation_type": "rename",
                "authoritative": True,
                "evidence_kind": "native_backlink",
            }
            for source_id in task.source_assets
        ]
        cert = issue_v2_certificate(
            self.source,
            target,
            task_contract=task,
            relations=relations,
            converter_trace=trace,
            issuer="native-adapter",
            private_key=self.key,
            certificate_id="target-reuse",
            transformation_id="target-reuse",
            issued_at="2026-08-06T00:00:00Z",
            nonce="target-reuse",
        )
        decision = self.verifier().verify(
            self.source, target, cert, requested_task="N1_AC", converter_trace=trace
        )
        self.assertEqual(decision.status, REJECT)
        self.assertIn("target_identity_reused_across_independent_relations", decision.reasons)

    def test_tampered_task_contract_rejects(self) -> None:
        cert = copy.deepcopy(self.certificate())
        cert["task_contract"]["target_assets"] = ["line-x"]
        decision = self.verifier().verify(
            self.source, self.target, cert, requested_task="N1_AC", converter_trace=self.trace
        )
        self.assertEqual(decision.status, REJECT)
        self.assertIn("task_contract_hash_mismatch", decision.reasons)

    def test_v1_high_risk_task_is_unresolved(self) -> None:
        decision = self.verifier().verify(
            self.source,
            self.target,
            {"contract_version": "pcc-cgmes-v1"},
            requested_task="N1_AC",
            converter_trace=[],
        )
        self.assertEqual(decision.status, UNRESOLVED)
        self.assertIn("legacy_certificate_lacks_task_semantics", decision.reasons)

    def test_provenance_only_repair_then_gate_execution(self) -> None:
        incomplete_target = {"assets": {"line-x": copy.deepcopy(self.target["assets"]["line-x"])}}
        incomplete_relations = [self.relations[0]]
        repair_trace = [
            self.trace[0],
            {
                **self.trace[1],
                "reversible": True,
                "reconstructed_assets": {"line-y": copy.deepcopy(self.target["assets"]["line-y"])},
            },
        ]
        repaired = ProofGuidedRepairer().repair(
            self.source,
            incomplete_target,
            self.task,
            incomplete_relations,
            repair_trace,
        )
        self.assertEqual(repaired.status, ACCEPT)
        self.assertIn("line-y", repaired.target_snapshot["assets"])

        cert = issue_v2_certificate(
            self.source,
            repaired.target_snapshot,
            task_contract=self.task,
            relations=repaired.relations,
            converter_trace=repair_trace,
            issuer="native-adapter",
            private_key=self.key,
            certificate_id="repaired",
            transformation_id="repaired",
            issued_at="2026-08-06T00:00:00Z",
            nonce="repaired",
        )
        calls = []

        def solver(snapshot):
            calls.append(snapshot)
            return {"candidate_count": len(snapshot["assets"])}

        outcome = ExecutionGate(self.verifier()).execute(
            self.source,
            repaired.target_snapshot,
            cert,
            requested_task="N1_AC",
            converter_trace=repair_trace,
            solver=solver,
        )
        self.assertEqual(outcome.receipt.solver_status, "completed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(outcome.result["candidate_count"], 2)

    def test_unresolved_gate_never_starts_solver(self) -> None:
        calls = []
        result = ExecutionGate(self.verifier()).execute(
            self.source,
            self.target,
            self.certificate(),
            requested_task="N1_AC",
            converter_trace=[],
            solver=lambda snapshot: calls.append(snapshot),
        )
        self.assertEqual(result.receipt.solver_status, "not_started")
        self.assertFalse(result.receipt.solver_started)
        self.assertGreaterEqual(result.receipt.verification_us, 0.0)
        self.assertIsNone(result.receipt.solver_us)
        self.assertEqual(calls, [])

    def test_execution_receipt_binds_inputs_and_timing(self) -> None:
        outcome = ExecutionGate(self.verifier()).execute(
            self.source,
            self.target,
            self.certificate(),
            requested_task="N1_AC",
            converter_trace=self.trace,
            solver=lambda snapshot: {"asset_count": len(snapshot["assets"])},
        )
        self.assertTrue(outcome.receipt.solver_started)
        self.assertEqual(outcome.receipt.solver_status, "completed")
        self.assertTrue(outcome.receipt.source_input_hash)
        self.assertTrue(outcome.receipt.target_input_hash)
        self.assertIsNotNone(outcome.receipt.result_hash)
        self.assertGreaterEqual(outcome.receipt.solver_us, 0.0)

    def test_uniform_evidence_row_rejects_false_prevention_claim(self) -> None:
        row = EvidenceRow(
            experiment_id="semantic-confirmatory",
            scenario_id="case14:drop:0",
            network="case14",
            data_split="development",
            environment="windows-python",
            solver="none",
            task_kind="N1_AC",
            state_id="base",
            transform_class="harmful",
            attack_family="task_asset_drop",
            baseline="pcc_v2",
            decision="reject",
            solver_status="not_started",
            solver_started=False,
            source_hash="a" * 64,
            target_hash="b" * 64,
            certificate_hash="c" * 64,
            consequence_observed=True,
            unsafe_result_prevented=True,
            reasons=("task_asset_unmapped",),
        )
        serialized = row.to_dict()
        validate_evidence_mapping(serialized)
        self.assertEqual(serialized["schema_version"], "pcc-v2-evidence-row-v1")

        invalid = EvidenceRow(**{**row.__dict__, "solver_started": True})
        with self.assertRaisesRegex(ValueError, "solver_start_status_inconsistent"):
            invalid.validate()

    def test_all_frozen_attack_families_fail_closed(self) -> None:
        source = {
            "assets": {
                f"line-{index}": {
                    "asset_type": "line",
                    "from_bus": str(index),
                    "to_bus": str(index + 1),
                    "r_pu": 0.01 + index * 0.001,
                    "x_pu": 0.10 + index * 0.001,
                    "outage_capable": True,
                }
                for index in range(4)
            }
        }
        for family in ATTACK_FAMILIES:
            with self.subTest(family=family):
                target, relations, trace = transform(source, family, 0)
                verification_source = copy.deepcopy(source)
                if family == "source_snapshot_mismatch":
                    verification_source["assets"]["line-0"]["source_version"] = "wrong"
                task = TaskContract(
                    task_id="attack:" + family,
                    task_kind="N1_AC",
                    source_assets=tuple(source["assets"]),
                    target_assets=tuple(target["assets"]),
                    intervention_type="outage",
                    required_attributes=("asset_type", "from_bus", "to_bus", "r_pu", "x_pu"),
                )
                cert = issue_v2_certificate(
                    source,
                    target,
                    task_contract=task,
                    relations=relations,
                    converter_trace=trace,
                    issuer="native-adapter",
                    private_key=self.key,
                    certificate_id="attack:" + family,
                    transformation_id="attack:" + family,
                    issued_at="2026-08-06T00:00:00Z",
                    nonce="attack:" + family,
                )
                decision = self.verifier().verify(
                    verification_source,
                    target,
                    cert,
                    requested_task="N1_AC",
                    converter_trace=trace,
                )
                self.assertNotEqual(decision.status, ACCEPT)

    def test_ambiguous_repair_fails_closed(self) -> None:
        trace = [
            {
                "source_id": "line-b",
                "target_ids": ["line-y"],
                "relation_type": "rename",
                "authoritative": True,
                "evidence_kind": "native_backlink",
            },
            {
                "source_id": "line-b",
                "target_ids": ["line-z"],
                "relation_type": "rename",
                "authoritative": True,
                "evidence_kind": "native_backlink",
            },
        ]
        result = ProofGuidedRepairer().repair(
            self.source, self.target, self.task, [self.relations[0]], trace
        )
        self.assertEqual(result.status, UNRESOLVED)
        self.assertIn("repair_evidence_ambiguous:line-b", result.reasons)


if __name__ == "__main__":
    unittest.main()
