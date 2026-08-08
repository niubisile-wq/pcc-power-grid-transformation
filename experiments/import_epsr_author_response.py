"""Import filled author-response Markdown into the metadata JSON template.

Default mode is dry-run. Pass ``--apply`` to write non-empty answers into
``manuscript/EPSR_AUTHOR_METADATA_TEMPLATE.json``.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESPONSE = ROOT / "outputs" / "epsr_author_metadata" / "author_response_form.md"
TEMPLATE = ROOT / "manuscript" / "EPSR_AUTHOR_METADATA_TEMPLATE.json"
OUT = ROOT / "outputs" / "epsr_author_metadata"


def parse_response(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = re.fullmatch(r"##\s+(.+)", line.strip())
        if heading:
            value = heading.group(1).strip()
            current = None if value.lower().startswith("reference values") else value
            continue
        if current and line.startswith("Answer:"):
            fields[current] = line.split("Answer:", 1)[1].strip()
            current = None
    return fields


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write non-empty answers into the JSON template")
    args = parser.parse_args()

    answers = parse_response(RESPONSE.read_text(encoding="utf-8"))
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    non_empty = {field: value for field, value in answers.items() if value}
    empty = [field for field, value in answers.items() if not value]
    unknown = [field for field in non_empty if field not in template]

    applied = []
    if args.apply and not unknown:
        for field, value in non_empty.items():
            template[field] = value
            applied.append(field)
        TEMPLATE.write_text(json.dumps(template, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    result = {
        "importer": "epsr-author-response-import-v1",
        "mode": "apply" if args.apply else "dry_run",
        "response": str(RESPONSE.relative_to(ROOT)),
        "target_template": str(TEMPLATE.relative_to(ROOT)),
        "non_empty_answers": sorted(non_empty),
        "empty_answers": empty,
        "unknown_fields": unknown,
        "applied_fields": applied,
        "wrote_template": bool(applied),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "author_response_import.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not unknown else 2


if __name__ == "__main__":
    raise SystemExit(main())
