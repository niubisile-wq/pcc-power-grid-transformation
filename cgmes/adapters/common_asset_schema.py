from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


COLUMNS = [
    "case_id",
    "tool",
    "tool_version",
    "source_path",
    "source_sha256",
    "asset_id",
    "canonical_asset_id",
    "asset_type",
    "name",
    "code",
    "bus1_id",
    "bus2_id",
    "terminal_ids",
    "p_mw",
    "q_mvar",
    "in_service",
    "r",
    "x",
    "source_representation",
    "notes",
]


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_id(value: Any) -> str:
    """Normalize formatting only; this is not an identity-equivalence decision."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    text = re.sub(r"^(?:urn:uuid:)?(?:#_?|_)?", "", text, flags=re.IGNORECASE)
    # PowSyBl represents a topological-node bus as ``<mRID>_<bus-index>``.  Removing
    # that implementation suffix recovers the declared CGMES mRID; it does not assert
    # equivalence between different source objects.
    derived_bus = re.fullmatch(
        r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})_\d+",
        text,
    )
    if derived_bus:
        text = derived_bus.group(1)
    compact = re.sub(r"[^0-9a-fA-F]", "", text)
    if len(compact) == 32:
        return compact.lower()
    return text


def safe_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    return value


def endpoint_id(value: Any) -> str:
    if value is None:
        return ""
    for attr in ("idtag", "rdfid", "code", "name"):
        if hasattr(value, attr):
            candidate = getattr(value, attr)
            if candidate not in (None, ""):
                return canonical_id(candidate)
    return canonical_id(value)


def record(**values: Any) -> dict[str, Any]:
    row = {column: safe_value(values.get(column)) for column in COLUMNS}
    row["asset_id"] = "" if row["asset_id"] is None else str(row["asset_id"])
    row["canonical_asset_id"] = canonical_id(row["asset_id"])
    terminals = values.get("terminal_ids", [])
    if isinstance(terminals, str):
        row["terminal_ids"] = terminals
    else:
        row["terminal_ids"] = json.dumps([endpoint_id(item) for item in terminals], ensure_ascii=False)
    return row


def frame(records: Iterable[dict[str, Any]]) -> pd.DataFrame:
    result = pd.DataFrame(list(records), columns=COLUMNS)
    if not result.empty:
        result = result.sort_values(
            ["asset_type", "canonical_asset_id", "name"], kind="stable"
        ).reset_index(drop=True)
    return result
