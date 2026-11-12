
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

OUTPUT_CSV = METRICS_DIR / "lfp_16s_robustness_results.csv"
OUTPUT_JSON = METRICS_DIR / "lfp_16s_robustness_summary.json"
OUTPUT_PLOT = FIGURES_DIR / "lfp_16s_robustness_diagnostics.png"


# ============================================================
# 2. MODEL PARAMETERS
# ============================================================

CELL_COUNT = 16
DT = 1.0
DURATION = 180

CAPACITY_AH = 100.0

R0_HEALTHY = 0.0005
R0_DEGRADED = 0.00075

R1 = 0.0002
TAU = 30.0

REFERENCE_TEMPERATURE_C = 25.0

# Provisional temperature coefficient.
TEMP_COEFFICIENT = -0.004

# Simplified LFP OCV approximation for this experiment.
# This is an illustrative curve, not a calibrated cell OCV map.
def ocv_from_soc(soc):
    return 3.0 + 0.5 * np.clip(soc, 0.0, 1.0)


# Measurement noise assumptions.
VOLTAGE_NOISE_STD_V = 0.001
CURRENT_NOISE_STD_A = 0.10
TEMPERATURE_NOISE_STD_C = 0.25

RANDOM_SEED = 2026

# Provisional diagnostic thresholds.
RESISTANCE_RATIO_THRESHOLD = 1.20
VOLTAGE_DEVIATION_THRESHOLD_MV = 15.0
TEMPERATURE_DEVIATION_THRESHOLD_C = 5.0

INVALID_TEMPERATURE_MIN_C = -40.0
INVALID_TEMPERATURE_MAX_C = 100.0

# Current profile: (time seconds, current amperes).
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
# 3. CURRENT PROFILE
# ============================================================

def get_current(time_s):

    current = 0.0

    for start_time, value in CURRENT_PROFILE:
        if time_s >= start_time:
            current = value

    return current


# ============================================================
# 4. SCENARIO CONFIGURATION
# ============================================================

def create_scenario(
    name,
    resistance_faults=None,
    voltage_biases=None,
    temperature_biases=None,
    initial_soc=None,
    temperature_profile=None,
    missing_voltage_cells=None,
    invalid_temperature_cells=None,
    missing_temperature_cells=None,
    noise_scale=1.0,
):

    resistance_faults = resistance_faults or {}
    voltage_biases = voltage_biases or {}
    temperature_biases = temperature_biases or {}

    missing_voltage_cells = missing_voltage_cells or []
    invalid_temperature_cells = invalid_temperature_cells or []
    missing_temperature_cells = missing_temperature_cells or []

    r0 = np.full(CELL_COUNT, R0_HEALTHY, dtype=float)

    for cell, value in resistance_faults.items():
        r0[cell - 1] = value

    voltage_bias = np.zeros(CELL_COUNT)

    for cell, value in voltage_biases.items():
        voltage_bias[cell - 1] = value

    if initial_soc is None:
        initial_soc = np.full(CELL_COUNT, 0.90)

    if temperature_profile is None:
        temperature_profile = np.full(
            CELL_COUNT,
            REFERENCE_TEMPERATURE_C
        )

    temperature_bias = np.zeros(CELL_COUNT)

    for cell, value in temperature_biases.items():
        temperature_bias[cell - 1] = value

    return {
        "name": name,
        "r0": r0,
        "voltage_bias": voltage_bias,
        "initial_soc": np.array(initial_soc, dtype=float),
        "temperature_profile": np.array(
            temperature_profile,
            dtype=float
        ),
        "temperature_bias": temperature_bias,
        "missing_voltage_cells": missing_voltage_cells,
        "invalid_temperature_cells": invalid_temperature_cells,
        "missing_temperature_cells": missing_temperature_cells,
        "noise_scale": float(noise_scale),
    }


# ============================================================
# 5. DEFINE SIX ROBUSTNESS SCENARIOS
# ============================================================

