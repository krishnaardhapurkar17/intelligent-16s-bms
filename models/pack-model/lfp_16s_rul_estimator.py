
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# ============================================================
# 16S LFP REMAINING USEFUL LIFE (RUL) ESTIMATION
# Synthetic cycle-aging experiment
# ============================================================

CELL_COUNT = 16

TOTAL_CYCLES = 600
HISTORY_WINDOW = 200

NOMINAL_CAPACITY_AH = 100.0
INITIAL_RESISTANCE_OHM = 0.0005

# Simulation end-of-life criteria
CAPACITY_EOL_SOH_PERCENT = 80.0
RESISTANCE_EOL_GROWTH_PERCENT = 100.0

# Baseline degradation rates per equivalent full cycle
BASE_CAPACITY_FADE_PER_CYCLE = 0.008
BASE_RESISTANCE_GROWTH_PER_CYCLE = 0.015

# Accelerated degradation rates
WEAK_CELL_CAPACITY_FADE = 0.020
WEAK_CELL_RESISTANCE_GROWTH = 0.060

CAPACITY_NOISE_STD = 0.015
RESISTANCE_NOISE_STD = 0.025

RANDOM_SEED = 20261032

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
    "SIM-RUL-001_HEALTHY": {
        "capacity_fault_cells": [],
        "resistance_fault_cells": []
    },

    "SIM-RUL-002_CAPACITY_AGING": {
        "capacity_fault_cells": [8],
        "resistance_fault_cells": []
    },

    "SIM-RUL-003_RESISTANCE_AGING": {
        "capacity_fault_cells": [],
        "resistance_fault_cells": [12]
    },

    "SIM-RUL-004_COMBINED_AGING": {
        "capacity_fault_cells": [8],
        "resistance_fault_cells": [12]
    }
}


# ============================================================
# DEGRADATION MODEL
# ============================================================

def generate_aging_data(config):

    cycles = np.arange(TOTAL_CYCLES + 1)

    capacity_soh = np.zeros(
        (TOTAL_CYCLES + 1, CELL_COUNT)
    )

    resistance_growth = np.zeros(
        (TOTAL_CYCLES + 1, CELL_COUNT)
    )

    capacity_rates = np.full(
        CELL_COUNT,
        BASE_CAPACITY_FADE_PER_CYCLE
    )

    resistance_rates = np.full(
        CELL_COUNT,
        BASE_RESISTANCE_GROWTH_PER_CYCLE
    )

    for cell in config["capacity_fault_cells"]:
        capacity_rates[cell - 1] = WEAK_CELL_CAPACITY_FADE

    for cell in config["resistance_fault_cells"]:
        resistance_rates[cell - 1] = WEAK_CELL_RESISTANCE_GROWTH

    for cell in range(CELL_COUNT):

        capacity_soh[:, cell] = (
            100.0
            - capacity_rates[cell] * cycles
            + rng.normal(
                0,
                CAPACITY_NOISE_STD,
                len(cycles)
            )
        )

        resistance_growth[:, cell] = (
            resistance_rates[cell] * cycles
            + rng.normal(
                0,
                RESISTANCE_NOISE_STD,
                len(cycles)
            )
        )

    capacity_soh = np.clip(
        capacity_soh,
        0,
        100
    )

    resistance_growth = np.maximum(
        resistance_growth,
        0
    )

    return {
        "cycles": cycles,
        "capacity_soh": capacity_soh,
        "resistance_growth": resistance_growth,
        "capacity_rates": capacity_rates,
        "resistance_rates": resistance_rates
    }


# ============================================================
# LINEAR TREND ESTIMATION
# ============================================================

def estimate_degradation_trend(values):

    x = np.arange(
        len(values) - HISTORY_WINDOW,
        len(values)
    )

    y = values[-HISTORY_WINDOW:]

    slope, intercept = np.polyfit(
        x,
        y,
        1
    )

    return float(slope), float(intercept)


# ============================================================
# RUL ESTIMATION
# ============================================================

