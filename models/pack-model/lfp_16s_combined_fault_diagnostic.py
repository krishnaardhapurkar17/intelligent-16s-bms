
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

OUTPUT_CSV = METRICS_DIR / "lfp_16s_combined_fault_diagnostics.csv"
OUTPUT_JSON = METRICS_DIR / "lfp_16s_combined_fault_summary.json"
OUTPUT_PLOT = FIGURES_DIR / "lfp_16s_combined_fault_diagnostics.png"


# ============================================================
# 2. MODEL AND DIAGNOSTIC PARAMETERS
# ============================================================

CELL_COUNT = 16

R0_HEALTHY = 0.0005
R0_DEGRADED = 0.00075

R1 = 0.0002
TAU = 30.0

OCV = 3.30

ACTUAL_TEMPERATURE_C = 25.0

DT = 1.0

# Provisional diagnostic thresholds.
RESISTANCE_RATIO_THRESHOLD = 1.20
VOLTAGE_DEVIATION_THRESHOLD_MV = 15.0
TEMPERATURE_DEVIATION_THRESHOLD_C = 5.0

# Resistance estimation validation tolerance.
R0_TOLERANCE = 2e-6

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

def make_scenario(
    name,
    resistance_fault_cells=None,
    voltage_bias_cells=None,
    temperature_bias_cells=None
):

    resistance_fault_cells = (
        resistance_fault_cells or {}
    )

    voltage_bias_cells = (
        voltage_bias_cells or {}
    )

    temperature_bias_cells = (
        temperature_bias_cells or {}
    )

    r0_values = np.full(
        CELL_COUNT,
        R0_HEALTHY,
        dtype=float
    )

    voltage_bias = np.zeros(
        CELL_COUNT,
        dtype=float
    )

    actual_temperature = np.full(
        CELL_COUNT,
        ACTUAL_TEMPERATURE_C,
        dtype=float
    )

    temperature_bias = np.zeros(
        CELL_COUNT,
        dtype=float
    )

    # Inject internal resistance faults.
    for cell_number, resistance in resistance_fault_cells.items():

        r0_values[cell_number - 1] = resistance

    # Inject voltage sensor bias.
    for cell_number, bias in voltage_bias_cells.items():

        voltage_bias[cell_number - 1] = bias

    # Inject temperature sensor bias.
    for cell_number, bias in temperature_bias_cells.items():

        temperature_bias[cell_number - 1] = bias

    measured_temperature = (
        actual_temperature + temperature_bias
    )

    return {
        "name": name,
        "r0_values": r0_values,
        "voltage_bias": voltage_bias,
        "actual_temperature": actual_temperature,
        "measured_temperature": measured_temperature,
        "temperature_bias": temperature_bias,
    }


# ============================================================
# 5. DEFINE SIX SCENARIOS
# ============================================================

scenarios = [

    # SIM-001: Healthy pack.
    make_scenario(
        "SIM-001 Healthy pack"
    ),

    # SIM-002: Cell 8 resistance growth.
    make_scenario(
        "SIM-002 Cell 8 resistance growth",
        resistance_fault_cells={
            8: R0_DEGRADED
        }
    ),

    # SIM-003: Cell 8 voltage sensor bias.
    make_scenario(
        "SIM-003 Cell 8 voltage sensor bias",
        voltage_bias_cells={
            8: -0.030
        }
    ),

    # SIM-004: Cell 8 temperature sensor bias.
    make_scenario(
        "SIM-004 Cell 8 temperature sensor bias",
        temperature_bias_cells={
            8: 15.0
        }
    ),

    # SIM-005: Two faults on Cell 8.
    make_scenario(
        "SIM-005 Cell 8 combined faults",
        resistance_fault_cells={
            8: R0_DEGRADED
        },
        temperature_bias_cells={
            8: 15.0
        }
    ),

    # SIM-006: Faults affecting three different cells.
    make_scenario(
        "SIM-006 Multiple cell faults",
        resistance_fault_cells={
            8: R0_DEGRADED
        },
        voltage_bias_cells={
            12: -0.030
        },
        temperature_bias_cells={
            14: 15.0
        }
    ),
]


# ============================================================
# 6. BATTERY PLANT SIMULATION
# ============================================================

def simulate_battery(scenario):

    time = np.arange(
        0,
        181,
        DT
    )

    current = np.array([
        get_current(t) for t in time
    ])

    polarization = np.zeros(
        CELL_COUNT
    )

    voltage = np.zeros(
        (len(time), CELL_COUNT)
    )

    for k in range(len(time)):

        # True terminal voltage plus measurement bias.
        voltage[k, :] = (
            OCV
            - current[k] * scenario["r0_values"]
            - polarization
            + scenario["voltage_bias"]
        )

        # First-order RC polarization.
        polarization += (
            DT / TAU
        ) * (
            current[k] * R1 - polarization
        )

    return {
        "time": time,
        "current": current,
        "voltage": voltage,
    }