# All cells start at 90% SOC by default.
normal_soc = np.full(CELL_COUNT, 0.90)

# SOC imbalance: Cell 8 starts at 80%.
imbalanced_soc = normal_soc.copy()
imbalanced_soc[7] = 0.80

# Distributed temperatures between 22C and 28C.
distributed_temperatures = np.linspace(
    22.0,
    28.0,
    CELL_COUNT
)

scenarios = [

    # A: Healthy pack with measurement noise.
    create_scenario(
        "SIM-018A Healthy with measurement noise"
    ),

    # B: Healthy cells with SOC imbalance.
    create_scenario(
        "SIM-018B Initial SOC imbalance",
        initial_soc=imbalanced_soc
    ),

    # C: Healthy pack with temperature variation.
    create_scenario(
        "SIM-018C Temperature variation",
        temperature_profile=distributed_temperatures
    ),

    # D: One degraded cell under noisy measurements.
    create_scenario(
        "SIM-018D Resistance fault with noise",
        resistance_faults={8: R0_DEGRADED}
    ),

    # E: Multiple faults with noisy measurements.
    create_scenario(
        "SIM-018E Multiple faults with noise",
        resistance_faults={8: R0_DEGRADED},
        voltage_biases={12: -0.030},
        temperature_biases={14: 15.0}
    ),

    # F: Missing and invalid measurements.
    create_scenario(
        "SIM-018F Missing and invalid sensors",
        missing_voltage_cells=[14],
        invalid_temperature_cells=[15],
        missing_temperature_cells=[16]
    ),

    # G: Measurement-noise distribution shift (diagnostic proxy, not AI).
    create_scenario(
        "SIM-018G Twofold sensor-noise shift",
        noise_scale=2.0,
    ),
]


# ============================================================
# 6. BATTERY AND SENSOR SIMULATION
# ============================================================

def simulate_scenario(scenario, seed):

    rng = np.random.default_rng(seed)

    time = np.arange(
        0,
        DURATION + 1,
        DT
    )

    true_current = np.array([
        get_current(t) for t in time
    ])

    measured_current = (
        true_current
        + rng.normal(
            0,
            CURRENT_NOISE_STD_A * scenario["noise_scale"],
            len(time)
        )
    )

    soc = np.zeros(
        (len(time), CELL_COUNT)
    )

    soc[0, :] = scenario["initial_soc"]

    voltage = np.zeros(
        (len(time), CELL_COUNT)
    )

    temperature = np.zeros(
        (len(time), CELL_COUNT)
    )

    polarization = np.zeros(CELL_COUNT)

    # Temperature-dependent resistance.
    resistance_factor = (
        1.0
        + TEMP_COEFFICIENT
        * (
            scenario["temperature_profile"]
            - REFERENCE_TEMPERATURE_C
        )
    )

    if np.any(resistance_factor <= 0):
        raise ValueError("Invalid temperature resistance factor.")

    actual_r0 = scenario["r0"] * resistance_factor

    for k in range(len(time)):

        # Actual cell OCV depends on its SOC.
        cell_ocv = ocv_from_soc(soc[k, :])

        # True terminal voltage.
        true_voltage = (
            cell_ocv
            - true_current[k] * actual_r0
            - polarization
        )

        # Add voltage measurement noise and bias.
        voltage[k, :] = (
            true_voltage
            + scenario["voltage_bias"]
            + rng.normal(
                0,
                VOLTAGE_NOISE_STD_V * scenario["noise_scale"],
                CELL_COUNT
            )
        )

        # Temperature measurement noise and bias.
        temperature[k, :] = (
            scenario["temperature_profile"]
            + scenario["temperature_bias"]
            + rng.normal(
                0,
                TEMPERATURE_NOISE_STD_C * scenario["noise_scale"],
                CELL_COUNT
            )
        )

        # Update SOC for the next sample.
        if k < len(time) - 1:

            soc[k + 1, :] = (
                soc[k, :]
                - true_current[k] * DT
                / (CAPACITY_AH * 3600.0)
            )

            soc[k + 1, :] = np.clip(
                soc[k + 1, :],
                0.0,
                1.0
            )

        # First-order RC polarization update.
        polarization += (
            DT / TAU
        ) * (
            true_current[k] * R1 - polarization
        )

    # Inject missing voltage measurements.
    for cell in scenario["missing_voltage_cells"]:

        voltage[:, cell - 1] = np.nan

    # Inject invalid temperature readings.
    for cell in scenario["invalid_temperature_cells"]:

        temperature[:, cell - 1] = 150.0

    # Inject missing temperature measurements.
    for cell in scenario["missing_temperature_cells"]:

        temperature[:, cell - 1] = np.nan

    return {
        "time": time,
        "true_current": true_current,
        "measured_current": measured_current,
        "soc": soc,
        "voltage": voltage,
        "temperature": temperature,
        "actual_r0": actual_r0,
    }


