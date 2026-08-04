from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUTPUT = RESULTS / "full_roundtrip_asset_mapping.csv"
SUMMARY = RESULTS / "full_roundtrip_asset_mapping_summary.json"


def _series(frame: pd.DataFrame, name: str, default: str = "") -> pd.Series:
    if name in frame.columns:
        return frame[name].fillna("").astype(str)
    return pd.Series(default, index=frame.index, dtype="object")


def _bus(frame: pd.DataFrame, prefix: str) -> pd.Series:
    left = _series(frame, f"{prefix}_bus1")
    right = _series(frame, f"{prefix}_bus2")
    return pd.Series(
        ["|".join(item for item in (a, b) if item) for a, b in zip(left, right)],
        index=frame.index,
    )


def _shacl_status(row: pd.Series) -> str:
    if row["status"] == "timeout":
        return "timeout"
    if row["status"] != "success":
        message = str(row.get("error_message", ""))
        if "two elements cannot use the same ID" in message:
            return "strict_rdf_parse_error_duplicate_id"
        return f"execution_error:{row['status']}"
    if str(row["shacl_conforms"]).lower() == "true":
        return "conforming"
    return "nonconforming"


def _combined_shacl_status(source: str, target: str) -> str:
    if source == "conforming" and target == "conforming":
        return "true_both_conforming"
    if source == "nonconforming":
        return f"false_source_nonconforming_target_{target}"
    if target in {"nonconforming", "strict_rdf_parse_error_duplicate_id"}:
        return f"false_target_{target}_source_{source}"
    return f"unresolved_source_{source}_target_{target}"


def _normalize(
    raw: pd.DataFrame,
    stage: str,
    source_version: str,
    target_version: str,
    evidence_role: str,
) -> pd.DataFrame:
    status_map = {
        "split": "unsupported_split",
        "merge": "unsupported_merge",
    }
    mapping_status = _series(raw, "mapping_status").replace(status_map)
    evidence = _series(raw, "identity_equivalence_evidence")
    same_mrid_relation = mapping_status.eq("exact") | (
        mapping_status.eq("renamed") & evidence.str.startswith("same_mrid")
    )
    identity_decision = pd.Series(
        "unresolved_no_explicit_identity_relation", index=raw.index, dtype="object"
    )
    identity_decision.loc[same_mrid_relation] = "accepted_same_mrid_relation"
    identity_decision.loc[mapping_status.isin(["dropped", "created"])] = (
        "rejected_missing_source_target_relation"
    )
    identity_decision.loc[
        mapping_status.isin(["unsupported_split", "unsupported_merge"])
    ] = "rejected_structural_candidate_without_identity_proof"

    output = pd.DataFrame(index=raw.index)
    output["run_id"] = (
        f"stage{stage}_" + _series(raw, "case_id") + "__" + _series(raw, "exporter")
    )
    output["case_id"] = _series(raw, "case_id")
    output["validation_stage"] = stage
    output["evidence_role"] = evidence_role
    output["toolchain"] = _series(raw, "route")
    output["source_format"] = f"CGMES_{source_version}_RDF_XML"
    output["target_format"] = f"CGMES_{target_version}_RDF_XML"
    output["source_profile"] = "profiles_declared_in_source_package"
    output["target_profile"] = "exporter_EQ_TP_SSH_profile_set"
    output["source_snapshot_hash"] = _series(raw, "source_sha256")
    output["target_snapshot_hash"] = _series(raw, "target_sha256")
    output["source_mrid"] = _series(raw, "source_mrid")
    output["target_mrid"] = _series(raw, "target_mrid")
    output["source_asset_type"] = _series(raw, "source_asset_type")
    output["target_asset_type"] = _series(raw, "target_asset_type")
    output["source_bus"] = _bus(raw, "source")
    output["target_bus"] = _bus(raw, "target")
    output["source_terminal"] = _series(raw, "source_terminal_ids")
    output["target_terminal"] = _series(raw, "target_terminal_ids")
    output["source_p"] = _series(raw, "source_p_mw")
    output["target_p"] = _series(raw, "target_p_mw")
    output["source_q"] = _series(raw, "source_q_mvar")
    output["target_q"] = _series(raw, "target_q_mvar")
    output["source_status"] = _series(raw, "source_in_service")
    output["target_status"] = _series(raw, "target_in_service")
    output["mapping_status"] = mapping_status
    output["mapping_confidence"] = _series(raw, "mapping_confidence")
    output["common_parent"] = ""
    output["identity_equivalence_evidence"] = evidence
    output["schema_valid"] = "unresolved_not_assessed_at_asset_relation_level"
    output["source_shacl_status"] = (
        "unresolved_no_version_matched_official_shapes"
        if stage in {"2", "version_migration"}
        else "pending_stage5_source_result_merge"
    )
    output["target_shacl_status"] = (
        "unresolved_no_version_matched_official_shapes"
        if stage == "2"
        else "pending_converted_target_result_merge"
    )
    output["shacl_valid"] = (
        "unresolved_no_version_matched_official_shapes"
        if stage in {"2", "version_migration"}
        else "pending_stage5_source_result_merge"
    )
    output["conservation_valid"] = "not_evaluated_at_full_asset_census_level"
    output["identity_only_valid"] = same_mrid_relation
    output["identity_only_decision"] = identity_decision
    output["full_pcc_valid"] = False
    output["full_pcc_decision"] = "rejected_no_native_pcc_certificate"
    output["adjudication_status"] = _series(raw, "adjudication_status")
    output["notes"] = _series(raw, "claim_scope")
    return output


