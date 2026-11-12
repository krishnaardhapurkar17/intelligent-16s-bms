
from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# 1. PROJECT CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[2]

METRICS_DIR = ROOT / "results" / "metrics"
FIGURES_DIR = ROOT / "results" / "figures"

METRICS_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_RUNS = METRICS_DIR / "lfp_16s_monte_carlo_runs.csv"
OUTPUT_SUMMARY = METRICS_DIR / "lfp_16s_monte_carlo_summary.json"
OUTPUT_PLOT = FIGURES_DIR / "lfp_16s_monte_carlo_performance.png"

RUNS_PER_SCENARIO = 100
BASE_SEED = 20261030

CELL_COUNT = 16
DT = 1.0
DURATION = 180

CAPACITY_AH = 100.0

R0_HEALTHY = 0.0005
R0_DEGRADED = 0.00075

R1 = 0.0002
TAU = 30.0

VOLTAGE_NOISE_STD_V = 0.001
CURRENT_NOISE_STD_A = 0.10
TEMPERATURE_NOISE_STD_C = 0.25

RESISTANCE_THRESHOLD = 1.20
VOLTAGE_THRESHOLD_MV = 15.0
TEMPERATURE_THRESHOLD_C = 5.0

INVALID_TEMP_MIN = -40.0
INVALID_TEMP_MAX = 100.0

TEMP_COEFFICIENT = -0.004

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
# 2. BATTERY MODEL
# ============================================================

def get_current(time_s):

    value = 0.0

    for start, current in CURRENT_PROFILE:
        if time_s >= start:
            value = current

    return value


def ocv_from_soc(soc):

    # Illustrative linear approximation.
    # Not a calibrated LFP OCV-SOC relationship.
    return 3.0 + 0.5 * np.clip(soc, 0.0, 1.0)


# ============================================================
# 3. SCENARIO DEFINITIONS
# ============================================================

def make_scenario(
    name,
    resistance_faults=None,
    voltage_biases=None,
    temperature_biases=None,
    initial_soc=None,
    temperatures=None,
    missing_voltage=None,
    invalid_temperature=None,
    missing_temperature=None,
):

    resistance_faults = resistance_faults or {}
    voltage_biases = voltage_biases or {}
    temperature_biases = temperature_biases or {}

    r0 = np.full(CELL_COUNT, R0_HEALTHY)

    for cell, value in resistance_faults.items():
        r0[cell - 1] = value

    voltage_bias = np.zeros(CELL_COUNT)

    for cell, value in voltage_biases.items():
        voltage_bias[cell - 1] = value

    temperature_bias = np.zeros(CELL_COUNT)

    for cell, value in temperature_biases.items():
        temperature_bias[cell - 1] = value

    if initial_soc is None:
        initial_soc = np.full(CELL_COUNT, 0.90)

    if temperatures is None:
        temperatures = np.full(CELL_COUNT, 25.0)

    return {
        "name": name,
        "r0": r0,
        "voltage_bias": voltage_bias,
        "temperature_bias": temperature_bias,
        "initial_soc": np.array(initial_soc, dtype=float),
        "temperatures": np.array(temperatures, dtype=float),
        "missing_voltage": missing_voltage or [],
        "invalid_temperature": invalid_temperature or [],
        "missing_temperature": missing_temperature or [],
    }


soc_imbalance = np.full(CELL_COUNT, 0.90)
soc_imbalance[7] = 0.80

temperature_spread = np.linspace(22.0, 28.0, CELL_COUNT)

SCENARIOS = [

    make_scenario(
        "SIM-018A Healthy noisy pack"
    ),

    make_scenario(
        "SIM-018B SOC imbalance",
        initial_soc=soc_imbalance
    ),

    make_scenario(
        "SIM-018C Temperature variation",
        temperatures=temperature_spread
    ),

    make_scenario(
        "SIM-018D Resistance fault",
        resistance_faults={8: R0_DEGRADED}
    ),

    make_scenario(
        "SIM-018E Multiple faults",
        resistance_faults={8: R0_DEGRADED},
        voltage_biases={12: -0.030},
        temperature_biases={14: 15.0}
    ),

    make_scenario(
        "SIM-018F Sensor data faults",
        missing_voltage=[14],
        invalid_temperature=[15],
        missing_temperature=[16]
    ),
]


