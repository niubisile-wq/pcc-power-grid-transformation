"""Demonstrate orthogonality between official SHACL and PCC task evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
CGMES = ROOT / "cgmes"
if str(CGMES) not in sys.path:
    sys.path.insert(0, str(CGMES))

from validation.execution_gate import ExecutionGate  # noqa: E402
from validation.pcc_v2 import PCCV2Verifier, TaskContract, issue_v2_certificate  # noqa: E402


SOURCE = CGMES / "corpus" / "cas303_svedala_eqbd.zip"
SHACL_RESULT = (
    CGMES / "results" / "apl111_positive_control" / "cas303_svedala_eqbd.json"
)
OUTPUT = ROOT / "outputs" / "cgmes_apl111_pcc_separation" / "separation_summary.json"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
CIM = "http://iec.ch/TC57/CIM100#"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_snapshot(path: Path) -> dict:
    assets: dict[str, dict] = {}
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".xml")]
        if members != ["Svedala_EQBD.xml"]:
            raise RuntimeError(f"unexpected_official_package_members:{members}")
        root = ET.fromstring(archive.read(members[0]))
    for element in root.findall(f"{{{CIM}}}BaseVoltage"):
        asset_id = element.attrib.get(f"{{{RDF}}}ID", "").removeprefix("_")
        nominal = element.find(f"{{{CIM}}}BaseVoltage.nominalVoltage")
        if not asset_id or nominal is None or nominal.text is None:
            raise RuntimeError("incomplete_base_voltage_record")
        assets[asset_id] = {
            "asset_type": "BaseVoltage",
            "nominal_voltage_kv": float(nominal.text),
        }
    if len(assets) < 2:
        raise RuntimeError("insufficient_task_assets")
    return {"artifact_sha256": sha256_file(path), "assets": assets}


def main() -> None:
    shacl = json.loads(SHACL_RESULT.read_text(encoding="utf-8"))
    if shacl.get("status") != "success" or shacl.get("shacl_conforms") is not True:
        raise RuntimeError("official_positive_control_does_not_conform")
    source = source_snapshot(SOURCE)
    if shacl.get("source_sha256") != source["artifact_sha256"]:
        raise RuntimeError("positive_control_hash_mismatch")

    # The target artifact is byte-identical to the official source.  PCC is
    # challenged only by incomplete transformation evidence: the first task
    # asset has no identity relation or converter-trace entry.
    target = json.loads(json.dumps(source))
    asset_ids = tuple(source["assets"])
    omitted = asset_ids[0]
    relations = []
    trace = []
    for asset_id in asset_ids[1:]:
        relations.append(
            {
                "source_ids": [asset_id],
                "target_ids": [asset_id],
                "relation_type": "exact",
                "authoritative_evidence": {"kind": "signed_converter_trace"},
                "intervention_map": {asset_id: [asset_id]},
            }
        )
        trace.append(
            {
                "source_id": asset_id,
                "target_ids": [asset_id],
                "relation_type": "exact",
                "authoritative": True,
                "evidence_kind": "signed_converter_trace",
            }
        )
    task = TaskContract(
        task_id="svedala-base-voltage-pf",
        task_kind="PF",
        source_assets=asset_ids,
        target_assets=asset_ids,
        intervention_type="observation",
        required_attributes=("asset_type", "nominal_voltage_kv"),
        tolerances={"nominal_voltage_kv": 0.0},
    )
    key = Ed25519PrivateKey.from_private_bytes(
        hashlib.sha256(b"apl111-svedala-pcc-separation-v1").digest()
    )
    certificate = issue_v2_certificate(
        source,
        target,
        task_contract=task,
        relations=relations,
        converter_trace=trace,
        issuer="cas303-byte-preserving-adapter",
        private_key=key,
        certificate_id="svedala-eqbd-incomplete-task-proof",
        transformation_id="svedala-eqbd-byte-identical",
        issued_at="2026-08-07T00:00:00Z",
        nonce="svedala-eqbd-separation-v1",
    )
    solver_calls: list[str] = []

    def forbidden_solver(_snapshot):
        solver_calls.append(task.task_id)
        return {"status": "should_not_run"}

    receipt = ExecutionGate(
        PCCV2Verifier(
            trusted_issuers={"cas303-byte-preserving-adapter": key.public_key()}
        )
    ).execute(
        source,
        target,
        certificate,
        requested_task="PF",
        converter_trace=trace,
        solver=forbidden_solver,
    ).receipt
    ready = (
        shacl["shacl_conforms"] is True
        and receipt.decision != "accept"
        and len(solver_calls) == 0
        and source["artifact_sha256"] == target["artifact_sha256"]
    )
    summary = {
        "experiment": "cgmes_apl111_pcc_orthogonal_separation_v1",
        "official_source": "ENTSO-E CAS 3.0.3 Svedala_EQBD.xml",
        "official_artifact_sha256": source["artifact_sha256"],
        "target_byte_identical": source["artifact_sha256"] == target["artifact_sha256"],
        "official_shapes_version": shacl["official_shapes_version"],
        "official_shacl_status": shacl["status"],
        "official_shacl_conforms": shacl["shacl_conforms"],
        "official_shacl_results": shacl["validation_result_count"],
        "task_kind": task.task_kind,
        "task_asset_count": len(asset_ids),
        "omitted_task_evidence_asset": omitted,
        "pcc_decision": receipt.decision,
        "pcc_reasons": list(receipt.reasons),
        "solver_starts": len(solver_calls),
        "ready": ready,
        "interpretation": (
            "The official target remains SHACL-conforming, while PCC fails closed "
            "because the proof does not cover every declared task asset."
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

