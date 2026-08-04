"""Reference contract verifier for H39.

This is a protocol-level executable specification, not the production verifier
and not evidence that the manuscript's experiments have been run.
It intentionally uses a pluggable signature checker; cryptographic deployment
must be implemented with a standard library/provider such as Ed25519.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence


ACCEPT = "ACCEPT"
REJECT_INCOMPLETE = "REJECT_INCOMPLETE"
REJECT_INCONSISTENT = "REJECT_INCONSISTENT"

MANDATORY_CERT_FIELDS = {
    "source_ids",
    "target_ids",
    "relation_type",
    "conservation_payload",
    "provenance_hash",
    "contract_version",
    "authorized_tasks",
    "composition_chain",
    "chain_digest",
    "signature",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()


def reference_signature(certificate: Mapping[str, Any]) -> str:
    """Deterministic integrity token for tests; not a cryptographic signature."""
    unsigned = {k: v for k, v in certificate.items() if k != "signature"}
    return hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VerificationResult:
    decision: str
    reasons: tuple[str, ...] = ()


def _missing(mapping: Mapping[str, Any], keys: Iterable[str]) -> List[str]:
    return sorted(k for k in keys if k not in mapping or mapping[k] in (None, ""))


def verify_certificate(
    snapshot: Mapping[str, Any],
    certificate: Mapping[str, Any],
    *,
    expected_version: str,
    requested_task: str,
    signature_checker: Callable[[Mapping[str, Any]], bool] | None = None,
) -> VerificationResult:
    """Verify the contract boundary and fail closed on missing semantics."""

    missing = _missing(certificate, MANDATORY_CERT_FIELDS)
    if missing:
        return VerificationResult(REJECT_INCOMPLETE, (f"missing:{','.join(missing)}",))

    reasons: List[str] = []
    source_ids = list(certificate["source_ids"])
    target_ids = list(certificate["target_ids"])
    assets = snapshot.get("assets", {})

    if not source_ids or not target_ids:
        reasons.append("empty_source_or_target")
    if len(source_ids) != len(set(source_ids)):
        reasons.append("duplicate_source_id")
    if any(asset_id not in assets for asset_id in source_ids):
        reasons.append("unknown_source_id")
    if certificate["contract_version"] != expected_version:
        reasons.append("version_mismatch")
    if requested_task not in set(certificate["authorized_tasks"]):
        reasons.append("task_not_authorized")
    if certificate["provenance_hash"] != snapshot_hash(snapshot):
        reasons.append("provenance_mismatch")
    if not certificate["relation_type"]:
        reasons.append("empty_relation_type")
    relation_type = str(certificate["relation_type"])
    # Numerical aggregation is not evidence of semantic equivalence.  The
    # reference policy therefore requires an explicit lawful relation for any
    # operation that changes asset cardinality; feature-only merges are
    # rejected even when their conservation payload is numerically valid.
    if relation_type in {"feature_only_merge", "numerical_merge"} and len(source_ids) > 1:
        reasons.append("identity_equivalence_unproven")
    if relation_type == "lawful_split" and len(target_ids) < 2:
        reasons.append("split_target_cardinality_invalid")
    if relation_type == "lawful_merge" and len(source_ids) < 2:
        reasons.append("merge_source_cardinality_invalid")
    if not isinstance(certificate["composition_chain"], list):
        reasons.append("invalid_composition_chain")
    elif certificate["chain_digest"] != hashlib.sha256(
        canonical_json(certificate["composition_chain"]).encode("utf-8")
    ).hexdigest():
        reasons.append("composition_chain_digest_mismatch")

    if signature_checker is not None and not signature_checker(certificate):
        reasons.append("invalid_signature")

    if reasons:
        return VerificationResult(REJECT_INCONSISTENT, tuple(sorted(set(reasons))))
    return VerificationResult(ACCEPT)


def compose_certificates(first: Mapping[str, Any], second: Mapping[str, Any]) -> Dict[str, Any]:
    """Compose two certificates only when the boundary IDs and contracts match."""

    if set(first["target_ids"]) != set(second["source_ids"]):
        raise ValueError("composition_boundary_mismatch")
    if first["contract_version"] != second["contract_version"]:
        raise ValueError("composition_version_mismatch")
    if first["provenance_hash"] != second["provenance_hash"]:
        raise ValueError("composition_provenance_mismatch")

    return {
        "source_ids": list(first["source_ids"]),
        "target_ids": list(second["target_ids"]),
        "relation_type": f"{first['relation_type']}+{second['relation_type']}",
        "conservation_payload": {
            "first": first["conservation_payload"],
            "second": second["conservation_payload"],
        },
        "provenance_hash": first["provenance_hash"],
        "contract_version": first["contract_version"],
        "authorized_tasks": sorted(
            set(first["authorized_tasks"]).intersection(second["authorized_tasks"])
        ),
        "composition_chain": [*first["composition_chain"], *second["composition_chain"]],
        "chain_digest": hashlib.sha256(
            canonical_json([*first["composition_chain"], *second["composition_chain"]]).encode("utf-8")
        ).hexdigest(),
        "signature": None,
    }


def make_fixture() -> tuple[Dict[str, Any], Dict[str, Any]]:
    snapshot = {
        "assets": {
            "a1": {"asset_type": "bus", "identity": "A"},
            "a2": {"asset_type": "bus", "identity": "B"},
        },
        "schema": "h39-v1",
    }
    certificate = {
        "source_ids": ["a1"],
        "target_ids": ["g1", "g2"],
        "relation_type": "lawful_split",
        "conservation_payload": {"p": "sum"},
        "provenance_hash": snapshot_hash(snapshot),
        "contract_version": "h39-v1",
        "authorized_tasks": ["PF"],
        "composition_chain": ["c1", "c2"],
        "chain_digest": hashlib.sha256(canonical_json(["c1", "c2"]).encode("utf-8")).hexdigest(),
        "signature": "pending",
    }
    certificate["signature"] = reference_signature(certificate)
    return snapshot, certificate


def run_reference_properties() -> Dict[str, str]:
    snapshot, certificate = make_fixture()
    outcomes: Dict[str, str] = {}

    outcomes["P1_identity_and_complete_contract"] = verify_certificate(
        snapshot, certificate, expected_version="h39-v1", requested_task="PF"
    ).decision

    missing = dict(certificate)
    missing.pop("provenance_hash")
    outcomes["P2_missing_semantics_fail_closed"] = verify_certificate(
        snapshot, missing, expected_version="h39-v1", requested_task="PF"
    ).decision

    wrong_task = verify_certificate(
        snapshot, certificate, expected_version="h39-v1", requested_task="OPF"
    )
    outcomes["P3_task_authorization"] = wrong_task.decision

    wrong_version = verify_certificate(
        snapshot, certificate, expected_version="h39-v2", requested_task="PF"
    )
    outcomes["P4_version_binding"] = wrong_version.decision

    wrong_source = dict(certificate)
    wrong_source["provenance_hash"] = "0" * 64
    outcomes["P5_provenance_binding"] = verify_certificate(
        snapshot, wrong_source, expected_version="h39-v1", requested_task="PF"
    ).decision

    second = dict(certificate)
    second["source_ids"] = ["g1", "g2"]
    second["target_ids"] = ["z1"]
    composed = compose_certificates(certificate, second)
    outcomes["P6_composition"] = composed["target_ids"][0]

    numeric_alias = dict(certificate)
    numeric_alias["source_ids"] = ["a1", "a2"]
    numeric_alias["relation_type"] = "feature_only_merge"
    numeric_alias["signature"] = reference_signature(numeric_alias)
    outcomes["P7_numeric_alias_without_identity_proof"] = verify_certificate(
        snapshot, numeric_alias, expected_version="h39-v1", requested_task="PF"
    ).decision

    assert outcomes["P1_identity_and_complete_contract"] == ACCEPT
    assert outcomes["P2_missing_semantics_fail_closed"] == REJECT_INCOMPLETE
    assert outcomes["P3_task_authorization"] == REJECT_INCONSISTENT
    assert outcomes["P4_version_binding"] == REJECT_INCONSISTENT
    assert outcomes["P5_provenance_binding"] == REJECT_INCONSISTENT
    assert outcomes["P6_composition"] == "z1"
    assert outcomes["P7_numeric_alias_without_identity_proof"] == REJECT_INCONSISTENT
    return outcomes


if __name__ == "__main__":
    print(json.dumps(run_reference_properties(), ensure_ascii=False, indent=2))
