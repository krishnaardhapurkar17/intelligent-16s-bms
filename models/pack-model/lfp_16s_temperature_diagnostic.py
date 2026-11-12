
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

OUTPUT_CSV = METRICS_DIR / "lfp_16s_temperature_diagnostics.csv"
OUTPUT_JSON = METRICS_DIR / "lfp_16s_temperature_summary.json"
OUTPUT_PLOT = FIGURES_DIR / "lfp_16s_temperature_diagnostic.png"


# ============================================================
# 2. MODEL PARAMETERS
# ============================================================

CELL_COUNT = 16

R0_REFERENCE = 0.0005       # Ohm at 25 degrees C
R1 = 0.0002                 # Ohm
TAU = 30.0                  # Seconds

OCV = 3.30                  # Simplified constant OCV

REFERENCE_TEMPERATURE = 25.0

# Provisional model coefficient, not experimentally calibrated.
TEMP_COEFFICIENT = -0.004   # -0.4% per degree C

DT = 1.0

# Diagnostic thresholds for this experiment only.
THERMAL_DEVIATION_THRESHOLD = 10.0  # degrees C above pack median
ABSOLUTE_TEMP_THRESHOLD = 45.0      # degrees C
RESISTANCE_RATIO_THRESHOLD = 1.20
VOLTAGE_DEVIATION_THRESHOLD_MV = 15.0

# Current pulse profile: (time seconds, current amperes)
CURRENT_PROFILE = [
    (0, 0),
    (20, 25),
    (50, 0),
    (70, 50),
    (100, 0),
    (120, 100),
    (150, 0),
    (180, 0),
]


# ============================================================
# 3. TEMPERATURE SCENARIOS
# ============================================================

def make_temperature_array(default_temperature):
    return np.full(
        CELL_COUNT,
        default_temperature,
        dtype=float
    )


# Scenario 1: All cells at 25 degrees C.
healthy_temperature = make_temperature_array(25.0)


# Scenario 2: Cell 8 at 40 degrees C.
moderate_temperature = make_temperature_array(25.0)
moderate_temperature[7] = 40.0


# Scenario 3: Cell 8 at 50 degrees C.
high_temperature = make_temperature_array(25.0)
high_temperature[7] = 50.0


# Scenario 4: Temperature variation across the pack.
distributed_temperature = np.linspace(
    20.0,
    35.0,
    CELL_COUNT
)


TEMPERATURE_SCENARIOS = [
    ("Healthy baseline", healthy_temperature),
    ("Cell 8 at 40C", moderate_temperature),
    ("Cell 8 at 50C", high_temperature),
    ("Distributed temperature", distributed_temperature),
]


# ============================================================
# 4. CURRENT PROFILE
# ============================================================

def get_current(time_s):

    current = 0.0

    for start_time, value in CURRENT_PROFILE:

        if time_s >= start_time:
            current = value

    return current


# ============================================================
# 5. TEMPERATURE-DEPENDENT RESISTANCE
# ============================================================

def calculate_temperature_factor(temperature):

    return (
        1.0
        + TEMP_COEFFICIENT
        * (temperature - REFERENCE_TEMPERATURE)
    )


def calculate_cell_resistance(temperature):

    factor = calculate_temperature_factor(temperature)

    if np.any(factor <= 0):
        raise ValueError(
            "Temperature model produced non-positive resistance."
        )

    return R0_REFERENCE * factor


# ============================================================
# 6. SIMULATE ONE 16S SCENARIO
# ============================================================

def simulate_scenario(scenario_name, temperatures):

    time = np.arange(0, 181, DT)

    current = np.array([
        get_current(t) for t in time
    ])

    r0_values = calculate_cell_resistance(
        temperatures
    )

    polarization = np.zeros(CELL_COUNT)

    voltage = np.zeros(
        (len(time), CELL_COUNT)
    )

    for k in range(len(time)):

        # Simplified terminal voltage model.
        voltage[k, :] = (
            OCV
            - current[k] * r0_values
            - polarization
        )

        # First-order RC polarization update.
        polarization += (
            DT / TAU
        ) * (
            current[k] * R1 - polarization
        )

    return {
        "scenario": scenario_name,
        "time": time,
        "current": current,
        "temperature": temperatures.copy(),
        "voltage": voltage,
        "true_r0": r0_values,
    }


