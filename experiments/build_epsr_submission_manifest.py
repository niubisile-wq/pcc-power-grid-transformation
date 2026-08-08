"""Build a fail-closed manifest for the final EPSR submission package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "epsr_submission_manifest"


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


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))


def resolved_field(text: str, label: str) -> bool:
    match = re.search(rf"{re.escape(label)}:\s*(.+)", text)
    if not match:
        return False
    value = match.group(1).strip()
    return bool(value) and "[" not in value and "]" not in value


def main() -> int:
    science_paths = [
        "manuscript/EPSR_MANUSCRIPT_DRAFT.md",
        "manuscript/EPSR_SUPPLEMENTARY_INFORMATION.md",
        "manuscript/EPSR_PRE_SUBMISSION_REVIEW.md",
        "outputs/epsr_manuscript_tables/epsr_manuscript_tables.md",
        "outputs/epsr_manuscript_tables/table_source_snapshot.json",
        "outputs/epsr_evidence_dashboard/epsr_evidence_dashboard.json",
        "outputs/epsr_clean_room_audit/audit_summary.json",
        "protocols/semantic_confirmatory_lock_v2.json",
        "protocols/dc_scopf_confirmatory_lock_v2.json",
    ]
    figure_stems = [
        "fig1_pcc_workflow",
        "fig2_semantic_baseline_ladder",
        "fig3_operational_consequences",
        "fig4_dc_scopf_heterogeneity",
        "fig5_validation_portability_scaling",
        "fig6_external_tool_blind_roundtrip",
    ]
    figure_paths = [
        f"manuscript/figures/{stem}.{suffix}"
        for stem in figure_stems
        for suffix in ("pdf", "svg", "png")
    ]
    figure_support_paths = [
        "manuscript/figures/FIGURE_LEGENDS.md",
        "manuscript/figures/figure_source_manifest.json",
    ]
    author_paths = [
        "manuscript/EPSR_COVER_LETTER_DRAFT.md",
        "manuscript/EPSR_AUTHOR_INPUT_FORM.md",
    ]

    dashboard = load_json("outputs/epsr_evidence_dashboard/epsr_evidence_dashboard.json")
    audit = load_json("outputs/epsr_clean_room_audit/audit_summary.json")
    science_records = [record(path) for path in science_paths]
    figures = [record(path) for path in figure_paths]
    figure_support = [record(path) for path in figure_support_paths]
    author_records = [record(path) for path in author_paths]

    complete_figure_stems = []
    for stem in figure_stems:
        if all((ROOT / "manuscript" / "figures" / f"{stem}.{suffix}").is_file()
               for suffix in ("pdf", "svg", "png")):
            complete_figure_stems.append(stem)

    author_form = (ROOT / author_paths[1]).read_text(encoding="utf-8")
    release_doi_ready = resolved_field(author_form, "Final release/version DOI")
    release_tag_ready = resolved_field(author_form, "Release tag/version")
    unresolved_author_markers = [
        marker for marker in (
            "[required", "[Author]", "[roles", "[confirm", "[yes/no]"
        ) if marker in author_form
    ]
    manuscript = (ROOT / science_paths[0]).read_text(encoding="utf-8")
    manuscript_forbidden_tokens = [
        token for token in ("FINAL-DC", "Provisional references", "�")
        if token in manuscript
    ]

    scientific_package_ready = (
        all(item["exists"] for item in science_records)
        and dashboard.get("submission_ready") is True
        and dashboard.get("ready_gates") == dashboard.get("total_gates") == 9
        and audit.get("status") == "pass"
        and not manuscript_forbidden_tokens
    )
    figures_ready = (
        len(complete_figure_stems) == len(figure_stems)
        and all(item["exists"] for item in figure_support)
    )
    author_metadata_ready = not unresolved_author_markers
    final_archive_ready = author_metadata_ready and release_doi_ready and release_tag_ready
    submission_package_ready = (
        scientific_package_ready
        and figures_ready
        and author_metadata_ready
        and final_archive_ready
    )

    missing = []
    if not scientific_package_ready:
        missing.append("scientific evidence or clean-room audit")
    if not figures_ready:
        missing.append("six PDF/SVG/PNG figure triplets, legends, and source manifest")
    if not author_metadata_ready:
        missing.append("author-confirmed title-page metadata and declarations")
    if not final_archive_ready:
        if not release_doi_ready:
            missing.append("final immutable archive version DOI")
        if not release_tag_ready:
            missing.append("final immutable archive release tag")

    result = {
        "manifest_version": "epsr-submission-manifest-v1",
        "target_journal": "Electric Power Systems Research",
        "scientific_package_ready": scientific_package_ready,
        "figures_ready": figures_ready,
        "author_metadata_ready": author_metadata_ready,
        "final_archive_ready": final_archive_ready,
        "submission_package_ready": submission_package_ready,
        "missing": missing,
        "dashboard": {
            "ready_gates": dashboard.get("ready_gates"),
            "total_gates": dashboard.get("total_gates"),
            "submission_ready": dashboard.get("submission_ready"),
        },
        "audit": {
            "status": audit.get("status"),
            "steps": audit.get("steps"),
        },
        "manuscript_forbidden_tokens": manuscript_forbidden_tokens,
        "science_artifacts": science_records,
        "figure_artifacts": figures,
        "figure_support_artifacts": figure_support,
        "complete_figure_stems": complete_figure_stems,
        "author_artifacts": author_records,
        "unresolved_author_markers": unresolved_author_markers,
        "release_doi_ready": release_doi_ready,
        "release_tag_ready": release_tag_ready,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "submission_manifest.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if submission_package_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
