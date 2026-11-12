"""Compare RUL forests with causal SOH-slope extrapolation on fixed holdouts."""

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "results/raw/lfp/uconn_rpt_features.csv"
CELL_REPORT = ROOT / "results/metrics/lfp_ai_validation.json"
GROUP_REPORT = ROOT / "results/metrics/lfp_ai_protocol_group_validation.json"
OUT = ROOT / "results/metrics/lfp_rul_baseline_comparison.json"
EOL_SOH_PCT = 80.0


def add_past_slope(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["cell_id"], []).append(row)
    for history in grouped.values():
        history.sort(key=lambda x: float(x["cumulative_cycles"]))
        for i, row in enumerate(history):
            window = history[max(0, i - 3):i + 1]
            if len(window) < 2:
                row["_slope"] = None
                continue
            x = np.array([float(item["cumulative_cycles"]) for item in window])
            y = np.array([float(item["soh_pct"]) for item in window])
            xc, yc = x - x.mean(), y - y.mean()
            denom = float(xc @ xc)
            slope = float(xc @ yc / denom) if denom else 0.0
            row["_slope"] = max(0.0, -slope * 1000.0)


def score(rows, held_cells):
    sample = [r for r in rows if r["cell_id"] in held_cells and r.get("rul_cycles_to_80pct", "") != ""]
    actual = np.array([float(r["rul_cycles_to_80pct"]) for r in sample])
    predicted = []
    slope_missing = 0
    for row in sample:
        slope = row["_slope"]
        if slope is None or slope <= 0:
            predicted.append(float("nan"))
            slope_missing += 1
        else:
            predicted.append(max(0.0, (float(row["soh_pct"]) - EOL_SOH_PCT) * 1000.0 / slope))
    pred = np.asarray(predicted)
    valid = np.isfinite(pred)
    residual = pred[valid] - actual[valid]
    return {"rows": len(sample), "usable_slope_rows": int(valid.sum()), "missing_or_zero_slope_rows": slope_missing,
            "linear_soh_slope_baseline": {
                "mae_cycles": float(np.mean(np.abs(residual))) if len(residual) else None,
                "rmse_cycles": float(np.sqrt(np.mean(residual ** 2))) if len(residual) else None,
                "max_absolute_error_cycles": float(np.max(np.abs(residual))) if len(residual) else None,
            }}


def main():
    with FEATURES.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    add_past_slope(rows)
    cell_eval = json.loads(CELL_REPORT.read_text(encoding="utf-8-sig"))
    group_eval = json.loads(GROUP_REPORT.read_text(encoding="utf-8-sig"))
    cell_holdout = set(cell_eval["held_out_cells"])
    groups = set(map(str, group_eval["held_out_groups"]))
    params_candidates = list((ROOT / "datasets").glob("UConn*/CyclingParameters.csv"))
    if len(params_candidates) != 1:
        raise FileNotFoundError("Unable to uniquely locate UConn CyclingParameters.csv")
    with params_candidates[0].open(encoding="utf-8-sig", newline="") as f:
        cell_group = {str(int(float(r["Cell ID"]))).zfill(2): str(int(float(r["Group Number"])))
                      for r in csv.DictReader(f)}
    group_cells = {cell for cell, group in cell_group.items() if group in groups}
    report = {
        "target": "cycles until first observed reference capacity at or below 80% SOH",
        "baseline": "past-only trailing four-RPT linear SOH fade slope extrapolated to 80%",
        "limitations": [
            "Slope extrapolation assumes near-term linear capacity fade and can be unstable with few RPTs.",
            "These fixed holdouts were also used to report the forest scores; do not tune on them and reuse them as final unbiased test sets.",
            "End-of-life is observed-threshold RUL, not a prospective field-life guarantee.",
        ],
        "whole_cell_holdout": {"held_out_cells": sorted(cell_holdout),
                               **score(rows, cell_holdout),
                               "forest_metrics": cell_eval["models"]["rul"]["held_out_metrics"]},
        "whole_protocol_group_holdout": {"held_out_groups": sorted(groups, key=int),
                                          **score(rows, group_cells),
                                          "forest_metrics": group_eval["models"]["rul"]["held_out_metrics"]},
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("Report:", OUT)


if __name__ == "__main__":
    main()
