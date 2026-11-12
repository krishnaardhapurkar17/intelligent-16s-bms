
from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# 1. PROJECT PATHS
# ============================================================

ROOT = Path(__file__).resolve().parents[2]

METRICS_DIR = ROOT / "results" / "metrics"
FIGURES_DIR = ROOT / "results" / "figures"

METRICS_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_CSV = METRICS_DIR / "lfp_16s_temperature_sensor_faults.csv"
OUTPUT_JSON = METRICS_DIR / "lfp_16s_temperature_sensor_faults_summary.json"
OUTPUT_PLOT = FIGURES_DIR / "lfp_16s_temperature_sensor_faults.png"


# ============================================================
# 2. EXPERIMENT CONFIGURATION
# ============================================================

CELL_COUNT = 16
SAMPLE_COUNT = 181
SAMPLE_INTERVAL_SECONDS = 1

ACTUAL_TEMPERATURE_C = 25.0

# Provisional diagnostic thresholds.
TEMP_DEVIATION_THRESHOLD_C = 5.0
NOISE_STD_THRESHOLD_C = 1.5

# Healthy sensor noise and injected faulty sensor noise.
HEALTHY_SENSOR_NOISE_STD_C = 0.2
FAULTY_SENSOR_NOISE_STD_C = 2.5

POSITIVE_SENSOR_BIAS_C = 15.0
NEGATIVE_SENSOR_BIAS_C = -15.0

RANDOM_SEED = 42


# ============================================================
# 3. CREATE ACTUAL CELL TEMPERATURES
# ============================================================

actual_temperatures = np.full(
    (SAMPLE_COUNT, CELL_COUNT),
    ACTUAL_TEMPERATURE_C,
    dtype=float
)

time_seconds = (
    np.arange(SAMPLE_COUNT)
    * SAMPLE_INTERVAL_SECONDS
)


# ============================================================
# 4. SENSOR MEASUREMENT SIMULATION
# ============================================================

def simulate_sensor_measurements(
    scenario_name,
    sensor_bias_cell=None,
    sensor_bias_c=0.0,
    noisy_sensor_cell=None
):

    rng = np.random.default_rng(RANDOM_SEED)

    # Start with healthy measurement noise on all channels.
    noise = rng.normal(
        loc=0.0,
        scale=HEALTHY_SENSOR_NOISE_STD_C,
        size=(SAMPLE_COUNT, CELL_COUNT)
    )

    # Inject excessive noise into the selected sensor.
    if noisy_sensor_cell is not None:

        noise[:, noisy_sensor_cell - 1] = rng.normal(
            loc=0.0,
            scale=FAULTY_SENSOR_NOISE_STD_C,
            size=SAMPLE_COUNT
        )

    # Apply measurement noise.
    measured = actual_temperatures + noise

    # Inject constant sensor bias.
    if sensor_bias_cell is not None:

        measured[:, sensor_bias_cell - 1] += sensor_bias_c

    return {
        "scenario": scenario_name,
        "actual": actual_temperatures.copy(),
        "measured": measured,
    }


# ============================================================
# 5. DEFINE EXPERIMENT SCENARIOS
# ============================================================

scenarios = [

    simulate_sensor_measurements(
        "Healthy sensors"
    ),

    simulate_sensor_measurements(
        "Cell 8 positive bias",
        sensor_bias_cell=8,
        sensor_bias_c=POSITIVE_SENSOR_BIAS_C
    ),

    simulate_sensor_measurements(
        "Cell 8 negative bias",
        sensor_bias_cell=8,
        sensor_bias_c=NEGATIVE_SENSOR_BIAS_C
    ),

    simulate_sensor_measurements(
        "Cell 8 excessive noise",
        noisy_sensor_cell=8
    ),
]


# ============================================================
# 6. SENSOR FAULT DIAGNOSTICS
# ============================================================

all_results = []
scenario_summaries = {}

print("=" * 70)
print("16S LFP TEMPERATURE SENSOR FAULT DIAGNOSTICS")
print("=" * 70)

