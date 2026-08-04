from __future__ import annotations

import copy
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from validation.pcc_contract import (
    ACCEPT,
    PCCVerifier,
    digest,
    issue_certificate,
    sign,
)


class PCCContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = Ed25519PrivateKey.generate()
        self.source = {
            "assets": {
                "load-1": {"asset_type": "load", "bus": "b1", "p_mw": 10.0, "q_mvar": 4.0}
            }
        }
        self.target = {
            "assets": {
                "load-1a": {"asset_type": "load", "bus": "b1", "parent_id": "load-1", "p_mw": 6.0, "q_mvar": 2.5},
                "load-1b": {"asset_type": "load", "bus": "b1", "parent_id": "load-1", "p_mw": 4.0, "q_mvar": 1.5},
            }
        }
        self.cert = issue_certificate(
            self.source,
            self.target,
            source_ids=["load-1"],
            target_ids=["load-1a", "load-1b"],
            relation_type="lawful_split",
            common_parent="load-1",
            authorized_tasks=["PF", "N-1"],
            issuer="adapter",
            private_key=self.key,
        )

    def verifier(self) -> PCCVerifier:
        return PCCVerifier(
            contract_version="pcc-cgmes-v1",
            trusted_issuers={"adapter": self.key.public_key()},
        )

    def test_clean_lawful_split_accepts(self) -> None:
        self.assertEqual(
            self.verifier().verify(self.source, self.target, self.cert, requested_task="N-1").status,
            ACCEPT,
        )

    def test_valid_signature_does_not_override_wrong_task(self) -> None:
        cert = copy.deepcopy(self.cert)
        cert["authorized_tasks"] = ["PF"]
        cert["signature"] = sign(cert, self.key)
        decision = self.verifier().verify(self.source, self.target, cert, requested_task="N-1")
        self.assertIn("task_not_authorized", decision.reasons)

    def test_valid_signature_does_not_override_payload_tamper(self) -> None:
        cert = copy.deepcopy(self.cert)
        cert["transformation_payload"]["target_totals"]["p_mw"] = 999.0
        cert["signature"] = sign(cert, self.key)
        decision = self.verifier().verify(self.source, self.target, cert, requested_task="PF")
        self.assertIn("payload_mismatch", decision.reasons)

    def test_composition_order_and_replay_fail_closed(self) -> None:
        cert = copy.deepcopy(self.cert)
        cert["composition_chain"] = list(reversed(cert["composition_chain"]))
        cert["chain_digest"] = digest(cert["composition_chain"])
        cert["signature"] = sign(cert, self.key)
        self.assertIn(
            "composition_order_invalid",
            self.verifier().verify(self.source, self.target, cert, requested_task="PF").reasons,
        )
        verifier = self.verifier()
        self.assertEqual(verifier.verify(self.source, self.target, self.cert, requested_task="PF").status, ACCEPT)
        self.assertIn(
            "replay_detected",
            verifier.verify(self.source, self.target, self.cert, requested_task="PF").reasons,
        )


if __name__ == "__main__":
    unittest.main()
