
from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# 1. PROJECT PATHS AND CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[2]

METRICS_DIR = ROOT / "results" / "metrics"
FIGURES_DIR = ROOT / "results" / "figures"

METRICS_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_CSV = METRICS_DIR / "lfp_16s_fault_isolation.csv"
OUTPUT_JSON = METRICS_DIR / "lfp_16s_fault_isolation_summary.json"
OUTPUT_PLOT = FIGURES_DIR / "lfp_16s_fault_isolation.png"


# ============================================================
# 2. BATTERY MODEL PARAMETERS
# ============================================================

CELL_COUNT = 16

R0_HEALTHY = 0.0005       # 0.5 mOhm
R0_DEGRADED = 0.00075     # 0.75 mOhm

R1 = 0.0002
TAU = 30.0

OCV = 3.30

SENSOR_BIAS = -0.030      # -30 mV

DT = 1.0

VOLTAGE_THRESHOLD_MV = 15.0
RESISTANCE_THRESHOLD_RATIO = 1.20

R0_TOLERANCE = 2e-6       # 0.002 mOhm


# ============================================================
# 3. CURRENT PULSE PROFILE
# ============================================================

# Each entry: (time in seconds, current in amperes)

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


def get_current(time_s):

    current = 0.0

    for start_time, value in CURRENT_PROFILE:
        if time_s >= start_time:
            current = value

    return current


# ============================================================
# 4. BATTERY SCENARIO SIMULATION
# ============================================================

def simulate_scenario(
    scenario_name,
    degraded_cell=None,
    sensor_fault_cell=None
):

    time = np.arange(0, 181, DT)

    current = np.array([
        get_current(t) for t in time
    ])

    # All cells begin with healthy resistance.
    r0_values = np.full(
        CELL_COUNT,
        R0_HEALTHY,
        dtype=float
    )

    # Inject internal resistance degradation.
    if degraded_cell is not None:

        r0_values[degraded_cell - 1] = R0_DEGRADED

    # Initialize voltage sensor bias.
    sensor_bias = np.zeros(CELL_COUNT)

    # Inject sensor bias into selected channel.
    if sensor_fault_cell is not None:

        sensor_bias[sensor_fault_cell - 1] = SENSOR_BIAS

    # First-order RC polarization voltage.
    polarization = np.zeros(CELL_COUNT)

    voltage = np.zeros(
        (len(time), CELL_COUNT)
    )

    for k in range(len(time)):

        # Terminal voltage:
        # V = OCV - I*R0 - Vpolarization + sensor_bias

        voltage[k, :] = (
            OCV
            - current[k] * r0_values
            - polarization
            + sensor_bias
        )

        # Update RC polarization.
        polarization += (
            DT / TAU
        ) * (
            current[k] * R1 - polarization
        )

    return {
        "scenario": scenario_name,
        "time": time,
        "current": current,
        "voltage": voltage,
        "r0_true": r0_values,
        "sensor_bias": sensor_bias,
    }


# ============================================================
# 5. ESTIMATE INTERNAL RESISTANCE
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

        # Estimated instantaneous resistance.
        estimated_r0 = (
            -delta_voltage / delta_current
        )

        for cell_index in range(CELL_COUNT):

            estimates[cell_index].append(
                estimated_r0[cell_index]
            )

    median_estimates = np.array([
        np.median(values) if values else np.nan
        for values in estimates
    ])

    return median_estimates


# ============================================================
# 6. CALCULATE VOLTAGE DEVIATION
# ============================================================

def calculate_voltage_deviation(simulation):

    voltage = simulation["voltage"]

    # Evaluate during the 100 A pulse at t = 140 seconds.
    index = np.where(
        simulation["time"] == 140
    )[0][0]

    loaded_voltage = voltage[index, :]

    reference_voltage = np.median(
        loaded_voltage
    )

    # Positive = cell voltage is below median.
    deviation_mv = (
        reference_voltage - loaded_voltage
    ) * 1000.0

    return deviation_mv


