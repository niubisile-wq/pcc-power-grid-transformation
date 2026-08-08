"""Conservative, provenance-only repair for PCC v2 identity relations."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from validation.pcc_v2 import ACCEPT, UNRESOLVED, TaskContract, digest


@dataclass(frozen=True)
class RepairResult:
    status: str
    target_snapshot: Mapping[str, Any]
    relations: tuple[Mapping[str, Any], ...]
    patch: Mapping[str, Any]
    reasons: tuple[str, ...] = ()


class ProofGuidedRepairer:
    """Repair only from unique, authoritative converter evidence.

    Feature similarity, names and electrical proximity are intentionally not
    considered authoritative evidence.
    """

    _AUTHORITATIVE_KINDS = {"mrid", "native_backlink", "signed_converter_trace", "parent_relation"}

    def repair(
        self,
        source_snapshot: Mapping[str, Any],
        target_snapshot: Mapping[str, Any],
        task_contract: TaskContract,
        relations: Sequence[Mapping[str, Any]],
        converter_trace: Sequence[Mapping[str, Any]],
    ) -> RepairResult:
        target = deepcopy(target_snapshot)
        repaired_relations = [dict(relation) for relation in relations]
        covered = {
            source_id
            for relation in repaired_relations
            for source_id in relation.get("source_ids", [])
        }
        missing = [asset_id for asset_id in task_contract.source_assets if asset_id not in covered]
        operations: list[Mapping[str, Any]] = []

        for source_id in missing:
            candidates = [
                row
                for row in converter_trace
                if row.get("source_id") == source_id
                and row.get("authoritative") is True
                and row.get("evidence_kind") in self._AUTHORITATIVE_KINDS
            ]
            distinct = {
                (
                    tuple(row.get("target_ids", [])),
                    str(row.get("relation_type", "")),
                    str(row.get("evidence_kind", "")),
                )
                for row in candidates
            }
            if len(distinct) != 1:
                reason = "repair_evidence_missing" if not distinct else "repair_evidence_ambiguous"
                return RepairResult(
                    UNRESOLVED,
                    target_snapshot,
                    tuple(relations),
                    {"operations": operations},
                    (reason + ":" + source_id,),
                )

            row = candidates[0]
            target_ids = list(row.get("target_ids", []))
            relation_type = str(row.get("relation_type", ""))
            if not target_ids or relation_type not in {"exact", "rename", "split", "merge", "derived"}:
                return RepairResult(
                    UNRESOLVED,
                    target_snapshot,
                    tuple(relations),
                    {"operations": operations},
                    ("repair_trace_incomplete:" + source_id,),
                )

            for target_id in target_ids:
                if target_id in target.get("assets", {}):
                    continue
                reconstructed = row.get("reconstructed_assets", {}).get(target_id)
                if row.get("reversible") is not True or not isinstance(reconstructed, Mapping):
                    return RepairResult(
                        UNRESOLVED,
                        target_snapshot,
                        tuple(relations),
                        {"operations": operations},
                        ("target_materialization_unproven:" + target_id,),
                    )
                required = {"asset_type"}
                if not required.issubset(reconstructed):
                    return RepairResult(
                        UNRESOLVED,
                        target_snapshot,
                        tuple(relations),
                        {"operations": operations},
                        ("reconstructed_asset_incomplete:" + target_id,),
                    )
                target.setdefault("assets", {})[target_id] = deepcopy(dict(reconstructed))
                operations.append(
                    {"operation": "materialize_asset", "source_id": source_id, "target_id": target_id}
                )

            relation = {
                "source_ids": [source_id],
                "target_ids": target_ids,
                "relation_type": relation_type,
                "authoritative_evidence": {
                    "kind": row["evidence_kind"],
                    "trace_record_hash": digest(row),
                },
                "intervention_map": {source_id: target_ids},
            }
            if row.get("group_intervention_authorized") is True:
                relation["group_intervention_authorized"] = True
            repaired_relations.append(relation)
            operations.append(
                {"operation": "restore_relation", "source_id": source_id, "target_ids": target_ids}
            )

        return RepairResult(
            ACCEPT,
            target,
            tuple(repaired_relations),
            {
                "repair_policy": "provenance-only-v1",
                "operations": operations,
                "pre_target_hash": digest(target_snapshot),
                "post_target_hash": digest(target),
            },
        )

