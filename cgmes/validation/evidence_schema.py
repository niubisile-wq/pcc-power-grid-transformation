"""Uniform, fail-fast evidence rows for PCC v2 experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any, Mapping


EVIDENCE_SCHEMA_VERSION = "pcc-v2-evidence-row-v1"
DECISIONS = {"accept", "reject", "unresolved", "not_run"}
SOLVER_STATUSES = {"completed", "failed", "not_started", "not_run"}


@dataclass(frozen=True)
class EvidenceRow:
    experiment_id: str
    scenario_id: str
    network: str
    data_split: str
    environment: str
    solver: str
    task_kind: str
    state_id: str
    transform_class: str
    attack_family: str
    baseline: str
    decision: str
    solver_status: str
    solver_started: bool
    source_hash: str
    target_hash: str
    certificate_hash: str
    consequence_observed: bool
    unsafe_result_prevented: bool
    failure_class: str = ""
    reasons: tuple[str, ...] = ()
    verification_us: float | None = None
    solver_us: float | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = EVIDENCE_SCHEMA_VERSION

    def validate(self) -> None:
        required = {
            "experiment_id": self.experiment_id,
            "scenario_id": self.scenario_id,
            "network": self.network,
            "data_split": self.data_split,
            "environment": self.environment,
            "task_kind": self.task_kind,
            "state_id": self.state_id,
            "transform_class": self.transform_class,
            "baseline": self.baseline,
            "source_hash": self.source_hash,
            "target_hash": self.target_hash,
        }
        missing = sorted(key for key, value in required.items() if not str(value).strip())
        if missing:
            raise ValueError("missing_evidence_fields:" + ",".join(missing))
        if self.decision not in DECISIONS:
            raise ValueError("invalid_decision:" + self.decision)
        if self.solver_status not in SOLVER_STATUSES:
            raise ValueError("invalid_solver_status:" + self.solver_status)
        if self.solver_started != (self.solver_status in {"completed", "failed"}):
            raise ValueError("solver_start_status_inconsistent")
        if self.unsafe_result_prevented and (
            not self.consequence_observed or self.solver_started
        ):
            raise ValueError("invalid_prevention_claim")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        value = asdict(self)
        value["reasons"] = ";".join(self.reasons)
        value["metrics_json"] = json.dumps(
            value.pop("metrics"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return value


def validate_evidence_mapping(row: Mapping[str, Any]) -> None:
    """Validate serialized rows before archival or aggregation."""

    required = {field.name for field in EvidenceRow.__dataclass_fields__.values()}
    serialized = (required - {"metrics", "reasons"}) | {"metrics_json", "reasons"}
    missing = sorted(serialized - set(row))
    if missing:
        raise ValueError("missing_serialized_evidence_fields:" + ",".join(missing))
    try:
        json.loads(str(row["metrics_json"]))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_metrics_json") from exc