# ============================================================
# 7. RESISTANCE ESTIMATION
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
        np.median(values)
        for values in estimates
    ])


# ============================================================
# 8. VOLTAGE DEVIATION DIAGNOSTIC
# ============================================================

def calculate_voltage_deviation(simulation):

    # Analyze the 100 A pulse at t = 140 seconds.
    index = np.where(
        simulation["time"] == 140
    )[0][0]

    loaded_voltage = simulation["voltage"][index, :]

    pack_median = np.median(
        loaded_voltage
    )

    return (
        pack_median - loaded_voltage
    ) * 1000.0


# ============================================================
# 9. INTEGRATED DIAGNOSTIC ENGINE
# ============================================================

all_results = []
scenario_summaries = {}
plot_data = []

print("=" * 75)
print("16S LFP COMBINED MULTI-FAULT DIAGNOSTICS")
print("=" * 75)

for scenario in scenarios:

    name = scenario["name"]

    simulation = simulate_battery(
        scenario
    )

    estimated_r0 = estimate_resistance(
        simulation
    )

    voltage_deviation = calculate_voltage_deviation(
        simulation
    )

    measured_temperature = (
        scenario["measured_temperature"]
    )

    temperature_reference = np.median(
        measured_temperature
    )

    temperature_deviation = (
        measured_temperature - temperature_reference
    )

    pack_median_r0 = float(
        np.median(estimated_r0)
    )

    scenario_rows = []

    for i in range(CELL_COUNT):

        resistance_ratio = (
            estimated_r0[i] / pack_median_r0
        )

        resistance_fault = (
            resistance_ratio
            > RESISTANCE_RATIO_THRESHOLD
        )

        voltage_fault = (
            voltage_deviation[i]
            >= VOLTAGE_DEVIATION_THRESHOLD_MV
        )

        temperature_sensor_fault = (
            abs(temperature_deviation[i])
            >= TEMPERATURE_DEVIATION_THRESHOLD_C
        )

        detected_faults = []

        if resistance_fault:

            detected_faults.append(
                "Possible resistance degradation"
            )

        if voltage_fault:

            detected_faults.append(
                "Voltage anomaly - cause unresolved"
            )

        if temperature_sensor_fault:

            detected_faults.append(
                "Possible temperature sensor bias"
            )

        if not detected_faults:

            classification = "No anomaly detected"

        else:

            classification = " + ".join(
                detected_faults
            )

        # Localization is based on the measured
        # channel that crossed a diagnostic threshold.
        # It does not establish physical root cause.
        if detected_faults:

            localization = (
                "Cell/channel localized; root cause "
                "not independently confirmed"
            )

        else:

            localization = "No fault localized"

        row = {

            "Scenario": name,

            "Cell": i + 1,

            "Estimated_R0_mOhm": (
                estimated_r0[i] * 1000
            ),

            "Pack_Median_R0_mOhm": (
                pack_median_r0 * 1000
            ),

            "Resistance_Ratio": (
                resistance_ratio
            ),

            "Voltage_Deviation_mV": (
                voltage_deviation[i]
            ),

            "Measured_Temperature_C": (
                measured_temperature[i]
            ),

            "Temperature_Deviation_C": (
                temperature_deviation[i]
            ),

            "Resistance_Fault": bool(
                resistance_fault
            ),

            "Voltage_Fault": bool(
                voltage_fault
            ),

            "Temperature_Sensor_Fault": bool(
                temperature_sensor_fault
            ),

            "Detected_Fault_Count": len(
                detected_faults
            ),

            "Classification": classification,

            "Localization_Status": localization,
        }

        scenario_rows.append(row)
        all_results.append(row)

    # --------------------------------------------------------
    # Print scenario summary.
    # --------------------------------------------------------

    flagged_cells = [
        row for row in scenario_rows
        if row["Detected_Fault_Count"] > 0
    ]

    print(f"\nSCENARIO: {name}")
    print("-" * 75)

    if not flagged_cells:

        print("No diagnostic anomalies detected.")

    else:

        for row in flagged_cells:

            print(
                f"Cell {row['Cell']:02d}: "
                f"{row['Classification']}"
            )

            print(
                f"  Estimated R0: "
                f"{row['Estimated_R0_mOhm']:.4f} mOhm"
            )

            print(
                f"  Voltage deviation: "
                f"{row['Voltage_Deviation_mV']:.2f} mV"
            )

            print(
                f"  Temperature deviation: "
                f"{row['Temperature_Deviation_C']:.2f} C"
            )

    scenario_summaries[name] = {
        "flagged_cells": [
            {
                "cell": row["Cell"],
                "classification": row["Classification"],
                "localization_status": row["Localization_Status"],
            }
            for row in flagged_cells
        ],
        "number_of_flagged_cells": len(flagged_cells),
    }

    plot_data.append({
        "name": name,
        "resistance_ratio": [
            row["Resistance_Ratio"]
            for row in scenario_rows
        ],
        "voltage_deviation": [
            row["Voltage_Deviation_mV"]
            for row in scenario_rows
        ],
        "temperature_deviation": [
            row["Temperature_Deviation_C"]
            for row in scenario_rows
        ],
    })


