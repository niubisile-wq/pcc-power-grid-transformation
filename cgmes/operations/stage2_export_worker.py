from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import time
import traceback
from pathlib import Path

import pypowsybl as pp


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.common_asset_schema import sha256  # noqa: E402

from VeraGridEngine.IO.cim.cgmes.cgmes_enums import CgmesProfileType  # noqa: E402
from VeraGridEngine.IO.file_open import FileOpen, FileOpenOptions  # noqa: E402
from VeraGridEngine.IO.file_save import FileSave, FileSavingOptions  # noqa: E402
from VeraGridEngine.enumerations import CGMESVersions, FileType  # noqa: E402


PYPOWSYBL_EXPORT_PARAMETERS = {
    "iidm.export.cgmes.profiles": "EQ,TP,SSH",
    "iidm.export.cgmes.naming-strategy": "identity",
}


def _veragrid_version(cgmes_version: str) -> CGMESVersions:
    versions = {
        "2.4.15": CGMESVersions.v2_4_15,
        "3.0": CGMESVersions.v3_0_0,
        "3.0.0": CGMESVersions.v3_0_0,
    }
    try:
        return versions[cgmes_version]
    except KeyError as exc:
        raise ValueError(f"Unsupported CGMES version: {cgmes_version}") from exc


def export_veragrid(
    source: Path, boundary: Path | None, output: Path, cgmes_version: str
) -> tuple[list[str], dict[str, object]]:
    version = _veragrid_version(cgmes_version)
    options = FileOpenOptions(file_type=FileType.CGMES, cgmes_version=version)
    circuit = FileOpen(str(source), options=options).open()
    if circuit is None:
        raise RuntimeError("VeraGrid returned no circuit")
    kwargs: dict[str, object] = {
        "file_type": FileType.CGMES,
        "cgmes_version": version,
        "cgmes_profiles": [CgmesProfileType.EQ, CgmesProfileType.TP, CgmesProfileType.SSH],
        "cgmes_one_file_per_profile": False,
    }
    if boundary is not None:
        kwargs["cgmes_boundary_set"] = str(boundary)
    save_log = FileSave(circuit, str(output), options=FileSavingOptions(**kwargs)).save()
    messages = [str(entry) for entry in save_log.entries]
    metadata = {
        "boundary_supplied": boundary is not None,
        "profiles": ["EQ", "TP", "SSH"],
        "cgmes_version": cgmes_version,
    }
    return messages, metadata


def export_pypowsybl(
    source: Path, output: Path, case_id: str, cgmes_version: str
) -> tuple[list[str], dict[str, object]]:
    network = pp.network.load(str(source))
    parameters = {
        **PYPOWSYBL_EXPORT_PARAMETERS,
        "iidm.export.cgmes.cim-version": "100"
        if cgmes_version in {"3.0", "3.0.0"}
        else "16",
        "iidm.export.cgmes.base-name": f"{case_id}_pypowsybl",
    }
    network.save(str(output), format="CGMES", parameters=parameters)
    return [], {"export_parameters": parameters}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", choices=("veragrid", "pypowsybl"), required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--boundary", type=Path)
    parser.add_argument("--cgmes-version", default="2.4.15")
    parser.add_argument("--export-output", type=Path, required=True)
    parser.add_argument("--result-output", type=Path, required=True)
    args = parser.parse_args()
    args.export_output.parent.mkdir(parents=True, exist_ok=True)
    args.result_output.parent.mkdir(parents=True, exist_ok=True)
    capture = io.StringIO()
    messages: list[str] = []
    metadata: dict[str, object] = {}
    status = "success"
    error_type = ""
    error_message = ""
    started = time.perf_counter()
    try:
        with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
            if args.tool == "veragrid":
                messages, metadata = export_veragrid(
                    args.source, args.boundary, args.export_output, args.cgmes_version
                )
            else:
                messages, metadata = export_pypowsybl(
                    args.source, args.export_output, args.case_id, args.cgmes_version
                )
        if not args.export_output.is_file() or args.export_output.stat().st_size == 0:
            raise RuntimeError("Exporter did not create a non-empty archive")
    except Exception as exc:
        status = "error"
        error_type = type(exc).__name__
        error_message = str(exc)
        messages.append(traceback.format_exc())
    messages.extend(line for line in capture.getvalue().splitlines() if line.strip())
    payload = {
        "case_id": args.case_id,
        "tool": args.tool,
        "status": status,
        "source_path": args.source.as_posix(),
        "source_sha256": sha256(args.source),
        "boundary_path": args.boundary.as_posix() if args.boundary else "",
        "boundary_sha256": sha256(args.boundary) if args.boundary else "",
        "export_path": args.export_output.as_posix() if args.export_output.is_file() else "",
        "export_sha256": sha256(args.export_output) if args.export_output.is_file() else "",
        "export_size_bytes": args.export_output.stat().st_size if args.export_output.is_file() else 0,
        "worker_elapsed_seconds": time.perf_counter() - started,
        "metadata": metadata,
        "message_count": len(messages),
        "messages": messages,
        "error_type": error_type,
        "error_message": error_message,
    }
    args.result_output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: payload[key] for key in ("case_id", "tool", "status", "export_size_bytes", "error_type")}))


if __name__ == "__main__":
    main()
