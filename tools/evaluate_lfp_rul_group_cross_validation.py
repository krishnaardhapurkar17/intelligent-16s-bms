"""Evaluate LFP RUL models with every protocol group held out in turn.

This is grouped cross-validation, not an external final test: each fold keeps
all cells and RPT rows from one cycling protocol out of that fold's training.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from train_lfp_tree_models import read_cell_groups, train_one  # noqa: E402

FEATURES = ROOT / "results/raw/lfp/uconn_rpt_features.csv"
OUT = ROOT / "results/metrics/lfp_rul_group_cross_validation.json"
CELL_HOLDOUT = ROOT / "results/metrics/lfp_ai_validation.json"
GROUP_HOLDOUT = ROOT / "results/metrics/lfp_ai_protocol_group_validation.json"
PARAMETERS = next((ROOT / "datasets").glob("UConn*/CyclingParameters.csv"))
EOL_SOH_PCT = 80.0
FEATURE_SETS = {
    "full_five_features": ["cumulative_cycles", "soh_pct", "pulse_resistance_ohm_mean",
                            "pulse_soc_count", "soh_fade_pct_per_1000_cycles"],
    "capacity_and_causal_fade": ["cumulative_cycles", "soh_pct",
                                  "soh_fade_pct_per_1000_cycles"],
    "capacity_and_resistance": ["cumulative_cycles", "soh_pct",
                                 "pulse_resistance_ohm_mean"],
}


def add_causal_fade(rows: list[dict[str, str]]) -> None:
    by_cell: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_cell.setdefault(row["cell_id"], []).append(row)
    for history in by_cell.values():
        history.sort(key=lambda row: float(row["cumulative_cycles"]))
        for index, row in enumerate(history):
            window = history[max(0, index - 3):index + 1]
            if len(window) < 2:
                row["soh_fade_pct_per_1000_cycles"] = ""
                continue
            cycles = np.asarray([float(item["cumulative_cycles"]) for item in window])
            soh = np.asarray([float(item["soh_pct"]) for item in window])
            centered = cycles - cycles.mean()
            denom = float(centered @ centered)
            slope = float(centered @ (soh - soh.mean()) / denom) if denom else 0.0
            row["soh_fade_pct_per_1000_cycles"] = f"{max(0.0, -slope * 1000):.8f}"


def error_metrics(actual: list[float], predicted: list[float]) -> dict[str, float | int]:
    errors = np.asarray(predicted, dtype=float) - np.asarray(actual, dtype=float)
    return {"rows": int(len(errors)), "mae_cycles": float(np.mean(np.abs(errors))),
            "rmse_cycles": float(np.sqrt(np.mean(errors ** 2))),
            "max_absolute_error_cycles": float(np.max(np.abs(errors)))}


def main() -> int:
    with FEATURES.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    add_causal_fade(rows)
    cell_groups = read_cell_groups(PARAMETERS)
    groups = sorted({cell_groups[row["cell_id"]] for row in rows}, key=int)
    folds = []
    variant_scores = {name: {"actual": [], "predicted": []} for name in FEATURE_SETS}
    slope_actual: list[float] = []
    slope_predicted: list[float] = []
    for fold_index, group in enumerate(groups):
        test_cells = {cell for cell, value in cell_groups.items() if value == group}
        train_cells = {row["cell_id"] for row in rows} - test_cells
        fold_models = {}
        for variant_index, (variant, feature_names) in enumerate(FEATURE_SETS.items()):
            _, metrics, test_rows, actual, prediction = train_one(
                rows, feature_names, "rul_cycles_to_80pct", train_cells, test_cells,
                seed=20261110 + fold_index, tree_count=64, max_depth=8, min_leaf=5)
            variant_scores[variant]["actual"].extend(float(x) for x in actual)
            variant_scores[variant]["predicted"].extend(float(x) for x in prediction)
            fold_models[variant] = metrics
        actual_values = np.asarray(actual, dtype=float)
        fold_slope_actual, fold_slope_pred = [], []
        for row, target in zip(test_rows, actual_values, strict=True):
            rate = float(row.get("soh_fade_pct_per_1000_cycles") or 0.0)
            if rate <= 0:
                continue
            estimate = max(0.0, (float(row["soh_pct"]) - EOL_SOH_PCT) * 1000.0 / rate)
            fold_slope_actual.append(float(target))
            fold_slope_pred.append(estimate)
        slope_actual.extend(fold_slope_actual)
        slope_predicted.extend(fold_slope_pred)
        folds.append({"protocol_group": group,
                      "train_cells": len(train_cells),
                      "held_out_cells": sorted(test_cells),
                      "model_metrics": fold_models,
                      "slope_baseline_metrics": error_metrics(fold_slope_actual, fold_slope_pred)
                      if fold_slope_actual else None})
        print(f"Group {group}: " + ", ".join(
            f"{name} MAE {score['mae']:.1f}" for name, score in fold_models.items()))

    model_metrics = {name: error_metrics(values["actual"], values["predicted"])
                     for name, values in variant_scores.items()}
    reused_holdouts = {}
    for label, report_path in (("whole_cell", CELL_HOLDOUT), ("protocol_group", GROUP_HOLDOUT)):
        holdout = json.loads(report_path.read_text(encoding="utf-8"))
        held_out = set(holdout["held_out_cells"])
        train_cells = {row["cell_id"] for row in rows} - held_out
        test_cells = held_out
        if label == "protocol_group":
            held_groups = set(map(str, holdout["held_out_groups"]))
            test_cells = {cell for cell, group in cell_groups.items() if group in held_groups}
            train_cells = {row["cell_id"] for row in rows} - test_cells
        scores = {}
        for variant_index, (variant, feature_names) in enumerate(FEATURE_SETS.items()):
            _, score, _, _, _ = train_one(
                rows, feature_names, "rul_cycles_to_80pct", train_cells, test_cells,
                seed=20261110 + variant_index, tree_count=64, max_depth=8, min_leaf=5)
            scores[variant] = {"mae_cycles": score["mae"],
                               "rmse_cycles": score["rmse"],
                               "max_absolute_error_cycles": score["max_absolute_error"]}
        reused_holdouts[label] = scores

    report = {
        "dataset": "UConn-ISU-ILCC LFP/graphite RPT",
        "evaluation": "11-fold leave-one-protocol-group-out cross-validation",
        "model_parameters": {"seed_base": 20261110,
                  "trees": 64, "max_depth": 8, "min_leaf": 5},
        "feature_ablation_metrics": model_metrics,
        "selected_candidate_features": FEATURE_SETS["capacity_and_causal_fade"],
        "development_holdout_feature_ablation": reused_holdouts,
        "causal_four_rpt_slope_baseline_metrics": error_metrics(slope_actual, slope_predicted),
        "slope_baseline_usable_rows": len(slope_actual),
        "folds": folds,
        "limitations": [
            "Each fold excludes every cell and row from its held-out protocol group during fitting.",
            "This cross-validation uses the same source dataset used to develop the model and is not an external final test.",
            "The whole-cell and protocol-group feature ablations reuse prior development holdouts and are not new test evidence.",
            "The slope baseline is scored only where a positive past-only capacity fade rate is available.",
            "End of life is observed 80% reference capacity, not prospective field lifetime.",
            "Model output remains research-only and must not control battery protection.",
        ],
        "status": "RESEARCH_ONLY",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"feature_ablation_metrics": report["feature_ablation_metrics"],
                      "slope_baseline_metrics": report["causal_four_rpt_slope_baseline_metrics"],
                      "report": str(OUT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