def estimate_rul(aging_data):

    capacity_soh = aging_data["capacity_soh"]
    resistance_growth = aging_data["resistance_growth"]

    capacity_rul = np.zeros(CELL_COUNT)
    resistance_rul = np.zeros(CELL_COUNT)

    capacity_slope = np.zeros(CELL_COUNT)
    resistance_slope = np.zeros(CELL_COUNT)

    current_capacity = capacity_soh[-1]
    current_resistance_growth = resistance_growth[-1]

    for cell in range(CELL_COUNT):

        capacity_slope[cell], _ = (
            estimate_degradation_trend(
                capacity_soh[:, cell]
            )
        )

        resistance_slope[cell], _ = (
            estimate_degradation_trend(
                resistance_growth[:, cell]
            )
        )

        # Capacity RUL
        if capacity_slope[cell] < 0:

            capacity_rul[cell] = max(
                0,
                (
                    current_capacity[cell]
                    - CAPACITY_EOL_SOH_PERCENT
                ) / abs(capacity_slope[cell])
            )

        else:
            capacity_rul[cell] = np.inf

        # Resistance RUL
        if resistance_slope[cell] > 0:

            resistance_rul[cell] = max(
                0,
                (
                    RESISTANCE_EOL_GROWTH_PERCENT
                    - current_resistance_growth[cell]
                ) / resistance_slope[cell]
            )

        else:
            resistance_rul[cell] = np.inf

    total_rul = np.minimum(
        capacity_rul,
        resistance_rul
    )

    limiting_mechanism = np.where(
        capacity_rul <= resistance_rul,
        "Capacity",
        "Resistance"
    )

    limiting_cell = int(
        np.argmin(total_rul) + 1
    )

    return {
        "capacity_rul": capacity_rul,
        "resistance_rul": resistance_rul,
        "total_rul": total_rul,
        "capacity_slope": capacity_slope,
        "resistance_slope": resistance_slope,
        "limiting_mechanism": limiting_mechanism,
        "limiting_cell": limiting_cell
    }


# ============================================================
# RUN SCENARIOS
# ============================================================

scenario_data = {}
all_rows = []
summary_rows = []

for scenario_name, config in SCENARIOS.items():

    print("\n" + "=" * 65)
    print("RUNNING:", scenario_name)
    print("=" * 65)

    aging = generate_aging_data(config)
    rul = estimate_rul(aging)

    scenario_data[scenario_name] = {
        "aging": aging,
        "rul": rul
    }

    for cell in range(CELL_COUNT):

        true_capacity_rul = max(
            0,
            (
                100.0 - CAPACITY_EOL_SOH_PERCENT
            ) / aging["capacity_rates"][cell]
            - TOTAL_CYCLES
        )

        true_resistance_rul = max(
            0,
            (
                RESISTANCE_EOL_GROWTH_PERCENT
            ) / aging["resistance_rates"][cell]
            - TOTAL_CYCLES
        )

        true_total_rul = min(
            true_capacity_rul,
            true_resistance_rul
        )

        all_rows.append({

            "Scenario": scenario_name,
            "Cell": cell + 1,

            "Current_Capacity_SOH_percent":
                aging["capacity_soh"][-1, cell],

            "Current_Resistance_Growth_percent":
                aging["resistance_growth"][-1, cell],

            "Estimated_Capacity_Fade_percent_per_cycle":
                -rul["capacity_slope"][cell],

            "Estimated_Resistance_Growth_percent_per_cycle":
                rul["resistance_slope"][cell],

            "Estimated_Capacity_RUL_cycles":
                rul["capacity_rul"][cell],

            "Estimated_Resistance_RUL_cycles":
                rul["resistance_rul"][cell],

            "Estimated_Total_RUL_cycles":
                rul["total_rul"][cell],

            "True_Total_RUL_cycles":
                true_total_rul,

            "Limiting_Mechanism":
                rul["limiting_mechanism"][cell]
        })

    summary_rows.append({

        "Scenario": scenario_name,

        "Limiting_Cell":
            rul["limiting_cell"],

        "Limiting_Mechanism":
            rul["limiting_mechanism"][
                rul["limiting_cell"] - 1
            ],

        "Minimum_Predicted_RUL_cycles":
            rul["total_rul"][
                rul["limiting_cell"] - 1
            ],

        "Mean_Capacity_RUL_cycles":
            np.mean(rul["capacity_rul"]),

        "Mean_Resistance_RUL_cycles":
            np.mean(rul["resistance_rul"])
    })


# ============================================================
# SAVE RESULTS
# ============================================================

results_df = pd.DataFrame(all_rows)
summary_df = pd.DataFrame(summary_rows)

results_path = (
    METRICS_DIR / "lfp_16s_rul_estimation.csv"
)

summary_path = (
    METRICS_DIR / "lfp_16s_rul_summary.csv"
)

