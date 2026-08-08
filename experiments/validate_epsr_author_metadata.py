"""Validate author-supplied EPSR metadata before applying it to Markdown."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "epsr_author_metadata"
INPUT = ROOT / "manuscript" / "EPSR_AUTHOR_METADATA_TEMPLATE.json"

REQUIRED_FIELDS = [
    "final_author_order",
    "full_names",
    "affiliations_and_postal_addresses",
    "author_affiliation_mapping",
    "corresponding_author",
    "corresponding_email",
    "orcid_identifiers",
    "credit_roles",
    "funding_statement",
    "competing_interests_statement",
    "acknowledgements",
    "generative_ai_disclosure",
    "all_author_approval",
    "not_under_review_elsewhere",
    "final_zenodo_concept_doi",
    "final_release_doi",
    "release_tag",
    "code_license",
    "source_data_license",
    "third_party_dataset_confirmation",
]

ALLOWED_CREDIT_ROLES = {
    "Conceptualization",
    "Methodology",
    "Software",
    "Validation",
    "Formal analysis",
    "Investigation",
    "Resources",
    "Data curation",
    "Writing—original draft",
    "Writing—review and editing",
    "Visualization",
    "Supervision",
    "Project administration",
    "Funding acquisition",
}

YES_NO_FIELDS = [
    "all_author_approval",
    "not_under_review_elsewhere",
    "third_party_dataset_confirmation",
]


def is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return not stripped or stripped.lower() in {"todo", "tbd", "unknown", "n/a?"}
    if isinstance(value, list):
        return not value or any(is_missing(item) for item in value)
    return False


def main() -> int:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    missing = [field for field in REQUIRED_FIELDS if is_missing(data.get(field))]

    invalid_yes_no = [
        field for field in YES_NO_FIELDS
        if str(data.get(field, "")).strip().lower() not in {"yes", "no"}
    ]
    invalid_email = []
    email = str(data.get("corresponding_email", "")).strip()
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        invalid_email.append("corresponding_email")

    invalid_doi = []
    for field in ("final_zenodo_concept_doi", "final_release_doi"):
        value = str(data.get(field, "")).strip()
        if value and not re.fullmatch(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", value):
            invalid_doi.append(field)

    invalid_roles = []
    roles = data.get("credit_roles")
    if not isinstance(roles, list):
        invalid_roles.append("credit_roles must be a list")
    else:
        invalid_roles.extend([role for role in roles if role not in ALLOWED_CREDIT_ROLES])

    invalid_release_tag = []
    tag = str(data.get("release_tag", "")).strip()
    if tag and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", tag):
        invalid_release_tag.append("release_tag")

    checks = {
        "all_required_fields_present": not missing,
        "yes_no_fields_valid": not invalid_yes_no,
        "email_format_valid": not invalid_email,
        "doi_format_valid": not invalid_doi,
        "credit_roles_valid": not invalid_roles,
        "release_tag_valid": not invalid_release_tag,
    }
    valid = all(checks.values())
    result = {
        "validator": "epsr-author-metadata-v1",
        "valid": valid,
        "checks": checks,
        "missing_fields": missing,
        "invalid_yes_no_fields": invalid_yes_no,
        "invalid_email_fields": invalid_email,
        "invalid_doi_fields": invalid_doi,
        "invalid_credit_roles": invalid_roles,
        "invalid_release_tag_fields": invalid_release_tag,
        "input": str(INPUT.relative_to(ROOT)),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "author_metadata_validation.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