for scenario in scenarios:

    scenario_name = scenario["scenario"]

    actual = scenario["actual"]
    measured = scenario["measured"]

    # Calculate average measured temperature for each cell.
    mean_temperature = np.mean(
        measured,
        axis=0
    )

    # Calculate temporal standard deviation for each sensor.
    noise_std = np.std(
        measured,
        axis=0,
        ddof=1
    )

    # Calculate the pack median based on sensor averages.
    pack_median = np.median(
        mean_temperature
    )

    # Absolute deviation from the pack median.
    temperature_deviation = np.abs(
        mean_temperature - pack_median
    )

    scenario_rows = []

    for i in range(CELL_COUNT):

        bias_warning = (
            temperature_deviation[i]
            >= TEMP_DEVIATION_THRESHOLD_C
        )

        noise_warning = (
            noise_std[i]
            >= NOISE_STD_THRESHOLD_C
        )

        if bias_warning and noise_warning:

            classification = (
                "Possible sensor bias and excessive noise"
            )

        elif bias_warning:

            classification = (
                "Possible temperature sensor bias"
            )

        elif noise_warning:

            classification = (
                "Possible excessive temperature sensor noise"
            )

        else:

            classification = (
                "No temperature sensor anomaly detected"
            )

        row = {
            "Scenario": scenario_name,
            "Cell": i + 1,
            "Actual_Temperature_C": float(
                np.mean(actual[:, i])
            ),
            "Measured_Mean_Temperature_C": float(
                mean_temperature[i]
            ),
            "Measured_Temperature_Std_C": float(
                noise_std[i]
            ),
            "Pack_Median_Measured_Temperature_C": float(
                pack_median
            ),
            "Temperature_Deviation_C": float(
                temperature_deviation[i]
            ),
            "Bias_Warning": bool(bias_warning),
            "Noise_Warning": bool(noise_warning),
            "Classification": classification,
        }

        scenario_rows.append(row)
        all_results.append(row)

    # Cell 8 diagnostic summary.
    cell8 = scenario_rows[7]

    print(f"\nSCENARIO: {scenario_name}")
    print("-" * 70)

    print(
        f"Actual Cell 8 temperature: "
        f"{cell8['Actual_Temperature_C']:.2f} C"
    )

    print(
        f"Measured Cell 8 mean: "
        f"{cell8['Measured_Mean_Temperature_C']:.2f} C"
    )

    print(
        f"Measured Cell 8 standard deviation: "
        f"{cell8['Measured_Temperature_Std_C']:.3f} C"
    )

    print(
        f"Deviation from pack median: "
        f"{cell8['Temperature_Deviation_C']:.2f} C"
    )

    print(
        f"Bias warning: "
        f"{cell8['Bias_Warning']}"
    )

    print(
        f"Noise warning: "
        f"{cell8['Noise_Warning']}"
    )

    print(
        f"Classification: "
        f"{cell8['Classification']}"
    )

    scenario_summaries[scenario_name] = {
        "cell_8_actual_temperature_C": (
            cell8["Actual_Temperature_C"]
        ),
        "cell_8_measured_mean_C": (
            cell8["Measured_Mean_Temperature_C"]
        ),
        "cell_8_noise_std_C": (
            cell8["Measured_Temperature_Std_C"]
        ),
        "cell_8_temperature_deviation_C": (
            cell8["Temperature_Deviation_C"]
        ),
        "bias_warning": cell8["Bias_Warning"],
        "noise_warning": cell8["Noise_Warning"],
        "classification": cell8["Classification"],
    }


# ============================================================
# 7. SAVE CSV RESULTS
# ============================================================

results_df = pd.DataFrame(all_results)

results_df.to_csv(
    OUTPUT_CSV,
    index=False
)


# ============================================================
# 8. SAVE JSON SUMMARY
# ============================================================

summary = {
    "experiment": "16S LFP temperature sensor fault injection",
    "cell_count": CELL_COUNT,
    "actual_cell_temperature_C": ACTUAL_TEMPERATURE_C,
    "sample_count": SAMPLE_COUNT,
    "sample_interval_seconds": SAMPLE_INTERVAL_SECONDS,
    "healthy_sensor_noise_std_C": HEALTHY_SENSOR_NOISE_STD_C,
    "faulty_sensor_noise_std_C": FAULTY_SENSOR_NOISE_STD_C,
    "positive_sensor_bias_C": POSITIVE_SENSOR_BIAS_C,
    "negative_sensor_bias_C": NEGATIVE_SENSOR_BIAS_C,
    "temperature_deviation_threshold_C": TEMP_DEVIATION_THRESHOLD_C,
    "noise_std_threshold_C": NOISE_STD_THRESHOLD_C,
    "random_seed": RANDOM_SEED,
    "scenarios": scenario_summaries,
    "limitations": [
        "All actual cell temperatures are fixed at 25 C.",
        "Temperature bias is identified through pack median comparison.",
        "A real thermal anomaly and a sensor bias may be indistinguishable using temperature measurements alone.",
        "The diagnostic thresholds are provisional.",
        "The experiment does not model thermal dynamics."
    ]
}

with open(
    OUTPUT_JSON,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        summary,
        f,
        indent=4
    )