results_df.to_csv(
    results_path,
    index=False
)

summary_df.to_csv(
    summary_path,
    index=False
)


# ============================================================
# VALIDATION
# ============================================================

healthy = scenario_data[
    "SIM-RUL-001_HEALTHY"
]

capacity_fault = scenario_data[
    "SIM-RUL-002_CAPACITY_AGING"
]

resistance_fault = scenario_data[
    "SIM-RUL-003_RESISTANCE_AGING"
]

combined_fault = scenario_data[
    "SIM-RUL-004_COMBINED_AGING"
]

checks = {

    "Healthy scenario has positive RUL for every cell":
        np.all(
            healthy["rul"]["total_rul"] > 0
        ),

    "Capacity aging identifies Cell 8 as limiting":
        capacity_fault["rul"]["limiting_cell"] == 8,

    "Cell 8 capacity degradation is limiting mechanism":
        capacity_fault["rul"]["limiting_mechanism"][7]
        == "Capacity",

    "Resistance aging identifies Cell 12 as limiting":
        resistance_fault["rul"]["limiting_cell"] == 12,

    "Cell 12 resistance degradation is limiting mechanism":
        resistance_fault["rul"]["limiting_mechanism"][11]
        == "Resistance",

    "Combined aging identifies Cell 8 as limiting":
        combined_fault["rul"]["limiting_cell"] == 8,

    "Combined scenario detects Cell 12 resistance degradation":
        combined_fault["rul"]["resistance_rul"][11]
        < combined_fault["rul"]["resistance_rul"][0],

    "All estimated RUL values are non-negative":
        all(
            np.all(result["rul"]["total_rul"] >= 0)
            for result in scenario_data.values()
        )
}


# ============================================================
# PRINT RESULTS
# ============================================================

print("\n" + "=" * 70)
print("16S LFP RUL ESTIMATION RESULTS")
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

for scenario_name, result in scenario_data.items():

    aging = result["aging"]
    rul = result["rul"]

    cycles = aging["cycles"]
    cells = np.arange(1, CELL_COUNT + 1)

    # Capacity degradation history
    plt.figure(figsize=(11, 6))

    for cell in range(CELL_COUNT):

        plt.plot(
            cycles,
            aging["capacity_soh"][:, cell],
            label=f"Cell {cell + 1}"
        )

    plt.axhline(
        CAPACITY_EOL_SOH_PERCENT,
        linestyle="--",
        label="Capacity EOL threshold"
    )

    plt.xlabel("Equivalent Full Cycles")
    plt.ylabel("Capacity SOH (%)")
    plt.title(scenario_name + " - Capacity Aging")
    plt.grid(True)
    plt.legend(ncol=4, fontsize=8)
    plt.tight_layout()

    plt.savefig(
        FIGURES_DIR
        / f"{scenario_name.lower()}_capacity_aging.png",
        dpi=300
    )

    plt.close()

    # Resistance degradation history
    plt.figure(figsize=(11, 6))

    for cell in range(CELL_COUNT):

        plt.plot(
            cycles,
            aging["resistance_growth"][:, cell],
            label=f"Cell {cell + 1}"
        )

    plt.axhline(
        RESISTANCE_EOL_GROWTH_PERCENT,
        linestyle="--",
        label="Resistance EOL threshold"
    )

    plt.xlabel("Equivalent Full Cycles")
    plt.ylabel("Resistance Growth (%)")
    plt.title(scenario_name + " - Resistance Aging")
    plt.grid(True)
    plt.legend(ncol=4, fontsize=8)
    plt.tight_layout()

    plt.savefig(
        FIGURES_DIR
        / f"{scenario_name.lower()}_resistance_aging.png",
        dpi=300
    )

    plt.close()

    # Cell-level RUL estimates
    plt.figure(figsize=(11, 6))

    plt.bar(
        cells,
        rul["total_rul"]
    )

    plt.xlabel("Cell Number")
    plt.ylabel("Estimated Remaining Cycles")
    plt.title(scenario_name + " - Cell-Level RUL")
    plt.xticks(cells)
    plt.grid(axis="y")
    plt.tight_layout()

    plt.savefig(
        FIGURES_DIR
        / f"{scenario_name.lower()}_rul.png",
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

print("\n16S LFP RUL ESTIMATION EXPERIMENT COMPLETE")

if not all(checks.values()):
    raise AssertionError("One or more RUL validation checks failed.")
