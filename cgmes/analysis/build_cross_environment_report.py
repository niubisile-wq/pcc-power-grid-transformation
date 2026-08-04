from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "cross_environment"
ENVIRONMENTS = {
    "windows_py312": BASE / "windows_py312" / "cross_environment_probe_results.csv",
    "linux_py311": BASE / "linux_py311" / "cross_environment_probe_results.csv",
    "linux_py312": BASE / "linux_py312" / "cross_environment_probe_results.csv",
}


def main() -> None:
    frames: dict[str, pd.DataFrame] = {}
    availability: dict[str, str] = {}
    for name, path in ENVIRONMENTS.items():
        if not path.is_file():
            availability[name] = "not_attempted_environment_unavailable"
            continue
        lock_path = path.parent / "cross_environment_probe_lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        if not lock.get("created_before_attempts"):
            raise RuntimeError(f"Missing valid pre-probe lock for {name}")
        frame = pd.read_csv(path, keep_default_na=False)
        if len(frame) != 6 or frame[["case_id", "tool"]].drop_duplicates().shape[0] != 6:
            raise RuntimeError(f"Incomplete cross-environment denominator for {name}")
        frames[name] = frame
        availability[name] = "completed"

    if "windows_py312" not in frames:
        raise RuntimeError("The frozen Windows reference probe is missing")

    keys = ["case_id", "family", "package_sha256", "tool"]
    comparison = frames["windows_py312"][keys + ["status", "asset_count"]].rename(
        columns={"status": "windows_py312_status", "asset_count": "windows_py312_assets"}
    )
    for name in ("linux_py311", "linux_py312"):
        if name in frames:
            part = frames[name][keys + ["status", "asset_count"]].rename(
                columns={"status": f"{name}_status", "asset_count": f"{name}_assets"}
            )
            comparison = comparison.merge(part, on=keys, how="outer", validate="one_to_one")
        else:
            comparison[f"{name}_status"] = "not_attempted_environment_unavailable"
            comparison[f"{name}_assets"] = ""

    all_planned_available = all(name in frames for name in ENVIRONMENTS)
    if all_planned_available:
        status_match = (
            comparison.windows_py312_status.eq(comparison.linux_py311_status)
            & comparison.windows_py312_status.eq(comparison.linux_py312_status)
        )
        all_success = (
            comparison.windows_py312_status.eq("success")
            & comparison.linux_py311_status.eq("success")
            & comparison.linux_py312_status.eq("success")
        )
        asset_match = (~all_success) | (
            comparison.windows_py312_assets.eq(comparison.linux_py311_assets)
            & comparison.windows_py312_assets.eq(comparison.linux_py312_assets)
        )
        comparison["status_reproduced_all"] = status_match
        comparison["asset_count_reproduced_all_successes"] = asset_match
        status_reproduced_rows: int | None = int(status_match.sum())
        status_mismatch_rows: int | None = int((~status_match).sum())
        asset_match_rows: int | None = int((all_success & asset_match).sum())
        asset_mismatch_rows: int | None = int((all_success & ~asset_match).sum())
    else:
        comparison["status_reproduced_all"] = "not_estimable_environment_unavailable"
        comparison["asset_count_reproduced_all_successes"] = "not_estimable_environment_unavailable"
        status_reproduced_rows = None
        status_mismatch_rows = None
        asset_match_rows = None
        asset_mismatch_rows = None
    comparison.to_csv(BASE / "cross_environment_comparison.csv", index=False)

    summary = {
        "evidence_role": "single_team_cross_environment_reproducibility_not_external_replication",
        "planned_environments": list(ENVIRONMENTS),
        "environment_availability": availability,
        "planned_environment_count": 3,
        "completed_environment_count": len(frames),
        "observed_operating_system_count": 1 if len(frames) == 1 else 2,
        "observed_python_version_count": len(frames),
        "frozen_case_count": int(comparison.case_id.nunique()),
        "tool_count": int(comparison.tool.nunique()),
        "comparison_rows": len(comparison),
        "available_environment_denominators_complete": all(len(frame) == 6 for frame in frames.values()),
        "planned_cross_environment_denominator_complete": all_planned_available,
        "status_reproduced_rows": status_reproduced_rows,
        "status_mismatch_rows": status_mismatch_rows,
        "asset_count_reproduced_success_rows": asset_match_rows,
        "asset_count_mismatch_success_rows": asset_mismatch_rows,
        "infrastructure_failure": (
            "Docker Desktop Linux engine terminated while resolving/pulling the Python base images; "
            "BuildKit reported registry metadata size-validation failures, so Linux probes were not run."
            if not all_planned_available
            else ""
        ),
        "claim_limit": (
            "Only the frozen Windows/Python 3.12 probe completed; cross-OS reproducibility is not established. "
            "The unavailable Linux environments are infrastructure non-attempts, not tool-conversion failures."
            if not all_planned_available
            else "This is a frozen two-model, three-tool single-team environment probe, not independent external replication."
        ),
    }
    (BASE / "cross_environment_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    rows = [
        "# Cross-environment reproducibility report",
        "",
        (
            "The two frozen CGMES 3.0 packages and three import tools completed on Windows/Python 3.12. "
            "The planned Linux probes were not attempted because the Docker Linux engine failed during base-image resolution."
        ),
        "",
        "| case_id | tool | Windows 3.12 | Linux 3.11 | Linux 3.12 | status match | asset-count match when all succeed |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for _, row in comparison.iterrows():
        rows.append(
            "| "
            + " | ".join(
                str(value)
                for value in (
                    row.case_id,
                    row.tool,
                    row.windows_py312_status,
                    row.linux_py311_status,
                    row.linux_py312_status,
                    row.status_reproduced_all,
                    row.asset_count_reproduced_all_successes,
                )
            )
            + " |"
        )
    rows.extend(
        [
            "",
            "## Infrastructure outcome",
            "",
            summary["infrastructure_failure"] or "All planned environments completed.",
            "",
            "## Scope limit",
            "",
            summary["claim_limit"],
        ]
    )
    (BASE / "CROSS_ENVIRONMENT_REPRODUCIBILITY_REPORT.md").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