# ============================================================
# 7. DEFINE AND RUN SCENARIOS
# ============================================================

scenarios = [

    # Scenario 1: All cells healthy.
    simulate_scenario(
        "Healthy"
    ),

    # Scenario 2: Cell 8 has 50% higher internal resistance.
    simulate_scenario(
        "Cell 8 resistance growth",
        degraded_cell=8
    ),

    # Scenario 3: Healthy Cell 8 with -30 mV sensor bias.
    simulate_scenario(
        "Cell 8 sensor bias",
        sensor_fault_cell=8
    ),
]


# ============================================================
# 8. DIAGNOSTIC PROCESSING
# ============================================================

all_results = []

print("=" * 65)
print("16S LFP MULTI-SIGNAL FAULT ISOLATION TEST")
print("=" * 65)

for simulation in scenarios:

    scenario_name = simulation["scenario"]

    estimated_r0 = estimate_resistance(
        simulation
    )

    voltage_deviation = calculate_voltage_deviation(
        simulation
    )

    pack_median_r0 = float(
        np.median(estimated_r0)
    )

    scenario_rows = []

    for i in range(CELL_COUNT):

        resistance_ratio = (
            estimated_r0[i] / pack_median_r0
        )

        resistance_anomaly = (
            resistance_ratio > RESISTANCE_THRESHOLD_RATIO
        )

        voltage_anomaly = (
            voltage_deviation[i] >= VOLTAGE_THRESHOLD_MV
        )

        # Resistance evidence takes priority.
        if resistance_anomaly:

            classification = (
                "Possible resistance degradation"
            )

        elif voltage_anomaly:

            classification = (
                "Possible voltage sensor bias"
            )

        else:

            classification = (
                "No anomaly detected"
            )

        row = {
            "Scenario": scenario_name,
            "Cell": i + 1,
            "Estimated_R0_mOhm": (
                estimated_r0[i] * 1000
            ),
            "Pack_Median_R0_mOhm": (
                pack_median_r0 * 1000
            ),
            "Resistance_Ratio": resistance_ratio,
            "Voltage_Deviation_mV": voltage_deviation[i],
            "Resistance_Anomaly": resistance_anomaly,
            "Voltage_Anomaly": voltage_anomaly,
            "Classification": classification,
        }

        scenario_rows.append(row)
        all_results.append(row)

    # Display Cell 8 results.
    cell8 = scenario_rows[7]

    print(f"\nSCENARIO: {scenario_name}")
    print("-" * 65)

    print(
        f"Cell 8 estimated R0: "
        f"{cell8['Estimated_R0_mOhm']:.4f} mOhm"
    )

    print(
        f"Pack median R0: "
        f"{cell8['Pack_Median_R0_mOhm']:.4f} mOhm"
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
        f"Classification: "
        f"{cell8['Classification']}"
    )


# ============================================================
# 9. SAVE CSV RESULTS
# ============================================================

results_df = pd.DataFrame(all_results)

results_df.to_csv(
    OUTPUT_CSV,
    index=False
)


# ============================================================
# 10. SAVE JSON SUMMARY
# ============================================================

summary = {

    "experiment": (
        "16S LFP multi-signal fault isolation"
    ),

    "model_type": (
        "Simplified first-order ECM"
    ),

    "cell_count": CELL_COUNT,

    "healthy_R0_ohm": R0_HEALTHY,

    "degraded_R0_ohm": R0_DEGRADED,

    "sensor_bias_V": SENSOR_BIAS,

    "current_profile": CURRENT_PROFILE,

    "resistance_threshold_ratio": (
        RESISTANCE_THRESHOLD_RATIO
    ),

    "voltage_threshold_mV": (
        VOLTAGE_THRESHOLD_MV
    ),

    "limitations": [
        "The first-order ECM and injected sensor bias are simplified simulation assumptions.",
        "Threshold isolation does not confirm a physical root cause.",
        "No hardware or field validation is represented.",
    ],

    "scenarios": {}
}

