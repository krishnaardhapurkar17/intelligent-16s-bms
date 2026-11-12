
from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from lfp_voltage_baseline import evaluate_voltage_deviation

ROOT = Path(__file__).resolve().parents[2]

INPUT = ROOT / "results" / "metrics" / "lfp_16s_weak_cell.csv"
OUTPUT = ROOT / "results" / "metrics"
FIGURES = ROOT / "results" / "figures"

OUTPUT.mkdir(parents=True, exist_ok=True)
FIGURES.mkdir(parents=True, exist_ok=True)

# Provisional detection settings.
# These are experiment settings, not validated BMS safety thresholds.
VOLTAGE_DEVIATION_THRESHOLD_V = 0.015
PERSISTENCE_SAMPLES = 5

# --------------------------------------------------
# 1. LOAD CELL VOLTAGE MEASUREMENTS
# --------------------------------------------------

data = pd.read_csv(INPUT)

voltage_columns = [
    f"Cell_{i}_voltage_V"
    for i in range(1, 17)
]

voltages = data[voltage_columns].to_numpy(dtype=float)

if not np.all(np.isfinite(voltages)):
    raise ValueError("Invalid or missing cell voltage data.")

# --------------------------------------------------
# 2. CALCULATE CELL-TO-MEDIAN VOLTAGE DEVIATION
# --------------------------------------------------

reference_voltage = np.median(voltages, axis=1)

# Positive deviation means a cell is below the pack median.
deviations = reference_voltage[:, None] - voltages

# --------------------------------------------------
# 3. APPLY PERSISTENCE-BASED DETECTION
# --------------------------------------------------

baseline_result = evaluate_voltage_deviation(
    voltages,
    threshold_v=VOLTAGE_DEVIATION_THRESHOLD_V,
    persistence_samples=PERSISTENCE_SAMPLES,
)
first_detection = baseline_result.first_detection_index
detected_cell = baseline_result.suspected_cell

# --------------------------------------------------
# 4. BUILD DIAGNOSTIC OUTPUT
# --------------------------------------------------

diagnostic_data = pd.DataFrame({
    "Time_min": data["Time_min"],
    "Reference_voltage_V": reference_voltage,
})

for cell_index in range(16):

    diagnostic_data[
        f"Cell_{cell_index+1}_deviation_V"
    ] = deviations[:, cell_index]

row_candidates = deviations >= VOLTAGE_DEVIATION_THRESHOLD_V
diagnostic_data["Suspected_cell"] = [
    int(np.flatnonzero(candidates)[0] + 1) if np.count_nonzero(candidates) == 1 else None
    for candidates in row_candidates
]

diagnostic_data["Maximum_deviation_V"] = (
    np.max(deviations, axis=1)
)

# --------------------------------------------------
# 5. FINAL CELL RANKING
# --------------------------------------------------

final_deviations = deviations[-1]

ranking = np.argsort(final_deviations)[::-1]

print("=" * 60)
print("16S LFP VOLTAGE DEVIATION DIAGNOSTICS")
print("=" * 60)

print("\nFINAL CELL DEVIATIONS")
print("-" * 60)

for index in ranking:

    print(
        f"Cell {index+1:02d}: "
        f"{final_deviations[index] * 1000:.2f} mV below median"
    )

# --------------------------------------------------
# 6. DETECTION RESULT
# --------------------------------------------------

if detected_cell is not None:

    detection_time = float(
        data.iloc[first_detection]["Time_min"]
    )

    result = "VOLTAGE ANOMALY DETECTED"

    print("\nDIAGNOSTIC RESULT")
    print("-" * 60)
    print(result)
    print(f"Suspected cell: Cell {detected_cell}")
    print(f"Detection time: {detection_time:.2f} minutes")
    print(
        "Detection deviation: "
        f"{deviations[first_detection, detected_cell-1]*1000:.2f} mV"
    )

else:

    detection_time = None
    result = "NO VOLTAGE ANOMALY DETECTED"

    print("\nDIAGNOSTIC RESULT")
    print("-" * 60)
    print(result)

# --------------------------------------------------
# 7. EXPORT DIAGNOSTIC DATA
# --------------------------------------------------

csv_path = OUTPUT / "lfp_voltage_deviation_diagnostics.csv"

diagnostic_data.to_csv(csv_path, index=False)

summary = {
    "method": "Cell-to-median voltage deviation",
    "threshold_mV": VOLTAGE_DEVIATION_THRESHOLD_V * 1000,
    "persistence_samples": PERSISTENCE_SAMPLES,
    "result": result,
    "localization_status": baseline_result.status,
    "localization_candidates": list(baseline_result.candidates),
    "suspected_cell": detected_cell,
    "detection_time_minutes": detection_time,
    "final_largest_deviation_mV": float(
        np.max(final_deviations) * 1000
    ),
    "limitations": [
        "Provisional threshold",
        "Single controlled simulated fault",
        "No sensor noise or initial cell variation",
        "Voltage anomaly does not uniquely prove capacity degradation"
    ]
}

json_path = OUTPUT / "lfp_voltage_diagnostic_summary.json"

with open(json_path, "w") as file:
    json.dump(summary, file, indent=4)

# --------------------------------------------------
# 8. PLOT CELL VOLTAGE DEVIATIONS
# --------------------------------------------------

plt.figure(figsize=(12, 6))

for cell_index in range(16):

    plt.plot(
        data["Time_min"],
        deviations[:, cell_index] * 1000,
        linewidth=1.2,
        label=f"Cell {cell_index+1}"
    )

plt.axhline(
    VOLTAGE_DEVIATION_THRESHOLD_V * 1000,
    linestyle="--",
    label="Detection threshold"
)

if detection_time is not None:
    plt.axvline(
        detection_time,
        linestyle=":",
        label="First detection"
    )

plt.xlabel("Time (minutes)")
plt.ylabel("Voltage below median (mV)")
plt.title("16S LFP Pack - Cell Voltage Deviation Diagnostic")

plt.grid(True)
plt.legend(ncol=3, fontsize=8)
plt.tight_layout()

plot_path = FIGURES / "lfp_voltage_deviation_diagnostic.png"

plt.savefig(plot_path, dpi=300)
plt.show()

print("\nGENERATED FILES")
print(csv_path)
print(json_path)
print(plot_path)

print("\nDIAGNOSTIC EXPERIMENT COMPLETE")
