"""Deterministic PCC v2 verifier scaling benchmark."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import platform
import statistics
import sys
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
CGMES = ROOT / "cgmes"
if str(CGMES) not in sys.path:
    sys.path.insert(0, str(CGMES))

from validation.pcc_v2 import PCCV2Verifier, TaskContract, issue_v2_certificate  # noqa: E402


SIZES = (118, 300, 571, 1354, 2869, 9241, 13659)
WARMUP = 5
REPEATS = 30
OUTPUT = ROOT / "outputs" / "pcc_v2_scaling"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def fixture(size: int):
    source_assets = {}
    target_assets = {}
    relations = []
    trace = []
    for index in range(size):
        source_id = f"line-{index:05d}"
        target_id = f"canonical-{index:05d}"
        asset = {"asset_type": "line", "outage_capable": True, "x_pu": 0.1}
        source_assets[source_id] = dict(asset)
        target_assets[target_id] = dict(asset)
        relations.append(
            {
                "source_ids": [source_id],
                "target_ids": [target_id],
                "relation_type": "rename",
                "authoritative_evidence": {"kind": "signed_converter_trace"},
                "intervention_map": {source_id: [target_id]},
            }
        )
        trace.append(
            {
                "source_id": source_id,
                "target_ids": [target_id],
                "relation_type": "rename",
                "authoritative": True,
                "evidence_kind": "signed_converter_trace",
            }
        )
    return {"assets": source_assets}, {"assets": target_assets}, relations, trace


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    verifier = PCCV2Verifier(
        trusted_issuers={"scaling-adapter": key.public_key()},
        stateful_replay_protection=False,
    )
    rows = []
    summaries = []
    for size in SIZES:
        source, target, relations, trace = fixture(size)
        task = TaskContract(
            task_id=f"scale-{size}",
            task_kind="N1_AC",
            source_assets=tuple(source["assets"]),
            target_assets=tuple(target["assets"]),
            intervention_type="outage",
            required_attributes=("asset_type", "x_pu"),
            tolerances={"x_pu": 1e-12},
        )
        cert = issue_v2_certificate(
            source,
            target,
            task_contract=task,
            relations=relations,
            converter_trace=trace,
            issuer="scaling-adapter",
            private_key=key,
            certificate_id=f"scale-{size}",
            transformation_id=f"scale-{size}",
            issued_at="2026-08-06T00:00:00Z",
            nonce=f"scale-{size}",
        )
        for trial in range(WARMUP + REPEATS):
            started = time.perf_counter_ns()
            decision = verifier.verify(
                source,
                target,
                cert,
                requested_task="N1_AC",
                converter_trace=trace,
                record_replay=False,
            )
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
            if decision.status != "accept":
                raise RuntimeError(f"scale_verification_failed:{size}:{decision}")
            if trial >= WARMUP:
                rows.append({"asset_count": size, "trial": trial - WARMUP, "verification_ms": elapsed_ms})
        values = [row["verification_ms"] for row in rows if row["asset_count"] == size]
        summaries.append(
            {
                "asset_count": size,
                "repeats": len(values),
                "p50_ms": statistics.median(values),
                "p95_ms": percentile(values, 0.95),
                "p99_ms": percentile(values, 0.99),
                "max_ms": max(values),
                "target_ms": 50.0 if size <= 3000 else 250.0,
                "target_met": percentile(values, 0.95) <= (50.0 if size <= 3000 else 250.0),
            }
        )
    with (OUTPUT / "pcc_v2_scaling_trials.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (OUTPUT / "pcc_v2_scaling_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    summary = {
        "experiment": "pcc_v2_verifier_scaling_v1",
        "environment": f"{platform.system()}-python-{platform.python_version()}",
        "warmup": WARMUP,
        "repeats": REPEATS,
        "sizes": summaries,
        "all_targets_met": all(row["target_met"] for row in summaries),
        "scope": "single-process in-memory verifier benchmark; excludes solver and network I/O",
    }
    (OUTPUT / "pcc_v2_scaling_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