# ============================================================
# 4. SIMULATE ONE MONTE CARLO RUN
# ============================================================

def simulate(scenario, seed):

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
            CURRENT_NOISE_STD_A,
            len(time)
        )
    )

    soc = np.zeros((len(time), CELL_COUNT))
    soc[0] = scenario["initial_soc"]

    polarization = np.zeros(CELL_COUNT)

    voltage = np.zeros((len(time), CELL_COUNT))
    temperature = np.zeros((len(time), CELL_COUNT))

    temperature_factor = (
        1.0
        + TEMP_COEFFICIENT
        * (scenario["temperatures"] - 25.0)
    )

    actual_r0 = scenario["r0"] * temperature_factor

    for k in range(len(time)):

        ocv = ocv_from_soc(soc[k])

        true_voltage = (
            ocv
            - true_current[k] * actual_r0
            - polarization
        )

        voltage[k] = (
            true_voltage
            + scenario["voltage_bias"]
            + rng.normal(
                0,
                VOLTAGE_NOISE_STD_V,
                CELL_COUNT
            )
        )

        temperature[k] = (
            scenario["temperatures"]
            + scenario["temperature_bias"]
            + rng.normal(
                0,
                TEMPERATURE_NOISE_STD_C,
                CELL_COUNT
            )
        )

        if k < len(time) - 1:

            soc[k + 1] = (
                soc[k]
                - true_current[k] * DT
                / (CAPACITY_AH * 3600)
            )

            soc[k + 1] = np.clip(
                soc[k + 1],
                0.0,
                1.0
            )

        polarization += (
            DT / TAU
        ) * (
            true_current[k] * R1 - polarization
        )

    # Sensor data faults.
    for cell in scenario["missing_voltage"]:
        voltage[:, cell - 1] = np.nan

    for cell in scenario["invalid_temperature"]:
        temperature[:, cell - 1] = 150.0

    for cell in scenario["missing_temperature"]:
        temperature[:, cell - 1] = np.nan

    return {
        "time": time,
        "current": measured_current,
        "voltage": voltage,
        "temperature": temperature,
        "actual_r0": actual_r0,
    }


# ============================================================
# 5. RESISTANCE ESTIMATION
# ============================================================

def estimate_resistance(data):

    current = data["current"]
    voltage = data["voltage"]

    estimates = [[] for _ in range(CELL_COUNT)]

    for k in range(1, len(current)):

        delta_current = (
            current[k] - current[k - 1]
        )

        if abs(delta_current) < 5.0:
            continue

        for cell in range(CELL_COUNT):

            v1 = voltage[k - 1, cell]
            v2 = voltage[k, cell]

            if not np.isfinite(v1) or not np.isfinite(v2):
                continue

            estimate = -(
                v2 - v1
            ) / delta_current

            if np.isfinite(estimate) and estimate > 0:
                estimates[cell].append(estimate)

    result = np.full(CELL_COUNT, np.nan)

    for cell, values in enumerate(estimates):

        if values:
            result[cell] = np.median(values)

    return result


# ============================================================
# 6. VOLTAGE DIAGNOSTIC
# ============================================================

def voltage_diagnostic(data):

    index = 140

    voltage = data["voltage"][index]

    valid = np.isfinite(voltage)

    deviation = np.full(CELL_COUNT, np.nan)

    if valid.sum() < 8:
        return deviation

    reference = np.median(voltage[valid])

    deviation[valid] = (
        reference - voltage[valid]
    ) * 1000.0

    return deviation


# ============================================================
# 7. TEMPERATURE DIAGNOSTIC
# ============================================================

