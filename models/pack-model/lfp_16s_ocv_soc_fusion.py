
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# ============================================================
# 16S LFP COULOMB COUNTING + OCV SOC FUSION
# Simulation experiment - illustrative parameters only
# ============================================================

CELL_COUNT = 16
CAPACITY_AH = 100.0

DISCHARGE_CURRENT_A = 50.0
DT_SECONDS = 1

CURRENT_SENSOR_BIAS_A = 0.20
CURRENT_NOISE_STD_A = 0.10
OCV_NOISE_STD_V = 0.00005

MIN_REST_SECONDS = 300
REST_CURRENT_THRESHOLD_A = 1.0

# Minimum OCV slope required for accepting correction.
# Units: volts per SOC percentage point.
MIN_OCV_SLOPE = 0.0025

OCV_WEIGHT = 0.70
RANDOM_SEED = 20261030

BASE_DIR = Path(__file__).resolve().parents[2]
METRICS_DIR = BASE_DIR / "results" / "metrics"
FIGURES_DIR = BASE_DIR / "results" / "figures"

METRICS_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(RANDOM_SEED)

# ============================================================
# ILLUSTRATIVE LFP OCV-SOC LOOKUP TABLE
# Not manufacturer-characterized data.
# ============================================================

OCV_SOC_PERCENT = np.array([
    0, 5, 10, 15, 20, 30, 40,
    50, 60, 70, 80, 90, 95, 100
], dtype=float)

OCV_VOLTAGE = np.array([
    2.50, 3.00, 3.15, 3.20, 3.215, 3.225, 3.230,
    3.235, 3.240, 3.250, 3.265, 3.300, 3.350, 3.600
], dtype=float)


def soc_to_ocv(soc):
    return np.interp(
        soc,
        OCV_SOC_PERCENT,
        OCV_VOLTAGE
    )


def ocv_to_soc(voltage):
    return np.interp(
        voltage,
        OCV_VOLTAGE,
        OCV_SOC_PERCENT
    )


def get_ocv_slope(soc):
    index = np.searchsorted(
        OCV_SOC_PERCENT,
        soc,
        side="right"
    ) - 1

    index = np.clip(
        index,
        0,
        len(OCV_SOC_PERCENT) - 2
    )

    dv = (
        OCV_VOLTAGE[index + 1]
        - OCV_VOLTAGE[index]
    )

    ds = (
        OCV_SOC_PERCENT[index + 1]
        - OCV_SOC_PERCENT[index]
    )

    return dv / ds


# ============================================================
# SOC FUSION SIMULATION
# ============================================================

