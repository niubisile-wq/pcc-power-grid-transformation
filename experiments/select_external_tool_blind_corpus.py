"""Mechanically select the frozen external CGMES challenge corpus.

This selector is intentionally independent of PCC outcomes.  It reads the
repository archive named in the frozen protocol, applies only the preregistered
path/profile/hash rules, and writes both selected bundles and a complete
selection manifest.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMIT = "61842900c40e19accb9528503a8591d4ff2004ee"
ARCHIVE = ROOT / "cgmes" / "corpus" / "holdout" / f"pandapower-{COMMIT}.tar.gz"
OUTPUT_DIR = ROOT / "cgmes" / "corpus" / "external_blind_roundtrip_v1"
MANIFEST = OUTPUT_DIR / "selection_manifest.json"
MAX_BUNDLES = 10
PROFILE_RE = re.compile(r"(?:^|[_\-.])(EQ|SSH|TP|SV)(?:[_\-.]|$)", re.IGNORECASE)


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def existing_zip_hashes() -> set[str]:
    hashes: set[str] = set()
    excluded = {OUTPUT_DIR.resolve()}
    for path in ROOT.rglob("*.zip"):
        if any(parent in excluded for parent in [path.resolve(), *path.resolve().parents]):
            continue
        try:
            hashes.add(hashlib.sha256(path.read_bytes()).hexdigest())
        except OSError:
            continue
    return hashes


def nested_profiles(value: bytes) -> tuple[list[str], list[str], str | None]:
    try:
        with zipfile.ZipFile(io.BytesIO(value)) as archive:
            members = sorted(name for name in archive.namelist() if not name.endswith("/"))
    except (zipfile.BadZipFile, OSError) as exc:
        return [], [], f"{type(exc).__name__}:{exc}"
    profiles = sorted({match.group(1).upper() for name in members for match in PROFILE_RE.finditer(Path(name).name)})
    return profiles, members, None


def main() -> None:
    if not ARCHIVE.is_file():
        raise FileNotFoundError(ARCHIVE)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prior_hashes = existing_zip_hashes()
    archive_hash = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    records: list[dict[str, object]] = []
    selected: list[dict[str, object]] = []
    seen_candidate_hashes: set[str] = set()

    with tarfile.open(ARCHIVE, "r:gz") as outer:
        candidates = sorted(
            (
                member
                for member in outer.getmembers()
                if member.isfile()
                and member.name.lower().endswith(".zip")
                and any(token in member.name.lower() for token in ("cim", "cgmes"))
            ),
            key=lambda member: member.name,
        )
        for member in candidates:
            stream = outer.extractfile(member)
            if stream is None:
                continue
            value = stream.read()
            sha256 = digest_bytes(value)
            profiles, nested_members, error = nested_profiles(value)
            has_required_profiles = {"EQ", "SSH", "TP"}.issubset(profiles)
            duplicate_prior = sha256 in prior_hashes
            duplicate_candidate = sha256 in seen_candidate_hashes
            seen_candidate_hashes.add(sha256)
            eligible = bool(
                error is None
                and has_required_profiles
                and not duplicate_prior
                and not duplicate_candidate
            )
            reason = "eligible"
            if error:
                reason = "invalid_nested_zip"
            elif not has_required_profiles:
                reason = "missing_required_EQ_SSH_TP_profiles"
            elif duplicate_prior:
                reason = "byte_identical_prior_local_artifact"
            elif duplicate_candidate:
                reason = "byte_identical_earlier_candidate"
            elif len(selected) >= MAX_BUNDLES:
                reason = "eligible_beyond_frozen_maximum"
                eligible = False

            record: dict[str, object] = {
                "repository_member": member.name,
                "sha256": sha256,
                "bytes": len(value),
                "profiles_from_member_names": profiles,
                "nested_member_count": len(nested_members),
                "eligible": eligible,
                "selection_reason": reason,
            }
            if eligible:
                bundle_id = f"ext{len(selected) + 1:02d}_{Path(member.name).stem}"
                target = OUTPUT_DIR / f"{bundle_id}.zip"
                target.write_bytes(value)
                record["bundle_id"] = bundle_id
                record["selected_path"] = target.relative_to(ROOT).as_posix()
                selected.append(record)
            records.append(record)

    payload = {
        "protocol": "external_tool_blind_roundtrip_v1",
        "source_commit": COMMIT,
        "archive_path": ARCHIVE.relative_to(ROOT).as_posix(),
        "archive_sha256": archive_hash,
        "archive_bytes": ARCHIVE.stat().st_size,
        "candidate_count": len(records),
        "selected_count": len(selected),
        "maximum_selected_bundles": MAX_BUNDLES,
        "selected_bundle_ids": [str(row["bundle_id"]) for row in selected],
        "records": records,
        "selection_used_no_PCC_or_operational_outcomes": True,
    }
    MANIFEST.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