for simulation in scenarios:

    scenario_name = simulation["scenario"]

    scenario_rows = results_df[
        results_df["Scenario"] == scenario_name
    ]

    cell8 = scenario_rows[
        scenario_rows["Cell"] == 8
    ].iloc[0]

    summary["scenarios"][scenario_name] = {

        "cell_8_estimated_R0_mOhm": float(
            cell8["Estimated_R0_mOhm"]
        ),

        "cell_8_voltage_deviation_mV": float(
            cell8["Voltage_Deviation_mV"]
        ),

        "cell_8_resistance_ratio": float(
            cell8["Resistance_Ratio"]
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
# 11. PLOT RESISTANCE ESTIMATION
# ============================================================

plt.figure(figsize=(12, 6))

for simulation in scenarios:

    estimates = (
        estimate_resistance(simulation) * 1000
    )

    plt.plot(
        range(1, CELL_COUNT + 1),
        estimates,
        marker="o",
        label=simulation["scenario"]
    )

plt.xlabel("Cell Number")

plt.ylabel("Estimated R0 (mOhm)")

plt.title(
    "16S LFP - Current Response Resistance Estimation"
)

plt.xticks(
    range(1, CELL_COUNT + 1)
)

plt.grid(True)

plt.legend()

plt.tight_layout()

plt.savefig(
    OUTPUT_PLOT,
    dpi=200
)

plt.close()


# ============================================================
# 12. VALIDATION
# ============================================================

healthy = scenarios[0]

resistance_fault = scenarios[1]

sensor_fault = scenarios[2]


healthy_r0 = estimate_resistance(
    healthy
)

resistance_fault_r0 = estimate_resistance(
    resistance_fault
)

sensor_fault_r0 = estimate_resistance(
    sensor_fault
)


# Check 1: Healthy resistance estimate.
assert np.allclose(
    healthy_r0,
    R0_HEALTHY,
    atol=R0_TOLERANCE
), "Healthy resistance estimation failed."


# Check 2: Degraded Cell 8 resistance estimate.
assert np.isclose(
    resistance_fault_r0[7],
    R0_DEGRADED,
    atol=R0_TOLERANCE
), "Cell 8 resistance fault estimation failed."


# Check 3: Sensor bias must not change estimated R0.
assert np.isclose(
    sensor_fault_r0[7],
    R0_HEALTHY,
    atol=R0_TOLERANCE
), "Sensor bias incorrectly changed resistance estimate."


# Check 4: Negative sensor bias must create positive deviation.
sensor_voltage_deviation = (
    calculate_voltage_deviation(sensor_fault)
)

assert (
    sensor_voltage_deviation[7]
    >= VOLTAGE_THRESHOLD_MV
), "Cell 8 sensor bias was not detected."


# Check 5: Confirm the three expected classifications.
cell8_results = results_df[
    results_df["Cell"] == 8
].set_index("Scenario")

assert (
    cell8_results.loc[
        "Healthy", "Classification"
    ] == "No anomaly detected"
)

assert (
    cell8_results.loc[
        "Cell 8 resistance growth", "Classification"
    ] == "Possible resistance degradation"
)

assert (
    cell8_results.loc[
        "Cell 8 sensor bias", "Classification"
    ] == "Possible voltage sensor bias"
)


# ============================================================
# 13. FINAL VALIDATION REPORT
# ============================================================

print("\n" + "=" * 65)
print("VALIDATION RESULTS")
print("=" * 65)

print("Healthy resistance estimation: PASS")

print("Resistance growth identification: PASS")

print("Sensor bias cancellation in delta-V/delta-I: PASS")

print("Negative sensor bias detection: PASS")

print("Three-scenario classification: PASS")


# ============================================================
# 14. GENERATED FILES
# ============================================================

print("\nGENERATED FILES")

print(OUTPUT_CSV)

print(OUTPUT_JSON)

print(OUTPUT_PLOT)

print("\n" + "=" * 65)
print("EXPERIMENT COMPLETE")
print("=" * 65)