def temperature_diagnostic(data):

    temperature = data["temperature"]

    mean_temperature = np.array([
        np.mean(
            temperature[
                np.isfinite(temperature[:, cell]),
                cell
            ]
        )
        if np.isfinite(temperature[:, cell]).any()
        else np.nan

        for cell in range(CELL_COUNT)
    ])

    valid = (
        np.isfinite(mean_temperature)
        & (mean_temperature >= INVALID_TEMP_MIN)
        & (mean_temperature <= INVALID_TEMP_MAX)
    )

    deviation = np.full(CELL_COUNT, np.nan)

    if valid.sum() >= 8:

        reference = np.median(
            mean_temperature[valid]
        )

        deviation[valid] = (
            mean_temperature[valid] - reference
        )

    return mean_temperature, deviation


# ============================================================
# 8. RUN MONTE CARLO EXPERIMENTS
# ============================================================

run_records = []

print("=" * 75)
print("16S LFP MONTE CARLO ROBUSTNESS EVALUATION")
print("=" * 75)

for scenario_index, scenario in enumerate(SCENARIOS):

    print(
        f"\nRunning {scenario['name']} "
        f"({RUNS_PER_SCENARIO} trials)"
    )

    for run_number in range(RUNS_PER_SCENARIO):

        seed = (
            BASE_SEED
            + scenario_index * 100000
            + run_number
        )

        data = simulate(
            scenario,
            seed
        )

        estimated_r0 = estimate_resistance(data)

        voltage_deviation = voltage_diagnostic(data)

        (
            mean_temperature,
            temperature_deviation
        ) = temperature_diagnostic(data)

        valid_r0 = np.isfinite(estimated_r0)

        if valid_r0.sum() >= 8:

            r0_reference = np.median(
                estimated_r0[valid_r0]
            )

        else:

            r0_reference = np.nan

        voltage_available = np.any(
            np.isfinite(data["voltage"]),
            axis=0
        )

        for cell in range(CELL_COUNT):

            resistance_ratio = np.nan
            resistance_flag = False

            if (
                np.isfinite(estimated_r0[cell])
                and np.isfinite(r0_reference)
                and r0_reference > 0
            ):

                resistance_ratio = (
                    estimated_r0[cell] / r0_reference
                )

                resistance_flag = (
                    resistance_ratio > RESISTANCE_THRESHOLD
                )

            voltage_flag = (
                np.isfinite(voltage_deviation[cell])
                and voltage_deviation[cell] >= VOLTAGE_THRESHOLD_MV
            )

            temperature_flag = (
                np.isfinite(temperature_deviation[cell])
                and abs(temperature_deviation[cell])
                >= TEMPERATURE_THRESHOLD_C
            )

            voltage_missing = not voltage_available[cell]

            temperature_missing = (
                not np.isfinite(mean_temperature[cell])
            )

            temperature_invalid = (
                np.isfinite(mean_temperature[cell])
                and (
                    mean_temperature[cell] < INVALID_TEMP_MIN
                    or mean_temperature[cell] > INVALID_TEMP_MAX
                )
            )

            run_records.append({

                "Scenario": scenario["name"],
                "Run": run_number + 1,
                "Seed": seed,
                "Cell": cell + 1,

                "Estimated_R0_mOhm": (
                    estimated_r0[cell] * 1000
                    if np.isfinite(estimated_r0[cell])
                    else np.nan
                ),

                "Resistance_Ratio": resistance_ratio,

                "Voltage_Deviation_mV": voltage_deviation[cell],

                "Temperature_Deviation_C": temperature_deviation[cell],

                "Resistance_Flag": bool(resistance_flag),

                "Voltage_Flag": bool(voltage_flag),

                "Temperature_Flag": bool(temperature_flag),

                "Voltage_Missing": bool(voltage_missing),

                "Temperature_Missing": bool(temperature_missing),

                "Temperature_Invalid": bool(temperature_invalid),
            })


# ============================================================
# 9. SAVE RAW RUN RESULTS
# ============================================================

runs_df = pd.DataFrame(run_records)

runs_df.to_csv(
    OUTPUT_RUNS,
    index=False
)


# ============================================================
# 10. COMPUTE PERFORMANCE METRICS
# ============================================================

summary_rows = []

