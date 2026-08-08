"""Aggregate PCC decision reasons into an operator-facing taxonomy."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs" / "pcc_decision_reason_taxonomy"
SOURCES = [
    ("semantic_attack_matrix", ROOT / "outputs" / "pcc_v2_attack_matrix" / "attack_matrix_results.csv", "v2_decision", "v2_reasons"),
    ("dc_scopf_gate", ROOT / "outputs" / "pcc_v2_dc_scopf_gate", "gate_decision", "gate_reasons"),
    (
        "dc_scopf_case500",
        ROOT / "outputs" / "pcc_v2_dc_scopf_case500_clarabel_portfolio",
        "gate_decision",
        "gate_reasons",
    ),
    ("external_blind_roundtrip", ROOT / "outputs" / "external_tool_blind_roundtrip" / "pcc_receipts.csv", "pcc_decision", "pcc_reasons"),
]


ACTION_MAP = {
    "task_selector_not_preserved": "Repair task asset mapping or restore the missing target asset.",
    "task_target_missing": "Regenerate the target model with the declared task target present.",
    "independent_task_assets_merged": "Provide authorized aggregate intervention evidence or avoid merging independent task assets.",
    "target_identity_reused_across_independent_relations": "Assign unique target identities or provide a valid many-source relation proof.",
    "required_attribute_changed:asset_type": "Preserve the required asset type or declare a different task contract.",
    "required_attribute_changed:x": "Preserve reactance within tolerance or reissue authoritative attribute evidence.",
    "required_attribute_changed:in_service": "Preserve in-service state for the task or reissue a task-specific contract.",
    "source_snapshot_mismatch": "Reissue the certificate against the exact source snapshot.",
    "target_snapshot_mismatch": "Reissue the certificate against the exact target snapshot.",
    "converter_trace_missing": "Attach the authoritative converter trace.",
    "authoritative_identity_evidence_missing": "Attach authoritative relation evidence from the conversion route.",
    "identity_relations_missing": "Provide source-target identity relation records.",
    "task_asset_unmapped": "Map every task-selected source asset.",
}


def split_reasons(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text or text == "[]":
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text.replace("'", '"'))
            return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
    return [item.strip() for item in text.replace(",", ";").split(";") if item.strip()]


def iter_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def source_rows(source_name: str, path: Path) -> list[dict[str, str]]:
    if path.is_dir():
        rows: list[dict[str, str]] = []
        if source_name == "dc_scopf_gate":
            patterns = ["dc_scopf_gate_all_case*_offset*_1states_results.csv"]
        elif source_name == "dc_scopf_case500":
            patterns = ["dc_scopf_gate_all_case500_offset*_1states_v11_results.csv"]
        else:
            patterns = ["*_results.csv"]
        for pattern in patterns:
            for csv_path in sorted(path.glob(pattern)):
                if source_name == "dc_scopf_gate" and "case500" in csv_path.name:
                    continue
                for row in iter_csv(csv_path):
                    row["_source_file"] = csv_path.relative_to(ROOT).as_posix()
                    rows.append(row)
        return rows
    if path.is_file():
        rows = iter_csv(path)
        for row in rows:
            row["_source_file"] = path.relative_to(ROOT).as_posix()
        return rows
    return []


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    BASE.mkdir(parents=True, exist_ok=True)
    decision_counts: Counter[tuple[str, str]] = Counter()
    reason_counts: Counter[tuple[str, str, str]] = Counter()
    examples: dict[tuple[str, str, str], dict[str, object]] = {}
    rows_seen = 0
    rows_with_reasons = 0

    for source_name, path, decision_column, reason_column in SOURCES:
        rows = source_rows(source_name, path)
        for row in rows:
            rows_seen += 1
            decision = str(row.get(decision_column, "")).strip() or "missing"
            decision_counts[(source_name, decision)] += 1
            reasons = split_reasons(row.get(reason_column, ""))
            if reasons:
                rows_with_reasons += 1
            for reason in reasons:
                reason_counts[(source_name, decision, reason)] += 1
                key = (source_name, decision, reason)
                if key not in examples:
                    examples[key] = {
                        "source": source_name,
                        "decision": decision,
                        "reason": reason,
                        "example_source_file": row.get("_source_file", ""),
                        "example_network": row.get("network", ""),
                        "example_scenario": row.get("scenario_id", row.get("bundle_id", "")),
                        "example_asset_or_candidate": row.get("asset_id", row.get("omitted_candidate", "")),
                    }

    decision_rows = [
        {"source": source, "decision": decision, "count": count}
        for (source, decision), count in sorted(decision_counts.items())
    ]
    reason_rows = [
        {
            "source": source,
            "decision": decision,
            "reason": reason,
            "count": count,
            "operator_action": ACTION_MAP.get(reason, "Inspect the receipt counterexample and authoritative trace."),
        }
        for (source, decision, reason), count in sorted(reason_counts.items())
    ]
    example_rows = [
        {
            **example,
            "operator_action": ACTION_MAP.get(str(example["reason"]), "Inspect the receipt counterexample and authoritative trace."),
        }
        for example in examples.values()
    ]
    write_csv(BASE / "decision_counts.csv", decision_rows)
    write_csv(BASE / "reason_counts.csv", reason_rows)
    write_csv(BASE / "reason_examples.csv", example_rows)

    summary = {
        "protocol": "pcc_decision_reason_taxonomy_v1",
        "sources": [name for name, _path, _decision, _reason in SOURCES],
        "rows_seen": rows_seen,
        "rows_with_reasons": rows_with_reasons,
        "unique_reasons": len({reason for _source, _decision, reason in reason_counts}),
        "decision_counts": decision_rows,
        "top_reasons": sorted(reason_rows, key=lambda row: int(row["count"]), reverse=True)[:15],
        "ready": rows_seen > 0 and bool(reason_rows),
        "interpretation": (
            "PCC decisions are operator-facing: reject reasons point to repairable "
            "contract violations, while unresolved reasons identify missing evidence."
        ),
    }
    (BASE / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
