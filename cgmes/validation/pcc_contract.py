"""Executable PCC sidecar contract used by the solo CGMES validation.

The verifier is deliberately fail-closed.  Ed25519 authenticates the complete
certificate, while independent checks bind it to both snapshots, the declared
identity relation, task, version, payload and composition order.  A signature
alone is never treated as proof that the transformation is lawful.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


ACCEPT = "accept"
REJECT = "reject"

MANDATORY_FIELDS = {
    "certificate_id",
    "transformation_id",
    "source_ids",
    "target_ids",
    "relation_type",
    "common_parent",
    "identity_equivalence_evidence",
    "source_snapshot_hash",
    "target_snapshot_hash",
    "provenance_hash",
    "contract_version",
    "authorized_tasks",
    "transformation_payload",
    "composition_chain",
    "chain_digest",
    "issuer",
    "signer_public_key",
    "signature",
}
EXPECTED_CHAIN = ["source_snapshot", "identity_relation", "target_snapshot"]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    return digest(snapshot)


def provenance_hash(source_hash: str, target_hash: str) -> str:
    return digest({"source_snapshot_hash": source_hash, "target_snapshot_hash": target_hash})


def public_key_hex(private_key: Ed25519PrivateKey) -> str:
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def unsigned(certificate: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in certificate.items() if key != "signature"}


def sign(certificate: Mapping[str, Any], private_key: Ed25519PrivateKey) -> str:
    return private_key.sign(canonical_json(unsigned(certificate)).encode("utf-8")).hex()


def _asset_sum(snapshot: Mapping[str, Any], ids: Sequence[str], field: str) -> float:
    return sum(float(snapshot["assets"][asset_id].get(field, 0.0)) for asset_id in ids)


def _payload(source: Mapping[str, Any], target: Mapping[str, Any], source_ids: Sequence[str], target_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "fields": ["p_mw", "q_mvar"],
        "source_totals": {
            field: _asset_sum(source, source_ids, field) for field in ("p_mw", "q_mvar")
        },
        "target_totals": {
            field: _asset_sum(target, target_ids, field) for field in ("p_mw", "q_mvar")
        },
        "source_types": [source["assets"][asset_id].get("asset_type", "") for asset_id in source_ids],
        "target_types": [target["assets"][asset_id].get("asset_type", "") for asset_id in target_ids],
    }


def issue_certificate(
    source_snapshot: Mapping[str, Any],
    target_snapshot: Mapping[str, Any],
    *,
    source_ids: Sequence[str],
    target_ids: Sequence[str],
    relation_type: str,
    authorized_tasks: Sequence[str],
    issuer: str,
    private_key: Ed25519PrivateKey,
    contract_version: str = "pcc-cgmes-v1",
    common_parent: str = "",
    identity_equivalence_evidence: str = "",
    certificate_id: str = "cert-1",
    transformation_id: str = "transform-1",
) -> dict[str, Any]:
    source_ids = list(source_ids)
    target_ids = list(target_ids)
    source_hash = snapshot_hash(source_snapshot)
    target_hash = snapshot_hash(target_snapshot)
    certificate: dict[str, Any] = {
        "certificate_id": certificate_id,
        "transformation_id": transformation_id,
        "source_ids": source_ids,
        "target_ids": target_ids,
        "relation_type": relation_type,
        "common_parent": common_parent,
        "identity_equivalence_evidence": identity_equivalence_evidence,
        "source_snapshot_hash": source_hash,
        "target_snapshot_hash": target_hash,
        "provenance_hash": provenance_hash(source_hash, target_hash),
        "contract_version": contract_version,
        "authorized_tasks": sorted(set(authorized_tasks)),
        "transformation_payload": _payload(source_snapshot, target_snapshot, source_ids, target_ids),
        "composition_chain": list(EXPECTED_CHAIN),
        "chain_digest": digest(EXPECTED_CHAIN),
        "issuer": issuer,
        "signer_public_key": public_key_hex(private_key),
        "signature": "",
    }
    certificate["signature"] = sign(certificate, private_key)
    return certificate


@dataclass(frozen=True)
class Decision:
    status: str
    reasons: tuple[str, ...]


class PCCVerifier:
    def __init__(
        self,
        *,
        contract_version: str,
        trusted_issuers: Mapping[str, Ed25519PublicKey],
        stateful_replay_protection: bool = True,
    ) -> None:
        self.contract_version = contract_version
        self.trusted_issuers = dict(trusted_issuers)
        self.stateful_replay_protection = stateful_replay_protection
        self._seen_transformations: set[str] = set()

    def reset_replay_state(self) -> None:
        self._seen_transformations.clear()

    def verify(
        self,
        source_snapshot: Mapping[str, Any],
        target_snapshot: Mapping[str, Any],
        certificate: Mapping[str, Any],
        *,
        requested_task: str,
        record_replay: bool = True,
    ) -> Decision:
        missing = sorted(field for field in MANDATORY_FIELDS if field not in certificate)
        if missing:
            return Decision(REJECT, ("missing:" + ",".join(missing),))
        reasons: list[str] = []
        source_ids = list(certificate.get("source_ids", []))
        target_ids = list(certificate.get("target_ids", []))
        source_assets = source_snapshot.get("assets", {})
        target_assets = target_snapshot.get("assets", {})
        if not source_ids or not target_ids:
            reasons.append("empty_source_or_target")
        if len(source_ids) != len(set(source_ids)):
            reasons.append("duplicate_source_id")
        if len(target_ids) != len(set(target_ids)):
            reasons.append("duplicate_target_id")
        if any(asset_id not in source_assets for asset_id in source_ids):
            reasons.append("unknown_source_id")
        if any(asset_id not in target_assets for asset_id in target_ids):
            reasons.append("unknown_target_id")

        actual_source_hash = snapshot_hash(source_snapshot)
        actual_target_hash = snapshot_hash(target_snapshot)
        if certificate.get("source_snapshot_hash") != actual_source_hash:
            reasons.append("source_snapshot_mismatch")
        if certificate.get("target_snapshot_hash") != actual_target_hash:
            reasons.append("target_snapshot_mismatch")
        expected_provenance = provenance_hash(actual_source_hash, actual_target_hash)
        if certificate.get("provenance_hash") != expected_provenance:
            reasons.append("provenance_mismatch")
        if certificate.get("contract_version") != self.contract_version:
            reasons.append("version_mismatch")
        if requested_task not in set(certificate.get("authorized_tasks", [])):
            reasons.append("task_not_authorized")
        if certificate.get("composition_chain") != EXPECTED_CHAIN:
            reasons.append("composition_order_invalid")
        if certificate.get("chain_digest") != digest(certificate.get("composition_chain")):
            reasons.append("chain_digest_mismatch")

        issuer = str(certificate.get("issuer", ""))
        public_key = self.trusted_issuers.get(issuer)
        if public_key is None:
            reasons.append("untrusted_issuer")
        else:
            expected_key = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
            if certificate.get("signer_public_key") != expected_key:
                reasons.append("signer_key_mismatch")
            try:
                public_key.verify(
                    bytes.fromhex(str(certificate.get("signature", ""))),
                    canonical_json(unsigned(certificate)).encode("utf-8"),
                )
            except Exception:
                reasons.append("invalid_ed25519_signature")

        relation = str(certificate.get("relation_type", ""))
        if relation in {"exact", "lawful_rename"}:
            if len(source_ids) != len(target_ids):
                reasons.append("one_to_one_cardinality_invalid")
            if relation == "lawful_rename" and not certificate.get("identity_equivalence_evidence"):
                reasons.append("rename_provenance_missing")
        elif relation == "lawful_split":
            if len(source_ids) != 1 or len(target_ids) < 2:
                reasons.append("split_cardinality_invalid")
            if certificate.get("common_parent") != (source_ids[0] if source_ids else ""):
                reasons.append("split_common_parent_missing")
            if source_ids and all(asset_id in target_assets for asset_id in target_ids):
                if any(target_assets[asset_id].get("parent_id") != source_ids[0] for asset_id in target_ids):
                    reasons.append("split_parent_relation_invalid")
        elif relation == "lawful_merge":
            if len(source_ids) < 2 or len(target_ids) != 1:
                reasons.append("merge_cardinality_invalid")
            expected_evidence = digest(
                {"source_ids": sorted(source_ids), "target_ids": target_ids, "relation": "lawful_merge"}
            )
            if certificate.get("identity_equivalence_evidence") != expected_evidence:
                reasons.append("identity_equivalence_unproven")
        elif relation == "derived_topology":
            if not certificate.get("common_parent"):
                reasons.append("derived_common_parent_missing")
        else:
            reasons.append("relation_not_authorized")

        if all(asset_id in source_assets for asset_id in source_ids) and all(
            asset_id in target_assets for asset_id in target_ids
        ):
            expected_payload = _payload(source_snapshot, target_snapshot, source_ids, target_ids)
            if certificate.get("transformation_payload") != expected_payload:
                reasons.append("payload_mismatch")
            for field in ("p_mw", "q_mvar"):
                if not math.isclose(
                    expected_payload["source_totals"][field],
                    expected_payload["target_totals"][field],
                    rel_tol=0.0,
                    abs_tol=1e-9,
                ):
                    reasons.append("conservation_failed:" + field)
            source_types = set(expected_payload["source_types"])
            target_types = set(expected_payload["target_types"])
            if relation not in {"derived_topology"} and source_types != target_types:
                reasons.append("asset_type_changed")

        transformation_id = str(certificate.get("transformation_id", ""))
        if self.stateful_replay_protection and transformation_id in self._seen_transformations:
            reasons.append("replay_detected")
        if reasons:
            return Decision(REJECT, tuple(sorted(set(reasons))))
        if self.stateful_replay_protection and record_replay:
            self._seen_transformations.add(transformation_id)
        return Decision(ACCEPT, ())


def provenance_signature_decision(
    source_snapshot: Mapping[str, Any],
    target_snapshot: Mapping[str, Any],
    certificate: Mapping[str, Any],
    trusted_issuers: Mapping[str, Ed25519PublicKey],
) -> Decision:
    """B6: authenticate provenance and signature, intentionally ignoring semantics."""
    reasons: list[str] = []
    source_hash = snapshot_hash(source_snapshot)
    target_hash = snapshot_hash(target_snapshot)
    if certificate.get("source_snapshot_hash") != source_hash:
        reasons.append("source_snapshot_mismatch")
    if certificate.get("target_snapshot_hash") != target_hash:
        reasons.append("target_snapshot_mismatch")
    if certificate.get("provenance_hash") != provenance_hash(source_hash, target_hash):
        reasons.append("provenance_mismatch")
    issuer = str(certificate.get("issuer", ""))
    public_key = trusted_issuers.get(issuer)
    if public_key is None:
        reasons.append("untrusted_issuer")
    else:
        try:
            public_key.verify(
                bytes.fromhex(str(certificate.get("signature", ""))),
                canonical_json(unsigned(certificate)).encode("utf-8"),
            )
        except Exception:
            reasons.append("invalid_ed25519_signature")
    return Decision(ACCEPT if not reasons else REJECT, tuple(sorted(set(reasons))))