# ============================================================
# 10. SAVE CELL-WISE DIAGNOSTIC CSV
# ============================================================

results_df = pd.DataFrame(
    all_results
)

results_df.to_csv(
    OUTPUT_CSV,
    index=False
)


# ============================================================
# 11. SAVE JSON SUMMARY
# ============================================================

summary = {

    "experiment": (
        "16S LFP integrated multi-fault diagnosis"
    ),

    "cell_count": CELL_COUNT,

    "model_type": (
        "Simplified first-order ECM"
    ),

    "resistance_threshold_ratio": (
        RESISTANCE_RATIO_THRESHOLD
    ),

    "voltage_deviation_threshold_mV": (
        VOLTAGE_DEVIATION_THRESHOLD_MV
    ),

    "temperature_deviation_threshold_C": (
        TEMPERATURE_DEVIATION_THRESHOLD_C
    ),

    "scenario_results": scenario_summaries,

    "limitations": [

        "Voltage anomaly alone does not prove sensor failure.",

        "Temperature deviation identifies an inconsistent "
        "temperature channel, not definitive sensor failure.",

        "Resistance estimation uses idealized current transitions.",

        "The model does not include measurement noise.",

        "The model does not include thermal dynamics.",

        "Thresholds are provisional and not calibrated.",

        "Fault localization identifies the affected measurement "
        "channel, not necessarily the physical root cause."
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
# 12. PLOT ALL DIAGNOSTIC CHANNELS
# ============================================================

fig, axes = plt.subplots(
    3,
    2,
    figsize=(16, 13)
)

axes = axes.flatten()

for index, data in enumerate(plot_data):

    x = range(1, CELL_COUNT + 1)

    axes[index].plot(
        x,
        data["resistance_ratio"],
        marker="o",
        label="Resistance ratio"
    )

    axes[index].axhline(
        RESISTANCE_RATIO_THRESHOLD,
        linestyle="--",
        label="Resistance threshold"
    )

    axes[index].set_title(
        data["name"]
    )

    axes[index].set_xlabel(
        "Cell Number"
    )

    axes[index].set_ylabel(
        "Resistance ratio"
    )

    axes[index].set_xticks(
        range(1, CELL_COUNT + 1)
    )

    axes[index].grid(True)
    axes[index].legend()

plt.tight_layout()

# Save resistance overview.
RESISTANCE_PLOT = (
    FIGURES_DIR / "lfp_16s_combined_resistance_overview.png"
)

plt.savefig(
    RESISTANCE_PLOT,
    dpi=180
)

plt.close()


# ============================================================
# 13. PLOT VOLTAGE AND TEMPERATURE EVIDENCE
# ============================================================

fig, axes = plt.subplots(
    2,
    1,
    figsize=(15, 10)
)

for data in plot_data:

    x = range(1, CELL_COUNT + 1)

    axes[0].plot(
        x,
        data["voltage_deviation"],
        marker="o",
        label=data["name"]
    )

    axes[1].plot(
        x,
        data["temperature_deviation"],
        marker="o",
        label=data["name"]
    )

axes[0].axhline(
    VOLTAGE_DEVIATION_THRESHOLD_MV,
    linestyle="--",
    label="Voltage threshold"
)

axes[0].set_title(
    "Voltage Deviation Across Combined Scenarios"
)

axes[0].set_ylabel(
    "Voltage deviation (mV)"
)

axes[0].set_xlabel(
    "Cell Number"
)

axes[0].set_xticks(
    range(1, CELL_COUNT + 1)
)

axes[0].grid(True)
axes[0].legend(fontsize=8)


axes[1].axhline(
    TEMPERATURE_DEVIATION_THRESHOLD_C,
    linestyle="--",
    label="Positive temperature threshold"
)

axes[1].axhline(
    -TEMPERATURE_DEVIATION_THRESHOLD_C,
    linestyle="--",
    label="Negative temperature threshold"
)

axes[1].set_title(
    "Temperature Sensor Deviation Across Combined Scenarios"
)

axes[1].set_ylabel(
    "Temperature deviation (C)"
)

axes[1].set_xlabel(
    "Cell Number"
)

axes[1].set_xticks(
    range(1, CELL_COUNT + 1)
)

axes[1].grid(True)
axes[1].legend(fontsize=8)

plt.tight_layout()

EVIDENCE_PLOT = (
    FIGURES_DIR / "lfp_16s_combined_voltage_temperature.png"
)

plt.savefig(
    EVIDENCE_PLOT,
    dpi=180
)

plt.close()


# ============================================================
# 14. VALIDATION
# ============================================================

def get_flagged_cells(scenario_name):

    selected = results_df[
        results_df["Scenario"] == scenario_name
    ]

    return set(
        selected.loc[
            selected["Detected_Fault_Count"] > 0,
            "Cell"
        ].astype(int)
    )


# SIM-001: Healthy pack.
assert get_flagged_cells(
    "SIM-001 Healthy pack"
) == set(), "Healthy pack generated false alarms."

healthy_rows = results_df[
    results_df["Scenario"] == "SIM-001 Healthy pack"
]
assert healthy_rows["Localization_Status"].eq("No fault localized").all(), (
    "Healthy pack must report no reliable fault localization."
)


# SIM-002: Cell 8 resistance fault.
assert get_flagged_cells(
    "SIM-002 Cell 8 resistance growth"
) == {8}, "Resistance fault localization failed."


# SIM-003: Cell 8 voltage sensor bias.
assert get_flagged_cells(
    "SIM-003 Cell 8 voltage sensor bias"
) == {8}, "Voltage anomaly localization failed."


# SIM-004: Cell 8 temperature sensor bias.
assert get_flagged_cells(
    "SIM-004 Cell 8 temperature sensor bias"
) == {8}, "Temperature anomaly localization failed."


# SIM-005: Two fault types on Cell 8.
assert get_flagged_cells(
    "SIM-005 Cell 8 combined faults"
) == {8}, "Same-cell combined fault localization failed."


# SIM-006: Three different affected cells.
assert get_flagged_cells(
    "SIM-006 Multiple cell faults"
) == {8, 12, 14}, (
    "Multiple-cell fault localization failed."
)

multiple_rows = results_df[
    results_df["Scenario"] == "SIM-006 Multiple cell faults"
]
flagged_multiple_rows = multiple_rows[
    multiple_rows["Detected_Fault_Count"] > 0
]
assert flagged_multiple_rows["Localization_Status"].eq(
    "Cell/channel localized; root cause not independently confirmed"
).all(), "Multi-fault results must state the root-cause limitation."


# Verify individual fault channels.
sim5 = results_df[
    results_df["Scenario"] == "SIM-005 Cell 8 combined faults"
]

cell8_sim5 = sim5[
    sim5["Cell"] == 8
].iloc[0]

assert bool(
    cell8_sim5["Resistance_Fault"]
), "SIM-005 resistance evidence missing."

assert bool(
    cell8_sim5["Temperature_Sensor_Fault"]
), "SIM-005 temperature evidence missing."


sim6 = results_df[
    results_df["Scenario"] == "SIM-006 Multiple cell faults"
]

cell8_sim6 = sim6[
    sim6["Cell"] == 8
].iloc[0]

cell12_sim6 = sim6[
    sim6["Cell"] == 12
].iloc[0]

cell14_sim6 = sim6[
    sim6["Cell"] == 14
].iloc[0]

assert bool(
    cell8_sim6["Resistance_Fault"]
)

assert bool(
    cell12_sim6["Voltage_Fault"]
)

assert bool(
    cell14_sim6["Temperature_Sensor_Fault"]
)


# ============================================================
# 15. VALIDATION REPORT
# ============================================================

print("\n" + "=" * 75)
print("VALIDATION RESULTS")
print("=" * 75)

print("SIM-001 Healthy baseline: PASS")
print("SIM-002 Resistance growth: PASS")
print("SIM-003 Voltage sensor bias: PASS")
print("SIM-004 Temperature sensor bias: PASS")
print("SIM-005 Combined faults on one cell: PASS")
print("SIM-006 Multiple faults across cells: PASS")
print("Fault-channel evidence verification: PASS")

print("\n" + "=" * 75)
print("GENERATED FILES")
print("=" * 75)

print(OUTPUT_CSV)
print(OUTPUT_JSON)
print(OUTPUT_PLOT)
print(RESISTANCE_PLOT)
print(EVIDENCE_PLOT)

print("\n" + "=" * 75)
print("COMBINED MULTI-FAULT DIAGNOSTIC COMPLETE")
print("=" * 75)