def run_scenario(name, initial_soc, discharge_seconds):

    total_seconds = (
        discharge_seconds
        + MIN_REST_SECONDS
        + 300
    )

    time = np.arange(
        0,
        total_seconds + DT_SECONDS,
        DT_SECONDS
    )

    sample_count = len(time)

    true_current = np.where(
        time < discharge_seconds,
        DISCHARGE_CURRENT_A,
        0.0
    )

    measured_current = (
        true_current
        + CURRENT_SENSOR_BIAS_A
        + rng.normal(
            0,
            CURRENT_NOISE_STD_A,
            sample_count
        )
    )

    true_soc = np.zeros(
        (sample_count, CELL_COUNT)
    )

    cc_soc = np.zeros(
        (sample_count, CELL_COUNT)
    )

    fused_soc = np.zeros(
        (sample_count, CELL_COUNT)
    )

    true_soc[0, :] = initial_soc
    cc_soc[0, :] = initial_soc
    fused_soc[0, :] = initial_soc

    correction_applied = np.zeros(
        CELL_COUNT,
        dtype=bool
    )

    correction_rejected = np.zeros(
        CELL_COUNT,
        dtype=bool
    )

    rest_counter = 0
    correction_attempted = False
    correction_time = None

    for k in range(1, sample_count):

        dt_hours = DT_SECONDS / 3600.0

        # ----------------------------------------------------
        # Ground-truth SOC
        # ----------------------------------------------------

        true_soc[k] = (
            true_soc[k - 1]
            - true_current[k - 1]
            * dt_hours
            / CAPACITY_AH
            * 100.0
        )

        true_soc[k] = np.clip(
            true_soc[k],
            0,
            100
        )

        # ----------------------------------------------------
        # Coulomb-counting SOC
        # ----------------------------------------------------

        cc_soc[k] = (
            cc_soc[k - 1]
            - measured_current[k - 1]
            * dt_hours
            / CAPACITY_AH
            * 100.0
        )

        cc_soc[k] = np.clip(
            cc_soc[k],
            0,
            100
        )

        # ----------------------------------------------------
        # Fused SOC propagation
        # Carry forward the previous fused estimate.
        # ----------------------------------------------------

        fused_soc[k] = (
            fused_soc[k - 1]
            - measured_current[k - 1]
            * dt_hours
            / CAPACITY_AH
            * 100.0
        )

        fused_soc[k] = np.clip(
            fused_soc[k],
            0,
            100
        )

        # ----------------------------------------------------
        # Rest detection
        # ----------------------------------------------------

        if abs(measured_current[k]) <= REST_CURRENT_THRESHOLD_A:
            rest_counter += 1
        else:
            rest_counter = 0

        # ----------------------------------------------------
        # OCV correction attempt after continuous rest
        # ----------------------------------------------------

        if (
            rest_counter >= MIN_REST_SECONDS
            and not correction_attempted
        ):

            correction_attempted = True
            correction_time = time[k]

            print(
                f"\nOCV correction attempt: {name}"
            )

            print(
                f"Time: {time[k]} seconds | "
                f"Ground-truth SOC: "
                f"{true_soc[k, 0]:.4f}%"
            )

            for cell in range(CELL_COUNT):

                actual_ocv = soc_to_ocv(
                    true_soc[k, cell]
                )

                measured_ocv = (
                    actual_ocv
                    + rng.normal(
                        0,
                        OCV_NOISE_STD_V
                    )
                )

                estimated_ocv_soc = ocv_to_soc(
                    measured_ocv
                )

                slope = get_ocv_slope(
                    estimated_ocv_soc
                )

                print(
                    f"Cell {cell + 1:02d}: "
                    f"OCV={measured_ocv:.6f} V | "
                    f"OCV SOC={estimated_ocv_soc:.3f}% | "
                    f"Slope={slope:.6f} V/%"
                )

                if slope >= MIN_OCV_SLOPE:

                    fused_soc[k, cell] = (
                        (1 - OCV_WEIGHT)
                        * fused_soc[k, cell]
                        + OCV_WEIGHT
                        * estimated_ocv_soc
                    )

                    correction_applied[cell] = True

                else:

                    correction_rejected[cell] = True

    # --------------------------------------------------------
    # Calculate estimation errors
    # --------------------------------------------------------

    cc_error = cc_soc - true_soc
    fused_error = fused_soc - true_soc

    return {
        "scenario": name,
        "time_seconds": time,
        "true_current": true_current,
        "measured_current": measured_current,
        "true_soc": true_soc,
        "cc_soc": cc_soc,
        "fused_soc": fused_soc,

        "cc_rmse": float(
            np.sqrt(np.mean(cc_error ** 2))
        ),

        "fused_rmse": float(
            np.sqrt(np.mean(fused_error ** 2))
        ),

        "cc_final_error": float(
            np.mean(cc_error[-1])
        ),

        "fused_final_error": float(
            np.mean(fused_error[-1])
        ),

        "corrections_applied": int(
            np.sum(correction_applied)
        ),

        "corrections_rejected": int(
            np.sum(correction_rejected)
        ),

        "correction_time": correction_time
    }


# ============================================================
# RUN SCENARIOS
# ============================================================

scenarios = [

    # 100% SOC - 5% discharge.
    # This places the cell near the steep upper OCV region.
    run_scenario(
        "OCV_CORRECTION_REGION",
        initial_soc=100.0,
        discharge_seconds=360
    ),

    # 90% SOC - approximately 16.67% discharge.
    # This places the cell near the flatter OCV region.
    run_scenario(
        "LFP_FLAT_REGION",
        initial_soc=90.0,
        discharge_seconds=1200
    )
]


# ============================================================
# EXPORT RESULTS
# ============================================================

summary_rows = []
timeseries_rows = []

