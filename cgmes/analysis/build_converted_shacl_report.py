from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def _classify(row: pd.Series) -> str:
    if row["status"] == "timeout":
        return "validation_timeout"
    if row["status"] == "success":
        if str(row["shacl_conforms"]).lower() == "true":
            return "shacl_conforming"
        return "shacl_nonconforming"
    message = str(row.get("error_message", ""))
    if "two elements cannot use the same ID" in message:
        return "strict_rdf_parse_duplicate_id"
    if "RDF/XML parse failures" in message:
        return "strict_rdf_parse_other"
    return "validation_execution_error_other"


def main() -> None:
    frame = pd.read_csv(
        RESULTS / "converted_cgmes3_shacl_validation_results.csv",
        keep_default_na=False,
    )
    stage5 = pd.read_csv(RESULTS / "stage5_roundtrip_matrix_results.csv")
    migration = pd.read_csv(RESULTS / "version_migration_matrix_results.csv")
    expected_stage5 = int(
        ((stage5.stage == "export") & (stage5.status == "success")).sum()
    )
    expected_migration = int(
        ((migration.stage == "export") & (migration.status == "success")).sum()
    )
    expected = expected_stage5 + expected_migration
    if len(frame) != expected or frame.artifact_id.nunique() != expected:
        raise RuntimeError(
            f"Converted SHACL denominator incomplete: {len(frame)}/{expected}"
        )
    frame["outcome_class"] = frame.apply(_classify, axis=1)
    taxonomy = (
        frame.groupby(["artifact_group", "outcome_class"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    taxonomy.to_csv(
        RESULTS / "converted_cgmes3_shacl_outcome_taxonomy.csv", index=False
    )
    conforming = frame.outcome_class.eq("shacl_conforming")
    successful = frame.status.eq("success")
    elapsed = pd.to_numeric(frame.worker_elapsed_seconds, errors="coerce").dropna()
    validation_results = pd.to_numeric(
        frame.validation_result_count, errors="coerce"
    ).fillna(0)
    peak_rss = pd.to_numeric(frame.peak_rss_mb, errors="coerce").dropna()
    summary = {
        "expected_artifacts": expected,
        "recorded_artifacts": len(frame),
        "complete_denominator": True,
        "stage5_artifacts": expected_stage5,
        "version_migration_artifacts": expected_migration,
        "outcome_counts": frame.outcome_class.value_counts().sort_index().to_dict(),
        "successful_shacl_executions": int(successful.sum()),
        "validation_result_count": int(validation_results.sum()),
        "conforming_artifacts": int(conforming.sum()),
        "nonconforming_artifacts": int(
            frame.outcome_class.eq("shacl_nonconforming").sum()
        ),
        "elapsed_seconds_p50": float(elapsed.quantile(0.50)),
        "elapsed_seconds_p95": float(elapsed.quantile(0.95)),
        "elapsed_seconds_max": float(elapsed.max()),
        "peak_worker_rss_mb_max": float(peak_rss.max()),
        "critical_pattern_shacl_passes_but_pcc_rejects_established": False,
        "critical_pattern_reason": (
            "No converted artifact both conformed to the official validation profile and "
            "supplied a native PCC certificate. A parse error, SHACL nonconformance or "
            "timeout cannot support a claim that official validation passed."
        ),
        "claim_limit": (
            "Validation applies only to successfully exported CGMES 3.0 artifacts. "
            "Upstream export failures remain in their route matrices."
        ),
    }
    if int(conforming.sum()) > 0:
        summary["critical_pattern_reason"] = (
            "At least one artifact conformed, but establishing the critical pattern also "
            "requires a predeclared identity failure and downstream task consequence; this "
            "report does not infer those links from conformance alone."
        )
    (RESULTS / "converted_cgmes3_shacl_report_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Official SHACL audit of converted CGMES 3.0 artifacts",
        "",
        (
            f"The audit retained {len(frame)}/{expected} eligible artifacts: "
            f"{expected_stage5} internal-validation round-trip exports and "
            f"{expected_migration} development version-migration exports. Upstream export "
            "failures remain in the route matrices and were not silently reclassified as "
            "SHACL attempts."
        ),
        "",
        "| artifact group | outcome class | count |",
        "| --- | --- | ---: |",
    ]
    for _, row in taxonomy.iterrows():
        lines.append(
            f"| {row.artifact_group} | {row.outcome_class} | {int(row['count'])} |"
        )
    lines.extend(
        [
            "",
            (
                f"Successful SHACL executions produced "
                f"{summary['validation_result_count']:,} validation results. Runtime over "
                f"all retained attempts was p50 {summary['elapsed_seconds_p50']:.3f} s, "
                f"p95 {summary['elapsed_seconds_p95']:.3f} s and maximum "
                f"{summary['elapsed_seconds_max']:.3f} s, including timeout durations. "
                f"Maximum recorded worker RSS was {summary['peak_worker_rss_mb_max']:.1f} MB."
            ),
            "",
            "## Claim gate",
            "",
            summary["critical_pattern_reason"],
            "",
            "Strict RDF/XML duplicate-ID errors are parse-gate failures. They must not be "
            "reported as successful SHACL executions or as SHACL nonconformance results.",
        ]
    )
    (RESULTS / "CONVERTED_CGMES3_SHACL_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
