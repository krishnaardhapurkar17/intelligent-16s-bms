"""Train portable LFP SOH/RUL regression forests from UConn RPT summaries.

The implementation uses NumPy only and exports the same small JSON tree format
consumed by the project's portable ensemble runner. The holdout is selected by
cell, so adjacent RPT rows from one cell never appear in both partitions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SOH_FEATURES = ["cumulative_cycles", "pulse_resistance_ohm_mean", "pulse_soc_count"]
RUL_FEATURES = ["cumulative_cycles", "soh_pct", "soh_fade_pct_per_1000_cycles"]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def read_cell_groups(path: Path) -> dict[str, str]:
    mapping = {}
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            cell = str(int(float(row["Cell ID"]))).zfill(2)
            mapping[cell] = str(int(float(row["Group Number"])))
    return mapping


def feature_matrix(rows: list[dict[str, str]], names: list[str], imputation: dict[str, float]):
    values = []
    for row in rows:
        sample = []
        for name in names:
            raw = row.get(name, "")
            sample.append(imputation[name] if raw == "" else float(raw))
        values.append(sample)
    return np.asarray(values, dtype=np.float64)


def fit_tree(x: np.ndarray, y: np.ndarray, rng: np.random.Generator,
             *, max_depth: int, min_leaf: int) -> dict:
    """Build one randomized CART regression tree and return portable arrays."""
    children: list[list[int]] = []
    feature_index: list[int] = []
    cut_point: list[float] = []
    node_mean: list[float] = []
    feature_count = x.shape[1]
    max_features = max(1, int(math.sqrt(feature_count)))

    def grow(indices: np.ndarray, depth: int) -> int:
        node = len(children)
        children.append([0, 0])
        feature_index.append(0)
        cut_point.append(0.0)
        node_mean.append(float(np.mean(y[indices])))
        if depth >= max_depth or len(indices) < 2 * min_leaf:
            return node

        best_loss = float("inf")
        best_split = None
        features = rng.choice(feature_count, size=max_features, replace=False)
        for feature in features:
            order = np.argsort(x[indices, feature], kind="stable")
            ordered_indices = indices[order]
            xv = x[ordered_indices, feature]
            if xv[0] == xv[-1]:
                continue
            yv = y[ordered_indices]
            cumulative = np.cumsum(yv)
            cumulative_sq = np.cumsum(yv * yv)
            positions = np.arange(min_leaf, len(indices) - min_leaf + 1)
            boundaries = positions[(xv[positions - 1] < xv[positions])]
            if not len(boundaries):
                continue
            left_sum = cumulative[boundaries - 1]
            right_sum = cumulative[-1] - left_sum
            left_sq = cumulative_sq[boundaries - 1]
            right_sq = cumulative_sq[-1] - left_sq
            left_n = boundaries.astype(np.float64)
            right_n = len(indices) - left_n
            loss = (left_sq - left_sum * left_sum / left_n
                    + right_sq - right_sum * right_sum / right_n)
            best_at = int(np.argmin(loss))
            if float(loss[best_at]) < best_loss:
                split_pos = int(boundaries[best_at])
                left_val = float(xv[split_pos - 1])
                right_val = float(xv[split_pos])
                best_loss = float(loss[best_at])
                best_split = (int(feature), (left_val + right_val) / 2.0,
                              ordered_indices[:split_pos], ordered_indices[split_pos:])
        if best_split is None:
            return node
        feature, threshold, left_rows, right_rows = best_split
        feature_index[node] = feature + 1  # Portable format uses one-based indices.
        cut_point[node] = threshold
        left_node = grow(left_rows, depth + 1)
        right_node = grow(right_rows, depth + 1)
        children[node] = [left_node + 1, right_node + 1]
        return node

    grow(np.arange(len(y), dtype=np.int64), 0)
    return {"children": children, "cut_predictor_index": feature_index,
            "cut_point": cut_point, "node_mean": node_mean}


def predict_tree(tree: dict, values: np.ndarray) -> np.ndarray:
    result = np.empty(len(values), dtype=np.float64)
    children = tree["children"]
    for row_index, sample in enumerate(values):
        node = 0
        while children[node][0] != 0:
            feature = tree["cut_predictor_index"][node] - 1
            node = children[node][0 if sample[feature] < tree["cut_point"][node] else 1] - 1
        result[row_index] = tree["node_mean"][node]
    return result


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = predicted - actual
    return {"mae": float(np.mean(np.abs(error))),
            "rmse": float(np.sqrt(np.mean(error * error))),
            "max_absolute_error": float(np.max(np.abs(error))),
            "r2": float(1.0 - np.sum(error * error) /
                        max(float(np.sum((actual - np.mean(actual)) ** 2)), 1e-12))}


def train_one(rows, feature_names, target_name, train_cells, test_cells,
              seed, tree_count, max_depth, min_leaf):
    train = [row for row in rows if row["cell_id"] in train_cells
             and row.get(target_name, "") != ""]
    test = [row for row in rows if row["cell_id"] in test_cells
            and row.get(target_name, "") != ""]
    if not train or not test:
        raise ValueError(f"Insufficient rows for {target_name}: train={len(train)} test={len(test)}")
    imputation = {}
    for name in feature_names:
        observed = [float(row[name]) for row in train if row.get(name, "") != ""]
        if not observed:
            raise ValueError(f"No training values for feature {name}")
        imputation[name] = float(np.median(observed))
    x_train = feature_matrix(train, feature_names, imputation)
    y_train = np.asarray([float(row[target_name]) for row in train])
    x_test = feature_matrix(test, feature_names, imputation)
    y_test = np.asarray([float(row[target_name]) for row in test])
    rng = np.random.default_rng(seed)
    trees = []
    predictions = np.zeros(len(test), dtype=np.float64)
    for tree_index in range(tree_count):
        sample_indices = rng.integers(0, len(y_train), size=len(y_train))
        tree = fit_tree(x_train[sample_indices], y_train[sample_indices], rng,
                        max_depth=max_depth, min_leaf=min_leaf)
        trees.append(tree)
        predictions += predict_tree(tree, x_test) / tree_count
    model = {"format_version": 1, "model_type": "portable randomized regression forest",
             "method": "Bag", "features": feature_names, "target": target_name,
             "weights": [1.0 / tree_count] * tree_count, "bias": 0.0,
             "trees": trees, "feature_imputation": imputation,
             "training_cells": sorted(train_cells), "held_out_cells": sorted(test_cells),
             "seed": seed}
    return model, metrics(y_test, predictions), test, y_test, predictions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path,
                        default=ROOT / "results/raw/lfp/uconn_rpt_features.csv")
    parser.add_argument("--models-dir", type=Path, default=ROOT / "models/ai")
    parser.add_argument("--report", type=Path, default=ROOT / "results/metrics/lfp_ai_validation.json")
    parser.add_argument("--split", choices=("cell", "protocol-group"), default="cell")
    parser.add_argument("--cycling-parameters", type=Path)
    parser.add_argument("--seed", type=int, default=20261110)
    parser.add_argument("--trees", type=int, default=64)
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--min-leaf", type=int, default=5)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    args = parser.parse_args()
    if not 0.1 <= args.test_fraction <= 0.4:
        parser.error("--test-fraction must be between 0.1 and 0.4")
    rows = read_rows(args.features)
    cells = sorted({row["cell_id"] for row in rows})
    if len(cells) < 5:
        raise ValueError("At least five distinct cells are required for cell holdout evaluation")
    split_rng = np.random.default_rng(args.seed)
    group_mapping = None
    if args.split == "protocol-group":
        parameters_path = args.cycling_parameters
        if parameters_path is None:
            candidates = list((ROOT / "datasets").glob("UConn*/CyclingParameters.csv"))
            candidates += list((ROOT / "datasets").glob("UConn*/cycling_parameters.csv"))
            if len(candidates) != 1:
                raise FileNotFoundError("Pass --cycling-parameters to identify UConn group metadata")
            parameters_path = candidates[0]
        group_mapping = read_cell_groups(parameters_path)
        missing_cells = sorted(set(cells) - set(group_mapping))
        if missing_cells:
            raise ValueError(f"Cycling parameters lack cells: {missing_cells}")
        groups = sorted(set(group_mapping[cell] for cell in cells), key=int)
        permuted_groups = list(np.asarray(groups)[split_rng.permutation(len(groups))])
        test_group_count = max(1, round(len(groups) * args.test_fraction))
        test_groups = set(permuted_groups[:test_group_count])
        test_cells = {cell for cell in cells if group_mapping[cell] in test_groups}
    else:
        permuted = list(np.asarray(cells)[split_rng.permutation(len(cells))])
        test_count = max(1, round(len(cells) * args.test_fraction))
        test_cells = set(permuted[:test_count])
        test_groups = set()
    train_cells = set(cells) - test_cells
    # A trailing, past-only linear slope reduces RUL sensitivity to single-RPT
    # capacity noise. It never uses observations after the current row.
    by_cell: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_cell.setdefault(row["cell_id"], []).append(row)
    for cell_rows in by_cell.values():
        cell_rows.sort(key=lambda row: float(row["cumulative_cycles"]))
        for index, row in enumerate(cell_rows):
            history = cell_rows[max(0, index - 3):index + 1]
            if len(history) < 2:
                row["soh_fade_pct_per_1000_cycles"] = ""
                continue
            cycles = np.asarray([float(item["cumulative_cycles"]) for item in history])
            soh = np.asarray([float(item["soh_pct"]) for item in history])
            centered = cycles - np.mean(cycles)
            denominator = float(centered @ centered)
            slope = float(centered @ (soh - np.mean(soh)) / denominator) if denominator else 0.0
            row["soh_fade_pct_per_1000_cycles"] = f"{max(0.0, -slope * 1000.0):.8f}"
    args.models_dir.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    report = {"dataset": "UConn-ISU-ILCC LFP/Gr battery aging RPT",
              "split": ("whole-protocol-group holdout" if args.split == "protocol-group"
                        else "whole-cell holdout"), "seed": args.seed,
              "training_cells": sorted(train_cells), "held_out_cells": sorted(test_cells),
              "training_rows": sum(row["cell_id"] in train_cells for row in rows),
              "held_out_rows": sum(row["cell_id"] in test_cells for row in rows),
              "models": {},
              "limitations": [
                  "Validation holds out cells, while some aging protocol groups may appear in both partitions.",
                  "SOH and RUL labels derive from reference discharge capacity and observed 80% end of life.",
                  "Pulse resistance is an approximate first-sample voltage/current step estimate.",
                  "This is offline research evidence and does not authorize primary protection use.",
              ]}
    if group_mapping is not None:
        report["training_groups"] = sorted({group_mapping[cell] for cell in train_cells}, key=int)
        report["held_out_groups"] = sorted(test_groups, key=int)
        report["limitations"].remove(
            "Validation holds out cells, while some aging protocol groups may appear in both partitions.")
    predictions_rows = []
    settings = [("soh", SOH_FEATURES, "soh_pct"),
                ("rul", RUL_FEATURES, "rul_cycles_to_80pct")]
    for offset, (model_name, feature_names, target) in enumerate(settings):
        model, score, test_rows, actual, predicted = train_one(
            rows, feature_names, target, train_cells, test_cells,
            args.seed + offset, args.trees, args.max_depth, args.min_leaf)
        report["models"][model_name] = {"features": feature_names, "target": target,
                                         "held_out_metrics": score}
        path = args.models_dir / f"lfp_{model_name}_ensemble.json"
        path.write_text(json.dumps(model, separators=(",", ":")), encoding="utf-8")
        for row, actual_value, prediction in zip(test_rows, actual, predicted, strict=True):
            predictions_rows.append({"model": model_name, "cell_id": row["cell_id"],
                                     "rpt_number": row["rpt_number"],
                                     "actual": float(actual_value),
                                     "predicted": float(prediction)})
        print(f"{model_name.upper()} held-out metrics: {score}")

    report["status"] = "RESEARCH_ONLY"
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    pred_path = args.report.with_name("lfp_ai_holdout_predictions.csv")
    with pred_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["model", "cell_id", "rpt_number",
                                                    "actual", "predicted"])
        writer.writeheader()
        writer.writerows(predictions_rows)
    print(f"Report written to {args.report}")
    print(f"Portable model assets written to {args.models_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