# ============================================================
# 7. RESISTANCE ESTIMATION WITH INVALID-DATA HANDLING
# ============================================================

def estimate_resistance(simulation):

    current = simulation["measured_current"]
    voltage = simulation["voltage"]

    estimates = [
        [] for _ in range(CELL_COUNT)
    ]

    for k in range(1, len(current)):

        delta_current = (
            current[k] - current[k - 1]
        )

        # Ignore transitions with insufficient current change.
        if abs(delta_current) < 5.0:
            continue

        for cell_index in range(CELL_COUNT):

            v_now = voltage[k, cell_index]
            v_previous = voltage[k - 1, cell_index]

            # Skip missing or invalid voltage samples.
            if not np.isfinite(v_now):
                continue

            if not np.isfinite(v_previous):
                continue

            delta_voltage = (
                v_now - v_previous
            )

            estimate = (
                -delta_voltage / delta_current
            )

            if np.isfinite(estimate) and estimate > 0:
                estimates[cell_index].append(estimate)

    final_estimates = np.full(
        CELL_COUNT,
        np.nan
    )

    for i, values in enumerate(estimates):

        if values:
            final_estimates[i] = np.median(values)

    return final_estimates


# ============================================================
# 8. ROBUST VOLTAGE DIAGNOSTIC
# ============================================================

def calculate_voltage_deviation(simulation):

    # Evaluate the 100 A pulse at 140 seconds.
    index = np.where(
        simulation["time"] == 140
    )[0][0]

    voltage = simulation["voltage"][index, :]

    valid = np.isfinite(voltage)

    deviations = np.full(
        CELL_COUNT,
        np.nan
    )

    if np.sum(valid) < 8:
        return deviations

    reference = np.nanmedian(
        voltage[valid]
    )

    deviations[valid] = (
        reference - voltage[valid]
    ) * 1000.0

    return deviations


# ============================================================
# 9. TEMPERATURE DIAGNOSTIC
# ============================================================

def calculate_temperature_deviation(simulation):

    temperature = simulation["temperature"]

    # Use the average temperature over the simulation.
    mean_temperature = np.array([
        np.mean(temperature[
            np.isfinite(temperature[:, i]), i
        ])
        if np.isfinite(temperature[:, i]).any()
        else np.nan
        for i in range(CELL_COUNT)
    ])

    valid = np.isfinite(mean_temperature)

    # Reject implausible values before computing reference.
    valid &= (
        (mean_temperature >= INVALID_TEMPERATURE_MIN_C)
        & (mean_temperature <= INVALID_TEMPERATURE_MAX_C)
    )

    deviations = np.full(
        CELL_COUNT,
        np.nan
    )

    if np.sum(valid) < 8:
        return mean_temperature, deviations, valid

    reference = np.median(
        mean_temperature[valid]
    )

    deviations[valid] = (
        mean_temperature[valid] - reference
    )

    return mean_temperature, deviations, valid


