from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any

from pandapower.converter.cim.cim2pp.from_cim import from_cim

from adapters.common_asset_schema import endpoint_id, record, sha256


TABLES = {
    "bus": "bus",
    "line": "line",
    "trafo": "transformer_2w",
    "trafo3w": "transformer_3w",
    "load": "load",
    "gen": "generator",
    "sgen": "static_generator",
    "ext_grid": "external_grid",
    "shunt": "shunt",
    "switch": "switch",
}


def _value(row: Any, *columns: str) -> Any:
    for column in columns:
        if column in row.index:
            value = row[column]
            if value is not None:
                return value
    return None


def _bus_origin(net: Any, value: Any) -> str:
    try:
        row = net.bus.loc[int(value)]
    except (KeyError, TypeError, ValueError):
        return endpoint_id(value)
    return endpoint_id(_value(row, "origin_id", "cim_topnode", "name"))


def load_and_extract(
    path: str | Path,
    case_id: str,
    cgmes_version: str = "2.4.15",
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    source = Path(path)
    net = from_cim(
        str(source),
        cgmes_version=cgmes_version,
        ignore_errors=False,
        run_powerflow=False,
        use_sv_data_for_assets=False,
    )
    version = importlib.metadata.version("pandapower")
    common = {
        "case_id": case_id,
        "tool": "pandapower",
        "tool_version": version,
        "source_path": source.as_posix(),
        "source_sha256": sha256(source),
        "source_representation": "pandapowerNet",
    }
    records: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for table_name, asset_type in TABLES.items():
        table = getattr(net, table_name, None)
        if table is None:
            continue
        counts[table_name] = len(table)
        for index, row in table.iterrows():
            asset_id = _value(row, "origin_id", "rdfId", "name")
            if asset_id in (None, ""):
                asset_id = f"pandapower:{table_name}:{index}"
            bus1 = _value(row, "bus", "from_bus", "hv_bus")
            bus2 = _value(row, "to_bus", "lv_bus")
            records.append(
                record(
                    **common,
                    asset_id=asset_id,
                    asset_type=asset_type,
                    name=_value(row, "name"),
                    code=None,
                    bus1_id=_bus_origin(net, bus1),
                    bus2_id=_bus_origin(net, bus2),
                    terminal_ids=[_value(row, "terminal_from"), _value(row, "terminal_to")],
                    p_mw=_value(row, "p_mw"),
                    q_mvar=_value(row, "q_mvar"),
                    in_service=_value(row, "in_service", "closed"),
                    r=_value(row, "r_ohm_per_km", "r_pu"),
                    x=_value(row, "x_ohm_per_km", "x_pu"),
                    notes=f"table={table_name};index={index}",
                )
            )
    metadata = {
        "network_name": str(getattr(net, "name", "")),
        "table_counts": counts,
        "cgmes_version": cgmes_version,
    }
    return records, metadata, []
