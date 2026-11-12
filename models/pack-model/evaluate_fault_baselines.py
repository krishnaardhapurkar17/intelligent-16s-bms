"""Compare voltage-only alarms with the simulated multi-signal classifier."""

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "results" / "metrics" / "lfp_16s_fault_isolation.csv"
OUT = ROOT / "results" / "metrics"
EXPECTED_FAULT = {
    "Healthy": (None, None),
    "Cell 8 resistance growth": (8, "Possible resistance degradation"),
    "Cell 8 sensor bias": (8, "Possible voltage sensor bias"),
}


def confusion(truth, prediction):
    tp = sum(bool(t and p) for t, p in zip(truth, prediction, strict=True))
    fp = sum(bool(not t and p) for t, p in zip(truth, prediction, strict=True))
    fn = sum(bool(t and not p) for t, p in zip(truth, prediction, strict=True))
    tn = sum(bool(not t and not p) for t, p in zip(truth, prediction, strict=True))
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "false_positive_rate": fp / (fp + tn) if fp + tn else None}


def evaluate(frame: pd.DataFrame) -> dict:
    required = {"Scenario", "Cell", "Voltage_Anomaly", "Resistance_Anomaly", "Classification"}
    if not required.issubset(frame.columns):
        raise ValueError("fault isolation data lacks required labels or predictions")
    truth, baseline, enhanced, cause_correct = [], [], [], []
    baseline_cause_correct = []
    unknown_scenarios = []
    for row in frame.to_dict("records"):
        expected = EXPECTED_FAULT.get(row["Scenario"])
        if expected is None:
            unknown_scenarios.append(row["Scenario"])
            continue
        true_cell, expected_cause = expected
        actual = true_cell == int(row["Cell"])
        truth.append(actual)
        baseline.append(bool(row["Voltage_Anomaly"]))
        enhanced_prediction = row["Classification"] != "No anomaly detected"
        enhanced.append(enhanced_prediction)
        if actual:
            cause_correct.append(row["Classification"] == expected_cause)
            # The voltage-only baseline can say only "voltage anomaly";
            # it distinguishes neither resistance growth nor sensor bias.
            baseline_cause_correct.append(expected_cause == "Possible voltage sensor bias")
    if unknown_scenarios:
        raise ValueError(f"unexpected scenarios: {sorted(set(unknown_scenarios))}")
    return {"sample_count": len(truth),
            "ground_truth_fault_cells": sum(truth),
            "voltage_only_baseline": confusion(truth, baseline),
            "multi_signal_classifier": confusion(truth, enhanced),
            "baseline_fault_type_correct": sum(baseline_cause_correct),
            "baseline_fault_type_total": len(baseline_cause_correct),
            "fault_type_correct": sum(cause_correct),
            "fault_type_total": len(cause_correct),
            "limitations": [
                "These are three deterministic simulated scenarios, not an independent statistical holdout.",
                "Voltage-only alarms identify anomalies but cannot distinguish resistance growth from sensor bias.",
                "No hardware or field generalization is demonstrated.",
            ]}


def main() -> int:
    if not INPUT.is_file():
        raise FileNotFoundError(f"Run the fault-isolation scenario first: {INPUT}")
    report = evaluate(pd.read_csv(INPUT))
    report["experiment"] = "voltage-only baseline versus multi-signal simulated classifier"
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "lfp_fault_baseline_comparison.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("Report:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
