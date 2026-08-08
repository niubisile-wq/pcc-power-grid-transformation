from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import zipfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rdflib import Graph, RDF


ROOT = Path(__file__).resolve().parents[1]
CGMES = ROOT / "cgmes"
if str(CGMES) not in sys.path:
    sys.path.insert(0, str(CGMES))

from validation.execution_gate import ExecutionGate  # noqa: E402
from validation.pcc_v2 import PCCV2Verifier, TaskContract, issue_v2_certificate  # noqa: E402


SOURCE = CGMES / "corpus" / "holdout" / "powsybl_core_holdout_bundle.zip"
OUTPUT = ROOT / "outputs" / "cgmes_untouched_holdout" / "pcc_summary.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_name(term: object) -> str:
    return str(term).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def source_snapshot(path: Path) -> dict:
    graph = Graph()
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if name.lower().endswith((".xml", ".rdf")):
                graph.parse(data=archive.read(name), format="xml")
    assets = {}
    for subject, _, type_uri in graph.triples((None, RDF.type, None)):
        if local_name(type_uri) != "BaseVoltage":
            continue
        values = [value for predicate, value in graph.predicate_objects(subject) if local_name(predicate) == "BaseVoltage.nominalVoltage"]
        if values:
            assets[str(subject)] = {
                "asset_type": "BaseVoltage",
                "nominal_voltage_kv": float(values[0]),
            }
    if len(assets) < 2:
        raise RuntimeError(f"insufficient_base_voltage_task_assets:{len(assets)}")
    return {"artifact_sha256": sha256_file(path), "assets": assets}


def proof(asset_ids: tuple[str, ...], omit: str | None = None) -> tuple[list[dict], list[dict]]:
    relations = []
    trace = []
    for asset_id in asset_ids:
        if asset_id == omit:
            continue
        relations.append({
            "source_ids": [asset_id],
            "target_ids": [asset_id],
            "relation_type": "exact",
            "authoritative_evidence": {"kind": "signed_converter_trace"},
            "intervention_map": {asset_id: [asset_id]},
        })
        trace.append({
            "source_id": asset_id,
            "target_ids": [asset_id],
            "relation_type": "exact",
            "authoritative": True,
            "evidence_kind": "signed_converter_trace",
        })
    return relations, trace


def main() -> None:
    source = source_snapshot(SOURCE)
    target = json.loads(json.dumps(source))
    asset_ids = tuple(sorted(source["assets"]))
    task = TaskContract(
        task_id="untouched-holdout-base-voltage-pf",
        task_kind="PF",
        source_assets=asset_ids,
        target_assets=asset_ids,
        intervention_type="observation",
        required_attributes=("asset_type", "nominal_voltage_kv"),
        tolerances={"nominal_voltage_kv": 0.0},
    )
    key = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"powsybl-core-holdout-pcc-v1").digest())
    verifier = PCCV2Verifier(trusted_issuers={"holdout-adapter": key.public_key()})
    outcomes = {}
    for label, omitted in (("lawful_complete_proof", None), ("harmful_missing_proof", asset_ids[0])):
        relations, trace = proof(asset_ids, omitted)
        certificate = issue_v2_certificate(
            source,
            target,
            task_contract=task,
            relations=relations,
            converter_trace=trace,
            issuer="holdout-adapter",
            private_key=key,
            certificate_id=label,
            transformation_id="byte-identical-holdout",
            issued_at="2026-08-07T00:00:00Z",
            nonce=label,
        )
        solver_calls = []

        def solver(_snapshot):
            solver_calls.append(label)
            return {"status": "dry_run_only"}

        receipt = ExecutionGate(verifier).execute(
            source,
            target,
            certificate,
            requested_task="PF",
            converter_trace=trace,
            solver=solver,
        ).receipt
        outcomes[label] = {
            "decision": receipt.decision,
            "reasons": list(receipt.reasons),
            "solver_starts": len(solver_calls),
            "omitted_asset": omitted,
        }
    ready = (
        outcomes["lawful_complete_proof"]["decision"] == "accept"
        and outcomes["lawful_complete_proof"]["solver_starts"] == 1
        and outcomes["harmful_missing_proof"]["decision"] != "accept"
        and outcomes["harmful_missing_proof"]["solver_starts"] == 0
    )
    summary = {
        "protocol": "cgmes_untouched_holdout_powsybl_core_v1",
        "artifact_sha256": source["artifact_sha256"],
        "target_byte_identical": source["artifact_sha256"] == target["artifact_sha256"],
        "task_asset_count": len(asset_ids),
        "outcomes": outcomes,
        "ready": ready,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
