from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total == 0:
        return math.nan, math.nan
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    half = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    ) / denominator
    return centre - half, centre + half


def _rate_row(
    evidence_set: str,
    endpoint: str,
    stratum: str,
    successes: int,
    total: int,
    unit: str,
) -> dict[str, object]:
    low, high = _wilson(successes, total)
    return {
        "evidence_set": evidence_set,
        "endpoint": endpoint,
        "stratum": stratum,
        "successes": successes,
        "total": total,
        "rate": successes / total if total else math.nan,
        "wilson_95ci_low": low,
        "wilson_95ci_high": high,
        "analysis_unit": unit,
    }


def main() -> None:
    rates: list[dict[str, object]] = []
    for stage, name in (("stage2", "CGMES_2.4.15_development"), ("stage5", "CGMES_3.0_internal_validation")):
        direct = pd.read_csv(RESULTS / f"{stage}_import_matrix_results.csv")
        for tool, group in direct.groupby("tool"):
            rates.append(
                _rate_row(
                    name,
                    "direct_import_success",
                    str(tool),
                    int(group.status.eq("success").sum()),
                    len(group),
                    "model_tool_route",
                )
            )
        roundtrip = pd.read_csv(RESULTS / f"{stage}_roundtrip_matrix_results.csv")
        exports = roundtrip[roundtrip.stage == "export"]
        for exporter, group in exports.groupby("exporter"):
            rates.append(
                _rate_row(
                    name,
                    "export_success",
                    str(exporter),
                    int(group.status.eq("success").sum()),
                    len(group),
                    "model_export_route",
                )
            )

    migration = pd.read_csv(RESULTS / "version_migration_matrix_results.csv")
    migration_exports = migration[migration.stage == "export"]
    rates.append(
        _rate_row(
            "CGMES_2.4.15_to_3.0_development_migration",
            "export_success",
            "pypowsybl",
            int(migration_exports.status.eq("success").sum()),
            len(migration_exports),
            "model_migration_route",
        )
    )
    pd.DataFrame(rates).to_csv(
        RESULTS / "confirmatory_route_rate_statistics.csv", index=False
    )

    full_mapping = json.loads(
        (RESULTS / "full_roundtrip_asset_mapping_summary.json").read_text()
    )
    mapping_rows = int(full_mapping["rows"])
    accepted = int(full_mapping["identity_only_accepted_rows"])
    pending = mapping_rows - accepted
    source_shacl = json.loads(
        (RESULTS / "cgmes_shacl_validation_summary.json").read_text()
    )
    operational = json.loads(
        (RESULTS / "natural_roundtrip_operational_replay_summary.json").read_text()
    )
    summary = {
        "route_rate_table": "results/confirmatory_route_rate_statistics.csv",
        "baseline_case_count": 340,
        "baseline_mcnemar_table": "results/baseline_mcnemar_results.csv",
        "baseline_rate_table": "results/baseline_comparison_summary.csv",
        "multiplicity_control": "Holm adjustment within the declared baseline endpoint family",
        "mapping_rows": mapping_rows,
        "identity_only_accepted_rows": accepted,
        "manual_or_additional_review_rows": pending,
        "manual_or_additional_review_fraction": pending / mapping_rows,
        "mapping_unit_warning": (
            "Asset-relation rows within the same model/tool route are dependent and are "
            "reported as workload, not independent prevalence samples."
        ),
        "source_shacl_successful_validations": source_shacl["successful_validations"],
        "source_shacl_nonconforming_artifacts": source_shacl["nonconforming_artifacts"],
        "source_shacl_timeouts": source_shacl["timeouts"],
        "natural_operational_model_count": 1,
        "natural_rank_bootstrap_status": "not_estimable_single_model",
        "natural_rank_bootstrap_reason": (
            "Only one preregistered natural mapping anomaly entered operational replay; "
            "resampling asset rows would create pseudoreplication."
        ),
        "natural_common_candidate_spearman": operational["nminus1_rank_comparison"][
            "spearman_common_candidates"
        ],
        "acopf_paired_valid": operational["acopf_paired_valid"],
        "statistical_boundary": (
            "Wilson intervals summarize route-level compatibility proportions. They are "
            "descriptive and do not convert public test models into an industry prevalence sample."
        ),
    }
    (RESULTS / "confirmatory_statistics_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
