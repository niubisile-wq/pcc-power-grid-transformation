from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def read_json(name: str) -> dict[str, object]:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    values = frame.fillna("").astype(str)
    header = "| " + " | ".join(values.columns) + " |"
    rule = "| " + " | ".join("---" for _ in values.columns) + " |"
    body = ["| " + " | ".join(row) + " |" for row in values.to_numpy().tolist()]
    return "\n".join([header, rule, *body])


def main() -> None:
    direct = pd.read_csv(RESULTS / "stage2_import_matrix_results.csv", keep_default_na=False)
    direct_retry = pd.read_csv(
        RESULTS / "stage2_boundary_retry_results.csv", keep_default_na=False
    )
    roundtrip = pd.read_csv(
        RESULTS / "stage2_roundtrip_matrix_results.csv", keep_default_na=False
    )
    roundtrip_retry = pd.read_csv(
        RESULTS / "stage2_roundtrip_boundary_retry_results.csv",
        keep_default_na=False,
    )
    routes = pd.read_csv(
        RESULTS / "stage2_full_roundtrip_mapping_routes.csv", keep_default_na=False
    )
    mapping = pd.read_csv(
        RESULTS / "stage2_full_roundtrip_asset_mapping.csv", keep_default_na=False
    )
    baseline = read_json("baseline_comparison_summary.json")
    performance = read_json("pcc_performance_summary.json")
    mapping_summary = read_json("stage2_full_roundtrip_mapping_summary.json")

    if len(direct) != 96 or len(roundtrip) != 256 or len(routes) != 64:
        raise RuntimeError("Stage 2 denominator is incomplete")
    raw_reimport_mask = (roundtrip.stage == "reimport") & (roundtrip.status == "error")
    if len(roundtrip_retry) != int(raw_reimport_mask.sum()):
        raise RuntimeError("Round-trip retry denominator does not match raw errors")

    import_status = (
        direct.groupby(["tool", "status"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    roundtrip_status = (
        roundtrip.groupby(["stage", "exporter", "target_tool", "status"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    retry_taxonomy = (
        roundtrip_retry.groupby(["raw_failure_class", "retry_status"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    mapping_counts = pd.DataFrame(
        [
            {"mapping_status": key, "count": value}
            for key, value in mapping_summary[
                "mapping_status_counts_including_zeros"
            ].items()
        ]
    )
    route_failures = routes[routes.mapping_status != "complete"][
        ["case_id", "exporter", "error_type", "error_message"]
    ]

    raw_reimport_failures = int(raw_reimport_mask.sum())
    raw_export_failures = int(
        ((roundtrip.stage == "export") & (roundtrip.status == "error")).sum()
    )
    recovered = int(roundtrip_retry.retry_status.eq("success").sum())
    still_failed = int(roundtrip_retry.retry_status.ne("success").sum())
    summary = {
        "stage": 2,
        "direct_import_attempts": len(direct),
        "direct_import_successes": int(direct.status.eq("success").sum()),
        "direct_import_raw_failures": int(direct.status.ne("success").sum()),
        "direct_import_boundary_retry_attempts": len(direct_retry),
        "direct_import_boundary_retry_successes": int(
            direct_retry.retry_status.eq("success").sum()
        ),
        "roundtrip_attempt_rows": len(roundtrip),
        "roundtrip_success_rows": int(roundtrip.status.eq("success").sum()),
        "roundtrip_raw_errors": raw_reimport_failures + raw_export_failures,
        "roundtrip_raw_export_errors": raw_export_failures,
        "roundtrip_raw_reimport_errors": raw_reimport_failures,
        "roundtrip_upstream_not_attempted": int(
            roundtrip.status.eq("not_attempted_export_failed").sum()
        ),
        "roundtrip_boundary_retry_attempts": len(roundtrip_retry),
        "roundtrip_boundary_retry_successes": recovered,
        "roundtrip_boundary_retry_failures": still_failed,
        "mapping_routes_expected": 64,
        "mapping_routes_complete": int(routes.mapping_status.eq("complete").sum()),
        "mapping_routes_export_failed": int(
            routes.mapping_status.eq("not_attempted_export_failed").sum()
        ),
        "mapping_relation_rows": len(mapping),
        "mapping_status_counts": mapping_summary[
            "mapping_status_counts_including_zeros"
        ],
        "baseline_cases": baseline["case_count"],
        "baseline_decisions": baseline["decision_count"],
        "baseline_count": baseline["baseline_count"],
        "official_cgmes_2415_shacl_status": (
            "unresolved_no_applicable_official_version_matched_shape_set"
        ),
        "pcc_verification_trials": performance["verification_trials"],
        "pcc_latency_ms_p50": performance["latency_ms_p50"],
        "pcc_latency_ms_p95": performance["latency_ms_p95"],
        "pcc_latency_ms_p99": performance["latency_ms_p99"],
        "raw_failures_retained": True,
        "route_denominators_complete": True,
        "claim_limits": [
            "CGMES 2.4.15 B2 remains unresolved; local RDFS diagnostics are not relabeled as official SHACL.",
            "Boundary retries are diagnostic secondary analyses and do not replace raw failures.",
            "Split/merge mapping rows are structural candidates pending identity adjudication.",
            "Natural-tool PCC decisions use a disclosed post-conversion sidecar; no tested tool emitted a native PCC certificate.",
        ],
    }
    (RESULTS / "stage2_complete_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    lines = [
        "# Stage 2 complete toolchain, mapping, baseline and failure report",
        "",
        "## Scope and denominator",
        "",
        (
            f"The frozen development corpus contains 32 included CGMES 2.4.15 model "
            f"bundles. Direct import produced {len(direct)}/96 recorded attempts. The "
            f"full round-trip matrix produced {len(roundtrip)}/256 recorded rows "
            f"(32 models × 2 exporters × [1 export + 3 reimports])."
        ),
        "",
        "Raw errors and upstream-not-attempted routes remain in every denominator. "
        "Adding the exact registered official boundary is reported only as a secondary "
        "diagnostic retry and never overwrites a raw result.",
        "",
        "## Direct import",
        "",
        table(import_status),
        "",
        (
            f"There were {int(direct.status.eq('success').sum())} direct successes and "
            f"{int(direct.status.ne('success').sum())} raw failures. All "
            f"{len(direct_retry)} raw direct failures recovered only after exact-boundary "
            "pairing; this establishes a dependency requirement, not a raw-import success."
        ),
        "",
        "## Full round-trip routes",
        "",
        table(roundtrip_status),
        "",
        "## Boundary-retry failure audit",
        "",
        table(retry_taxonomy),
        "",
        (
            f"The matrix retained {raw_export_failures} raw export errors separately. "
            f"Of {raw_reimport_failures} raw reimport errors, {recovered} recovered with "
            f"the exact boundary and {still_failed} remained failed. The retry result "
            "therefore cannot be used as a blanket correction for tool incompatibility."
        ),
        "",
        "## Full asset mapping",
        "",
        table(mapping_counts),
        "",
        (
            f"Asset mapping completed on {int(routes.mapping_status.eq('complete').sum())}/64 "
            f"export routes and contains {len(mapping):,} relation rows. The three missing "
            "routes are retained below as exporter failures. Same-mRID class changes, drops, "
            "creates and ambiguous relations require downstream adjudication; structural "
            "split/merge candidates are not identity-equivalence proofs."
        ),
        "",
        table(route_failures),
        "",
        "## Eight frozen baselines and performance",
        "",
        (
            f"The unified comparison contains {baseline['case_count']} cases, "
            f"{baseline['baseline_count']} baselines and {baseline['decision_count']} "
            "decisions across four case layers. B2 (CGMES/SHACL) is unresolved for every "
            "CGMES 2.4.15 case because no applicable official version-matched SHACL set is "
            "available; the local official RDFS diagnostic is not substituted."
        ),
        "",
        (
            f"Full PCC verification used {performance['verification_trials']:,} trials: "
            f"p50={performance['latency_ms_p50']:.4f} ms, "
            f"p95={performance['latency_ms_p95']:.4f} ms and "
            f"p99={performance['latency_ms_p99']:.4f} ms. These are local single-process "
            "microbenchmarks, not production service-level claims."
        ),
        "",
        "## Evidence boundaries",
        "",
        "- The denominator includes every failure and non-attempt caused by an upstream export failure.",
        "- CGMES 2.4.15 structural diagnostics are not called official SHACL.",
        "- Split/merge labels in the full census are candidates pending identity adjudication.",
        "- Natural-tool B7 decisions are a disclosed adapter sidecar; native certificate count is zero.",
        "- The CGMES 3.0 corpus is internal version/network validation, not an untouched final holdout.",
        "",
    ]
    (RESULTS / "STAGE2_COMPLETE_TOOLCHAIN_REPORT.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