# ============================================================
# 10. RUN DIAGNOSTICS
# ============================================================

all_results = []
scenario_summaries = {}

print("=" * 80)
print("16S LFP ROBUSTNESS AND DISTURBANCE TEST")
print("=" * 80)

for scenario_index, scenario in enumerate(scenarios):

    name = scenario["name"]

    simulation = simulate_scenario(
        scenario,
        RANDOM_SEED + scenario_index
    )

    resistance = estimate_resistance(
        simulation
    )

    voltage_deviation = calculate_voltage_deviation(
        simulation
    )

    (
        mean_temperature,
        temperature_deviation,
        valid_temperature
    ) = calculate_temperature_deviation(
        simulation
    )

    # Use median resistance of available estimates.
    valid_resistance = np.isfinite(resistance)

    if np.sum(valid_resistance) >= 8:

        reference_resistance = np.median(
            resistance[valid_resistance]
        )

    else:

        reference_resistance = np.nan

    # Check voltage channel availability.
    voltage_available = np.any(
        np.isfinite(simulation["voltage"]),
        axis=0
    )

    scenario_rows = []

    print(f"\nSCENARIO: {name}")
    print("-" * 80)

    for i in range(CELL_COUNT):

        resistance_ratio = np.nan
        resistance_fault = False

        if (
            np.isfinite(resistance[i])
            and np.isfinite(reference_resistance)
            and reference_resistance > 0
        ):

            resistance_ratio = (
                resistance[i] / reference_resistance
            )

            resistance_fault = (
                resistance_ratio
                > RESISTANCE_RATIO_THRESHOLD
            )

        voltage_fault = False

        if np.isfinite(voltage_deviation[i]):

            voltage_fault = (
                voltage_deviation[i]
                >= VOLTAGE_DEVIATION_THRESHOLD_MV
            )

        temperature_fault = False

        if np.isfinite(temperature_deviation[i]):

            temperature_fault = (
                abs(temperature_deviation[i])
                >= TEMPERATURE_DEVIATION_THRESHOLD_C
            )

        voltage_missing = not voltage_available[i]

        temperature_missing = not np.isfinite(
            mean_temperature[i]
        )

        temperature_invalid = (
            np.isfinite(mean_temperature[i])
            and (
                mean_temperature[i] < INVALID_TEMPERATURE_MIN_C
                or mean_temperature[i] > INVALID_TEMPERATURE_MAX_C
            )
        )

        detected_evidence = []

        if resistance_fault:
            detected_evidence.append(
                "Possible resistance degradation"
            )

        if voltage_fault:
            detected_evidence.append(
                "Voltage anomaly - cause unresolved"
            )

        if temperature_fault:
            detected_evidence.append(
                "Temperature anomaly - cause unresolved"
            )

        if voltage_missing:
            detected_evidence.append(
                "Missing voltage channel"
            )

        if temperature_missing:
            detected_evidence.append(
                "Missing temperature channel"
            )

        if temperature_invalid:
            detected_evidence.append(
                "Invalid temperature measurement"
            )

        if not detected_evidence:
            classification = "No anomaly detected"
        else:
            classification = " + ".join(
                detected_evidence
            )

        row = {
            "Scenario": name,
            "Cell": i + 1,
            "Estimated_R0_mOhm": (
                resistance[i] * 1000
                if np.isfinite(resistance[i])
                else np.nan
            ),
            "Resistance_Ratio": resistance_ratio,
            "Voltage_Deviation_mV": voltage_deviation[i],
            "Mean_Temperature_C": mean_temperature[i],
            "Temperature_Deviation_C": temperature_deviation[i],
            "Resistance_Fault": resistance_fault,
            "Voltage_Fault": voltage_fault,
            "Temperature_Fault": temperature_fault,
            "Voltage_Missing": voltage_missing,
            "Temperature_Missing": temperature_missing,
            "Temperature_Invalid": temperature_invalid,
            "Classification": classification,
        }

        scenario_rows.append(row)
        all_results.append(row)

    # Print only cells with diagnostic evidence.
    flagged = [
        row for row in scenario_rows
        if row["Classification"] != "No anomaly detected"
    ]

    if not flagged:
        print("No anomalies or sensor failures detected.")

    for row in flagged:

        print(
            f"Cell {row['Cell']:02d}: "
            f"{row['Classification']}"
        )

    scenario_summaries[name] = {
        "measurement_noise_scale": scenario["noise_scale"],
        "flagged_cells": [
            {
                "cell": row["Cell"],
                "classification": row["Classification"],
            }
            for row in flagged
        ],
        "flagged_cell_count": len(flagged),
    }


