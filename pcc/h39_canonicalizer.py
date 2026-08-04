"""Production-style certificate-backed asset canonicalizer for H39.

This module is intentionally independent from the earlier reference
specification.  It uses Ed25519 signatures, binds certificates to a snapshot
hash, checks relation cardinality and conservation, and fails closed when an
identity-equivalence proof is absent.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

ACCEPT = "ACCEPT"
REJECT_INCOMPLETE = "REJECT_INCOMPLETE"
REJECT_INCONSISTENT = "REJECT_INCONSISTENT"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _unsigned(cert: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in cert.items() if k != "signature"}


def _sign(private_key: Ed25519PrivateKey, cert: Mapping[str, Any]) -> str:
    return private_key.sign(canonical_json(_unsigned(cert)).encode("utf-8")).hex()


@dataclass(frozen=True)
class Decision:
    status: str
    reasons: tuple[str, ...] = ()


class CanonicalizationRejected(ValueError):
    pass


class Canonicalizer:
    """Issue and verify signed, task-scoped asset transformations."""

    def __init__(self, snapshot: Mapping[str, Any], *, contract_version: str = "h39-v1", private_key: Ed25519PrivateKey | None = None):
        self.snapshot = json.loads(canonical_json(snapshot))
        self.contract_version = contract_version
        self.private_key = private_key or Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        self.public_key_hex = self.public_key.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        self.snapshot_hash = digest(self.snapshot)

    def _base(self, source_ids: Sequence[str], target_ids: Sequence[str], relation_type: str, task: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        chain = ["h39-canonicalizer", relation_type]
        return {
            "source_ids": list(source_ids),
            "target_ids": list(target_ids),
            "relation_type": relation_type,
            "conservation_payload": dict(payload),
            "provenance_hash": self.snapshot_hash,
            "contract_version": self.contract_version,
            "authorized_tasks": [task],
            "composition_chain": chain,
            "chain_digest": digest(chain),
            "signer_public_key": self.public_key_hex,
            "signature": None,
        }

    def issue_split(self, source_id: str, target_ids: Sequence[str], *, values: Mapping[str, Mapping[str, float]], task: str = "PF") -> dict[str, Any]:
        if source_id not in self.snapshot.get("assets", {}):
            raise CanonicalizationRejected("unknown_source_id")
        if len(target_ids) < 2 or len(set(target_ids)) != len(target_ids):
            raise CanonicalizationRejected("invalid_split_targets")
        if any(t in self.snapshot.get("assets", {}) for t in target_ids):
            raise CanonicalizationRejected("target_id_already_exists")
        source = self.snapshot["assets"][source_id]
        for field in ("p_mw", "q_mvar"):
            total = sum(float(values[t][field]) for t in target_ids)
            if not math.isclose(total, float(source[field]), rel_tol=0.0, abs_tol=1e-12):
                raise CanonicalizationRejected(f"conservation_failed:{field}")
        cert = self._base([source_id], target_ids, "lawful_split", task, {"fields": ["p_mw", "q_mvar"], "values": values})
        cert["signature"] = _sign(self.private_key, cert)
        return cert

    def issue_merge(self, source_ids: Sequence[str], target_id: str, *, values: Mapping[str, float], identity_equivalence_proof: str | None = None, task: str = "PF") -> dict[str, Any]:
        source_ids = list(source_ids)
        assets = self.snapshot.get("assets", {})
        if len(source_ids) < 2 or len(set(source_ids)) != len(source_ids):
            raise CanonicalizationRejected("merge_requires_distinct_multiple_sources")
        if any(s not in assets for s in source_ids):
            raise CanonicalizationRejected("unknown_source_id")
        if not identity_equivalence_proof:
            raise CanonicalizationRejected("identity_equivalence_unproven")
        expected = digest({"snapshot": self.snapshot_hash, "source_ids": sorted(source_ids), "target_id": target_id})
        if identity_equivalence_proof != expected:
            raise CanonicalizationRejected("invalid_identity_equivalence_proof")
        for field in ("p_mw", "q_mvar"):
            total = sum(float(assets[s][field]) for s in source_ids)
            if not math.isclose(total, float(values[field]), rel_tol=0.0, abs_tol=1e-12):
                raise CanonicalizationRejected(f"conservation_failed:{field}")
        cert = self._base(source_ids, [target_id], "lawful_merge", task, {"fields": ["p_mw", "q_mvar"], "values": dict(values), "identity_equivalence_proof": identity_equivalence_proof})
        cert["signature"] = _sign(self.private_key, cert)
        return cert

    def verify(self, certificate: Mapping[str, Any], *, requested_task: str = "PF") -> Decision:
        required = {"source_ids", "target_ids", "relation_type", "conservation_payload", "provenance_hash", "contract_version", "authorized_tasks", "composition_chain", "chain_digest", "signer_public_key", "signature"}
        missing = sorted(k for k in required if not certificate.get(k))
        if missing:
            return Decision(REJECT_INCOMPLETE, ("missing:" + ",".join(missing),))
        reasons: list[str] = []
        source_ids = list(certificate["source_ids"]); target_ids = list(certificate["target_ids"])
        assets = self.snapshot.get("assets", {})
        if any(s not in assets for s in source_ids): reasons.append("unknown_source_id")
        if len(source_ids) != len(set(source_ids)): reasons.append("duplicate_source_id")
        if certificate["provenance_hash"] != self.snapshot_hash: reasons.append("provenance_mismatch")
        if certificate["contract_version"] != self.contract_version: reasons.append("version_mismatch")
        if requested_task not in set(certificate["authorized_tasks"]): reasons.append("task_not_authorized")
        if certificate["chain_digest"] != digest(certificate["composition_chain"]): reasons.append("chain_digest_mismatch")
        if certificate["signer_public_key"] != self.public_key_hex: reasons.append("signer_key_mismatch")
        try:
            self.public_key.verify(bytes.fromhex(certificate["signature"]), canonical_json(_unsigned(certificate)).encode("utf-8"))
        except Exception:
            reasons.append("invalid_ed25519_signature")
        if certificate["relation_type"] == "lawful_split" and (len(source_ids) != 1 or len(target_ids) < 2): reasons.append("invalid_split_cardinality")
        if certificate["relation_type"] == "lawful_merge" and len(source_ids) < 2: reasons.append("invalid_merge_cardinality")
        if certificate["relation_type"] in {"feature_only_merge", "numerical_merge"}: reasons.append("identity_equivalence_unproven")
        return Decision(ACCEPT if not reasons else REJECT_INCONSISTENT, tuple(sorted(set(reasons))))
