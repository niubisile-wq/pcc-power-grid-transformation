from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import time
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.common_asset_schema import frame, sha256  # noqa: E402
from adapters.pandapower_adapter import load_and_extract as load_pandapower  # noqa: E402
from adapters.pypowsybl_adapter import load_and_extract as load_pypowsybl  # noqa: E402
from adapters.veragrid_adapter import load_and_extract as load_veragrid  # noqa: E402


LOADERS = {
    "pandapower": load_pandapower,
    "pypowsybl": load_pypowsybl,
    "veragrid": load_veragrid,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", choices=sorted(LOADERS), required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--cgmes-version", default="2.4.15")
    parser.add_argument("--asset-output", type=Path, required=True)
    parser.add_argument("--result-output", type=Path, required=True)
    args = parser.parse_args()
    args.asset_output.parent.mkdir(parents=True, exist_ok=True)
    args.result_output.parent.mkdir(parents=True, exist_ok=True)
    capture = io.StringIO()
    started = time.perf_counter()
    status = "success"
    error_type = ""
    error_message = ""
    metadata: dict[str, object] = {}
    messages: list[str] = []
    asset_count = 0
    try:
        with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
            records, metadata, messages = LOADERS[args.tool](
                args.source,
                args.case_id,
                args.cgmes_version,
            )
        assets = frame(records)
        asset_count = len(assets)
        assets.to_csv(args.asset_output, index=False)
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
        "asset_output": args.asset_output.as_posix() if status == "success" else "",
        "asset_count": asset_count,
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
    print(json.dumps({key: payload[key] for key in ("case_id", "tool", "status", "asset_count", "error_type")}))


if __name__ == "__main__":
    main()
