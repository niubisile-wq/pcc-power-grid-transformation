"""Validate the final EPSR submission readiness boundary.

This script does not infer author declarations. It verifies that the local
scientific package is ready and that externally supplied metadata placeholders
have been resolved before a final archive is treated as release-ready.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "epsr_final_readiness"

AUTHOR_FORM = ROOT / "manuscript" / "EPSR_AUTHOR_INPUT_FORM.md"
SUBMISSION_MANIFEST = ROOT / "outputs" / "epsr_submission_manifest" / "submission_manifest.json"
ARCHIVE_MANIFEST = ROOT / "outputs" / "epsr_final_archive_candidate" / "archive_candidate_manifest.json"
ARCHIVE_ZIP = ROOT / "outputs" / "epsr_final_archive_candidate" / "epsr_pcc_v2_archive_candidate_20260807.zip"

PLACEHOLDER_PATTERNS = [
    "[required",
    "[confirm",
    "[roles",
    "[yes/no]",
    "[author confirmation required]",
]

REQUIRED_AUTHOR_FIELDS = {
    "corresponding_email": r"Corresponding email:\s*(.+)",
    "credit_roles": r"Zixuan Liu:\s*(.+)",
    "funding": r"Funding source and grant number.*:\s*(.+)",
    "competing_interests": r"Competing interests.*:\s*(.+)",
    "acknowledgements": r"Acknowledgements:\s*(.+)",
    "ai_disclosure": r"Use of generative AI disclosure.*:\s*(.+)",
    "author_approval": r"All-author approval.*:\s*(.+)",
    "not_under_review_elsewhere": r"Confirmation that the work is not under review elsewhere:\s*(.+)",
    "release_doi": r"Final release/version DOI:\s*(.+)",
    "release_tag": r"Release tag/version:\s*(.+)",
    "code_license": r"License for original code:\s*(.+)",
    "source_data_license": r"License for original manuscript/figure source data:\s*(.+)",
    "third_party_dataset_confirmation": r"Confirmation that third-party datasets are referenced rather than relicensed:\s*(.+)",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def extract_field(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return match.group(1).strip()


def field_is_resolved(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return not any(marker.lower() in lowered for marker in PLACEHOLDER_PATTERNS)


def main() -> int:
    author_text = AUTHOR_FORM.read_text(encoding="utf-8")
    manifest = read_json(SUBMISSION_MANIFEST)
    archive_manifest = read_json(ARCHIVE_MANIFEST) if ARCHIVE_MANIFEST.is_file() else {}

    fields = {
        name: extract_field(author_text, pattern)
        for name, pattern in REQUIRED_AUTHOR_FIELDS.items()
    }
    unresolved_fields = [
        name for name, value in fields.items()
        if not field_is_resolved(value)
    ]
    unresolved_markers = [
        marker for marker in PLACEHOLDER_PATTERNS
        if marker.lower() in author_text.lower()
    ]

    archive_hash = sha256(ARCHIVE_ZIP) if ARCHIVE_ZIP.is_file() else None
    archive_expected_hash = archive_manifest.get("archive_sha256")
    archive_hash_matches = (
        archive_hash is not None
        and archive_expected_hash is not None
        and archive_hash.lower() == archive_expected_hash.lower()
    )

    checks = {
        "scientific_package_ready": manifest.get("scientific_package_ready") is True,
        "figures_ready": manifest.get("figures_ready") is True,
        "dashboard_ready": manifest.get("dashboard", {}).get("ready_gates") == manifest.get("dashboard", {}).get("total_gates") == 9,
        "clean_room_audit_pass": manifest.get("audit", {}).get("status") == "pass",
        "author_fields_resolved": not unresolved_fields and not unresolved_markers,
        "author_metadata_ready_manifest": manifest.get("author_metadata_ready") is True,
        "final_archive_ready_manifest": manifest.get("final_archive_ready") is True,
        "archive_candidate_exists": ARCHIVE_ZIP.is_file(),
        "archive_hash_matches_manifest": archive_hash_matches,
    }
    final_ready = all(checks.values()) and manifest.get("submission_package_ready") is True

    result = {
        "validator": "epsr-final-readiness-v1",
        "final_ready": final_ready,
        "checks": checks,
        "unresolved_author_fields": unresolved_fields,
        "unresolved_author_markers": unresolved_markers,
        "author_field_values": fields,
        "archive": {
            "path": str(ARCHIVE_ZIP.relative_to(ROOT)),
            "exists": ARCHIVE_ZIP.is_file(),
            "sha256": archive_hash,
            "expected_sha256": archive_expected_hash,
            "bytes": ARCHIVE_ZIP.stat().st_size if ARCHIVE_ZIP.is_file() else None,
        },
        "submission_manifest": {
            "path": str(SUBMISSION_MANIFEST.relative_to(ROOT)),
            "submission_package_ready": manifest.get("submission_package_ready"),
            "missing": manifest.get("missing"),
        },
        "policy_note": (
            "Elsevier journal policy requires disclosure of generative AI tools "
            "used for manuscript preparation; grammar/spelling-only tools do not "
            "require a declaration. Source checked: "
            "https://www.elsevier.com/about/policies-and-standards/"
            "generative-ai-policies-for-journals"
        ),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "final_readiness.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if final_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
