from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any

from VeraGridEngine.IO.file_open import FileOpen, FileOpenOptions
from VeraGridEngine.enumerations import CGMESVersions, FileType

from adapters.common_asset_schema import endpoint_id, record, sha256


COLLECTIONS = {
    "buses": "bus",
    "lines": "line",
    "loads": "load",
    "generators": "generator",
    "transformers2w": "transformer_2w",
    "transformers3w": "transformer_3w",
    "switch_devices": "switch",
    "shunts": "shunt",
}


def _attribute(item: Any, *names: str) -> Any:
    for name in names:
        if hasattr(item, name):
            return getattr(item, name)
    return None


def load_and_extract(
    path: str | Path,
    case_id: str,
    cgmes_version: str = "2.4.15",
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    source = Path(path)
    versions = {
        "2.4.15": CGMESVersions.v2_4_15,
        "3.0": CGMESVersions.v3_0_0,
        "3.0.0": CGMESVersions.v3_0_0,
    }
    if cgmes_version not in versions:
        raise ValueError(f"Unsupported CGMES version: {cgmes_version}")
    options = FileOpenOptions(file_type=FileType.CGMES, cgmes_version=versions[cgmes_version])
    loader = FileOpen(str(source), options=options)
    circuit = loader.open()
    if circuit is None:
        raise RuntimeError("VeraGrid returned no circuit for an explicitly declared CGMES archive")
    try:
        version = importlib.metadata.version("VeraGrid")
    except importlib.metadata.PackageNotFoundError:
        version = importlib.metadata.version("VeraGridEngine")
    common = {
        "case_id": case_id,
        "tool": "veragrid",
        "tool_version": version,
        "source_path": source.as_posix(),
        "source_sha256": sha256(source),
        "source_representation": "VeraGrid_MultiCircuit",
    }
    records: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for collection_name, asset_type in COLLECTIONS.items():
        collection = getattr(circuit, collection_name, [])
        counts[collection_name] = len(collection)
        for item in collection:
            asset_id = _attribute(item, "idtag", "rdfid", "code", "name")
            records.append(
                record(
                    **common,
                    asset_id=asset_id,
                    asset_type=asset_type,
                    name=_attribute(item, "name"),
                    code=_attribute(item, "code"),
                    bus1_id=endpoint_id(_attribute(item, "bus", "bus_from")),
                    bus2_id=endpoint_id(_attribute(item, "bus_to")),
                    terminal_ids=[],
                    p_mw=_attribute(item, "P"),
                    q_mvar=_attribute(item, "Q"),
                    in_service=_attribute(item, "active"),
                    r=_attribute(item, "R", "r"),
                    x=_attribute(item, "X", "x"),
                    notes=f"collection={collection_name}",
                )
            )
    logs = [str(entry) for entry in loader.cgmes_logger.entries]
    metadata = {
        "network_name": str(getattr(circuit, "name", "")),
        "table_counts": counts,
        "cgmes_object_count": len(loader.cgmes_circuit.all_objects_dict) if loader.cgmes_circuit else 0,
        "cgmes_log_count": len(logs),
        "cgmes_version": cgmes_version,
    }
    return records, metadata, logs
