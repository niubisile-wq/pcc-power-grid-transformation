from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "cross_environment"
CURRENT = BASE / "windows_py312" / "tool_version" / "tool_version_probe_results.csv"
LEGACY = (
    BASE
    / "windows_py312_pypowsybl112"
    / "tool_version"
    / "tool_version_probe_results.csv"
)


def main() -> None:
    for path in (CURRENT.parent, LEGACY.parent):
        lock = json.loads(
            (path / "tool_version_probe_lock.json").read_text(encoding="utf-8")
        )
        if not lock.get("created_before_attempts"):
            raise RuntimeError(f"Missing valid pre-probe lock in {path}")
    current = pd.read_csv(CURRENT, keep_default_na=False)
    legacy = pd.read_csv(LEGACY, keep_default_na=False)
    if len(current) != 4 or len(legacy) != 4:
        raise RuntimeError("Tool-version probe denominator is incomplete")
    keys = ["case_id", "family", "package_sha256", "stage"]
    left = legacy[keys + ["pypowsybl_version", "status", "asset_count", "export_sha256"]].rename(
        columns={
            "pypowsybl_version": "legacy_version",
            "status": "legacy_status",
            "asset_count": "legacy_asset_count",
            "export_sha256": "legacy_export_sha256",
        }
    )
    right = current[keys + ["pypowsybl_version", "status", "asset_count", "export_sha256"]].rename(
        columns={
            "pypowsybl_version": "current_version",
            "status": "current_status",
            "asset_count": "current_asset_count",
            "export_sha256": "current_export_sha256",
        }
    )
    comparison = left.merge(right, on=keys, validate="one_to_one")
    comparison["status_match"] = comparison.legacy_status.eq(comparison.current_status)
    both_success = comparison.legacy_status.eq("success") & comparison.current_status.eq("success")
    comparison["asset_count_match_when_both_success"] = (~both_success) | comparison.legacy_asset_count.eq(
        comparison.current_asset_count
    )
    comparison["serialized_bytes_match"] = comparison.legacy_export_sha256.eq(
        comparison.current_export_sha256
    )
    comparison.to_csv(BASE / "tool_version_comparison.csv", index=False)
    summary = {
        "evidence_role": "same_team_same_os_tool_version_sensitivity_not_final_holdout",
        "legacy_version": sorted(comparison.legacy_version.unique().tolist()),
        "current_version": sorted(comparison.current_version.unique().tolist()),
        "case_count": int(comparison.case_id.nunique()),
        "comparison_rows": len(comparison),
        "complete_denominator": len(comparison) == 4,
        "status_match_rows": int(comparison.status_match.sum()),
        "asset_count_match_success_rows": int(
            (both_success & comparison.asset_count_match_when_both_success).sum()
        ),
        "serialized_byte_identical_rows": int(comparison.serialized_bytes_match.sum()),
        "claim_limit": (
            "This fixed two-model probe tests one adjacent PyPowSyBl version pair on the same Windows/Python 3.12 host; "
            "it is not a full historical-version compatibility study."
        ),
    }
    (BASE / "tool_version_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Adjacent PyPowSyBl version-sensitivity report",
        "",
        (
            "The same two frozen CGMES 3.0 models were exported and self-reimported with "
            f"PyPowSyBl {', '.join(summary['legacy_version'])} and "
            f"{', '.join(summary['current_version'])} on Windows/Python 3.12."
        ),
        "",
        "| case | stage | legacy status | current status | status match | asset-count match when both succeed | serialized bytes match |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in comparison.itertuples(index=False):
        lines.append(
            f"| {row.case_id} | {row.stage} | {row.legacy_status} | "
            f"{row.current_status} | {row.status_match} | "
            f"{row.asset_count_match_when_both_success} | {row.serialized_bytes_match} |"
        )
    lines.extend(["", "## Scope limit", "", summary["claim_limit"]])
    (BASE / "TOOL_VERSION_SENSITIVITY_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
