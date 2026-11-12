
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[2]

METRICS = ROOT / "results" / "metrics"
FIGURES = ROOT / "results" / "figures"

METRICS.mkdir(parents=True, exist_ok=True)
FIGURES.mkdir(parents=True, exist_ok=True)

CELL_COUNT = 16

CAPACITY_AH = 100.0

DT_SECONDS = 1.0
DURATION_HOURS = 1.0

SAMPLES = int(
    DURATION_HOURS * 3600 / DT_SECONDS
) + 1

CURRENT_A = 50.0

CURRENT_NOISE_STD_A = 0.10
CURRENT_SENSOR_BIAS_A = 0.20

RANDOM_SEED = 20261030

SOC_INITIAL = np.full(
    CELL_COUNT,
    0.90
)

SOC_IMBALANCED = SOC_INITIAL.copy()
SOC_IMBALANCED[7] = 0.80

CAPACITIES = np.full(
    CELL_COUNT,
    CAPACITY_AH
)

CAPACITIES[7] = 80.0


# ============================================================
# 2. COULOMB COUNTING FUNCTION
# ============================================================

def coulomb_counting(
    measured_current,
    initial_soc,
    capacities,
    dt
):

    soc = np.zeros(
        (len(measured_current), CELL_COUNT)
    )

    soc[0] = initial_soc

    for k in range(1, len(measured_current)):

        delta_soc = (
            measured_current[k - 1]
            * dt
            / (3600.0 * capacities)
        )

        soc[k] = soc[k - 1] - delta_soc

        soc[k] = np.clip(
            soc[k],
            0.0,
            1.0
        )

    return soc


# ============================================================
# 3. SIMULATION
# ============================================================

rng = np.random.default_rng(
    RANDOM_SEED
)

time_seconds = np.arange(
    SAMPLES
) * DT_SECONDS

time_hours = (
    time_seconds / 3600.0
)

true_current = np.full(
    SAMPLES,
    CURRENT_A
)

current_noise = rng.normal(
    0,
    CURRENT_NOISE_STD_A,
    SAMPLES
)

measured_current_healthy = (
    true_current + current_noise
)

measured_current_biased = (
    true_current
    + current_noise
    + CURRENT_SENSOR_BIAS_A
)


# ============================================================
# 4. GENERATE GROUND-TRUTH SOC
# ============================================================

def generate_true_soc(
    initial_soc,
    capacities
):

    return coulomb_counting(
        true_current,
        initial_soc,
        capacities,
        DT_SECONDS
    )


true_soc_healthy = generate_true_soc(
    SOC_INITIAL,
    np.full(CELL_COUNT, CAPACITY_AH)
)

true_soc_imbalanced = generate_true_soc(
    SOC_IMBALANCED,
    np.full(CELL_COUNT, CAPACITY_AH)
)

true_soc_weak_cell = generate_true_soc(
    SOC_INITIAL,
    CAPACITIES
)


# ============================================================
# 5. ESTIMATOR SCENARIO A: HEALTHY PACK
# ============================================================

estimated_soc_healthy = coulomb_counting(
    measured_current_healthy,
    SOC_INITIAL,
    np.full(CELL_COUNT, CAPACITY_AH),
    DT_SECONDS
)


# ============================================================
# 6. ESTIMATOR SCENARIO B: INITIAL SOC IMBALANCE
# ============================================================

estimated_soc_imbalanced = coulomb_counting(
    measured_current_healthy,
    SOC_IMBALANCED,
    np.full(CELL_COUNT, CAPACITY_AH),
    DT_SECONDS
)


# ============================================================
# 7. ESTIMATOR SCENARIO C: CURRENT SENSOR BIAS
# ============================================================

estimated_soc_biased_current = coulomb_counting(
    measured_current_biased,
    SOC_INITIAL,
    np.full(CELL_COUNT, CAPACITY_AH),
    DT_SECONDS
)


# ============================================================
# 8. ESTIMATOR SCENARIO D: WEAK CELL CAPACITY
# ============================================================

estimated_soc_weak_cell = coulomb_counting(
    measured_current_healthy,
    SOC_INITIAL,
    CAPACITIES,
    DT_SECONDS
)


