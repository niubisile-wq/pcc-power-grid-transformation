from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
VARIANTS = (
    (
        "attempt2_no_sv_multi_file_default",
        RESULTS / "minimum_roundtrip_results__attempt2_no_sv.csv",
        "SV omitted; exporter default multi-file/profile handling",
    ),
    (
        "attempt3_single_archive_no_sv",
        RESULTS / "minimum_roundtrip_results__attempt3_single_archive_no_sv.csv",
        "SV omitted; one explicit CGMES archive passed to each reimport target",
    ),
)


def main() -> None:
    rows: list[dict[str, object]] = []
    for variant, path, description in VARIANTS:
        frame = pd.read_csv(path, keep_default_na=False)
        rows.append(
            {
                "variant": variant,
                "description": description,
                "models": int(frame.case_id.nunique()),
                "attempt_rows": len(frame),
                "success": int(frame.status.eq("success").sum()),
                "error": int(frame.status.eq("error").sum()),
                "routes": " | ".join(sorted(frame.route.unique().tolist())),
                "complete_denominator": True,
            }
        )
    output = pd.DataFrame(rows)
    output.to_csv(RESULTS / "serialization_profile_variant_results.csv", index=False)
    summary = {
        "variant_count": len(output),
        "model_count": int(max(output.models)),
        "attempt_rows": int(output.attempt_rows.sum()),
        "success": int(output.success.sum()),
        "error": int(output.error.sum()),
        "claim_limit": (
            "This is a two-model minimum-round-trip sensitivity check. It does not "
            "represent an exhaustive enumeration of CGMES profile or serialization choices."
        ),
    }
    (RESULTS / "serialization_profile_variant_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Serialization and profile-combination sensitivity",
        "",
        "| variant | description | attempts | success | error |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['variant']} | {row['description']} | {row['attempt_rows']} | "
            f"{row['success']} | {row['error']} |"
        )
    lines.extend(
        [
            "",
            "The raw failure in the first variant is retained. The second variant shows that "
            "explicit single-archive handling enabled both VeraGrid exports and pandapower "
            "reimports, while both PyPowSyBl reimports still failed because a BaseVoltage "
            "nominal voltage was absent. This bounded diagnostic is not generalized beyond "
            "the two frozen MiniGrid models.",
        ]
    )
    (RESULTS / "SERIALIZATION_PROFILE_VARIANT_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
