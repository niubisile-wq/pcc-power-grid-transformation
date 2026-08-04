"""Deterministic bootstrap and paired-effect audit for public substitute runs."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
METRICS = ["V_mae", "theta_mae", "Pg_mae", "Qg_mae", "cost_mape"]


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def bootstrap_mean(values, rng, n_boot=20000):
    x = np.asarray(values, dtype=float)
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    means = x[idx].mean(axis=1)
    return {
        "n": int(len(x)),
        "mean": float(x.mean()),
        "sd": float(x.std(ddof=1)) if len(x) > 1 else 0.0,
        "ci95_low": float(np.quantile(means, 0.025)),
        "ci95_high": float(np.quantile(means, 0.975)),
    }


def summarize(rows, rng):
    return {m: bootstrap_mean([r[m] for r in rows], rng) for m in METRICS}


def paired(rows, left, right, rng):
    a = {r["case"]: r for r in rows if r["variant"] == left}
    b = {r["case"]: r for r in rows if r["variant"] == right}
    out = {}
    for m in METRICS:
        diffs = [float(a[k][m]) - float(b[k][m]) for k in sorted(set(a) & set(b))]
        out[m] = bootstrap_mean(diffs, rng)
    return out


def main():
    rng = np.random.default_rng(20260801)
    gridsfm = read_csv(ROOT / "gridsfm_representation_ablation_20260801.csv")
    lumina = read_csv(ROOT / "lumina_representation_ablation_20260801.csv")
    result = {
        "seed": 20260801,
        "bootstrap_replicates": 20000,
        "paired_case_count": len([r for r in gridsfm if r["variant"] == "official"]),
        "gridSFM": {
            "by_variant": {v: summarize([r for r in gridsfm if r["variant"] == v], rng) for v in sorted({r["variant"] for r in gridsfm})},
            "paired_differences": {
                "official_minus_certified_split": paired(gridsfm, "official", "certified_split", rng),
                "official_minus_feature_only_merge": paired(gridsfm, "official", "feature_only_merge", rng),
            },
        },
        "LUMINA-2M": {
            "by_variant": {v: summarize([r for r in lumina if r["variant"] == v], rng) for v in sorted({r["variant"] for r in lumina})},
            "paired_differences": {
                "official_minus_certified_split": paired(lumina, "official", "certified_split", rng),
                "official_minus_feature_only_merge": paired(lumina, "official", "feature_only_merge", rng),
            },
        },
        "multiple_comparison_note": "The public ablation has five primary numerical metrics per model; confidence intervals are descriptive and not a substitute for the pre-registered H39 lockbox analysis. Holm correction must be applied to formal hypothesis tests once independent H39 data are available.",
        "limitations": ["public substitute data", "53 paired cases for ablation", "no H39 lockbox", "bootstrap does not correct dataset shift"],
    }
    (ROOT / "public_stats_audit_summary_20260801.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
