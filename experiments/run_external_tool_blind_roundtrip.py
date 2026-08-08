"""Run the frozen external-tool blind roundtrip challenge.

The experiment keeps route/import failures as terminal outcomes.  It freezes a
challenge manifest before PCC decisions are computed, then writes receipts and
summary statistics without outcome-dependent bundle or task exclusion.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import pypowsybl as pp

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cgmes"))

from adapters.pypowsybl_adapter import load_and_extract  # noqa: E402
from validation.execution_gate import ExecutionGate  # noqa: E402
from validation.pcc_v2 import (  # noqa: E402
    PCCV2Verifier,
    TaskContract,
    digest,
    issue_v2_certificate,
)


BASE = ROOT / "outputs" / "external_tool_blind_roundtrip"
CORPUS = ROOT / "cgmes" / "corpus" / "external_blind_roundtrip_v1"
SELECTION = CORPUS / "selection_manifest.json"
ROUTE_DIR = BASE / "route_artifacts"
MAX_TASKS_PER_BUNDLE = 20
REQUIRED_ATTRIBUTES = ("asset_type", "x", "in_service")
FROZEN_CREATED_AT = "2026-08-07T00:00:00Z"
SIGNING_KEY_BYTES = hashlib.sha256(b"external-tool-blind-roundtrip-v1-signing-key").digest()
ROUTES = (
    "source_cgmes_to_pypowsybl_to_cgmes_to_pypowsybl",
    "source_cgmes_to_veragrid_to_cgmes_to_pypowsybl",
)
BOUNDARY_BY_KIND = {
    "MiniGrid_BusBranch": ROOT
    / "cgmes"
    / "corpus"
    / "extracted"
    / "cgmes24_testconfig"
    / "MiniGrid"
    / "BusBranch"
    / "CGMES_v2.4.15_MiniGridTestConfiguration_Boundary_v3.zip",
    "MiniGrid_NodeBreaker": ROOT
    / "cgmes"
    / "corpus"
    / "extracted"
    / "cgmes24_testconfig"
    / "MiniGrid"
    / "NodeBreaker"
    / "CGMES_v2.4.15_MiniGridTestConfiguration_Boundary_v3.zip",
    "SmallGrid_BusBranch": ROOT
    / "cgmes"
    / "corpus"
    / "extracted"
    / "cgmes24_testconfig"
    / "SmallGrid"
    / "BusBranch"
    / "CGMES_v2.4.15_SmallGridTestConfiguration_Boundary_v3.0.0.zip",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_selection() -> dict[str, Any]:
    if not SELECTION.is_file():
        raise FileNotFoundError(f"Run experiments/select_external_tool_blind_corpus.py first: {SELECTION}")
    return json.loads(SELECTION.read_text(encoding="utf-8-sig"))


def snapshot(records: list[dict[str, Any]]) -> dict[str, Any]:
    assets: dict[str, dict[str, Any]] = {}
    for row in records:
        asset_id = str(row.get("canonical_asset_id") or row.get("asset_id") or "")
        if not asset_id:
            continue
        assets[asset_id] = {
            "asset_type": row.get("asset_type"),
            "name": row.get("name"),
            "bus1_id": row.get("bus1_id"),
            "bus2_id": row.get("bus2_id"),
            "x": row.get("x"),
            "r": row.get("r"),
            "in_service": bool(row.get("in_service")) if row.get("in_service") is not None else None,
            "outage_capable": row.get("asset_type") in {"line", "transformer_2w"},
        }
    return {"snapshot_version": "external-roundtrip-task-projection-v1", "assets": assets}


def eligible_tasks(records: list[dict[str, Any]], bundle_id: str) -> list[str]:
    ids = sorted(
        {
            str(row.get("canonical_asset_id") or row.get("asset_id") or "")
            for row in records
            if row.get("asset_type") in {"line", "transformer_2w"}
            and str(row.get("canonical_asset_id") or row.get("asset_id") or "")
        },
        key=lambda asset_id: hashlib.sha256(f"{bundle_id}|{asset_id}".encode("utf-8")).hexdigest(),
    )
    return ids[:MAX_TASKS_PER_BUNDLE]


def export_with_pypowsybl(source: Path, target: Path) -> tuple[str, str | None]:
    try:
        network = pp.network.load(str(source))
        target.parent.mkdir(parents=True, exist_ok=True)
        network.save(
            str(target),
            format="CGMES",
            parameters={
                "iidm.export.cgmes.profiles": "EQ,TP,SSH,SV",
                "iidm.export.cgmes.cim-version": "16",
                "iidm.export.cgmes.base-name": target.stem,
            },
        )
        pp.network.load(str(target))
        return "success", None
    except Exception as exc:  # route failures are endpoints
        return "failure", f"{type(exc).__name__}:{exc}"


def cgmes_version_for_bundle(bundle_id: str) -> str:
    return "3.0" if "CGMES_v3" in bundle_id or "v3.0" in bundle_id else "2.4.15"


def veragrid_boundary_for_bundle(bundle_id: str) -> Path | None:
    if "MiniGrid" in bundle_id:
        return BOUNDARY_BY_KIND["MiniGrid_NodeBreaker"] if "_NB_" in bundle_id else BOUNDARY_BY_KIND["MiniGrid_BusBranch"]
    if "SmallGrid" in bundle_id:
        return BOUNDARY_BY_KIND["SmallGrid_BusBranch"]
    return BOUNDARY_BY_KIND["MiniGrid_BusBranch"]


def export_with_veragrid(source: Path, target: Path, bundle_id: str) -> tuple[str, str | None, dict[str, Any]]:
    details: dict[str, Any] = {}
    try:
        from VeraGridEngine.IO.cim.cgmes.cgmes_enums import CgmesProfileType
        from VeraGridEngine.IO.file_open import FileOpen, FileOpenOptions
        from VeraGridEngine.IO.file_save import FileSave, FileSavingOptions
        from VeraGridEngine.enumerations import CGMESVersions, FileType
    except Exception as exc:
        return "dependency_missing", f"{type(exc).__name__}:{exc}", details
    version = cgmes_version_for_bundle(bundle_id)
    cgmes_version = CGMESVersions.v3_0_0 if version == "3.0" else CGMESVersions.v2_4_15
    boundary = veragrid_boundary_for_bundle(bundle_id)
    if boundary is None or not boundary.is_file():
        return "boundary_missing", f"no CGMES boundary set available for {bundle_id}", details
    details["cgmes_version"] = version
    details["boundary_path"] = boundary.relative_to(ROOT).as_posix()
    details["boundary_sha256"] = sha256(boundary)
    try:
        circuit = FileOpen(
            str(source),
            options=FileOpenOptions(file_type=FileType.CGMES, cgmes_version=cgmes_version),
        ).open()
        if circuit is None:
            return "failure", "RuntimeError:VeraGrid returned no circuit", details
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        save_log = FileSave(
            circuit,
            str(target),
            options=FileSavingOptions(
                file_type=FileType.CGMES,
                cgmes_boundary_set=str(boundary),
                cgmes_version=cgmes_version,
                cgmes_profiles=[CgmesProfileType.EQ, CgmesProfileType.TP, CgmesProfileType.SSH],
                cgmes_one_file_per_profile=False,
            ),
        ).save()
        details["veragrid_log_count"] = len(getattr(save_log, "entries", []))
        if not target.is_file() or target.stat().st_size == 0:
            return "failure", "RuntimeError:VeraGrid export did not create a non-empty archive", details
        pp.network.load(str(target))
        return "success", None, details
    except Exception as exc:  # every route failure is retained
        if target.is_file() and target.stat().st_size > 0:
            details["target_path"] = target.relative_to(ROOT).as_posix()
            details["target_sha256"] = sha256(target)
            details["target_bytes"] = target.stat().st_size
            return "target_import_failure", f"{type(exc).__name__}:{exc}", details
        return "failure", f"{type(exc).__name__}:{exc}", details


def route_target(bundle_path: Path, bundle_id: str, route: str) -> tuple[Path | None, dict[str, Any]]:
    route_record: dict[str, Any] = {
        "bundle_id": bundle_id,
        "route": route,
        "source_path": bundle_path.relative_to(ROOT).as_posix(),
        "source_sha256": sha256(bundle_path),
    }
    if route == "source_cgmes_to_pypowsybl_to_cgmes_to_pypowsybl":
        target = ROUTE_DIR / f"{bundle_id}_pypowsybl_roundtrip.zip"
        status, error = export_with_pypowsybl(bundle_path, target)
        route_record.update({"status": status, "error": error})
        if status == "success":
            route_record.update({
                "target_path": target.relative_to(ROOT).as_posix(),
                "target_sha256": sha256(target),
                "target_bytes": target.stat().st_size,
            })
            return target, route_record
        return None, route_record
    if route == "source_cgmes_to_veragrid_to_cgmes_to_pypowsybl":
        target = ROUTE_DIR / f"{bundle_id}_veragrid_roundtrip.zip"
        status, error, details = export_with_veragrid(bundle_path, target, bundle_id)
        route_record.update(details)
        route_record.update({"status": status, "error": error})
        if target.is_file() and "target_path" not in route_record:
            route_record.update({
                "target_path": target.relative_to(ROOT).as_posix(),
                "target_sha256": sha256(target),
                "target_bytes": target.stat().st_size,
            })
        return (target, route_record) if status == "success" else (None, route_record)
    route_record.update({"status": "unknown_route", "error": route})
    return None, route_record


def close_enough(left: Any, right: Any, tol: float = 1e-9) -> bool:
    if left is None or right is None:
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= tol
    return left == right


def task_status(source: dict[str, Any], target: dict[str, Any], asset_id: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    s = source["assets"].get(asset_id)
    t = target["assets"].get(asset_id)
    if s is None:
        return "invalid_source_task", ["source_asset_missing"]
    if t is None:
        return "task_relevant_anomaly", ["target_asset_missing"]
    for attribute in REQUIRED_ATTRIBUTES:
        if not close_enough(s.get(attribute), t.get(attribute), 1e-9):
            reasons.append(f"required_attribute_changed:{attribute}")
    return ("task_relevant_anomaly", reasons) if reasons else ("lawful_exact_roundtrip", [])


def make_certificate(
    private_key: Ed25519PrivateKey,
    source: dict[str, Any],
    target: dict[str, Any],
    bundle_id: str,
    route: str,
    asset_id: str,
    status: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_assets = (asset_id,)
    target_assets = (asset_id,) if asset_id in target["assets"] else ()
    contract = TaskContract(
        task_id=f"{bundle_id}:{asset_id}:N1",
        task_kind="N1_AC",
        source_assets=source_assets,
        target_assets=target_assets,
        intervention_type="outage",
        required_attributes=REQUIRED_ATTRIBUTES,
        tolerances={"x": 1e-9},
    )
    if status == "lawful_exact_roundtrip":
        relations = [{
            "source_ids": [asset_id],
            "target_ids": [asset_id],
            "relation_type": "exact",
            "authoritative_evidence": "preserved-mrid-through-external-route",
            "intervention_map": {asset_id: [asset_id]},
        }]
    else:
        relations = []
    trace = [{
        "bundle_id": bundle_id,
        "route": route,
        "asset_id": asset_id,
        "trace_role": "external_route_manifest",
        "task_status_before_pcc": status,
    }]
    certificate = issue_v2_certificate(
        source,
        target,
        task_contract=contract,
        relations=relations,
        converter_trace=trace,
        issuer="external-roundtrip-test-issuer",
        private_key=private_key,
        certificate_id=f"cert:{bundle_id}:{route}:{asset_id}",
        transformation_id=f"transform:{bundle_id}:{route}",
        issued_at="2026-08-07T00:00:00Z",
        nonce=f"nonce:{bundle_id}:{route}:{asset_id}",
    )
    return certificate, trace


def solver_stub(target_snapshot: dict[str, Any]) -> dict[str, Any]:
    return {"status": "dry_run", "asset_count": len(target_snapshot["assets"])}


def main() -> int:
    BASE.mkdir(parents=True, exist_ok=True)
    selection = read_selection()
    selected = [row for row in selection["records"] if row.get("eligible")]

    challenge_rows: list[dict[str, Any]] = []
    route_rows: list[dict[str, Any]] = []
    receipt_rows: list[dict[str, Any]] = []
    consequence_rows: list[dict[str, Any]] = []
    private_key = Ed25519PrivateKey.from_private_bytes(SIGNING_KEY_BYTES)
    verifier = PCCV2Verifier(trusted_issuers={"external-roundtrip-test-issuer": private_key.public_key()})
    gate = ExecutionGate(verifier)

    for bundle in selected:
        bundle_id = str(bundle["bundle_id"])
        bundle_path = ROOT / str(bundle["selected_path"])
        try:
            source_records, source_meta, _logs = load_and_extract(bundle_path, bundle_id)
            source_status = "success"
            source_error = None
        except Exception as exc:
            source_records, source_meta = [], {}
            source_status = "failure"
            source_error = f"{type(exc).__name__}:{exc}"
        source_snapshot = snapshot(source_records)
        tasks = eligible_tasks(source_records, bundle_id) if source_status == "success" else []
        challenge_rows.append({
            "bundle_id": bundle_id,
            "source_path": str(bundle["selected_path"]),
            "source_sha256": bundle["sha256"],
            "source_import_status": source_status,
            "source_import_error": source_error,
            "source_asset_count": len(source_records),
            "eligible_task_asset_count": len(tasks),
            "selected_task_assets": tasks,
            "source_metadata": source_meta,
        })

    challenge_manifest = {
        "protocol": "external_tool_blind_roundtrip_v1",
        "manifest_role": "challenge_manifest_frozen_before_pcc_endpoints",
        "created_at": FROZEN_CREATED_AT,
        "selection_manifest_sha256": sha256(SELECTION),
        "routes": list(ROUTES),
        "maximum_tasks_per_bundle": MAX_TASKS_PER_BUNDLE,
        "selected_bundle_count": len(selected),
        "bundles": challenge_rows,
        "no_pcc_or_operational_outcomes_used_for_selection": True,
    }
    challenge_path = BASE / "challenge_manifest.json"
    write_json(challenge_path, challenge_manifest)
    challenge_hash = sha256(challenge_path)

    for challenge in challenge_rows:
        bundle_id = challenge["bundle_id"]
        bundle_path = ROOT / challenge["source_path"]
        if challenge["source_import_status"] != "success":
            for route in ROUTES:
                route_rows.append({
                    "bundle_id": bundle_id,
                    "route": route,
                    "status": "source_import_failure",
                    "error": challenge["source_import_error"],
                    "challenge_manifest_sha256": challenge_hash,
                })
            continue
        source_records, _meta, _logs = load_and_extract(bundle_path, bundle_id)
        source_snapshot = snapshot(source_records)
        for route in ROUTES:
            target_path, route_record = route_target(bundle_path, bundle_id, route)
            route_record["challenge_manifest_sha256"] = challenge_hash
            route_rows.append(route_record)
            if target_path is None:
                continue
            try:
                target_records, target_meta, _target_logs = load_and_extract(target_path, bundle_id + ":" + route)
                target_snapshot = snapshot(target_records)
                route_record["target_import_status"] = "success"
                route_record["target_metadata"] = target_meta
            except Exception as exc:
                route_record["target_import_status"] = "failure"
                route_record["target_import_error"] = f"{type(exc).__name__}:{exc}"
                continue
            for asset_id in challenge["selected_task_assets"]:
                status, reasons = task_status(source_snapshot, target_snapshot, asset_id)
                certificate, trace = make_certificate(
                    private_key, source_snapshot, target_snapshot, bundle_id, route, asset_id, status
                )
                result = gate.execute(
                    source_snapshot,
                    target_snapshot,
                    certificate,
                    requested_task="N1_AC",
                    converter_trace=trace,
                    solver=solver_stub,
                )
                receipt = result.receipt.to_dict()
                receipt_row = {
                    "bundle_id": bundle_id,
                    "route": route,
                    "asset_id": asset_id,
                    "pre_pcc_task_status": status,
                    "pre_pcc_task_reasons": reasons,
                    "pcc_decision": receipt["decision"],
                    "pcc_reasons": list(receipt["reasons"]),
                    "solver_started": receipt["solver_started"],
                    "solver_status": receipt["solver_status"],
                    "verification_us": receipt["verification_us"],
                    "certificate_hash": receipt["certificate_hash"],
                    "challenge_manifest_sha256": challenge_hash,
                }
                receipt_rows.append(receipt_row)
                consequence_rows.append({
                    "bundle_id": bundle_id,
                    "route": route,
                    "asset_id": asset_id,
                    "task_relevant_anomaly": status == "task_relevant_anomaly",
                    "anomaly_reasons": reasons,
                    "operational_consequence_evaluated": False,
                    "operationally_consequential": False,
                    "consequence_evaluation_reason": "N-1 source-target consequence adjudicator not implemented for external CGMES roundtrip in this run",
                })

    write_json(BASE / "route_artifacts_manifest.json", {"records": route_rows})
    with (BASE / "pcc_receipts.jsonl").open("w", encoding="utf-8") as stream:
        for row in receipt_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (BASE / "consequence_labels.jsonl").open("w", encoding="utf-8") as stream:
        for row in consequence_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    if receipt_rows:
        with (BASE / "pcc_receipts.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(receipt_rows[0]))
            writer.writeheader()
            writer.writerows(receipt_rows)

    lawful = [row for row in receipt_rows if row["pre_pcc_task_status"] == "lawful_exact_roundtrip"]
    harmful = [row for row in receipt_rows if row["pre_pcc_task_status"] == "task_relevant_anomaly"]
    route_successes = [row for row in route_rows if row.get("status") == "success" and row.get("target_import_status") == "success"]
    summary = {
        "protocol": "external_tool_blind_roundtrip_v1",
        "status": "complete_without_operational_consequence_adjudication",
        "created_at": FROZEN_CREATED_AT,
        "selection_manifest": SELECTION.relative_to(ROOT).as_posix(),
        "selection_manifest_sha256": sha256(SELECTION),
        "challenge_manifest": challenge_path.relative_to(ROOT).as_posix(),
        "challenge_manifest_sha256": challenge_hash,
        "selected_bundles": len(selected),
        "source_import_successes": sum(1 for row in challenge_rows if row["source_import_status"] == "success"),
        "route_attempts": len(route_rows),
        "route_successes": len(route_successes),
        "route_dependency_failures": sum(1 for row in route_rows if row.get("status") == "dependency_missing"),
        "receipt_count": len(receipt_rows),
        "lawful_exact_roundtrips": len(lawful),
        "lawful_exact_roundtrips_accepted": sum(1 for row in lawful if row["pcc_decision"] == "accept"),
        "lawful_exact_acceptance_rate": (
            sum(1 for row in lawful if row["pcc_decision"] == "accept") / len(lawful) if lawful else None
        ),
        "external_tool_generated_task_relevant_anomalies": len(harmful),
        "harmful_task_transformations_accepted": sum(1 for row in harmful if row["pcc_decision"] == "accept"),
        "harmful_solver_starts": sum(1 for row in harmful if row["solver_started"]),
        "unresolved_roundtrips": sum(1 for row in receipt_rows if row["pcc_decision"] == "unresolved"),
        "operational_consequence_evaluated": False,
        "operationally_consequential_anomalies": 0,
        "success_criteria": {
            "harmful_solver_starts_zero": sum(1 for row in harmful if row["solver_started"]) == 0,
            "lawful_exact_acceptance_rate_one": bool(lawful) and all(row["pcc_decision"] == "accept" for row in lawful),
            "at_least_one_external_tool_generated_task_relevant_anomaly": bool(harmful),
            "at_least_one_operationally_consequential_anomaly": False,
        },
        "claim_use": "external lawfulness/anomaly screening evidence only; do not promote to main operational-consequence claim until N-1 adjudication is implemented",
        "selection_used_no_PCC_or_operational_outcomes": True,
    }
    write_json(BASE / "consequence_summary.json", {
        "operational_consequence_evaluated": False,
        "records": consequence_rows,
    })
    write_json(BASE / "summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
