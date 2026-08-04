from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JENA_VERSION = "6.2.0"
JENA_HOME = ROOT / "environment" / "tools" / f"apache-jena-{JENA_VERSION}"
JENA_ARCHIVE = ROOT / "environment" / "tools" / f"apache-jena-{JENA_VERSION}.zip"
EXPECTED_JENA_SHA256 = "d2a6dadc586282f5be7d15010793a336eb8fac4db68eb49209ca5a5656e620b0"
APL_COMMIT = "110d92bf66ae7009e13b4e7c5e96745469c58f83"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_output(command: list[str], environment: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return completed.stdout.strip()


def main() -> None:
    jena_hash = sha256(JENA_ARCHIVE)
    if jena_hash != EXPECTED_JENA_SHA256:
        raise SystemExit(
            f"Apache Jena archive hash mismatch: {jena_hash} != {EXPECTED_JENA_SHA256}"
        )
    environment = os.environ.copy()
    environment["JENA_HOME"] = str(JENA_HOME)
    manifest = json.loads(
        (ROOT / "corpus" / "official_cgmes_corpus_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    apl = next(
        package
        for package in manifest["packages"]
        if package["corpus_id"] == "entsoe_application_profiles_library_main_110d92b"
    )
    payload = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "apache_jena": {
            "version": JENA_VERSION,
            "source_url": f"https://downloads.apache.org/jena/binaries/apache-jena-{JENA_VERSION}.zip",
            "archive_relative_path": JENA_ARCHIVE.relative_to(ROOT).as_posix(),
            "archive_size_bytes": JENA_ARCHIVE.stat().st_size,
            "archive_sha256": jena_hash,
            "version_output": command_output(
                [
                    "cmd.exe",
                    "/d",
                    "/c",
                    str(JENA_HOME / "bat" / "shacl.bat"),
                    "--version",
                ],
                environment,
            ),
            "licence": "Apache-2.0",
            "licence_relative_path": (
                JENA_HOME / "LICENSE"
            ).relative_to(ROOT).as_posix(),
            "role": "secondary SHACL engine compatibility diagnostic",
        },
        "entsoe_application_profiles_library": {
            "commit": APL_COMMIT,
            "source_url": f"https://github.com/entsoe/application-profiles-library/commit/{APL_COMMIT}",
            "download_sha256": apl["download_sha256"],
            "download_size_bytes": apl["download_size_bytes"],
            "licence": "Apache-2.0",
            "role": "post-freeze reference specification robustness only; not a model holdout",
        },
        "java": command_output(["java", "-version"]),
    }
    output = ROOT / "environment" / "external_tool_provenance.json"
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