# ============================================================
# 11. SAVE RESULTS
# ============================================================

results_df = pd.DataFrame(
    all_results
)

results_df.to_csv(
    OUTPUT_CSV,
    index=False
)


# ============================================================
# 12. SAVE SUMMARY JSON
# ============================================================

summary = {
    "experiment": "16S LFP robustness and disturbance testing",
    "cell_count": CELL_COUNT,
    "random_seed": RANDOM_SEED,
    "voltage_noise_std_V": VOLTAGE_NOISE_STD_V,
    "current_noise_std_A": CURRENT_NOISE_STD_A,
    "temperature_noise_std_C": TEMPERATURE_NOISE_STD_C,
    "resistance_ratio_threshold": RESISTANCE_RATIO_THRESHOLD,
    "voltage_threshold_mV": VOLTAGE_DEVIATION_THRESHOLD_MV,
    "temperature_threshold_C": TEMPERATURE_DEVIATION_THRESHOLD_C,
    "scenarios": scenario_summaries,
    "limitations": [
        "Simplified linear OCV-SOC approximation.",
        "Provisional temperature coefficient.",
        "No electrochemical thermal dynamics.",
        "Resistance estimation uses a small number of current transitions.",
        "SOC imbalance can cause voltage anomalies without cell degradation.",
        "Voltage anomalies alone do not establish physical fault type.",
        "Thresholds are not calibrated against experimental battery data."
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
# 13. PLOT RESISTANCE RATIOS
# ============================================================

fig, axes = plt.subplots(
    4,
    2,
    figsize=(16, 17)
)

axes = axes.flatten()

for scenario_index, scenario in enumerate(scenarios):

    scenario_rows = results_df[
        results_df["Scenario"] == scenario["name"]
    ]

    axes[scenario_index].plot(
        scenario_rows["Cell"],
        scenario_rows["Resistance_Ratio"],
        marker="o",
        label="Estimated resistance ratio"
    )

    axes[scenario_index].axhline(
        RESISTANCE_RATIO_THRESHOLD,
        linestyle="--",
        label="Resistance threshold"
    )

    axes[scenario_index].set_title(
        scenario["name"]
    )

    axes[scenario_index].set_xlabel(
        "Cell number"
    )

    axes[scenario_index].set_ylabel(
        "Resistance ratio"
    )

    axes[scenario_index].set_xticks(
        range(1, CELL_COUNT + 1)
    )

    axes[scenario_index].grid(True)
    axes[scenario_index].legend(fontsize=8)

for unused_axis in axes[len(scenarios):]:
    unused_axis.set_visible(False)

plt.tight_layout()

plt.savefig(
    OUTPUT_PLOT,
    dpi=180
)

plt.close()


# ============================================================
# 14. DETECTION METRICS
# ============================================================

# These are scenario-specific diagnostic indicators.
# They are not a substitute for a large statistical test set.

print("\n" + "=" * 80)
print("ROBUSTNESS SUMMARY")
print("=" * 80)

for name, data in scenario_summaries.items():

    print(
        f"{name}: "
        f"{data['flagged_cell_count']} flagged cells"
    )

    if data["flagged_cells"]:

        for item in data["flagged_cells"]:

            print(
                f"  Cell {item['cell']}: "
                f"{item['classification']}"
            )


# ============================================================
# 15. BASIC VALIDATION
# ============================================================

def rows_for(scenario_name):

    return results_df[
        results_df["Scenario"] == scenario_name
    ]


# A: Healthy noise should not trigger resistance faults.
a = rows_for(
    "SIM-018A Healthy with measurement noise"
)

assert not a["Resistance_Fault"].any(), (
    "Unexpected resistance fault in noisy healthy scenario."
)


# B: SOC imbalance should produce a voltage anomaly
# but should not create a resistance fault.
b = rows_for(
    "SIM-018B Initial SOC imbalance"
)

assert not b["Resistance_Fault"].any(), (
    "SOC imbalance incorrectly triggered resistance fault."
)


# C: Distributed temperature should not trigger
# the 5C relative temperature threshold.
c = rows_for(
    "SIM-018C Temperature variation"
)

assert not c["Temperature_Fault"].any(), (
    "Unexpected thermal anomaly in distributed temperature scenario."
)


# D: Cell 8 resistance degradation should be detected.
d = rows_for(
    "SIM-018D Resistance fault with noise"
)

assert bool(
    d.loc[
        d["Cell"] == 8,
        "Resistance_Fault"
    ].iloc[0]
), "Cell 8 resistance degradation was missed."


# E: Multiple faults should be detected on the intended channels.
e = rows_for(
    "SIM-018E Multiple faults with noise"
)

assert bool(
    e.loc[
        e["Cell"] == 8,
        "Resistance_Fault"
    ].iloc[0]
), "SIM-018E Cell 8 resistance fault was missed."

assert bool(
    e.loc[
        e["Cell"] == 12,
        "Voltage_Fault"
    ].iloc[0]
), "SIM-018E Cell 12 voltage anomaly was missed."

assert bool(
    e.loc[
        e["Cell"] == 14,
        "Temperature_Fault"
    ].iloc[0]
), "SIM-018E Cell 14 temperature anomaly was missed."


# F: Missing and invalid channels must be explicitly reported.
f = rows_for(
    "SIM-018F Missing and invalid sensors"
)

assert bool(
    f.loc[
        f["Cell"] == 14,
        "Voltage_Missing"
    ].iloc[0]
), "Missing voltage channel was not detected."

assert bool(
    f.loc[
        f["Cell"] == 15,
        "Temperature_Invalid"
    ].iloc[0]
), "Invalid temperature measurement was not detected."

assert bool(
    f.loc[
        f["Cell"] == 16,
        "Temperature_Missing"
    ].iloc[0]
), "Missing temperature channel was not detected."

# G: Twofold sensor-noise shift should not create resistance or thermal flags.
g = rows_for("SIM-018G Twofold sensor-noise shift")
assert not g["Resistance_Fault"].any(), "Noise shift created a resistance fault flag."
assert not g["Temperature_Fault"].any(), "Noise shift created a temperature fault flag."


# ============================================================
# 16. VALIDATION REPORT
# ============================================================

print("\n" + "=" * 80)
print("VALIDATION RESULTS")
print("=" * 80)

print("SIM-018A Healthy noisy pack: PASS")
print("SIM-018B SOC imbalance handling: PASS")
print("SIM-018C Temperature variation: PASS")
print("SIM-018D Degraded cell under noise: PASS")
print("SIM-018E Multiple faults under noise: PASS")
print("SIM-018F Missing and invalid sensors: PASS")
print("SIM-018G Twofold noise-shift diagnostic proxy: PASS")

print("\n" + "=" * 80)
print("GENERATED FILES")
print("=" * 80)

print(OUTPUT_CSV)
print(OUTPUT_JSON)
print(OUTPUT_PLOT)

print("\n" + "=" * 80)
print("ROBUSTNESS EXPERIMENT COMPLETE")
print("=" * 80)