# ============================================================
# 9. PLOT CELL 8 SENSOR READINGS
# ============================================================

fig, axes = plt.subplots(
    2,
    1,
    figsize=(13, 9)
)

for scenario in scenarios:

    measured = scenario["measured"]

    axes[0].plot(
        time_seconds,
        measured[:, 7],
        label=scenario["scenario"]
    )

axes[0].axhline(
    ACTUAL_TEMPERATURE_C,
    linestyle="--",
    label="Actual cell temperature"
)

axes[0].set_title(
    "Cell 8 - Actual vs Reported Temperature"
)

axes[0].set_xlabel(
    "Time (seconds)"
)

axes[0].set_ylabel(
    "Temperature (C)"
)

axes[0].grid(True)
axes[0].legend()


# ============================================================
# 10. PLOT SENSOR NOISE
# ============================================================

noise_plot_data = []

for scenario in scenarios:

    measured = scenario["measured"]

    standard_deviations = np.std(
        measured,
        axis=0,
        ddof=1
    )

    noise_plot_data.append(
        (scenario["scenario"], standard_deviations)
    )

for scenario_name, values in noise_plot_data:

    axes[1].plot(
        range(1, CELL_COUNT + 1),
        values,
        marker="o",
        label=scenario_name
    )

axes[1].axhline(
    NOISE_STD_THRESHOLD_C,
    linestyle="--",
    label="Noise warning threshold"
)

axes[1].set_title(
    "Temperature Sensor Noise Across 16 Cells"
)

axes[1].set_xlabel(
    "Cell Number"
)

axes[1].set_ylabel(
    "Temperature standard deviation (C)"
)

axes[1].set_xticks(
    range(1, CELL_COUNT + 1)
)

axes[1].grid(True)
axes[1].legend()

plt.tight_layout()

plt.savefig(
    OUTPUT_PLOT,
    dpi=200
)

plt.close()


# ============================================================
# 11. VALIDATION
# ============================================================

healthy_result = results_df[
    results_df["Scenario"] == "Healthy sensors"
]

positive_result = results_df[
    results_df["Scenario"] == "Cell 8 positive bias"
]

negative_result = results_df[
    results_df["Scenario"] == "Cell 8 negative bias"
]

noise_result = results_df[
    results_df["Scenario"] == "Cell 8 excessive noise"
]


# Check 1: Healthy sensors should not trigger warnings.
assert not healthy_result["Bias_Warning"].any(), (
    "Unexpected bias warning in healthy scenario."
)

assert not healthy_result["Noise_Warning"].any(), (
    "Unexpected noise warning in healthy scenario."
)


# Check 2: Positive bias should be detected on Cell 8.
assert bool(
    positive_result.loc[
        positive_result["Cell"] == 8,
        "Bias_Warning"
    ].iloc[0]
), "Positive sensor bias was not detected."


# Check 3: Negative bias should be detected on Cell 8.
assert bool(
    negative_result.loc[
        negative_result["Cell"] == 8,
        "Bias_Warning"
    ].iloc[0]
), "Negative sensor bias was not detected."


# Check 4: Excessive noise should be detected on Cell 8.
assert bool(
    noise_result.loc[
        noise_result["Cell"] == 8,
        "Noise_Warning"
    ].iloc[0]
), "Excessive sensor noise was not detected."


# Check 5: Other cells should not be falsely flagged.
for dataset, scenario_name in [
    (positive_result, "positive bias"),
    (negative_result, "negative bias"),
    (noise_result, "excessive noise"),
]:

    other_cells = dataset[
        dataset["Cell"] != 8
    ]

    assert not other_cells["Bias_Warning"].any(), (
        f"False bias warning in {scenario_name} scenario."
    )

    assert not other_cells["Noise_Warning"].any(), (
        f"False noise warning in {scenario_name} scenario."
    )


# ============================================================
# 12. VALIDATION REPORT
# ============================================================

print("\n" + "=" * 70)
print("VALIDATION RESULTS")
print("=" * 70)

print("Healthy sensor baseline: PASS")
print("Positive temperature sensor bias: PASS")
print("Negative temperature sensor bias: PASS")
print("Excessive temperature sensor noise: PASS")
print("No false alarms on unaffected cells: PASS")


# ============================================================
# 13. GENERATED FILES
# ============================================================

print("\nGENERATED FILES")

print(OUTPUT_CSV)
print(OUTPUT_JSON)
print(OUTPUT_PLOT)

print("\n" + "=" * 70)
print("TEMPERATURE SENSOR FAULT EXPERIMENT COMPLETE")
print("=" * 70)
