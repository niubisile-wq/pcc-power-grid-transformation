"""Task-semantic PCC v2 contract for power-grid model transformations.

PCC v2 extends the v1 artifact/provenance contract with machine-checkable
obligations for a named downstream task.  The verifier is deliberately
three-state: contradictory evidence is rejected, missing evidence is
unresolved, and only a complete proof is accepted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


ACCEPT = "accept"
REJECT = "reject"
UNRESOLVED = "unresolved"
V2_VERSION = "pcc-cgmes-v2"
HIGH_RISK_TASKS = {"N1_AC", "AC_OPF", "DC_SCOPF"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def unsigned(certificate: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in certificate.items() if key != "signature"}


@dataclass(frozen=True)
class TaskContract:
    task_id: str
    task_kind: str
    source_assets: tuple[str, ...]
    target_assets: tuple[str, ...]
    intervention_type: str
    required_attributes: tuple[str, ...] = ("asset_type",)
    tolerances: Mapping[str, float] = field(default_factory=dict)
    policy_version: str = "task-policy-v1"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["source_assets"] = list(self.source_assets)
        value["target_assets"] = list(self.target_assets)
        value["required_attributes"] = list(self.required_attributes)
        value["tolerances"] = dict(self.tolerances)
        return value

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TaskContract":
        return cls(
            task_id=str(value["task_id"]),
            task_kind=str(value["task_kind"]),
            source_assets=tuple(value["source_assets"]),
            target_assets=tuple(value["target_assets"]),
            intervention_type=str(value["intervention_type"]),
            required_attributes=tuple(value.get("required_attributes", ("asset_type",))),
            tolerances=dict(value.get("tolerances", {})),
            policy_version=str(value.get("policy_version", "task-policy-v1")),
        )


@dataclass(frozen=True)
class VerificationDecision:
    status: str
    reasons: tuple[str, ...] = ()
    counterexamples: tuple[Mapping[str, Any], ...] = ()


V2_MANDATORY_FIELDS = {
    "certificate_id",
    "transformation_id",
    "contract_version",
    "source_snapshot_hash",
    "target_snapshot_hash",
    "task_contract",
    "task_contract_hash",
    "relations",
    "converter_trace_hash",
    "issuer",
    "signer_public_key",
    "issued_at",
    "nonce",
    "signature",
}


def _public_key_hex(private_key: Ed25519PrivateKey) -> str:
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def issue_v2_certificate(
    source_snapshot: Mapping[str, Any],
    target_snapshot: Mapping[str, Any],
    *,
    task_contract: TaskContract,
    relations: Sequence[Mapping[str, Any]],
    converter_trace: Sequence[Mapping[str, Any]],
    issuer: str,
    private_key: Ed25519PrivateKey,
    certificate_id: str,
    transformation_id: str,
    issued_at: str,
    nonce: str,
) -> dict[str, Any]:
    """Issue a signed v2 certificate; semantic validity is checked separately."""

    task_value = task_contract.to_dict()
    certificate: dict[str, Any] = {
        "certificate_id": certificate_id,
        "transformation_id": transformation_id,
        "contract_version": V2_VERSION,
        "source_snapshot_hash": digest(source_snapshot),
        "target_snapshot_hash": digest(target_snapshot),
        "task_contract": task_value,
        "task_contract_hash": digest(task_value),
        "relations": [dict(item) for item in relations],
        "converter_trace_hash": digest(list(converter_trace)),
        "issuer": issuer,
        "signer_public_key": _public_key_hex(private_key),
        "issued_at": issued_at,
        "nonce": nonce,
        "signature": "",
    }
    certificate["signature"] = private_key.sign(
        canonical_json(unsigned(certificate)).encode("utf-8")
    ).hex()
    return certificate


def _asset(snapshot: Mapping[str, Any], asset_id: str) -> Mapping[str, Any] | None:
    value = snapshot.get("assets", {}).get(asset_id)
    return value if isinstance(value, Mapping) else None


def _close(left: Any, right: Any, tolerance: float) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance)
    return left == right


class PCCV2Verifier:
    """Verify authenticity, task coverage, identity and intervention semantics."""

    def __init__(
        self,
        *,
        trusted_issuers: Mapping[str, Ed25519PublicKey],
        legacy_verifier: Any | None = None,
        stateful_replay_protection: bool = True,
    ) -> None:
        self.trusted_issuers = dict(trusted_issuers)
        self.legacy_verifier = legacy_verifier
        self.stateful_replay_protection = stateful_replay_protection
        self._seen_nonces: set[str] = set()

    def reset_replay_state(self) -> None:
        self._seen_nonces.clear()

    def verify(
        self,
        source_snapshot: Mapping[str, Any],
        target_snapshot: Mapping[str, Any],
        certificate: Mapping[str, Any],
        *,
        requested_task: str,
        converter_trace: Sequence[Mapping[str, Any]] | None = None,
        record_replay: bool = True,
    ) -> VerificationDecision:
        version = str(certificate.get("contract_version", ""))
        if version != V2_VERSION:
            if requested_task in HIGH_RISK_TASKS:
                return VerificationDecision(UNRESOLVED, ("legacy_certificate_lacks_task_semantics",))
            if self.legacy_verifier is None:
                return VerificationDecision(UNRESOLVED, ("legacy_verifier_unavailable",))
            legacy = self.legacy_verifier.verify(
                source_snapshot, target_snapshot, certificate, requested_task=requested_task
            )
            return VerificationDecision(legacy.status, tuple(legacy.reasons))

        missing = sorted(field for field in V2_MANDATORY_FIELDS if field not in certificate)
        if missing:
            return VerificationDecision(UNRESOLVED, ("missing:" + ",".join(missing),))

        reject: list[str] = []
        unresolved: list[str] = []
        counterexamples: list[Mapping[str, Any]] = []

        if certificate.get("source_snapshot_hash") != digest(source_snapshot):
            reject.append("source_snapshot_mismatch")
        if certificate.get("target_snapshot_hash") != digest(target_snapshot):
            reject.append("target_snapshot_mismatch")

        task_value = certificate.get("task_contract")
        try:
            task = TaskContract.from_mapping(task_value)
        except (KeyError, TypeError, ValueError):
            return VerificationDecision(UNRESOLVED, ("invalid_task_contract",))
        if certificate.get("task_contract_hash") != digest(task_value):
            reject.append("task_contract_hash_mismatch")
        if requested_task not in {task.task_id, task.task_kind}:
            reject.append("task_not_authorized")
        if task.task_kind not in HIGH_RISK_TASKS and task.task_kind != "PF":
            unresolved.append("unsupported_task_kind")

        trace = list(converter_trace or [])
        if converter_trace is None:
            unresolved.append("converter_trace_missing")
        elif certificate.get("converter_trace_hash") != digest(trace):
            reject.append("converter_trace_mismatch")

        issuer = str(certificate.get("issuer", ""))
        public_key = self.trusted_issuers.get(issuer)
        if public_key is None:
            reject.append("untrusted_issuer")
        else:
            expected_key = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
            if certificate.get("signer_public_key") != expected_key:
                reject.append("signer_key_mismatch")
            try:
                public_key.verify(
                    bytes.fromhex(str(certificate.get("signature", ""))),
                    canonical_json(unsigned(certificate)).encode("utf-8"),
                )
            except Exception:
                reject.append("invalid_ed25519_signature")

        nonce = str(certificate.get("nonce", ""))
        if not nonce:
            unresolved.append("nonce_missing")
        elif self.stateful_replay_protection and nonce in self._seen_nonces:
            reject.append("replay_detected")

        relations = certificate.get("relations")
        if not isinstance(relations, list) or not relations:
            unresolved.append("identity_relations_missing")
            relations = []

        by_source: dict[str, list[Mapping[str, Any]]] = {}
        by_target: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
        for index, relation in enumerate(relations):
            if not isinstance(relation, Mapping):
                unresolved.append(f"invalid_relation:{index}")
                continue
            source_ids = list(relation.get("source_ids", []))
            target_ids = list(relation.get("target_ids", []))
            relation_type = str(relation.get("relation_type", ""))
            if not source_ids or not target_ids or not relation_type:
                unresolved.append(f"incomplete_relation:{index}")
                continue
            for source_id in source_ids:
                by_source.setdefault(source_id, []).append(relation)
                for target_id in target_ids:
                    by_target.setdefault(target_id, []).append((source_id, relation))

            if relation_type in {"exact", "rename"} and (len(source_ids) != 1 or len(target_ids) != 1):
                reject.append("one_to_one_cardinality_invalid")
            elif relation_type == "split" and (len(source_ids) != 1 or len(target_ids) < 2):
                reject.append("split_cardinality_invalid")
            elif relation_type == "merge":
                if len(source_ids) < 2 or len(target_ids) != 1:
                    reject.append("merge_cardinality_invalid")
                if any(source_id in task.source_assets for source_id in source_ids) and not relation.get(
                    "group_intervention_authorized", False
                ):
                    reject.append("independent_task_assets_merged")
            elif relation_type not in {"exact", "rename", "split", "merge", "derived"}:
                reject.append("relation_type_not_authorized")

            for source_id in source_ids:
                if _asset(source_snapshot, source_id) is None:
                    reject.append("unknown_source_asset")
            for target_id in target_ids:
                if _asset(target_snapshot, target_id) is None:
                    reject.append("unknown_target_asset")

            if not relation.get("authoritative_evidence"):
                unresolved.append("authoritative_identity_evidence_missing")
            intervention_map = relation.get("intervention_map")
            if not isinstance(intervention_map, Mapping):
                unresolved.append("intervention_map_missing")
            else:
                for source_id in source_ids:
                    if set(intervention_map.get(source_id, [])) != set(target_ids):
                        reject.append("intervention_commutativity_failed")

            for source_id in source_ids:
                source = _asset(source_snapshot, source_id)
                if source is None:
                    continue
                for target_id in target_ids:
                    target = _asset(target_snapshot, target_id)
                    if target is None:
                        continue
                    for attribute in task.required_attributes:
                        if attribute not in source or attribute not in target:
                            unresolved.append("required_attribute_missing:" + attribute)
                            continue
                        tolerance = float(task.tolerances.get(attribute, 0.0))
                        if relation_type in {"exact", "rename"} and not _close(
                            source[attribute], target[attribute], tolerance
                        ):
                            reject.append("required_attribute_changed:" + attribute)

        for target_id, assignments in by_target.items():
            source_ids = {source_id for source_id, _relation in assignments}
            relation_objects = {id(relation) for _source_id, relation in assignments}
            if len(source_ids) > 1 and len(relation_objects) > 1:
                reject.append("target_identity_reused_across_independent_relations")
                counterexamples.append(
                    {
                        "target_id": target_id,
                        "source_ids": sorted(source_ids),
                        "violation": "target_identity_reuse",
                    }
                )

        for source_id in task.source_assets:
            matches = by_source.get(source_id, [])
            if not matches:
                unresolved.append("task_asset_unmapped")
                counterexamples.append({"source_id": source_id, "violation": "missing_relation"})
            elif len(matches) > 1:
                reject.append("task_asset_mapped_multiple_times")
                counterexamples.append({"source_id": source_id, "violation": "non_unique_relation"})

        expected_targets = set(task.target_assets)
        task_mapped_targets: set[str] = set()
        for source_id in task.source_assets:
            for relation in by_source.get(source_id, []):
                task_mapped_targets.update(relation.get("target_ids", []))
        if task_mapped_targets != expected_targets:
            reject.append("task_selector_not_preserved")
            counterexamples.append(
                {
                    "violation": "task_selector_symmetric_difference",
                    "missing_targets": sorted(expected_targets - task_mapped_targets),
                    "unexpected_targets": sorted(task_mapped_targets - expected_targets),
                }
            )
        if not expected_targets:
            unresolved.append("target_task_footprint_empty")
        for target_id in expected_targets:
            target = _asset(target_snapshot, target_id)
            if target is None:
                reject.append("task_target_missing")
            elif task.intervention_type == "outage" and target.get("outage_capable") is not True:
                unresolved.append("outage_capability_unproven")
            elif task.intervention_type in {"control", "constraint"} and target.get("controllable") is not True:
                unresolved.append("control_capability_unproven")

        if reject:
            return VerificationDecision(
                REJECT, tuple(sorted(set(reject))), tuple(counterexamples)
            )
        if unresolved:
            return VerificationDecision(
                UNRESOLVED, tuple(sorted(set(unresolved))), tuple(counterexamples)
            )
        if self.stateful_replay_protection and record_replay:
            self._seen_nonces.add(nonce)
        return VerificationDecision(ACCEPT)
