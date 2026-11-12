
from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# --------------------------------------------------
# PATHS AND CONFIGURATION
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = ROOT / "results" / "metrics" / "lfp_16s_pack_baseline.csv"

OUTPUT_CSV = ROOT / "results" / "metrics" / "lfp_16s_sensor_bias.csv"
OUTPUT_DIAGNOSTICS = ROOT / "results" / "metrics" / "lfp_sensor_bias_diagnostics.csv"
OUTPUT_JSON = ROOT / "results" / "metrics" / "lfp_sensor_bias_summary.json"
OUTPUT_PLOT = ROOT / "results" / "figures" / "lfp_sensor_bias_diagnostic.png"

FAULT_CELL = 8
SENSOR_BIAS_V = -0.030
THRESHOLD_MV = 15.0
PERSISTENCE_SAMPLES = 5

CELL_COLUMNS = [
    f"Cell_{i}_voltage_V" for i in range(1, 17)
]


# --------------------------------------------------
# LOAD HEALTHY BASELINE
# --------------------------------------------------

print("=" * 60)
print("16S LFP VOLTAGE SENSOR BIAS FAULT TEST")
print("=" * 60)

if not INPUT_FILE.exists():
    raise FileNotFoundError(
        f"Healthy baseline not found: {INPUT_FILE}"
    )

df = pd.read_csv(INPUT_FILE)

required_columns = ["Time_min"] + CELL_COLUMNS
missing = [c for c in required_columns if c not in df.columns]

if missing:
    raise ValueError(f"Missing required columns: {missing}")

if df.empty:
    raise ValueError("Baseline CSV contains no data.")

# Copy actual simulated cell voltages.
measured = df[CELL_COLUMNS].copy()

# Inject bias into Cell 8's measurement only.
fault_column = f"Cell_{FAULT_CELL}_voltage_V"
measured[fault_column] += SENSOR_BIAS_V

# Preserve original time column.
output = pd.DataFrame()
output["Time_min"] = df["Time_min"]

for column in CELL_COLUMNS:
    output[column] = measured[column]

OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_DIAGNOSTICS.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_PLOT.parent.mkdir(parents=True, exist_ok=True)

output.to_csv(OUTPUT_CSV, index=False)


# --------------------------------------------------
# VOLTAGE-ONLY DIAGNOSTIC
# --------------------------------------------------

voltage_matrix = measured.to_numpy()

# Median reference across the 16 measured cell voltages.
median_voltage = np.median(voltage_matrix, axis=1)

# Positive deviation means a cell is below the median.
deviation_mv = (
    median_voltage[:, None] - voltage_matrix
) * 1000.0

consecutive_counts = np.zeros(16, dtype=int)
detected_cell = None
detection_index = None
detection_deviation = None

diagnostic_rows = []

for row_index in range(len(output)):

    row_deviations = deviation_mv[row_index]

    for cell_index in range(16):

        if row_deviations[cell_index] >= THRESHOLD_MV:
            consecutive_counts[cell_index] += 1
        else:
            consecutive_counts[cell_index] = 0

        if (
            detected_cell is None
            and consecutive_counts[cell_index] >= PERSISTENCE_SAMPLES
        ):
            detected_cell = cell_index + 1
            detection_index = row_index
            detection_deviation = float(row_deviations[cell_index])

    largest_index = int(np.argmax(row_deviations))

    diagnostic_rows.append({
        "Time_min": float(output.iloc[row_index]["Time_min"]),
        "Largest_deviation_cell": largest_index + 1,
        "Largest_deviation_mV": float(
            row_deviations[largest_index]
        ),
        "Detected_cell": detected_cell,
    })

diagnostics = pd.DataFrame(diagnostic_rows)
diagnostics.to_csv(OUTPUT_DIAGNOSTICS, index=False)


# --------------------------------------------------
# FINAL RESULTS
# --------------------------------------------------

final_deviations = deviation_mv[-1]

print("\nFINAL MEASURED VOLTAGE DEVIATIONS")
print("-" * 60)

for i, value in enumerate(final_deviations, start=1):
    print(f"Cell {i:02d}: {value:.2f} mV below median")

if detected_cell is not None:
    detection_time = float(
        output.iloc[detection_index]["Time_min"]
    )

    result = "VOLTAGE ANOMALY DETECTED"

    print("\nDIAGNOSTIC RESULT")
    print("-" * 60)
    print(result)
    print(f"Suspected cell: Cell {detected_cell}")
    print(f"Detection time: {detection_time:.4f} minutes")
    print(f"Detection deviation: {detection_deviation:.2f} mV")
else:
    detection_time = None
    result = "NO VOLTAGE ANOMALY DETECTED"

    print("\nDIAGNOSTIC RESULT")
    print("-" * 60)
    print(result)

summary = {
    "experiment": "16S voltage sensor bias fault injection",
    "battery_state": "Healthy baseline; no battery degradation injected",
    "fault_type": "Voltage sensor negative bias",
    "fault_cell": FAULT_CELL,
    "injected_sensor_bias_mV": SENSOR_BIAS_V * 1000.0,
    "detection_threshold_mV": THRESHOLD_MV,
    "persistence_samples": PERSISTENCE_SAMPLES,
    "diagnostic_result": result,
    "suspected_cell": detected_cell,
    "detection_time_min": detection_time,
    "final_cell_8_deviation_mV": float(
        final_deviations[FAULT_CELL - 1]
    ),
    "interpretation": (
        "The voltage-only detector identifies a measurement anomaly. "
        "It cannot determine whether the cause is a sensor fault "
        "or an actual cell voltage anomaly."
    ),
    "limitations": [
        "Sensor bias is injected in simulation; thresholds are provisional.",
        "A voltage residual alone cannot distinguish sensor bias from a cell fault.",
        "No physical cell or sensor validation is represented.",
    ],
}

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=4)


# --------------------------------------------------
# PLOT
# --------------------------------------------------

time = output["Time_min"].to_numpy()

plt.figure(figsize=(14, 6))

for i in range(16):
    plt.plot(
        time,
        deviation_mv[:, i],
        label=f"Cell {i + 1}"
    )

plt.axhline(
    THRESHOLD_MV,
    linestyle="--",
    linewidth=2,
    label="Detection threshold"
)

if detection_time is not None:
    plt.axvline(
        detection_time,
        linestyle=":",
        linewidth=2,
        label="First detection"
    )

plt.title("16S LFP Pack - Voltage Sensor Bias Diagnostic")
plt.xlabel("Time (minutes)")
plt.ylabel("Measured voltage below median (mV)")
plt.grid(True)
plt.legend(ncol=3)
plt.tight_layout()

plt.savefig(OUTPUT_PLOT, dpi=200)
plt.close()


# --------------------------------------------------
# VALIDATION
# --------------------------------------------------

assert detected_cell == FAULT_CELL, (
    f"Expected Cell {FAULT_CELL}, detected {detected_cell}"
)

assert abs(
    final_deviations[FAULT_CELL - 1] - 30.0
) < 1.0, "Injected sensor bias was not reflected as expected."

print("\nVALIDATION PASSED")
print("Sensor bias was detected on the intended measurement channel.")

print("\nGENERATED FILES")
print(OUTPUT_CSV)
print(OUTPUT_DIAGNOSTICS)
print(OUTPUT_JSON)
print(OUTPUT_PLOT)

print("\nEXPERIMENT COMPLETE")
