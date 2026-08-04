from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "corpus" / "extracted" / "cgmes24_testconfig"
RESULT_CSV = ROOT / "corpus" / "development_model_registry.csv"
RESULT_JSON = ROOT / "corpus" / "development_model_registry_summary.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slug(text: str) -> str:
    answer = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return answer[:100]


def inspect_archive(path: Path) -> tuple[int, list[str], int, str]:
    profiles: set[str] = set()
    xml_count = 0
    full_model_count = 0
    parse_status = "success"
    try:
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if not name.lower().endswith((".xml", ".rdf")):
                    continue
                xml_count += 1
                root = ET.fromstring(archive.read(name))
                for element in root.iter():
                    local = element.tag.rsplit("}", 1)[-1]
                    if local == "FullModel":
                        full_model_count += 1
                    elif local == "Model.profile" and element.text:
                        profiles.add(element.text.strip())
    except Exception as exc:
        parse_status = f"error:{type(exc).__name__}:{exc}"
    return xml_count, sorted(profiles), full_model_count, parse_status


def boundary_candidate(path: Path, archives: list[Path]) -> Path | None:
    siblings = [item for item in archives if item.parent == path.parent and item != path]
    candidates = [
        item
        for item in siblings
        if "boundary" in item.name.lower() or re.search(r"(?:^|_)BD(?:_|\.)", item.name, re.IGNORECASE)
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


def main() -> None:
    archives = sorted(BASE.rglob("*.zip"), key=lambda path: path.relative_to(BASE).as_posix().lower())
    rows: list[dict[str, object]] = []
    hashes = {path: sha256(path) for path in archives}
    duplicate_groups: dict[str, list[Path]] = {}
    for path, digest in hashes.items():
        duplicate_groups.setdefault(digest, []).append(path)
    for path in archives:
        relative = path.relative_to(BASE)
        parts = relative.parts
        family = parts[0]
        representation = next(
            (part for part in parts if part.lower() in {"busbranch", "nodebreaker"}),
            "assembled_or_unspecified",
        )
        is_error_fixture = family.lower().endswith("_error") or "error" in path.name.lower()
        is_boundary = "boundary" in path.name.lower() or bool(
            re.search(r"(?:^|_)BD(?:_|\.)", path.name, re.IGNORECASE)
        )
        duplicates = duplicate_groups[hashes[path]]
        duplicate_of = ""
        if len(duplicates) > 1 and path != duplicates[0]:
            duplicate_of = duplicates[0].relative_to(BASE).as_posix()
        xml_count, profiles, full_model_count, parse_status = inspect_archive(path)
        boundary = None if is_boundary else boundary_candidate(path, archives)
        included = not is_boundary and not is_error_fixture and not duplicate_of and parse_status == "success"
        if is_boundary:
            exclusion_reason = "boundary_reference_only"
        elif is_error_fixture:
            exclusion_reason = "official_negative_error_fixture"
        elif duplicate_of:
            exclusion_reason = "byte_identical_duplicate"
        elif parse_status != "success":
            exclusion_reason = "archive_or_xml_parse_failure"
        else:
            exclusion_reason = ""
        case_id = f"dev_{slug(relative.with_suffix('').as_posix())}_{hashes[path][:8].lower()}"
        rows.append(
            {
                "case_id": case_id,
                "relative_path": relative.as_posix(),
                "family": family,
                "representation": representation,
                "size_bytes": path.stat().st_size,
                "sha256": hashes[path],
                "xml_file_count": xml_count,
                "full_model_count": full_model_count,
                "profiles_json": json.dumps(profiles),
                "parse_status": parse_status,
                "is_boundary": is_boundary,
                "is_error_fixture": is_error_fixture,
                "duplicate_of": duplicate_of,
                "boundary_relative_path": "" if boundary is None else boundary.relative_to(BASE).as_posix(),
                "included": included,
                "exclusion_reason": exclusion_reason,
            }
        )
    with RESULT_CSV.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    included_rows = [row for row in rows if row["included"]]
    summary = {
        "archive_count": len(rows),
        "included_model_bundles": len(included_rows),
        "excluded_archives": len(rows) - len(included_rows),
        "exclusion_reason_counts": {
            reason: sum(row["exclusion_reason"] == reason for row in rows)
            for reason in sorted({str(row["exclusion_reason"]) for row in rows if row["exclusion_reason"]})
        },
        "included_by_family": {
            family: sum(row["family"] == family for row in included_rows)
            for family in sorted({str(row["family"]) for row in included_rows})
        },
        "included_by_representation": {
            representation: sum(row["representation"] == representation for row in included_rows)
            for representation in sorted({str(row["representation"]) for row in included_rows})
        },
        "missing_boundary_reference_count": sum(not row["boundary_relative_path"] for row in included_rows),
    }
    RESULT_JSON.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
