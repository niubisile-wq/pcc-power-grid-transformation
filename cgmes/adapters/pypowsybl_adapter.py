from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any, Callable

import pypowsybl as pp

from adapters.common_asset_schema import record, sha256


GETTERS: dict[str, tuple[str, str]] = {
    "bus": ("get_buses", "bus"),
    "line": ("get_lines", "line"),
    "load": ("get_loads", "load"),
    "generator": ("get_generators", "generator"),
    "transformer_2w": ("get_2_windings_transformers", "transformer_2w"),
    "transformer_3w": ("get_3_windings_transformers", "transformer_3w"),
    "switch": ("get_switches", "switch"),
    "shunt": ("get_shunt_compensators", "shunt"),
}


def _value(row: Any, *columns: str) -> Any:
    for column in columns:
        if column in row.index:
            return row[column]
    return None


def load_and_extract(
    path: str | Path,
    case_id: str,
    cgmes_version: str = "auto",
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    source = Path(path)
    network = pp.network.load(str(source))
    version = importlib.metadata.version("pypowsybl")
    common = {
        "case_id": case_id,
        "tool": "pypowsybl",
        "tool_version": version,
        "source_path": source.as_posix(),
        "source_sha256": sha256(source),
        "source_representation": "powsybl_network",
    }
    records: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for key, (getter_name, asset_type) in GETTERS.items():
        getter: Callable[..., Any] = getattr(network, getter_name)
        table = getter()
        counts[key] = len(table)
        for asset_id, row in table.iterrows():
            records.append(
                record(
                    **common,
                    asset_id=asset_id,
                    asset_type=asset_type,
                    name=_value(row, "name"),
                    code=None,
                    bus1_id=_value(row, "bus_id", "bus1_id"),
                    bus2_id=_value(row, "bus2_id"),
                    terminal_ids=[],
                    p_mw=_value(row, "p0", "target_p", "p"),
                    q_mvar=_value(row, "q0", "target_q", "q"),
                    in_service=_value(row, "connected", "connected1"),
                    r=_value(row, "r"),
                    x=_value(row, "x"),
                    notes=f"getter={getter_name}",
                )
            )
    metadata = {
        "network_id": network.id,
        "table_counts": counts,
        "cgmes_version": cgmes_version,
    }
    return records, metadata, []
