"""Build mechanism-level summaries for the frozen DC-SCOPF evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs" / "dc_scopf_mechanism_atlas"
STANDARD = ROOT / "outputs" / "pcc_v2_dc_scopf_gate"
CASE500 = ROOT / "outputs" / "pcc_v2_dc_scopf_case500_clarabel_portfolio"
STATS = ROOT / "outputs" / "pcc_v2_dc_scopf_statistics" / "summary.json"


def read_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    paths = sorted(STANDARD.glob("dc_scopf_gate_all_case*_offset*_1states_results.csv"))
    paths = [path for path in paths if "case500" not in path.name]
    paths += sorted(CASE500.glob("dc_scopf_gate_all_case500_offset*_1states_v11_results.csv"))
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                row["_source_file"] = path.relative_to(ROOT).as_posix()
                rows.append(row)
    return rows


def f(row: dict[str, str], name: str, default: float = 0.0) -> float:
    try:
        return float(row.get(name, "") or default)
    except ValueError:
        return default


def is_true(value: str | None) -> bool:
    return str(value).strip().lower() == "true"


def strict_false_secure(row: dict[str, str]) -> bool:
    if "strict_false_secure_dispatch" in row and row["strict_false_secure_dispatch"] != "":
        return is_true(row["strict_false_secure_dispatch"])
    return (
        f(row, "full_objective") > 0.0
        and f(row, "alias_objective") > 0.0
        and f(row, "full_post_contingency_max_loading_pu") <= 1.0001
        and f(row, "alias_post_contingency_max_loading_pu") > 1.0001
    )


def group_counts(rows: list[dict[str, str]], keys: tuple[str, ...]) -> list[dict[str, object]]:
    groups: dict[tuple[str, ...], list[dict[str, str]]] = {}
    for row in rows:
        groups.setdefault(tuple(row.get(key, "") for key in keys), []).append(row)
    output = []
    for group_key, group_rows in sorted(groups.items()):
        strict = [row for row in group_rows if strict_false_secure(row)]
        output.append({
            **{key: group_key[index] for index, key in enumerate(keys)},
            "rows": len(group_rows),
            "strict_false_secure": len(strict),
            "legacy_false_secure": sum(1 for row in group_rows if is_true(row.get("false_secure_dispatch"))),
            "prevented": sum(1 for row in strict if is_true(row.get("unsafe_result_prevented"))),
            "harmful_solver_starts": sum(int(f(row, "harmful_solver_starts")) for row in strict),
        })
    return output


def distribution(rows: list[dict[str, str]], field: str) -> dict[str, float | int]:
    values = sorted(f(row, field) for row in rows)
    if not values:
        return {"n": 0}
    q1 = values[len(values) // 4]
    q3 = values[(3 * len(values)) // 4]
    return {
        "n": len(values),
        "min": values[0],
        "q1": q1,
        "median": median(values),
        "q3": q3,
        "max": values[-1],
    }


def top_rows(rows: list[dict[str, str]], field: str, limit: int = 12) -> list[dict[str, object]]:
    selected = sorted(rows, key=lambda row: f(row, field), reverse=True)[:limit]
    fields = [
        "network",
        "state_offset",
        "omitted_candidate",
        "branch_component",
        "branch_id",
        "load_scale",
        "loading_rank",
        "full_post_contingency_max_loading_pu",
        "alias_post_contingency_max_loading_pu",
        "full_load_shed_mw",
        "alias_load_shed_mw",
        "relative_cost_understatement",
        "gate_decision",
        "gate_reasons",
        "_source_file",
    ]
    return [{field_name: row.get(field_name, "") for field_name in fields} for row in selected]


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    BASE.mkdir(parents=True, exist_ok=True)
    rows = read_rows()
    stats = json.loads(STATS.read_text(encoding="utf-8-sig"))
    strict = [row for row in rows if strict_false_secure(row)]
    legacy = [row for row in rows if is_true(row.get("false_secure_dispatch"))]
    invalid_pairs = []
    for row in rows:
        full_status = row.get("full_solver_status")
        alias_status = row.get("alias_solver_status")
        if full_status and full_status != "ok":
            invalid_pairs.append(row)
        elif alias_status and alias_status not in ("ok", "reused"):
            invalid_pairs.append(row)
    exacerbated = [
        row for row in rows
        if not strict_false_secure(row)
        and f(row, "full_post_contingency_max_loading_pu") > 1.0001
        and f(row, "alias_post_contingency_max_loading_pu") > f(row, "full_post_contingency_max_loading_pu")
    ]

    by_network_state = group_counts(rows, ("network", "state_offset"))
    by_component = group_counts(rows, ("branch_component",))
    write_csv(BASE / "false_secure_by_network_state.csv", by_network_state)
    write_csv(BASE / "false_secure_by_component.csv", by_component)
    write_csv(BASE / "top_loading_excess_cases.csv", top_rows(strict, "alias_post_contingency_max_loading_pu"))
    write_csv(BASE / "top_hidden_load_shed_cases.csv", top_rows(strict, "alias_load_shed_mw"))
    write_csv(BASE / "top_cost_understatement_cases.csv", top_rows(strict, "relative_cost_understatement"))

    summary = {
        "protocol": "dc_scopf_mechanism_atlas_v1",
        "source": "frozen per-state DC-SCOPF result CSV files",
        "rows": len(rows),
        "strict_false_secure_dispatches": len(strict),
        "legacy_false_secure_dispatches": len(legacy),
        "invalid_solver_pairs_retained": stats["safety"].get("invalid_paired_solver_rows_retained", len(invalid_pairs)),
        "exacerbated_existing_overload_rows": stats["safety"].get("exacerbated_existing_overload_rows", len(exacerbated)),
        "strict_prevented": sum(1 for row in strict if is_true(row.get("unsafe_result_prevented"))),
        "strict_harmful_solver_starts": sum(int(f(row, "harmful_solver_starts")) for row in strict),
        "networks_with_strict_false_secure": sorted({row["network"] for row in strict}),
        "states_with_strict_false_secure": len({(row["network"], row["state_offset"]) for row in strict}),
        "by_component": by_component,
        "effect_distributions_among_strict": {
            "loading_excess_pu": distribution(
                [
                    {
                        "loading_excess": str(
                            max(
                                0.0,
                                f(row, "alias_post_contingency_max_loading_pu")
                                - max(1.0001, f(row, "full_post_contingency_max_loading_pu")),
                            )
                        )
                    }
                    for row in strict
                ],
                "loading_excess",
            ),
            "hidden_load_shed_mw": distribution(
                [
                    {"hidden_load_shed": str(f(row, "full_load_shed_mw") - f(row, "alias_load_shed_mw"))}
                    for row in strict
                ],
                "hidden_load_shed",
            ),
            "relative_cost_understatement": distribution(strict, "relative_cost_understatement"),
        },
        "interpretation": (
            "The atlas separates strict paired false-secure dispatches from retained legacy "
            "overlimit labels, invalid solver pairs, and already-overloaded baselines."
        ),
        "ready": len(strict) == 369 and sum(int(f(row, "harmful_solver_starts")) for row in strict) == 0,
    }
    write_json(BASE / "summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
