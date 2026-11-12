
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# ============================================================
# 16S LFP STATE OF HEALTH (SOH) ESTIMATION
# Capacity degradation + internal resistance growth
# Simulation experiment - illustrative parameters only
# ============================================================

CELL_COUNT = 16

NOMINAL_CAPACITY_AH = 100.0
HEALTHY_RESISTANCE_OHM = 0.0005

DISCHARGE_CURRENT_A = 50.0
INITIAL_SOC_PERCENT = 90.0
FINAL_SOC_PERCENT = 10.0

DT_SECONDS = 1

CURRENT_NOISE_STD_A = 0.10
VOLTAGE_NOISE_STD_V = 0.0002

CAPACITY_SOH_THRESHOLD_PERCENT = 90.0
RESISTANCE_GROWTH_THRESHOLD_PERCENT = 20.0

RANDOM_SEED = 20261031

BASE_DIR = Path(__file__).resolve().parents[2]

METRICS_DIR = BASE_DIR / "results" / "metrics"
FIGURES_DIR = BASE_DIR / "results" / "figures"

METRICS_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(RANDOM_SEED)

# ============================================================
# SCENARIO CONFIGURATION
# ============================================================

SCENARIOS = {
    "SIM-SOH-001_HEALTHY": {
        "capacity": {},
        "resistance": {}
    },

    "SIM-SOH-002_CAPACITY_FAULT": {
        "capacity": {
            8: 80.0
        },
        "resistance": {}
    },

    "SIM-SOH-003_RESISTANCE_FAULT": {
        "capacity": {},
        "resistance": {
            12: 0.00075
        }
    },

    "SIM-SOH-004_COMBINED_FAULT": {
        "capacity": {
            8: 80.0
        },
        "resistance": {
            12: 0.00075
        }
    }
}


# ============================================================
# CAPACITY SOH ESTIMATION
# ============================================================

def estimate_capacity_soh(capacities):

    estimated_capacity = np.zeros(CELL_COUNT)
    true_capacity = capacities.copy()

    estimated_soh = np.zeros(CELL_COUNT)
    true_soh = np.zeros(CELL_COUNT)

    discharge_durations = np.zeros(CELL_COUNT)

    current_time = 0
    soc = np.full(
        CELL_COUNT,
        INITIAL_SOC_PERCENT,
        dtype=float
    )

    delivered_ah = np.zeros(CELL_COUNT)

    active = np.ones(
        CELL_COUNT,
        dtype=bool
    )

    # Each cell is discharged independently until it reaches
    # the 10% SOC test endpoint.
    max_duration = int(
        np.max(
            (INITIAL_SOC_PERCENT - FINAL_SOC_PERCENT)
            / 100.0
            * capacities
            / DISCHARGE_CURRENT_A
            * 3600
        )
    ) + 2

    for current_time in range(max_duration):

        measured_current = (
            DISCHARGE_CURRENT_A
            + rng.normal(
                0,
                CURRENT_NOISE_STD_A
            )
        )

        for cell in range(CELL_COUNT):

            if not active[cell]:
                continue

            current_ah = (
                measured_current
                * DT_SECONDS
                / 3600.0
            )

            delivered_ah[cell] += current_ah

            soc[cell] -= (
                DISCHARGE_CURRENT_A
                * DT_SECONDS
                / 3600.0
                / capacities[cell]
                * 100.0
            )

            if soc[cell] <= FINAL_SOC_PERCENT:

                active[cell] = False

                discharge_durations[cell] = (
                    current_time + 1
                )

        if not np.any(active):
            break

    # Capacity estimation assumes known 90% and 10% SOC
    # test endpoints. This is a controlled capacity test.
    usable_soc_fraction = (
        INITIAL_SOC_PERCENT - FINAL_SOC_PERCENT
    ) / 100.0

    estimated_capacity = (
        delivered_ah / usable_soc_fraction
    )

    estimated_soh = (
        estimated_capacity
        / NOMINAL_CAPACITY_AH
        * 100.0
    )

    true_soh = (
        true_capacity
        / NOMINAL_CAPACITY_AH
        * 100.0
    )

    return {
        "estimated_capacity": estimated_capacity,
        "true_capacity": true_capacity,
        "estimated_soh": estimated_soh,
        "true_soh": true_soh,
        "discharge_duration": discharge_durations
    }


# ============================================================
# INTERNAL RESISTANCE ESTIMATION
# ============================================================