# ============================================================
# 7. ESTIMATE RESISTANCE FROM CURRENT TRANSITIONS
# ============================================================

def estimate_resistance(simulation):

    current = simulation["current"]
    voltage = simulation["voltage"]

    estimates = [
        [] for _ in range(CELL_COUNT)
    ]

    for k in range(1, len(current)):

        delta_current = (
            current[k] - current[k - 1]
        )

        if abs(delta_current) < 1e-9:
            continue

        delta_voltage = (
            voltage[k, :] - voltage[k - 1, :]
        )

        estimated_r0 = (
            -delta_voltage / delta_current
        )

        for cell_index in range(CELL_COUNT):

            estimates[cell_index].append(
                estimated_r0[cell_index]
            )

    return np.array([
        np.median(values) if values else np.nan
        for values in estimates
    ])


# ============================================================
# 8. CALCULATE VOLTAGE DEVIATION
# ============================================================

def calculate_voltage_deviation(simulation):

    # Evaluate during the 100 A pulse at 140 seconds.
    index = np.where(
        simulation["time"] == 140
    )[0][0]

    loaded_voltage = simulation["voltage"][index, :]

    reference_voltage = np.median(
        loaded_voltage
    )

    return (
        reference_voltage - loaded_voltage
    ) * 1000.0


# ============================================================
# 9. RUN TEMPERATURE SCENARIOS
# ============================================================

all_results = []
simulation_results = []

print("=" * 70)
print("16S LFP TEMPERATURE DIAGNOSTIC EXPERIMENT")
print("=" * 70)

for scenario_name, temperatures in TEMPERATURE_SCENARIOS:

    simulation = simulate_scenario(
        scenario_name,
        temperatures
    )

    simulation_results.append(simulation)

    estimated_r0 = estimate_resistance(
        simulation
    )

    temperature_factor = calculate_temperature_factor(
        temperatures
    )

    # Convert estimated resistance to its equivalent
    # at the 25 degree C reference temperature.
    compensated_r0 = (
        estimated_r0 / temperature_factor
    )

    voltage_deviation = calculate_voltage_deviation(
        simulation
    )

    median_compensated_r0 = float(
        np.median(compensated_r0)
    )

    median_temperature = float(
        np.median(temperatures)
    )

    scenario_rows = []

    for i in range(CELL_COUNT):

        temperature_deviation = (
            temperatures[i] - median_temperature
        )

        resistance_ratio = (
            compensated_r0[i] / median_compensated_r0
        )

        thermal_deviation_warning = (
            temperature_deviation
            >= THERMAL_DEVIATION_THRESHOLD
        )

        absolute_temperature_warning = (
            temperatures[i]
            >= ABSOLUTE_TEMP_THRESHOLD
        )

        resistance_anomaly = (
            resistance_ratio
            > RESISTANCE_RATIO_THRESHOLD
        )

        voltage_anomaly = (
            voltage_deviation[i]
            >= VOLTAGE_DEVIATION_THRESHOLD_MV
        )

        thermal_warning = (
            thermal_deviation_warning
            or absolute_temperature_warning
        )

        # Diagnostic classification.
        if thermal_warning:

            classification = "Thermal warning"

        elif resistance_anomaly:

            classification = "Possible resistance degradation"

        elif voltage_anomaly:

            classification = "Voltage anomaly"

        else:

            classification = "No anomaly detected"

        row = {
            "Scenario": scenario_name,
            "Cell": i + 1,
            "Temperature_C": temperatures[i],
            "Temperature_Deviation_C": temperature_deviation,
            "Estimated_R0_mOhm": estimated_r0[i] * 1000,
            "Temperature_Factor": temperature_factor[i],
            "Compensated_R0_mOhm": compensated_r0[i] * 1000,
            "Resistance_Ratio": resistance_ratio,
            "Voltage_Deviation_mV": voltage_deviation[i],
            "Thermal_Warning": thermal_warning,
            "Resistance_Anomaly": resistance_anomaly,
            "Voltage_Anomaly": voltage_anomaly,
            "Classification": classification,
        }

        scenario_rows.append(row)
        all_results.append(row)

    # Display Cell 8 results.
    cell8 = scenario_rows[7]

    print(f"\nSCENARIO: {scenario_name}")
    print("-" * 70)

    print(
        f"Cell 8 temperature: "
        f"{cell8['Temperature_C']:.2f} C"
    )

    print(
        f"Pack median temperature: "
        f"{median_temperature:.2f} C"
    )

    print(
        f"Cell 8 raw estimated R0: "
        f"{cell8['Estimated_R0_mOhm']:.4f} mOhm"
    )

    print(
        f"Cell 8 compensated R0: "
        f"{cell8['Compensated_R0_mOhm']:.4f} mOhm"
    )

    print(
        f"Cell 8 resistance ratio: "
        f"{cell8['Resistance_Ratio']:.3f}"
    )

    print(
        f"Cell 8 voltage deviation: "
        f"{cell8['Voltage_Deviation_mV']:.2f} mV"
    )

    print(
        f"Cell 8 thermal warning: "
        f"{cell8['Thermal_Warning']}"
    )

    print(
        f"Cell 8 classification: "
        f"{cell8['Classification']}"
    )


