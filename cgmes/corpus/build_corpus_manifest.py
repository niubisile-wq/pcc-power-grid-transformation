from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus"
DOWNLOADS = CORPUS / "downloads"
EXTRACTED = CORPUS / "extracted"
OUTPUT = CORPUS / "official_cgmes_corpus_manifest.json"
IGNORED_EXTRACTED_ROOTS = {
    "entsoe_application_profiles_library_110d92bf66ae7009e13b4e7c5e96745469c58f83": (
        "empty directory tree left by failed PowerShell Expand-Archive; zero files; "
        "the verified extraction is apl_110d92bf66ae7009e13b4e7c5e96745469c58f83"
    )
}

SOURCE_RECORDS = {
    "ENTSOE_CGMES_v2.4.15_04Jul2016_RDFS.zip": {
        "corpus_id": "entsoe_cgmes_2_4_15_rdfs_04jul2016",
        "publisher": "ENTSO-E",
        "version": "CGMES 2.4.15 RDFS 04Jul2016 (archive root dated 16Feb2016)",
        "landing_page": "https://www.entsoe.eu/data/cim/cim-for-grid-models-exchange/",
        "extracted_root": "cgmes2415_rdfs",
        "role": "version_matched_schema",
        "split": "reference_only",
    },
    "CGMES_CAS_ApplicationProfiles_v3.0.2.zip": {
        "corpus_id": "entsoe_cgmes_cas_application_profiles_3_0_2",
        "publisher": "ENTSO-E",
        "version": "CGMES CAS Application Profiles 3.0.2",
        "landing_page": "https://www.entsoe.eu/data/cim/cim-conformity-and-interoperability/",
        "extracted_root": "cgmes3_profiles",
        "role": "specification",
        "split": "reference_only",
    },
    "CGMES_CAS_ReleaseNotes_v3.0.2.pdf": {
        "corpus_id": "entsoe_cgmes_cas_release_notes_3_0_2",
        "publisher": "ENTSO-E",
        "version": "CGMES CAS Release Notes 3.0.2",
        "landing_page": "https://www.entsoe.eu/data/cim/cim-conformity-and-interoperability/",
        "extracted_root": None,
        "role": "documentation",
        "split": "reference_only",
    },
    "CGMES_CAS_TestConfigurations_v3.0.3.zip": {
        "corpus_id": "entsoe_cgmes_cas_test_configurations_3_0_3",
        "publisher": "ENTSO-E",
        "version": "CGMES CAS Test Configurations 3.0.3",
        "landing_page": "https://www.entsoe.eu/data/cim/cim-conformity-and-interoperability/",
        "extracted_root": "cgmes3_testconfig",
        "role": "model_corpus",
        "split": "internal_validation",
        "licence_status": (
            "CC BY-SA 4.0 declared for ENTSO-E CGMES test configurations on "
            "the official conformity landing page; verified 2026-08-04"
        ),
        "licence_evidence_url": (
            "https://www.entsoe.eu/data/cim/cim-conformity-and-interoperability/"
        ),
        "redistribution_allowed": True,
        "redistribution_policy": (
            "Retain ENTSO-E attribution and distribute adaptations under CC BY-SA 4.0."
        ),
    },
    "CGMES_v2.4.15_TestConfigurations_v4.0.3.zip": {
        "corpus_id": "entsoe_cgmes_2_4_15_test_configurations_4_0_3",
        "publisher": "ENTSO-E",
        "version": "CGMES 2.4.15 Test Configurations 4.0.3",
        "landing_page": "https://www.entsoe.eu/data/cim/cgmes-archive/",
        "extracted_root": "cgmes24_testconfig",
        "role": "model_corpus",
        "split": "development",
        "licence_status": (
            "CC BY-SA 4.0 declared for ENTSO-E CGMES test configurations on "
            "the official conformity landing page; verified 2026-08-04"
        ),
        "licence_evidence_url": (
            "https://www.entsoe.eu/data/cim/cim-conformity-and-interoperability/"
        ),
        "redistribution_allowed": True,
        "redistribution_policy": (
            "Retain ENTSO-E attribution and distribute adaptations under CC BY-SA 4.0."
        ),
    },
    "NCP_v2.4.2_FullPackage.zip": {
        "corpus_id": "entsoe_network_code_profiles_2_4_2",
        "publisher": "ENTSO-E",
        "version": "Network Code Profiles 2.4.2",
        "landing_page": "https://www.entsoe.eu/data/cim/cim-for-grid-models-exchange/",
        "extracted_root": "ncp242_holdout",
        "role": "specification",
        "split": "reference_only",
    },
    "entsoe_application_profiles_library_110d92bf66ae7009e13b4e7c5e96745469c58f83.zip": {
        "corpus_id": "entsoe_application_profiles_library_main_110d92b",
        "publisher": "ENTSO-E",
        "version": "Application Profiles Library main commit 110d92bf66ae7009e13b4e7c5e96745469c58f83",
        "source_url": "https://github.com/entsoe/application-profiles-library/commit/110d92bf66ae7009e13b4e7c5e96745469c58f83",
        "landing_page": "https://github.com/entsoe/application-profiles-library",
        "extracted_root": "apl_110d92bf66ae7009e13b4e7c5e96745469c58f83",
        "role": "post_freeze_reference_specification_robustness_only",
        "split": "reference_only_not_model_holdout",
        "licence_status": "Apache-2.0 declared by publisher repository",
        "redistribution_allowed": True,
        "redistribution_policy": "Apache-2.0 terms and notices must be retained.",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iso_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def file_record(path: Path, base: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "relative_path": path.relative_to(base).as_posix(),
        "size_bytes": stat.st_size,
        "sha256": sha256(path),
        "modified_utc": iso_timestamp(stat.st_mtime),
        "extension": path.suffix.lower(),
        "parse_status": "not_attempted",
    }


def main() -> None:
    packages: list[dict[str, object]] = []
    known_roots: set[str] = set()
    for download in sorted(DOWNLOADS.iterdir(), key=lambda item: item.name.lower()):
        if not download.is_file():
            continue
        if download.name not in SOURCE_RECORDS:
            raise SystemExit(f"Unregistered download: {download.name}")
        metadata = SOURCE_RECORDS[download.name]
        extracted_root = metadata["extracted_root"]
        extracted_files: list[dict[str, object]] = []
        if extracted_root:
            known_roots.add(str(extracted_root))
            root_path = EXTRACTED / str(extracted_root)
            if not root_path.is_dir():
                raise SystemExit(f"Missing extracted root: {root_path}")
            extracted_files = [
                file_record(path, root_path)
                for path in sorted(root_path.rglob("*"), key=lambda item: item.as_posix().lower())
                if path.is_file()
            ]
        stat = download.stat()
        packages.append(
            {
                **metadata,
                "download_filename": download.name,
                "download_size_bytes": stat.st_size,
                "download_sha256": sha256(download),
                "downloaded_utc": iso_timestamp(stat.st_ctime),
                "licence_status": metadata.get(
                    "licence_status", "not_identified_in_local_package"
                ),
                "redistribution_allowed": metadata.get(
                    "redistribution_allowed", False
                ),
                "redistribution_policy": metadata.get(
                    "redistribution_policy",
                    "Do not redistribute until an explicit applicable licence is verified.",
                ),
                "extracted_file_count": len(extracted_files),
                "extracted_files": extracted_files,
            }
        )

    extraction_exclusions: list[dict[str, object]] = []
    for name, reason in IGNORED_EXTRACTED_ROOTS.items():
        path = EXTRACTED / name
        if not path.exists():
            continue
        file_count = sum(1 for item in path.rglob("*") if item.is_file())
        if file_count:
            raise SystemExit(f"Ignored extraction root unexpectedly contains files: {path}")
        extraction_exclusions.append(
            {"relative_path": path.relative_to(ROOT).as_posix(), "file_count": 0, "reason": reason}
        )
    unexpected_roots = sorted(
        path.name
        for path in EXTRACTED.iterdir()
        if path.is_dir()
        and path.name not in known_roots
        and path.name not in IGNORED_EXTRACTED_ROOTS
    )
    if unexpected_roots:
        raise SystemExit(f"Unregistered extracted roots: {unexpected_roots}")

    manifest = {
        "schema_version": "1.0.0",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "project": "solo_cgmes_validation",
        "original_manuscript_title": "Proof-carrying canonicalization exposes identity-loss risks in public power-grid benchmarks",
        "current_manuscript_title": "Proof-carrying canonicalization exposes identity-loss risks in public power-grid benchmarks",
        "assignment_frozen_before_full_matrix_experiments": True,
        "exploratory_import_smoke_preceded_assignment_freeze": True,
        "holdout_integrity": {
            "untouched_final_holdout_available": False,
            "reason": "No post-freeze model release remains unopened. The post-freeze Application Profiles Library archive is a reference specification, not a model holdout.",
            "required_action": "Acquire a later versioned public model release after code freeze, hash it before exploratory inspection, and execute the frozen pipeline once.",
        },
        "packages": packages,
        "local_extraction_exclusions": extraction_exclusions,
        "totals": {
            "download_count": len(packages),
            "extracted_file_count": sum(int(item["extracted_file_count"]) for item in packages),
            "download_bytes": sum(int(item["download_size_bytes"]) for item in packages),
        },
    }
    OUTPUT.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    print(json.dumps(manifest["totals"], indent=2))


if __name__ == "__main__":
    main()