def estimate_internal_resistance(resistances):

    estimated_resistance = np.zeros(CELL_COUNT)

    pulse_count = 10

    for cell in range(CELL_COUNT):

        resistance_samples = []

        for pulse in range(pulse_count):

            # Current before pulse.
            current_before = rng.normal(
                0,
                CURRENT_NOISE_STD_A
            )

            # Current after pulse.
            current_after = (
                DISCHARGE_CURRENT_A
                + rng.normal(
                    0,
                    CURRENT_NOISE_STD_A
                )
            )

            # Assume constant OCV over the short pulse.
            ocv = 3.30

            voltage_before = (
                ocv
                - current_before * resistances[cell]
                + rng.normal(
                    0,
                    VOLTAGE_NOISE_STD_V
                )
            )

            voltage_after = (
                ocv
                - current_after * resistances[cell]
                + rng.normal(
                    0,
                    VOLTAGE_NOISE_STD_V
                )
            )

            delta_voltage = (
                voltage_before - voltage_after
            )

            delta_current = (
                current_after - current_before
            )

            if abs(delta_current) > 1.0:

                resistance_estimate = (
                    delta_voltage / delta_current
                )

                if resistance_estimate > 0:

                    resistance_samples.append(
                        resistance_estimate
                    )

        estimated_resistance[cell] = np.median(
            resistance_samples
        )

    return estimated_resistance


# ============================================================
# RUN SCENARIOS
# ============================================================

all_results = []
scenario_details = {}

for scenario_name, config in SCENARIOS.items():

    print("\n" + "=" * 65)
    print("RUNNING:", scenario_name)
    print("=" * 65)

    capacities = np.full(
        CELL_COUNT,
        NOMINAL_CAPACITY_AH,
        dtype=float
    )

    resistances = np.full(
        CELL_COUNT,
        HEALTHY_RESISTANCE_OHM,
        dtype=float
    )

    for cell_number, capacity in config["capacity"].items():
        capacities[cell_number - 1] = capacity

    for cell_number, resistance in config["resistance"].items():
        resistances[cell_number - 1] = resistance

    capacity_result = estimate_capacity_soh(
        capacities
    )

    estimated_resistance = estimate_internal_resistance(
        resistances
    )

    true_resistance_growth = (
        resistances / HEALTHY_RESISTANCE_OHM - 1
    ) * 100.0

    estimated_resistance_growth = (
        estimated_resistance
        / HEALTHY_RESISTANCE_OHM - 1
    ) * 100.0

    capacity_fault_detected = (
        capacity_result["estimated_soh"]
        < CAPACITY_SOH_THRESHOLD_PERCENT
    )

    resistance_fault_detected = (
        estimated_resistance_growth
        > RESISTANCE_GROWTH_THRESHOLD_PERCENT
    )

    for cell in range(CELL_COUNT):

        all_results.append({

            "Scenario": scenario_name,

            "Cell": cell + 1,

            "True_Capacity_Ah":
                capacities[cell],

            "Estimated_Capacity_Ah":
                capacity_result["estimated_capacity"][cell],

            "True_Capacity_SOH_percent":
                capacity_result["true_soh"][cell],

            "Estimated_Capacity_SOH_percent":
                capacity_result["estimated_soh"][cell],

            "True_Resistance_mOhm":
                resistances[cell] * 1000,

            "Estimated_Resistance_mOhm":
                estimated_resistance[cell] * 1000,

            "True_Resistance_Growth_percent":
                true_resistance_growth[cell],

            "Estimated_Resistance_Growth_percent":
                estimated_resistance_growth[cell],

            "Capacity_Fault_Detected":
                capacity_fault_detected[cell],

            "Resistance_Fault_Detected":
                resistance_fault_detected[cell],

            "Discharge_Duration_seconds":
                capacity_result["discharge_duration"][cell]
        })

    scenario_details[scenario_name] = {
        "capacities": capacities,
        "resistances": resistances,
        "capacity_result": capacity_result,
        "estimated_resistance": estimated_resistance,
        "estimated_resistance_growth": estimated_resistance_growth
    }


# ============================================================
# SAVE CELL-LEVEL RESULTS
# ============================================================

results_df = pd.DataFrame(all_results)

results_path = (
    METRICS_DIR
    / "lfp_16s_soh_estimation.csv"
)

results_df.to_csv(
    results_path,
    index=False
)


# ============================================================
# SCENARIO-LEVEL SUMMARY
# ============================================================

summary_rows = []

for scenario_name, result in scenario_details.items():

    capacity_error = (
        result["capacity_result"]["estimated_soh"]
        - result["capacity_result"]["true_soh"]
    )

    resistance_error = (
        result["estimated_resistance_growth"]
        - (
            result["resistances"]
            / HEALTHY_RESISTANCE_OHM
            - 1
        ) * 100.0
    )

    summary_rows.append({

        "Scenario": scenario_name,

        "Capacity_SOH_RMSE_percent": float(
            np.sqrt(np.mean(capacity_error ** 2))
        ),

        "Resistance_Growth_RMSE_percent": float(
            np.sqrt(np.mean(resistance_error ** 2))
        ),

        "Capacity_Fault_Cells_Detected": int(
            np.sum(
                result["capacity_result"]["estimated_soh"]
                < CAPACITY_SOH_THRESHOLD_PERCENT
            )
        ),

        "Resistance_Fault_Cells_Detected": int(
            np.sum(
                result["estimated_resistance_growth"]
                > RESISTANCE_GROWTH_THRESHOLD_PERCENT
            )
        )
    })


summary_df = pd.DataFrame(summary_rows)

summary_path = (
    METRICS_DIR
    / "lfp_16s_soh_summary.csv"
)

