from __future__ import annotations

import hashlib
import json
import re
import tarfile
import zipfile
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMIT = "4e8024eaf07a43673c68226aefc8b57dae4c4ffb"
ARCHIVE = ROOT / "cgmes" / "corpus" / "holdout" / f"powsybl-core-{COMMIT}.tar.gz"
OUTPUT = ROOT / "cgmes" / "corpus" / "holdout" / "powsybl_core_holdout_bundle.zip"
MANIFEST = ROOT / "cgmes" / "corpus" / "holdout" / "powsybl_core_holdout_selection.json"
EXISTING_ROOTS = (
    ROOT / "cgmes" / "cas303",
    ROOT / "cgmes" / "corpus" / "extracted",
    ROOT / "cgmes" / "corpus" / "validation_packages",
)
PROFILE_MARKERS = ("EQ", "SSH", "TP", "SV")


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def filename_profiles(names: list[str]) -> set[str]:
    found = set()
    for marker in PROFILE_MARKERS:
        if any(re.search(rf"(?i)(^|_){marker}(_|\.)", Path(name).name) for name in names):
            found.add(marker)
    return found


def existing_xml_hashes() -> set[str]:
    hashes: set[str] = set()
    for root in EXISTING_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".xml", ".rdf"}:
                hashes.add(digest_file(path))
            elif path.is_file() and path.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(path) as archive:
                        for name in archive.namelist():
                            if name.lower().endswith((".xml", ".rdf")):
                                hashes.add(digest_bytes(archive.read(name)))
                except zipfile.BadZipFile:
                    pass
    return hashes


def main() -> None:
    archive_hash = digest_file(ARCHIVE)
    groups: dict[str, list[tarfile.TarInfo]] = defaultdict(list)
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        for member in archive.getmembers():
            if member.isfile() and member.name.lower().endswith((".xml", ".rdf")):
                groups[str(Path(member.name).parent).replace("\\", "/")].append(member)
        complete = [directory for directory, members in groups.items() if filename_profiles([item.name for item in members]) == set(PROFILE_MARKERS)]
        previous_hashes = existing_xml_hashes()
        selected = None
        audit = []
        for directory in sorted(complete):
            members = sorted(groups[directory], key=lambda item: item.name)
            member_hashes = []
            for member in members:
                stream = archive.extractfile(member)
                if stream is None:
                    raise RuntimeError(member.name)
                member_hashes.append(digest_bytes(stream.read()))
            duplicate_members = sum(value in previous_hashes for value in member_hashes)
            audit.append({
                "directory": directory,
                "xml_members": len(members),
                "byte_duplicate_members": duplicate_members,
                "all_members_byte_duplicate": duplicate_members == len(members),
            })
            if duplicate_members < len(members):
                selected = (directory, members, member_hashes)
                break
        if selected is None:
            raise RuntimeError("No complete non-byte-duplicate CGMES bundle found")
        directory, members, member_hashes = selected
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        member_manifest = []
        with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for member, member_hash in zip(members, member_hashes):
                stream = archive.extractfile(member)
                if stream is None:
                    raise RuntimeError(member.name)
                data = stream.read()
                output_name = Path(member.name).name
                info = zipfile.ZipInfo(output_name, date_time=(2026, 8, 7, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                target.writestr(info, data)
                member_manifest.append({
                    "source_path": member.name,
                    "output_name": output_name,
                    "bytes": len(data),
                    "sha256": member_hash,
                    "previously_seen_byte_identical": member_hash in previous_hashes,
                })
    manifest = {
        "protocol": "cgmes_untouched_holdout_powsybl_core_v1",
        "frozen_commit": COMMIT,
        "source_archive_sha256": archive_hash,
        "complete_directories_discovered": len(complete),
        "selection_rule": "lexicographically_first_complete_bundle_not_entirely_byte_duplicate",
        "preselection_audit": audit,
        "selected_directory": directory,
        "selected_members": member_manifest,
        "bundle_path": OUTPUT.relative_to(ROOT).as_posix(),
        "bundle_sha256": digest_file(OUTPUT),
        "validation_executed_during_selection": False,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