for result in scenarios:

    summary_rows.append({

        "Scenario": result["scenario"],

        "Coulomb_Counting_RMSE_percent":
            result["cc_rmse"],

        "Fused_SOC_RMSE_percent":
            result["fused_rmse"],

        "Coulomb_Counting_Final_Error_percent":
            result["cc_final_error"],

        "Fused_Final_Error_percent":
            result["fused_final_error"],

        "OCV_Corrections_Applied":
            result["corrections_applied"],

        "OCV_Corrections_Rejected":
            result["corrections_rejected"]
    })

    
    for k, seconds in enumerate(result["time_seconds"]):

        row = {
            "Scenario": result["scenario"],
            "Time_seconds": seconds,
            "True_Current_A": result["true_current"][k],
            "Measured_Current_A": result["measured_current"][k]
        }

        for cell in range(CELL_COUNT):

            cell_number = cell + 1

            row[f"True_SOC_Cell_{cell_number}"] = (
                result["true_soc"][k, cell]
            )

            row[f"Coulomb_Counting_SOC_Cell_{cell_number}"] = (
                result["cc_soc"][k, cell]
            )

            row[f"Fused_SOC_Cell_{cell_number}"] = (
                result["fused_soc"][k, cell]
            )

        timeseries_rows.append(row)



summary_df = pd.DataFrame(summary_rows)
timeseries_df = pd.DataFrame(timeseries_rows)

summary_path = (
    METRICS_DIR
    / "lfp_16s_ocv_soc_fusion_metrics.csv"
)

timeseries_path = (
    METRICS_DIR
    / "lfp_16s_ocv_soc_fusion.csv"
)

summary_df.to_csv(
    summary_path,
    index=False
)

timeseries_df.to_csv(
    timeseries_path,
    index=False
)


# ============================================================
# VALIDATION
# ============================================================

correction_result = scenarios[0]
flat_result = scenarios[1]

checks = {

    "OCV correction accepted in steep region":
        correction_result["corrections_applied"]
        == CELL_COUNT,

    "OCV correction reduces final SOC error":
        abs(correction_result["fused_final_error"])
        < abs(correction_result["cc_final_error"]),

    "OCV correction rejected in flat region":
        flat_result["corrections_rejected"]
        == CELL_COUNT,

    "No OCV correction applied in flat region":
        flat_result["corrections_applied"]
        == 0,

    "SOC estimates remain within physical limits":
        all(
            np.all(
                (result["fused_soc"] >= 0)
                & (result["fused_soc"] <= 100)
            )
            for result in scenarios
        ),

    "OCV correction attempted in both scenarios":
        all(
            result["correction_time"] is not None
            for result in scenarios
        ),
    "All 16 cells have SOC estimates":
        all(
        result["fused_soc"].shape[1] == CELL_COUNT
        for result in scenarios
        )
}


# ============================================================
# PRINT RESULTS
# ============================================================

print("\n")
print("=" * 70)
print("16S LFP OCV + COULOMB COUNTING SOC FUSION")
print("=" * 70)

print("\nSCENARIO METRICS")
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
# GENERATE PLOTS
# ============================================================

for result in scenarios:

    plt.figure(figsize=(11, 6))

    plt.plot(
        result["time_seconds"] / 60,
        result["true_soc"][:, 0],
        label="Ground Truth SOC"
    )

    plt.plot(
        result["time_seconds"] / 60,
        result["cc_soc"][:, 0],
        linestyle="--",
        label="Coulomb Counting"
    )

    plt.plot(
        result["time_seconds"] / 60,
        result["fused_soc"][:, 0],
        label="OCV + Coulomb Counting"
    )

    if result["correction_time"] is not None:

        plt.axvline(
            result["correction_time"] / 60,
            linestyle=":",
            label="OCV Correction Attempt"
        )

    plt.xlabel("Time (minutes)")
    plt.ylabel("SOC (%)")

    plt.title(
        result["scenario"]
    )

    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    filename = (
        "lfp_16s_ocv_fusion_"
        + result["scenario"].lower()
        + ".png"
    )

    plt.savefig(
        FIGURES_DIR / filename,
        dpi=300
    )

    plt.close()


# ============================================================
# FINAL OUTPUT
# ============================================================

print("\nGENERATED FILES")

print(summary_path)
print(timeseries_path)

print(
    FIGURES_DIR
    / "lfp_16s_ocv_fusion_ocv_correction_region.png"
)

print(
    FIGURES_DIR
    / "lfp_16s_ocv_fusion_lfp_flat_region.png"
)

print("\nOCV SOC FUSION EXPERIMENT COMPLETE")