# ============================================================
# 10. SAVE CSV
# ============================================================

results_df = pd.DataFrame(all_results)

results_df.to_csv(
    OUTPUT_CSV,
    index=False
)


# ============================================================
# 11. SAVE JSON SUMMARY
# ============================================================

summary = {
    "experiment": "16S LFP temperature diagnostics",
    "model_type": "Simplified first-order ECM",
    "reference_temperature_C": REFERENCE_TEMPERATURE,
    "temperature_coefficient_per_C": TEMP_COEFFICIENT,
    "thermal_deviation_threshold_C": THERMAL_DEVIATION_THRESHOLD,
    "absolute_temperature_threshold_C": ABSOLUTE_TEMP_THRESHOLD,
    "resistance_ratio_threshold": RESISTANCE_RATIO_THRESHOLD,
    "voltage_deviation_threshold_mV": VOLTAGE_DEVIATION_THRESHOLD_MV,
    "temperature_model_status": "Provisional assumption, not calibrated",
    "limitations": [
        "The first-order ECM and temperature coefficient are illustrative and uncalibrated.",
        "Temperature scenarios do not model thermal propagation or runaway.",
        "Results are simulation diagnostics, not physical validation.",
    ],
    "scenarios": {}
}

for scenario_name, _ in TEMPERATURE_SCENARIOS:

    scenario_rows = results_df[
        results_df["Scenario"] == scenario_name
    ]

    cell8 = scenario_rows[
        scenario_rows["Cell"] == 8
    ].iloc[0]

    summary["scenarios"][scenario_name] = {
        "cell_8_temperature_C": float(
            cell8["Temperature_C"]
        ),
        "cell_8_raw_R0_mOhm": float(
            cell8["Estimated_R0_mOhm"]
        ),
        "cell_8_compensated_R0_mOhm": float(
            cell8["Compensated_R0_mOhm"]
        ),
        "cell_8_voltage_deviation_mV": float(
            cell8["Voltage_Deviation_mV"]
        ),
        "cell_8_thermal_warning": bool(
            cell8["Thermal_Warning"]
        ),
        "cell_8_classification": (
            cell8["Classification"]
        ),
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
# 12. PLOT RESISTANCE AND TEMPERATURE
# ============================================================

fig, axes = plt.subplots(
    2,
    1,
    figsize=(13, 10)
)

for simulation in simulation_results:

    estimated_r0 = (
        estimate_resistance(simulation) * 1000
    )

    temperature_factor = calculate_temperature_factor(
        simulation["temperature"]
    )

    compensated_r0 = (
        estimated_r0 / temperature_factor
    ) * 1000

    axes[0].plot(
        range(1, CELL_COUNT + 1),
        compensated_r0,
        marker="o",
        label=simulation["scenario"]
    )

    axes[1].plot(
        range(1, CELL_COUNT + 1),
        simulation["temperature"],
        marker="o",
        label=simulation["scenario"]
    )

axes[0].set_title(
    "Temperature-compensated Internal Resistance"
)

axes[0].set_ylabel("R0 at 25C (mOhm)")
axes[0].set_xlabel("Cell Number")
axes[0].set_xticks(range(1, CELL_COUNT + 1))
axes[0].grid(True)
axes[0].legend()

axes[1].axhline(
    ABSOLUTE_TEMP_THRESHOLD,
    linestyle="--",
    label="Absolute temperature warning threshold"
)

axes[1].set_title(
    "Cell Temperature Distribution"
)

axes[1].set_ylabel("Temperature (C)")
axes[1].set_xlabel("Cell Number")
axes[1].set_xticks(range(1, CELL_COUNT + 1))
axes[1].grid(True)
axes[1].legend()

plt.tight_layout()

plt.savefig(
    OUTPUT_PLOT,
    dpi=200
)

plt.close()


# ============================================================
# 13. VALIDATION
# ============================================================

healthy_result = results_df[
    results_df["Scenario"] == "Healthy baseline"
]

moderate_result = results_df[
    results_df["Scenario"] == "Cell 8 at 40C"
]

high_result = results_df[
    results_df["Scenario"] == "Cell 8 at 50C"
]

distributed_result = results_df[
    results_df["Scenario"] == "Distributed temperature"
]


# Check 1: Healthy baseline has no thermal warnings.
assert not healthy_result["Thermal_Warning"].any(), (
    "Unexpected thermal warning in healthy baseline."
)


# Check 2: Cell 8 at 40C must trigger thermal warning.
assert bool(
    moderate_result.loc[
        moderate_result["Cell"] == 8,
        "Thermal_Warning"
    ].iloc[0]
), "40C thermal warning was not detected."


# Check 3: Cell 8 at 50C must trigger thermal warning.
assert bool(
    high_result.loc[
        high_result["Cell"] == 8,
        "Thermal_Warning"
    ].iloc[0]
), "50C thermal warning was not detected."


# Check 4: Temperature-compensated resistance should
# remain close to the healthy reference for all scenarios.
for scenario_name, _ in TEMPERATURE_SCENARIOS:

    scenario_rows = results_df[
        results_df["Scenario"] == scenario_name
    ]

    ratios = scenario_rows["Resistance_Ratio"].to_numpy()

    assert np.allclose(
        ratios,
        1.0,
        atol=0.02
    ), (
        f"Temperature compensation failed in {scenario_name}"
    )


# Check 5: Distributed temperature scenario should not
# produce a thermal warning with the selected 10C threshold.
assert not distributed_result["Thermal_Warning"].any(), (
    "Unexpected thermal warning in distributed temperature scenario."
)


# ============================================================
# 14. VALIDATION REPORT
# ============================================================

print("\n" + "=" * 70)
print("VALIDATION RESULTS")
print("=" * 70)

print("Healthy baseline thermal check: PASS")
print("40C thermal anomaly detection: PASS")
print("50C thermal anomaly detection: PASS")
print("Temperature-compensated resistance consistency: PASS")
print("Distributed temperature variation check: PASS")


# ============================================================
# 15. GENERATED FILES
# ============================================================

print("\nGENERATED FILES")

print(OUTPUT_CSV)
print(OUTPUT_JSON)
print(OUTPUT_PLOT)

print("\n" + "=" * 70)
print("TEMPERATURE DIAGNOSTIC EXPERIMENT COMPLETE")
print("=" * 70)
