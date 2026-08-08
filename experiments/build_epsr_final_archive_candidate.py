"""Build a pre-release EPSR archive candidate from verified artifacts.

This package is intentionally a candidate, not the final DOI-bound release:
author-supplied metadata and the immutable archive DOI are still fail-closed
gates in ``build_epsr_submission_manifest.py``.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "epsr_final_archive_candidate"
ARCHIVE_NAME = "epsr_pcc_v2_archive_candidate_20260809.zip"


CORE_PATHS = [
    "README.md",
    "CITATION.cff",
    ".zenodo.json",
    "requirements.txt",
    "requirements-pcc-v2.txt",
    "EPSR_EXECUTION_MASTER_20260807.md",
    "EPSR_CLAIM_EVIDENCE_MATRIX_20260807.md",
    "EPSR_COMPETITIVE_LANDSCAPE_20260807.md",
    "manuscript/EPSR_MANUSCRIPT_DRAFT.md",
    "manuscript/EPSR_template.tex",
    "manuscript/EPSR_template.pdf",
    "manuscript/EPSR_template_bibitems.tex",
    "manuscript/EPSR_SUPPLEMENTARY_INFORMATION.md",
    "manuscript/EPSR_PRE_SUBMISSION_REVIEW.md",
    "manuscript/EPSR_SUBMISSION_CHECKLIST.md",
    "manuscript/EPSR_COVER_LETTER_DRAFT.md",
    "manuscript/EPSR_AUTHOR_INPUT_FORM.md",
    "manuscript/EPSR_AUTHOR_METADATA_TEMPLATE.json",
    "manuscript/figures/FIGURE_LEGENDS.md",
    "manuscript/figures/FIGURE_CONTRACTS.md",
    "manuscript/figures/figure_source_manifest.json",
    "manuscript/figures/qa/FIGURE_QA_REPORT.md",
    "manuscript/figures/qa/figure_qa.json",
    "outputs/epsr_submission_manifest/submission_manifest.json",
    "outputs/epsr_author_metadata/author_metadata_validation.json",
    "outputs/epsr_author_metadata/author_metadata_request.json",
    "outputs/epsr_author_metadata/author_metadata_request.md",
    "outputs/epsr_author_metadata/author_response_form.md",
    "outputs/epsr_author_metadata/author_response_import.json",
    "outputs/epsr_author_metadata/author_request_coverage.json",
    "outputs/epsr_evidence_dashboard/epsr_evidence_dashboard.json",
    "outputs/epsr_clean_room_audit/audit_summary.json",
    "outputs/epsr_manuscript_tables/epsr_manuscript_tables.md",
    "outputs/epsr_manuscript_tables/table_source_snapshot.json",
    "outputs/pcc_v2_dc_scopf_statistics/summary.json",
    "outputs/pcc_v2_attack_matrix/attack_matrix_summary.json",
    "outputs/pcc_v2_semantic_baseline_ladder/summary.json",
    "outputs/pcc_v2_n1_gate/pcc_v2_n1_gate_summary.json",
    "outputs/pcc_v2_opf_gate/pcc_v2_opf_gate_summary.json",
    "outputs/pcc_v2_application_statistics/summary.json",
    "outputs/pcc_v2_scaling/pcc_v2_scaling_summary.json",
    "outputs/cgmes_apl111_pcc_separation/separation_summary.json",
    "outputs/qocdc_414_applicable_subset/summary.json",
    "outputs/cross_solver_dcmp_validation/cross_solver_dcmp_summary.json",
    "outputs/cgmes_untouched_holdout/holdout_summary.json",
    "outputs/dc_scopf_mechanism_atlas/summary.json",
    "outputs/pcc_decision_reason_taxonomy/summary.json",
    "outputs/external_tool_blind_roundtrip/summary.json",
    "outputs/external_tool_blind_roundtrip/consequence_summary.json",
    "experiments/build_epsr_submission_manifest.py",
    "experiments/build_epsr_final_archive_candidate.py",
    "experiments/apply_epsr_author_metadata.py",
    "experiments/build_epsr_author_metadata_request.py",
    "experiments/import_epsr_author_response.py",
    "experiments/validate_epsr_author_request_coverage.py",
    "experiments/validate_epsr_author_metadata.py",
    "experiments/freeze_epsr_submission_package.py",
    "experiments/validate_epsr_final_readiness.py",
    "protocols/epsr_submission_gate_v1.yaml",
    "protocols/benchmark_protocol_v5_pcc_v2.yaml",
    "protocols/semantic_confirmatory_lock_v2.json",
    "protocols/dc_scopf_confirmatory_lock_v2.json",
    "protocols/dc_scopf_protocol_v1.yaml",
    "protocols/cross_solver_powermodels_dcmp_v2.yaml",
    "protocols/cgmes_untouched_holdout_powsybl_core_v1.yaml",
    "protocols/qocdc_4_1_4_coverage_v1.yaml",
]

FIGURE_STEMS = [
    "fig1_pcc_workflow",
    "fig2_semantic_baseline_ladder",
    "fig3_operational_consequences",
    "fig4_dc_scopf_heterogeneity",
    "fig5_validation_portability_scaling",
    "fig6_external_tool_blind_roundtrip",
]

FIGURE_SOURCE_GLOBS = [
    "manuscript/figures/source_data/*.csv",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(relative: str) -> dict:
    path = ROOT / relative
    return {
        "path": relative,
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256(path) if path.is_file() else None,
    }


def main() -> int:
    figure_paths = [
        f"manuscript/figures/{stem}.{suffix}"
        for stem in FIGURE_STEMS
        for suffix in ("pdf", "svg", "png")
    ]
    source_paths = [
        path.relative_to(ROOT).as_posix()
        for pattern in FIGURE_SOURCE_GLOBS
        for path in ROOT.glob(pattern)
    ]
    paths = sorted(dict.fromkeys(CORE_PATHS + figure_paths + source_paths))
    records = [record(path) for path in paths]
    missing = [item["path"] for item in records if not item["exists"]]

    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "archive_candidate_manifest.json"
    archive_path = OUT / ARCHIVE_NAME
    checksum_path = OUT / f"{ARCHIVE_NAME}.sha256"

    candidate_manifest = {
        "manifest_version": "epsr-final-archive-candidate-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "candidate",
        "final_release_ready": False,
        "reason_not_final": [
            "author-confirmed metadata/declarations are still required",
            "final immutable archive DOI and release tag are still required",
        ],
        "archive_name": ARCHIVE_NAME,
        "files": records,
        "missing": missing,
    }
    manifest_path.write_text(
        json.dumps(candidate_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if missing:
        print(json.dumps(candidate_manifest, indent=2, ensure_ascii=False))
        return 2

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in paths:
            archive.write(ROOT / relative, arcname=relative)
        archive.write(manifest_path, arcname="archive_candidate_manifest.json")

    archive_hash = sha256(archive_path)
    checksum_path.write_text(f"{archive_hash}  {ARCHIVE_NAME}\n", encoding="utf-8")

    candidate_manifest["archive_sha256"] = archive_hash
    candidate_manifest["archive_bytes"] = archive_path.stat().st_size
    manifest_path.write_text(
        json.dumps(candidate_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(candidate_manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
