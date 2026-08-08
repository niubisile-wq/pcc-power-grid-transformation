"""Build a concise request package for the remaining author metadata."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "epsr_author_metadata"
VALIDATION = OUT / "author_metadata_validation.json"
TEMPLATE = ROOT / "manuscript" / "EPSR_AUTHOR_METADATA_TEMPLATE.json"
README = ROOT / "README.md"
CITATION = ROOT / "CITATION.cff"
ZENODO = ROOT / ".zenodo.json"

FIELD_PROMPTS = {
    "affiliations_and_postal_addresses": "Full affiliation and postal address exactly as Elsevier title page should show it.",
    "corresponding_email": "Corresponding author email.",
    "funding_statement": "Funding statement, or the no-specific-grant sentence if true.",
    "competing_interests_statement": "Competing interests declaration, or the standard no-known-competing-interests statement if true.",
    "acknowledgements": "Acknowledgements text; `None` is acceptable if confirmed.",
    "generative_ai_disclosure": "Elsevier AI declaration text, or an explicit no-use statement if applicable.",
    "all_author_approval": "`yes` or `no`.",
    "not_under_review_elsewhere": "`yes` or `no`.",
    "final_release_doi": "Final immutable release DOI after the archive/version is minted.",
    "release_tag": "Final release tag/version, e.g. `v1.0.1`.",
    "code_license": "License for original code, or explicit `No open-source license assigned` if confirmed.",
    "source_data_license": "License for original manuscript/figure source data.",
    "third_party_dataset_confirmation": "`yes` or `no`: third-party datasets are referenced, not relicensed.",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def main() -> int:
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    missing = validation.get("missing_fields", [])
    invalid_yes_no = validation.get("invalid_yes_no_fields", [])

    evidence = {
        "existing_author": template.get("full_names"),
        "existing_affiliation_short": "Detroit Green Technology Institute, Hubei University of Technology",
        "existing_orcid": "0009-0008-4941-5641",
        "existing_concept_doi": template.get("final_zenodo_concept_doi"),
        "citation_doi": "10.5281/zenodo.21796488" if "10.5281/zenodo.21796488" in read_text(CITATION) else None,
        "readme_license_note": "No open-source license has yet been assigned." if "No open-source license has yet been assigned" in read_text(README) else None,
        "zenodo_creator": json.loads(read_text(ZENODO)).get("creators", []) if ZENODO.is_file() else [],
    }

    request_items = []
    for field in missing:
        request_items.append({
            "field": field,
            "prompt": FIELD_PROMPTS.get(field, "Author-confirmed value required."),
            "current_value": template.get(field),
            "format": "yes/no" if field in invalid_yes_no else "free_text",
        })

    result = {
        "request": "epsr-author-metadata-request-v1",
        "status": "needs_author_input",
        "input_template": str(TEMPLATE.relative_to(ROOT)),
        "validation_report": str(VALIDATION.relative_to(ROOT)),
        "items": request_items,
        "reference_only_existing_metadata": evidence,
        "policy": "Do not infer author declarations from repository history; author must confirm every requested field.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "author_metadata_request.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# EPSR author metadata request",
        "",
        "Fill `manuscript/EPSR_AUTHOR_METADATA_TEMPLATE.json` with author-confirmed values.",
        "Do not infer declarations from repository history.",
        "",
        "## Required fields",
        "",
    ]
    for item in request_items:
        lines.extend([
            f"### {item['field']}",
            "",
            f"- Prompt: {item['prompt']}",
            f"- Current value: `{item['current_value']}`",
            f"- Required format: `{item['format']}`",
            "",
        ])
    lines.extend([
        "## Reference-only existing metadata",
        "",
        f"- Existing author: `{evidence['existing_author']}`",
        f"- Existing short affiliation: `{evidence['existing_affiliation_short']}`",
        f"- Existing ORCID: `{evidence['existing_orcid']}`",
        f"- Existing Zenodo concept DOI: `{evidence['existing_concept_doi']}`",
        f"- README license note: `{evidence['readme_license_note']}`",
        "",
        "These reference values are not confirmations. After filling the JSON, run:",
        "",
        "```powershell",
        "py -3.12 experiments\\freeze_epsr_submission_package.py",
        "```",
        "",
    ])
    (OUT / "author_metadata_request.md").write_text("\n".join(lines), encoding="utf-8")

    response_lines = [
        "# EPSR author response form",
        "",
        "Fill the `Answer` lines, then transfer the confirmed values into",
        "`manuscript/EPSR_AUTHOR_METADATA_TEMPLATE.json`.",
        "",
    ]
    for item in request_items:
        response_lines.extend([
            f"## {item['field']}",
            "",
            f"Prompt: {item['prompt']}",
            f"Format: {item['format']}",
            "Answer: ",
            "",
        ])
    response_lines.extend([
        "## Reference values that still require confirmation",
        "",
        f"- Author: {evidence['existing_author']}",
        f"- Short affiliation: {evidence['existing_affiliation_short']}",
        f"- ORCID: {evidence['existing_orcid']}",
        f"- Zenodo concept DOI: {evidence['existing_concept_doi']}",
        f"- Repository license note: {evidence['readme_license_note']}",
        "",
    ])
    (OUT / "author_response_form.md").write_text("\n".join(response_lines), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
