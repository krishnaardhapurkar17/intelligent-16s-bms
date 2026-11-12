"""Run a reproducible multi-location, multi-severity diagnostic stress grid."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "results/metrics"
CSV_PATH = OUT_DIR / "lfp_fault_diagnostic_grid.csv"
JSON_PATH = OUT_DIR / "lfp_fault_diagnostic_grid.json"
CELL_COUNT = 16
R0_HEALTHY = 0.0005
R1 = 0.0002
TAU_S = 30.0
OCV_V = 3.30
DT_S = 1.0
VOLTAGE_THRESHOLD_MV = 15.0
RESISTANCE_THRESHOLD_RATIO = 1.20
CURRENT_PROFILE = ((0, 0), (20, 25), (50, 0), (70, 50),
                   (100, 0), (120, 100), (150, 0), (180, 0))
REPLICATES = 3
VOLTAGE_NOISE_STD_V = 0.001
CURRENT_NOISE_STD_A = 0.1
MIN_CURRENT_STEP_A = 50.0


def simulate(cell_index: int | None, fault_type: str, severity: float,
             seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    time = np.arange(0.0, 181.0, DT_S)
    current = np.zeros_like(time)
    for start, value in CURRENT_PROFILE:
        current[time >= start] = value
    resistance = np.full(CELL_COUNT, R0_HEALTHY, dtype=float)
    bias = np.zeros(CELL_COUNT, dtype=float)
    if cell_index is not None and fault_type == "resistance_growth":
        resistance[cell_index] *= 1.0 + severity
    elif cell_index is not None and fault_type == "voltage_sensor_bias":
        bias[cell_index] = -severity / 1000.0
    polarization = np.zeros(CELL_COUNT, dtype=float)
    voltage = np.empty((len(time), CELL_COUNT), dtype=float)
    for index, amps in enumerate(current):
        voltage[index] = OCV_V - amps * resistance - polarization + bias
        polarization += DT_S / TAU_S * (amps * R1 - polarization)
    rng = np.random.default_rng(seed)
    voltage += rng.normal(0.0, VOLTAGE_NOISE_STD_V, voltage.shape)
    measured_current = current + rng.normal(0.0, CURRENT_NOISE_STD_A, current.shape)
    return time, measured_current, voltage


def classify(current: np.ndarray, voltage: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    resistance_samples = [[] for _ in range(CELL_COUNT)]
    for index in range(1, len(current)):
        delta_current = current[index] - current[index - 1]
        # Small steps amplify voltage noise when estimating milliohm-scale
        # resistance. Use the higher-amplitude excitation edges only.
        if abs(delta_current) < MIN_CURRENT_STEP_A:
            continue
        delta_voltage = voltage[index] - voltage[index - 1]
        estimates = -delta_voltage / delta_current
        for cell in range(CELL_COUNT):
            resistance_samples[cell].append(estimates[cell])
    resistance = np.asarray([np.median(samples) for samples in resistance_samples])
    reference_voltage = np.median(voltage[140])
    deviation_mv = (reference_voltage - voltage[140]) * 1000.0
    median_r = np.median(resistance)
    resistance_alarm = resistance / median_r > RESISTANCE_THRESHOLD_RATIO
    voltage_alarm = deviation_mv >= VOLTAGE_THRESHOLD_MV
    labels = np.where(resistance_alarm, "resistance_degradation",
                      np.where(voltage_alarm, "voltage_sensor_bias", "none"))
    return voltage_alarm, resistance_alarm, labels


def score(actual: np.ndarray, predicted: np.ndarray) -> dict:
    tp = int(np.sum(actual & predicted))
    fp = int(np.sum(~actual & predicted))
    fn = int(np.sum(actual & ~predicted))
    tn = int(np.sum(~actual & ~predicted))
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "false_positive_rate": fp / (fp + tn) if fp + tn else None}


def main() -> int:
    scenarios = [(None, "healthy", 0.0)]
    scenarios += [(cell, "resistance_growth", fraction)
                  for cell in range(CELL_COUNT) for fraction in (0.25, 0.50, 1.00)]
    scenarios += [(cell, "voltage_sensor_bias", mv)
                  for cell in range(CELL_COUNT) for mv in (10.0, 20.0, 30.0, 50.0)]
    rows = []
    for replicate in range(REPLICATES):
        for scenario_index, (fault_cell, fault_type, severity) in enumerate(scenarios):
            seed = 20261110 + replicate * 10000 + scenario_index
            _, current, voltage = simulate(fault_cell, fault_type, severity, seed)
            voltage_alarm, resistance_alarm, enhanced_labels = classify(current, voltage)
            for cell in range(CELL_COUNT):
                truth = fault_cell == cell
                baseline_alarm = bool(voltage_alarm[cell])
                enhanced_alarm = enhanced_labels[cell] != "none"
                expected_cause = ({"resistance_growth": "resistance_degradation",
                                   "voltage_sensor_bias": "voltage_sensor_bias"}
                                  .get(fault_type, "none") if truth else "none")
                rows.append({"seed": seed, "replicate": replicate,
                             "fault_type": fault_type, "severity": severity,
                             "fault_cell": "" if fault_cell is None else fault_cell + 1,
                             "cell": cell + 1, "fault_present": bool(truth),
                             "baseline_voltage_alarm": baseline_alarm,
                             "enhanced_resistance_alarm": bool(resistance_alarm[cell]),
                             "enhanced_alarm": enhanced_alarm,
                             "enhanced_classification": str(enhanced_labels[cell]),
                             "expected_cause": expected_cause})
    actual = np.asarray([row["fault_present"] for row in rows], dtype=bool)
    baseline = np.asarray([row["baseline_voltage_alarm"] for row in rows], dtype=bool)
    enhanced = np.asarray([row["enhanced_alarm"] for row in rows], dtype=bool)
    fault_rows = [row for row in rows if row["fault_present"]]
    cause_correct = sum(row["enhanced_classification"] == row["expected_cause"]
                        for row in fault_rows)
    by_type = {}
    for fault_type in ("resistance_growth", "voltage_sensor_bias"):
        subset = [row for row in fault_rows if row["fault_type"] == fault_type]
        expected_label = {"resistance_growth": "resistance_degradation",
                          "voltage_sensor_bias": "voltage_sensor_bias"}[fault_type]
        by_type[fault_type] = {"fault_cell_recall": sum(row["enhanced_alarm"] for row in subset) / len(subset),
                               "cause_accuracy": sum(row["enhanced_classification"] == expected_label for row in subset) / len(subset),
                               "cases": len(subset)}
    report = {
        "experiment": "seeded fault location, severity, and sensor-noise diagnostic grid",
        "scenario_count": len(scenarios) * REPLICATES,
        "cell_records": len(rows),
        "grid": {"cells": CELL_COUNT, "resistance_growth_fractions": [0.25, 0.5, 1.0],
                 "voltage_bias_mV": [10, 20, 30, 50], "replicates_per_case": REPLICATES,
                 "voltage_noise_std_mV": VOLTAGE_NOISE_STD_V * 1000,
                 "current_noise_std_A": CURRENT_NOISE_STD_A,
                 "minimum_resistance_estimation_current_step_A": MIN_CURRENT_STEP_A,
                 "thresholds": {"voltage_deviation_mV": VOLTAGE_THRESHOLD_MV,
                                "resistance_ratio": RESISTANCE_THRESHOLD_RATIO}},
        "voltage_only_baseline": score(actual, baseline),
        "multi_signal_classifier": score(actual, enhanced),
        "multi_signal_by_fault_type": by_type,
        "multi_signal_fault_cause_accuracy": cause_correct / len(fault_rows),
        "limitations": [
            "All cases use one simplified first-order ECM and fixed pulse profile; severity and cell location are varied synthetically.",
            "The three noise replicates are seeded simulations, not independent physical samples.",
            "Voltage-only detection is cell-voltage deviation; multi-signal classification uses voltage and pulse-derived resistance.",
            "Thresholds were selected before this grid but remain provisional and may not generalize to battery hardware.",
            "No field or hardware validation is demonstrated.",
        ],
        "status": "SIMULATION_STRESS_EVIDENCE_ONLY",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    JSON_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"CSV: {CSV_PATH}")
    print(f"JSON: {JSON_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