# ============================================================
# 9. CALCULATE ESTIMATION ERRORS
# ============================================================

def calculate_metrics(
    estimated,
    actual
):

    error = estimated - actual

    return {
        "RMSE_percent": float(
            np.sqrt(np.mean(error ** 2)) * 100
        ),

        "MAE_percent": float(
            np.mean(np.abs(error)) * 100
        ),

        "Maximum_absolute_error_percent": float(
            np.max(np.abs(error)) * 100
        )
    }


metrics = {

    "Healthy": calculate_metrics(
        estimated_soc_healthy,
        true_soc_healthy
    ),

    "SOC_imbalance": calculate_metrics(
        estimated_soc_imbalanced,
        true_soc_imbalanced
    ),

    "Current_sensor_bias": calculate_metrics(
        estimated_soc_biased_current,
        true_soc_healthy
    ),

    "Weak_cell_capacity": calculate_metrics(
        estimated_soc_weak_cell,
        true_soc_weak_cell
    )
}


# ============================================================
# 10. SAVE CELL-LEVEL RESULTS
# ============================================================

records = []

scenario_data = {

    "Healthy": (
        estimated_soc_healthy,
        true_soc_healthy
    ),

    "SOC_imbalance": (
        estimated_soc_imbalanced,
        true_soc_imbalanced
    ),

    "Current_sensor_bias": (
        estimated_soc_biased_current,
        true_soc_healthy
    ),

    "Weak_cell_capacity": (
        estimated_soc_weak_cell,
        true_soc_weak_cell
    )
}

for scenario_name, (estimated, actual) in scenario_data.items():

    for k, t in enumerate(time_hours):

        for cell in range(CELL_COUNT):

            records.append({

                "Scenario": scenario_name,

                "Time_hours": t,

                "Cell": cell + 1,

                "Estimated_SOC_percent":
                    estimated[k, cell] * 100,

                "True_SOC_percent":
                    actual[k, cell] * 100,

                "SOC_error_percent":
                    (
                        estimated[k, cell]
                        - actual[k, cell]
                    ) * 100
            })


results_df = pd.DataFrame(records)

results_df.to_csv(
    METRICS / "lfp_16s_soc_estimation.csv",
    index=False
)


# ============================================================
# 11. SAVE METRICS
# ============================================================

metrics_df = pd.DataFrame([
    {
        "Scenario": name,
        **values
    }
    for name, values in metrics.items()
])

metrics_df.to_csv(
    METRICS / "lfp_16s_soc_metrics.csv",
    index=False
)


# ============================================================
# 12. PLOT SOC ESTIMATION
# ============================================================

fig, axes = plt.subplots(
    2,
    2,
    figsize=(15, 10)
)

plot_scenarios = [
    (
        "Healthy pack",
        estimated_soc_healthy,
        true_soc_healthy
    ),
    (
        "Initial SOC imbalance",
        estimated_soc_imbalanced,
        true_soc_imbalanced
    ),
    (
        "Current sensor bias",
        estimated_soc_biased_current,
        true_soc_healthy
    ),
    (
        "Weak cell capacity",
        estimated_soc_weak_cell,
        true_soc_weak_cell
    )
]

for ax, (
    title,
    estimated,
    actual
) in zip(
    axes.flatten(),
    plot_scenarios
):

    for cell in range(CELL_COUNT):

        ax.plot(
            time_hours,
            estimated[:, cell] * 100,
            linewidth=0.9,
            alpha=0.65
        )

    ax.plot(
        time_hours,
        actual[:, 7] * 100,
        "k--",
        linewidth=2,
        label="Cell 8 ground truth"
    )

    ax.set_title(title)

    ax.set_xlabel("Time (hours)")
    ax.set_ylabel("SOC (%)")

    ax.grid(True)

    ax.set_ylim(0, 100)

    ax.legend(fontsize=8)


plt.suptitle(
    "16S LFP - SOC Estimation Scenarios"
)

plt.tight_layout()

plt.savefig(
    FIGURES / "lfp_16s_soc_estimation.png",
    dpi=180
)