for scenario in SCENARIOS:

    name = scenario["name"]

    subset = runs_df[
        runs_df["Scenario"] == name
    ]

    expected_resistance_cells = set(
        scenario["r0"].tolist()
    )

    degraded_cells = {
        i + 1
        for i, value in enumerate(scenario["r0"])
        if value > R0_HEALTHY * 1.01
    }

    expected_voltage_cells = {
        i + 1
        for i, value in enumerate(scenario["voltage_bias"])
        if abs(value) > 0
    }

    expected_temperature_cells = {
        i + 1
        for i, value in enumerate(scenario["temperature_bias"])
        if abs(value) > 0
    }

    expected_missing_voltage = set(
        scenario["missing_voltage"]
    )

    expected_invalid_temperature = set(
        scenario["invalid_temperature"]
    )

    expected_missing_temperature = set(
        scenario["missing_temperature"]
    )

    # Count correct detections per run.
    resistance_success = []
    voltage_success = []
    temperature_success = []
    data_quality_success = []

    for run_number in range(1, RUNS_PER_SCENARIO + 1):

        current_run = subset[
            subset["Run"] == run_number
        ]

        resistance_detected = set(
            current_run.loc[
                current_run["Resistance_Flag"],
                "Cell"
            ].astype(int)
        )

        voltage_detected = set(
            current_run.loc[
                current_run["Voltage_Flag"],
                "Cell"
            ].astype(int)
        )

        temperature_detected = set(
            current_run.loc[
                current_run["Temperature_Flag"],
                "Cell"
            ].astype(int)
        )

        missing_voltage_detected = set(
            current_run.loc[
                current_run["Voltage_Missing"],
                "Cell"
            ].astype(int)
        )

        invalid_temperature_detected = set(
            current_run.loc[
                current_run["Temperature_Invalid"],
                "Cell"
            ].astype(int)
        )

        missing_temperature_detected = set(
            current_run.loc[
                current_run["Temperature_Missing"],
                "Cell"
            ].astype(int)
        )

        if degraded_cells:
            resistance_success.append(
                degraded_cells.issubset(resistance_detected)
            )

        if expected_voltage_cells:
            voltage_success.append(
                expected_voltage_cells.issubset(voltage_detected)
            )

        if expected_temperature_cells:
            temperature_success.append(
                expected_temperature_cells.issubset(
                    temperature_detected
                )
            )

        expected_data_faults = (
            expected_missing_voltage
            | expected_invalid_temperature
            | expected_missing_temperature
        )

        if expected_data_faults:

            detected_data_faults = (
                missing_voltage_detected
                | invalid_temperature_detected
                | missing_temperature_detected
            )

            data_quality_success.append(
                expected_data_faults.issubset(
                    detected_data_faults
                )
            )

    def rate(values):

        if not values:
            return None

        return float(
            np.mean(values) * 100
        )

    # False-positive rate is calculated only for
    # the fully healthy noise scenario.
    false_positive_rate = None

    if name == "SIM-018A Healthy noisy pack":

        false_positive_count = (
            subset["Resistance_Flag"].sum()
            + subset["Temperature_Flag"].sum()
        )

        total_healthy_channel_checks = (
            RUNS_PER_SCENARIO * CELL_COUNT * 2
        )

        false_positive_rate = (
            false_positive_count
            / total_healthy_channel_checks
            * 100
        )

    # Resistance estimation error for degraded cells.
    resistance_error = None

    if degraded_cells:

        errors = []

        for cell in degraded_cells:

            cell_data = subset[
                subset["Cell"] == cell
            ]

            actual_r0 = (
                scenario["r0"][cell - 1] * 1000
            )

            errors.extend(
                np.abs(
                    cell_data["Estimated_R0_mOhm"].dropna()
                    - actual_r0
                ).tolist()
            )

        if errors:
            resistance_error = float(
                np.mean(errors)
            )

    summary_rows.append({

        "Scenario": name,

        "Runs": RUNS_PER_SCENARIO,

        "Resistance_Detection_Rate_Percent": rate(
            resistance_success
        ),

        "Voltage_Bias_Detection_Rate_Percent": rate(
            voltage_success
        ),

        "Temperature_Bias_Detection_Rate_Percent": rate(
            temperature_success
        ),

        "Sensor_Data_Fault_Detection_Rate_Percent": rate(
            data_quality_success
        ),

        "Healthy_False_Positive_Rate_Percent": (
            false_positive_rate
        ),

        "Mean_Resistance_Estimation_Error_mOhm": (
            resistance_error
        ),
    })


