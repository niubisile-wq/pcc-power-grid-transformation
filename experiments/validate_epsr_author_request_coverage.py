"""Validate that the author request package covers final-readiness blockers."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "epsr_author_metadata"
FINAL_READINESS = ROOT / "outputs" / "epsr_final_readiness" / "final_readiness.json"
REQUEST = OUT / "author_metadata_request.json"
TEMPLATE = ROOT / "manuscript" / "EPSR_AUTHOR_METADATA_TEMPLATE.json"

READINESS_TO_TEMPLATE = {
    "corresponding_email": "corresponding_email",
    "credit_roles": "credit_roles",
    "funding": "funding_statement",
    "competing_interests": "competing_interests_statement",
    "acknowledgements": "acknowledgements",
    "ai_disclosure": "generative_ai_disclosure",
    "author_approval": "all_author_approval",
    "not_under_review_elsewhere": "not_under_review_elsewhere",
    "release_doi": "final_release_doi",
    "release_tag": "release_tag",
    "code_license": "code_license",
    "source_data_license": "source_data_license",
    "third_party_dataset_confirmation": "third_party_dataset_confirmation",
}


def is_filled(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(is_filled(item) for item in value)
    return True


def main() -> int:
    readiness = json.loads(FINAL_READINESS.read_text(encoding="utf-8"))
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))

    requested = {item["field"] for item in request.get("items", [])}
    blockers = readiness.get("unresolved_author_fields", [])
    coverage = []
    uncovered = []
    for blocker in blockers:
        template_field = READINESS_TO_TEMPLATE.get(blocker)
        if not template_field:
            coverage.append({"blocker": blocker, "status": "unmapped"})
            uncovered.append(blocker)
            continue
        if template_field in requested:
            coverage.append({
                "blocker": blocker,
                "template_field": template_field,
                "status": "covered_by_author_request",
            })
        elif is_filled(template.get(template_field)):
            coverage.append({
                "blocker": blocker,
                "template_field": template_field,
                "status": "covered_by_prefilled_template",
            })
        else:
            coverage.append({
                "blocker": blocker,
                "template_field": template_field,
                "status": "uncovered",
            })
            uncovered.append(blocker)

    result = {
        "validator": "epsr-author-request-coverage-v1",
        "covered": not uncovered,
        "coverage": coverage,
        "uncovered": uncovered,
        "policy": (
            "A final-readiness blocker is covered when the corresponding "
            "template field is either requested from the author or already "
            "prefilled in the JSON template and will be applied to Markdown "
            "after author metadata validation passes."
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "author_request_coverage.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["covered"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