def main() -> None:
    stage2_raw = pd.read_csv(
        RESULTS / "stage2_full_roundtrip_asset_mapping.csv", keep_default_na=False
    )
    stage5_raw = pd.read_csv(
        RESULTS / "stage5_full_roundtrip_asset_mapping.csv", keep_default_na=False
    )
    migration_raw = pd.read_csv(
        RESULTS / "version_migration_asset_mapping.csv", keep_default_na=False
    )
    stage2 = _normalize(stage2_raw, "2", "2.4.15", "2.4.15", "development")
    stage5 = _normalize(
        stage5_raw,
        "5",
        "3.0.0",
        "3.0.0",
        "internal_validation_not_untouched_final_holdout",
    )
    migration = _normalize(
        migration_raw,
        "version_migration",
        "2.4.15",
        "3.0.0",
        "development_version_migration_not_final_holdout",
    )

    shacl = pd.read_csv(
        RESULTS / "cgmes_shacl_validation_results.csv", keep_default_na=False
    ).set_index("case_id")
    source_status: dict[str, str] = {}
    for case_id, row in shacl.iterrows():
        source_status[str(case_id)] = _shacl_status(row)
    stage5["source_shacl_status"] = stage5.case_id.map(source_status).fillna(
        "missing_source_result"
    )

    converted = pd.read_csv(
        RESULTS / "converted_cgmes3_shacl_validation_results.csv",
        keep_default_na=False,
    )
    converted["normalized_shacl_status"] = converted.apply(_shacl_status, axis=1)
    if converted.artifact_id.duplicated().any():
        raise RuntimeError("Converted SHACL results contain duplicate artifact IDs")
    target_lookup = {
        (str(row.artifact_group), str(row.case_id), str(row.exporter)): str(
            row.normalized_shacl_status
        )
        for row in converted.itertuples(index=False)
    }
    stage5["target_shacl_status"] = [
        target_lookup.get(
            ("stage5_cgmes3_roundtrip_export", str(case_id), str(exporter)),
            "missing_target_result",
        )
        for case_id, exporter in zip(stage5_raw.case_id, stage5_raw.exporter)
    ]
    migration["target_shacl_status"] = [
        target_lookup.get(
            (
                "development_cgmes2415_to_cgmes3_export",
                str(case_id),
                str(exporter),
            ),
            "missing_target_result",
        )
        for case_id, exporter in zip(migration_raw.case_id, migration_raw.exporter)
    ]
    stage5["shacl_valid"] = [
        _combined_shacl_status(source, target)
        for source, target in zip(
            stage5.source_shacl_status, stage5.target_shacl_status
        )
    ]
    migration["shacl_valid"] = [
        _combined_shacl_status(source, target)
        for source, target in zip(
            migration.source_shacl_status, migration.target_shacl_status
        )
    ]

    combined = pd.concat([stage2, stage5, migration], ignore_index=True)
    required = {
        "run_id",
        "case_id",
        "toolchain",
        "source_format",
        "target_format",
        "source_profile",
        "target_profile",
        "source_snapshot_hash",
        "target_snapshot_hash",
        "source_mrid",
        "target_mrid",
        "source_asset_type",
        "target_asset_type",
        "source_bus",
        "target_bus",
        "source_terminal",
        "target_terminal",
        "source_p",
        "target_p",
        "source_q",
        "target_q",
        "source_status",
        "target_status",
        "mapping_status",
        "mapping_confidence",
        "common_parent",
        "identity_equivalence_evidence",
        "schema_valid",
        "shacl_valid",
        "conservation_valid",
        "identity_only_valid",
        "full_pcc_valid",
        "adjudication_status",
        "notes",
    }
    missing = sorted(required - set(combined.columns))
    if missing:
        raise RuntimeError(f"Full mapping is missing required columns: {missing}")
    combined.to_csv(OUTPUT, index=False)
    summary = {
        "rows": len(combined),
        "stage2_rows": len(stage2),
        "stage5_rows": len(stage5),
        "version_migration_rows": len(migration),
        "run_count": int(combined.run_id.nunique()),
        "case_count": int(combined.case_id.nunique()),
        "mapping_status_counts_including_zeros": {
            status: int(combined.mapping_status.eq(status).sum())
            for status in (
                "exact",
                "renamed",
                "lawful_split",
                "lawful_merge",
                "unsupported_split",
                "unsupported_merge",
                "dropped",
                "created",
                "ambiguous",
                "unresolved",
            )
        },
        "native_pcc_certificate_rows": 0,
        "full_pcc_fail_closed_rows": int((~combined.full_pcc_valid).sum()),
        "identity_only_accepted_rows": int(combined.identity_only_valid.sum()),
        "source_shacl_status_counts": combined.source_shacl_status.value_counts()
        .sort_index()
        .to_dict(),
        "target_shacl_status_counts": combined.target_shacl_status.value_counts()
        .sort_index()
        .to_dict(),
        "combined_shacl_status_counts": combined.shacl_valid.value_counts()
        .sort_index()
        .to_dict(),
        "claim_limit": (
            "The table is a complete automated asset census for successful export routes. "
            "Unsupported split/merge labels are structural candidates, not identity proofs; "
            "failed export routes remain in the separate route-denominator tables."
        ),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