summary_df = pd.DataFrame(summary_rows)


# ============================================================
# 11. SAVE SUMMARY
# ============================================================

summary_df.to_csv(
    METRICS_DIR / "lfp_16s_monte_carlo_metrics.csv",
    index=False
)

summary_json = {

    "experiment": "16S LFP Monte Carlo robustness evaluation",

    "runs_per_scenario": RUNS_PER_SCENARIO,

    "total_runs": (
        RUNS_PER_SCENARIO * len(SCENARIOS)
    ),

    "base_random_seed": BASE_SEED,

    "noise_parameters": {
        "voltage_noise_std_V": VOLTAGE_NOISE_STD_V,
        "current_noise_std_A": CURRENT_NOISE_STD_A,
        "temperature_noise_std_C": TEMPERATURE_NOISE_STD_C,
    },

    "diagnostic_thresholds": {
        "resistance_ratio": RESISTANCE_THRESHOLD,
        "voltage_deviation_mV": VOLTAGE_THRESHOLD_MV,
        "temperature_deviation_C": TEMPERATURE_THRESHOLD_C,
    },

    "metrics": summary_df.astype(object).where(
        pd.notna(summary_df),
        None
    ).to_dict(orient="records"),

    "limitations": [
        "Results apply only to the simulated scenarios and assumed noise distributions.",
        "SOC imbalance is not counted as a confirmed hardware fault.",
        "Voltage deviation is not equivalent to voltage sensor fault.",
        "Temperature deviation is not definitive proof of sensor bias.",
        "The resistance model and OCV relationship are simplified.",
        "The reported false-positive rate covers resistance and temperature flags in the healthy noisy scenario only.",
        "These results are not physical battery validation."
    ]
}

with open(
    OUTPUT_SUMMARY,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        summary_json,
        f,
        indent=4,
        allow_nan=False,
    )


# ============================================================
# 12. PLOT DETECTION METRICS
# ============================================================

metric_columns = [
    "Resistance_Detection_Rate_Percent",
    "Voltage_Bias_Detection_Rate_Percent",
    "Temperature_Bias_Detection_Rate_Percent",
    "Sensor_Data_Fault_Detection_Rate_Percent",
]

plot_df = summary_df.set_index(
    "Scenario"
)[metric_columns]

ax = plot_df.plot(
    kind="bar",
    figsize=(15, 7)
)

ax.set_title(
    "16S LFP Monte Carlo Detection Performance"
)

ax.set_ylabel(
    "Detection rate (%)"
)

ax.set_xlabel(
    "Scenario"
)

ax.set_ylim(0, 105)

ax.grid(
    axis="y"
)

plt.xticks(
    rotation=25,
    ha="right"
)

plt.tight_layout(
    rect=(0, 0.05, 1, 1)
)
plt.figtext(
    0.99,
    0.015,
    "Blank bars indicate a metric that is not applicable to that scenario.",
    ha="right",
    fontsize=9,
)

plt.savefig(
    OUTPUT_PLOT,
    dpi=180
)

plt.close()


# ============================================================
# 13. TERMINAL REPORT
# ============================================================

print("\n" + "=" * 75)
print("MONTE CARLO PERFORMANCE SUMMARY")
print("=" * 75)

print(
    summary_df.to_string(
        index=False,
        na_rep="N/A"
    )
)

print("\n" + "=" * 75)
print("GENERATED FILES")
print("=" * 75)

print(OUTPUT_RUNS)
print(
    METRICS_DIR / "lfp_16s_monte_carlo_metrics.csv"
)
print(OUTPUT_SUMMARY)
print(OUTPUT_PLOT)

print("\n" + "=" * 75)
print("MONTE CARLO EXPERIMENT COMPLETE")
print("=" * 75)