summary_df.to_csv(
    summary_path,
    index=False
)


# ============================================================
# VALIDATION
# ============================================================

healthy = scenario_details[
    "SIM-SOH-001_HEALTHY"
]

capacity_fault = scenario_details[
    "SIM-SOH-002_CAPACITY_FAULT"
]

resistance_fault = scenario_details[
    "SIM-SOH-003_RESISTANCE_FAULT"
]

combined_fault = scenario_details[
    "SIM-SOH-004_COMBINED_FAULT"
]

checks = {

    "Healthy cells show capacity SOH above threshold":
        np.all(
            healthy["capacity_result"]["estimated_soh"]
            >= CAPACITY_SOH_THRESHOLD_PERCENT
        ),

    "Healthy cells show no resistance growth alarm":
        np.all(
            healthy["estimated_resistance_growth"]
            <= RESISTANCE_GROWTH_THRESHOLD_PERCENT
        ),

    "Cell 8 capacity degradation detected":
        capacity_fault["capacity_result"]["estimated_soh"][7]
        < CAPACITY_SOH_THRESHOLD_PERCENT,

    "Capacity fault correctly localized to Cell 8":
        np.where(
            capacity_fault["capacity_result"]["estimated_soh"]
            < CAPACITY_SOH_THRESHOLD_PERCENT
        )[0].tolist() == [7],

    "Cell 12 resistance growth detected":
        resistance_fault["estimated_resistance_growth"][11]
        > RESISTANCE_GROWTH_THRESHOLD_PERCENT,

    "Resistance fault correctly localized to Cell 12":
        np.where(
            resistance_fault["estimated_resistance_growth"]
            > RESISTANCE_GROWTH_THRESHOLD_PERCENT
        )[0].tolist() == [11],

    "Combined scenario detects Cell 8 capacity fault":
        combined_fault["capacity_result"]["estimated_soh"][7]
        < CAPACITY_SOH_THRESHOLD_PERCENT,

    "Combined scenario detects Cell 12 resistance fault":
        combined_fault["estimated_resistance_growth"][11]
        > RESISTANCE_GROWTH_THRESHOLD_PERCENT
}


# ============================================================
# PRINT RESULTS
# ============================================================

print("\n" + "=" * 70)
print("16S LFP SOH ESTIMATION RESULTS")
print("=" * 70)

print("\nSCENARIO SUMMARY")

print(
    summary_df.to_string(index=False)
)

print("\nVALIDATION RESULTS")

for check, passed in checks.items():

    print(
        f"{check}: "
        f"{'PASS' if passed else 'FAIL'}"
    )

print(
    "\nOVERALL:",
    "PASS" if all(checks.values()) else "FAIL"
)


# ============================================================
# PLOTS
# ============================================================

for scenario_name, result in scenario_details.items():

    cells = np.arange(
        1,
        CELL_COUNT + 1
    )

    # Capacity SOH plot.
    plt.figure(figsize=(11, 6))

    plt.plot(
        cells,
        result["capacity_result"]["true_soh"],
        marker="o",
        label="True Capacity SOH"
    )

    plt.plot(
        cells,
        result["capacity_result"]["estimated_soh"],
        marker="x",
        linestyle="--",
        label="Estimated Capacity SOH"
    )

    plt.axhline(
        CAPACITY_SOH_THRESHOLD_PERCENT,
        linestyle=":",
        label="Detection Threshold"
    )

    plt.xlabel("Cell Number")
    plt.ylabel("Capacity SOH (%)")
    plt.title(scenario_name + " - Capacity SOH")
    plt.xticks(cells)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    plt.savefig(
        FIGURES_DIR
        / f"{scenario_name.lower()}_capacity_soh.png",
        dpi=300
    )

    plt.close()

    # Resistance growth plot.
    plt.figure(figsize=(11, 6))

    true_growth = (
        result["resistances"]
        / HEALTHY_RESISTANCE_OHM - 1
    ) * 100

    plt.plot(
        cells,
        true_growth,
        marker="o",
        label="True Resistance Growth"
    )

    plt.plot(
        cells,
        result["estimated_resistance_growth"],
        marker="x",
        linestyle="--",
        label="Estimated Resistance Growth"
    )

    plt.axhline(
        RESISTANCE_GROWTH_THRESHOLD_PERCENT,
        linestyle=":",
        label="Detection Threshold"
    )

    plt.xlabel("Cell Number")
    plt.ylabel("Resistance Growth (%)")
    plt.title(scenario_name + " - Resistance Growth")
    plt.xticks(cells)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    plt.savefig(
        FIGURES_DIR
        / f"{scenario_name.lower()}_resistance_growth.png",
        dpi=300
    )

    plt.close()


# ============================================================
# FINAL OUTPUT
# ============================================================

print("\nGENERATED FILES")

print(results_path)
print(summary_path)

print("\nFigures saved in:")
print(FIGURES_DIR)

print("\n16S LFP SOH ESTIMATION EXPERIMENT COMPLETE")

if not all(checks.values()):
    raise AssertionError("One or more SOH validation checks failed.")
