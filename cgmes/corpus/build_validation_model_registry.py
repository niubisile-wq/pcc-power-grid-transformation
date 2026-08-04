from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT
    / "corpus"
    / "extracted"
    / "cgmes3_testconfig"
    / "CGMES_ConformityAssessmentScheme_TestConfigurations_v3-0-3"
    / "v3.0"
)
PACKAGES = ROOT / "corpus" / "validation_packages"


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def digest_files(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def package(files: list[Path], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.name)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())


def main() -> None:
    rows: list[dict[str, object]] = []
    directories = sorted({path.parent for path in BASE.rglob("*.xml")})
    for directory in directories:
        files = sorted(directory.glob("*.xml"), key=lambda path: path.name)
        names = [path.name.upper() for path in files]
        if not (
            any("_EQ" in name for name in names)
            and any("_TP" in name for name in names)
            and any("_SSH" in name for name in names)
        ):
            continue
        relative = directory.relative_to(BASE).as_posix()
        source_digest = digest_files(files)
        case_id = f"validation_cgmes3_{slug(relative)}_{source_digest[:8]}"
        archive = PACKAGES / f"{case_id}.zip"
        package(files, archive)
        archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        rows.append(
            {
                "case_id": case_id,
                "source_directory": relative,
                "family": relative.split("/", 1)[0],
                "cgmes_version": "3.0.0",
                "split": "internal_validation",
                "xml_file_count": len(files),
                "uncompressed_size_bytes": sum(path.stat().st_size for path in files),
                "source_content_sha256": source_digest,
                "package_relative_path": archive.relative_to(ROOT).as_posix(),
                "package_size_bytes": archive.stat().st_size,
                "package_sha256": archive_sha,
                "packaging_semantic_edit": False,
                "included": True,
                "exclusion_reason": "",
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(ROOT / "corpus" / "validation_model_registry.csv", index=False)
    summary = {
        "model_packages": len(frame),
        "families": frame.family.value_counts().to_dict(),
        "cgmes_version": "3.0.0",
        "split": "internal_validation",
        "packaging_semantic_edit": False,
        "source_package": "ENTSO-E CGMES CAS Test Configurations 3.0.3",
        "redistribution_allowed": False,
    }
    (ROOT / "corpus" / "validation_model_registry_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
