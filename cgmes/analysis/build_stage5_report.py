from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def _read_json(name: str) -> dict[str, object]:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def _table(frame: pd.DataFrame) -> str:
    values = frame.fillna("").astype(str)
    header = "| " + " | ".join(values.columns) + " |"
    separator = "| " + " | ".join("---" for _ in values.columns) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in values.to_numpy().tolist()]
    return "\n".join([header, separator, *rows])


def main() -> None:
    direct = pd.read_csv(RESULTS / "stage5_import_matrix_results.csv", keep_default_na=False)
    roundtrip = pd.read_csv(
        RESULTS / "stage5_roundtrip_matrix_results.csv", keep_default_na=False
    )
    shacl = pd.read_csv(
        RESULTS / "cgmes_shacl_validation_results.csv", keep_default_na=False
    )
    routes = pd.read_csv(
        RESULTS / "stage5_full_roundtrip_mapping_routes.csv", keep_default_na=False
    )
    mapping = pd.read_csv(
        RESULTS / "stage5_full_roundtrip_asset_mapping.csv", keep_default_na=False
    )
    mapping_summary = _read_json("stage5_full_roundtrip_mapping_summary.json")

    denominators = {
        "direct_import_attempts": (len(direct), 60),
        "roundtrip_rows": (len(roundtrip), 160),
        "shacl_artifacts": (len(shacl), 20),
        "mapping_routes": (len(routes), 40),
    }
    incomplete = {
        name: {"recorded": recorded, "expected": expected}
        for name, (recorded, expected) in denominators.items()
        if recorded != expected
    }
    if incomplete:
        raise RuntimeError(f"Stage 5 denominator is incomplete: {incomplete}")
    if direct[["case_id", "tool"]].drop_duplicates().shape[0] != 60:
        raise RuntimeError("Stage 5 direct import case/tool keys are not unique")

    import_status = (
        direct.groupby(["tool", "status"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    roundtrip_status = (
        roundtrip.groupby(["exporter", "stage", "target_tool", "status"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    shacl_status = (
        shacl.assign(shacl_conforms=shacl.shacl_conforms.astype(str))
        .groupby(["status", "shacl_conforms"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    successful_shacl = shacl[shacl.status == "success"].copy()
    elapsed = pd.to_numeric(successful_shacl.worker_elapsed_seconds, errors="coerce")
    memory = pd.to_numeric(successful_shacl.peak_rss_mb, errors="coerce")
    elapsed_all = pd.to_numeric(shacl.worker_elapsed_seconds, errors="coerce")
    memory_all = pd.to_numeric(shacl.peak_rss_mb, errors="coerce")

    summary = {
        "stage": 5,
        "evidence_role": "internal_validation_not_untouched_final_holdout",
        "cgmes_version": "3.0.0",
        "models": 20,
        "direct_import_attempts": 60,
        "direct_import_successes": int(direct.status.eq("success").sum()),
        "direct_import_failures": int(direct.status.ne("success").sum()),
        "roundtrip_rows": 160,
        "roundtrip_success_rows": int(roundtrip.status.eq("success").sum()),
        "roundtrip_error_rows": int(roundtrip.status.eq("error").sum()),
        "roundtrip_upstream_not_attempted": int(
            roundtrip.status.eq("not_attempted_export_failed").sum()
        ),
        "export_successes": int(
            ((roundtrip.stage == "export") & (roundtrip.status == "success")).sum()
        ),
        "export_failures": int(
            ((roundtrip.stage == "export") & (roundtrip.status == "error")).sum()
        ),
        "shacl_artifacts": 20,
        "shacl_successful_executions": int(shacl.status.eq("success").sum()),
        "shacl_timeouts": int(shacl.status.eq("timeout").sum()),
        "shacl_conforming_artifacts": int(
            successful_shacl.shacl_conforms.astype(str).str.lower().eq("true").sum()
        ),
        "shacl_nonconforming_artifacts": int(
            successful_shacl.shacl_conforms.astype(str).str.lower().eq("false").sum()
        ),
        "shacl_total_validation_results": int(
            pd.to_numeric(successful_shacl.validation_result_count, errors="coerce")
            .fillna(0)
            .sum()
        ),
        "shacl_elapsed_seconds_p50_successful": float(elapsed.quantile(0.50)),
        "shacl_elapsed_seconds_p95_successful": float(elapsed.quantile(0.95)),
        "shacl_peak_rss_mb_max_successful": float(memory.max()),
        "shacl_elapsed_seconds_p50_all": float(elapsed_all.quantile(0.50)),
        "shacl_elapsed_seconds_p95_all": float(elapsed_all.quantile(0.95)),
        "shacl_peak_rss_mb_max_all": float(memory_all.max()),
        "mapping_routes": 40,
        "mapping_successful_routes": int(routes.mapping_status.eq("complete").sum()),
        "mapping_failed_routes": int(
            routes.mapping_status.eq("not_attempted_export_failed").sum()
        ),
        "mapping_relation_rows": len(mapping),
        "mapping_status_counts": mapping_summary[
            "mapping_status_counts_including_zeros"
        ],
        "complete_denominators": True,
        "claim_limits": [
            "CGMES 3.0 is an internal validation version, not an untouched final holdout.",
            "A successful SHACL execution that returns nonconformance is not an engine failure.",
            "SHACL timeouts remain in the 20-artifact denominator.",
            "Split/merge mapping labels are structural candidates until identity adjudication.",
            "No tested natural tool output natively emitted a PCC certificate.",
        ],
    }
    (RESULTS / "stage5_validation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Stage 5 CGMES 3.0 internal-validation report",
        "",
        "## Evidence role",
        "",
        (
            "These 20 frozen CGMES 3.0 packages are an internal version/network-family "
            "validation set. They are not an untouched final holdout and are not evidence "
            "of independent external replication or production-grid prevalence."
        ),
        "",
        "## Direct imports (20 models × 3 tools)",
        "",
        _table(import_status),
        "",
        "All 60 case/tool attempts are retained, including parser errors and zero-asset failures.",
        "",
        "## Round-trip matrix (20 models × 2 exporters × [1 export + 3 reimports])",
        "",
        _table(roundtrip_status),
        "",
        (
            "The 160-row denominator retains export failures and all downstream routes "
            "that were not attempted because their upstream export failed."
        ),
        "",
        "## Official CGMES 3.0 SHACL",
        "",
        _table(shacl_status),
        "",
        (
            "Official profile-matched shapes were run on each merged package graph. "
            "Untyped CIM/XML literals were enriched only in memory from official "
            "shape-declared datatypes; source archives were not rewritten."
        ),
        "",
        "## Conservative full asset census mapping",
        "",
        _table(
            pd.DataFrame(
                [
                    {"mapping_status": key, "count": value}
                    for key, value in summary["mapping_status_counts"].items()
                ]
            )
        ),
        "",
        (
            "Exact and renamed relations with unique evidence are distinguished from "
            "pending split, merge, dropped, created and ambiguous candidates. Structural "
            "similarity is not treated as identity-equivalence proof."
        ),
        "",
        "## Claim boundary",
        "",
        "- This stage does not supply an untouched final holdout.",
        "- It does not turn public test configurations into operational grid data.",
        "- It does not establish a natural anomaly prevalence rate.",
        "- It does not establish native PCC support in any tested conversion tool.",
    ]
    (RESULTS / "STAGE5_CGMES3_VALIDATION_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