plt.close()


# ============================================================
# 13. PLOT ESTIMATION ERROR
# ============================================================

fig, ax = plt.subplots(
    figsize=(12, 6)
)

for name, (estimated, actual) in scenario_data.items():

    error = (
        estimated[:, 7] - actual[:, 7]
    ) * 100

    ax.plot(
        time_hours,
        error,
        label=name
    )

ax.set_title(
    "Cell 8 SOC Estimation Error"
)

ax.set_xlabel(
    "Time (hours)"
)

ax.set_ylabel(
    "SOC estimation error (%)"
)

ax.grid(True)
ax.legend()

plt.tight_layout()

plt.savefig(
    FIGURES / "lfp_16s_soc_error.png",
    dpi=180
)

plt.close()



# ============================================================
# 14. VALIDATION
# ============================================================

healthy_rmse = metrics["Healthy"]["RMSE_percent"]

bias_rmse = metrics["Current_sensor_bias"]["RMSE_percent"]

# Small tolerance for current measurement noise.
SOC_TOLERANCE = 5e-5

# Check that Cell 8 remains 10 percentage points
# below the other cells in the SOC imbalance scenario.
imbalance_difference = (
    estimated_soc_imbalanced[:, 7]
    - estimated_soc_imbalanced[:, 0]
)

imbalance_correct = np.allclose(
    imbalance_difference,
    -0.10,
    atol=SOC_TOLERANCE
)

# Check that the weak-capacity Cell 8 loses SOC
# faster than a healthy 100 Ah cell.
weak_cell_difference = (
    estimated_soc_weak_cell[-1, 7]
    - estimated_soc_weak_cell[-1, 0]
)

weak_cell_correct = (
    weak_cell_difference < -0.02
)

# Check that the estimator follows ground truth
# within a reasonable noise-related tolerance.
weak_cell_tracking_error = np.max(
    np.abs(
        estimated_soc_weak_cell
        - true_soc_weak_cell
    )
)

weak_cell_tracking_correct = (
    weak_cell_tracking_error <= SOC_TOLERANCE
)

imbalance_tracking_error = np.max(
    np.abs(
        estimated_soc_imbalanced
        - true_soc_imbalanced
    )
)

imbalance_tracking_correct = (
    imbalance_tracking_error <= SOC_TOLERANCE
)

checks = {

    "Healthy SOC estimation accuracy":
        healthy_rmse < 0.5,

    "SOC imbalance correctly represented":
        imbalance_correct,

    "SOC imbalance ground-truth tracking":
        imbalance_tracking_correct,

    "Current sensor bias produces SOC drift":
        bias_rmse > healthy_rmse,

    "Weak cell loses SOC faster":
        weak_cell_correct,

    "Weak cell ground-truth tracking":
        weak_cell_tracking_correct
}



# ============================================================
# 15. REPORT
# ============================================================

print("=" * 70)
print("16S LFP SOC ESTIMATION VALIDATION")
print("=" * 70)

print(
    f"Simulation duration: {DURATION_HOURS:.2f} hours"
)

print(
    f"Discharge current: {CURRENT_A:.2f} A"
)

print(
    f"Current sensor bias: {CURRENT_SENSOR_BIAS_A:.2f} A"
)

print("\nSOC ESTIMATION METRICS")

for name, values in metrics.items():

    print(f"\n{name}")

    for key, value in values.items():

        print(
            f"{key}: {value:.4f}"
        )

print("\nVALIDATION RESULTS")

for name, passed in checks.items():

    print(
        f"{name}: {'PASS' if passed else 'FAIL'}"
    )

print("\nGENERATED FILES")

print(
    METRICS / "lfp_16s_soc_estimation.csv"
)

print(
    METRICS / "lfp_16s_soc_metrics.csv"
)

print(
    FIGURES / "lfp_16s_soc_estimation.png"
)

print(
    FIGURES / "lfp_16s_soc_error.png"
)

print("\nSOC ESTIMATION EXPERIMENT COMPLETE")

if not all(checks.values()):

    raise AssertionError(
        "One or more SOC validation checks failed."
    )
