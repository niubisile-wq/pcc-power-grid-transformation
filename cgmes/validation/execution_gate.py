"""Runtime admission gate and immutable-style execution receipts for PCC v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import time
from typing import Any, Callable, Mapping, Sequence

from validation.pcc_v2 import ACCEPT, PCCV2Verifier, canonical_json, digest


@dataclass(frozen=True)
class ExecutionReceipt:
    receipt_version: str
    certificate_hash: str
    decision: str
    reasons: tuple[str, ...]
    requested_task: str
    solver_status: str
    solver_started: bool
    source_input_hash: str
    target_input_hash: str
    result_hash: str | None
    verification_us: float
    solver_us: float | None
    started_at: str | None
    completed_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GateResult:
    receipt: ExecutionReceipt
    result: Any = None


class ExecutionGate:
    def __init__(self, verifier: PCCV2Verifier) -> None:
        self.verifier = verifier

    def execute(
        self,
        source_snapshot: Mapping[str, Any],
        target_snapshot: Mapping[str, Any],
        certificate: Mapping[str, Any],
        *,
        requested_task: str,
        converter_trace: Sequence[Mapping[str, Any]],
        solver: Callable[[Mapping[str, Any]], Any],
    ) -> GateResult:
        verification_started = time.perf_counter_ns()
        decision = self.verifier.verify(
            source_snapshot,
            target_snapshot,
            certificate,
            requested_task=requested_task,
            converter_trace=converter_trace,
        )
        verification_us = (time.perf_counter_ns() - verification_started) / 1000.0
        certificate_hash = digest(certificate)
        source_input_hash = digest(source_snapshot)
        target_input_hash = digest(target_snapshot)
        if decision.status != ACCEPT:
            receipt = ExecutionReceipt(
                receipt_version="execution-receipt-v1",
                certificate_hash=certificate_hash,
                decision=decision.status,
                reasons=decision.reasons,
                requested_task=requested_task,
                solver_status="not_started",
                solver_started=False,
                source_input_hash=source_input_hash,
                target_input_hash=target_input_hash,
                result_hash=None,
                verification_us=verification_us,
                solver_us=None,
                started_at=None,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            return GateResult(receipt)

        started_at = datetime.now(timezone.utc).isoformat()
        solver_started = time.perf_counter_ns()
        try:
            result = solver(target_snapshot)
        except Exception as exc:
            solver_us = (time.perf_counter_ns() - solver_started) / 1000.0
            receipt = ExecutionReceipt(
                receipt_version="execution-receipt-v1",
                certificate_hash=certificate_hash,
                decision=decision.status,
                reasons=("solver_error:" + type(exc).__name__,),
                requested_task=requested_task,
                solver_status="failed",
                solver_started=True,
                source_input_hash=source_input_hash,
                target_input_hash=target_input_hash,
                result_hash=None,
                verification_us=verification_us,
                solver_us=solver_us,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            return GateResult(receipt)

        solver_us = (time.perf_counter_ns() - solver_started) / 1000.0
        try:
            result_hash = digest(result)
        except (TypeError, ValueError):
            result_hash = digest({"repr": repr(result), "canonicalizer": canonical_json.__name__})
        receipt = ExecutionReceipt(
            receipt_version="execution-receipt-v1",
            certificate_hash=certificate_hash,
            decision=decision.status,
            reasons=decision.reasons,
            requested_task=requested_task,
            solver_status="completed",
            solver_started=True,
            source_input_hash=source_input_hash,
            target_input_hash=target_input_hash,
            result_hash=result_hash,
            verification_us=verification_us,
            solver_us=solver_us,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        return GateResult(receipt, result)
