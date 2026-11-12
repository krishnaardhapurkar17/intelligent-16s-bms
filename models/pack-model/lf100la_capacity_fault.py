
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pathlib import Path

# --------------------------------------------------
# 1. PROJECT CONFIGURATION
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

RATED_CAPACITY_AH = 100.0

HEALTHY_ACTUAL_CAPACITY_AH = 100.0
DEGRADED_ACTUAL_CAPACITY_AH = 80.0

INITIAL_SOC = 0.90
MINIMUM_SOC = 0.10

DISCHARGE_CURRENT_A = 50.0
R0 = 0.0005
R1 = 0.0002
TAU = 30.0

DT = 1.0
TEMPERATURE_C = 25.0

# OCV table from our provisional ECM assumptions
import json

CONFIG_PATH = (
    ROOT / "models" / "battery-parameters"
    / "lf100la_ecm_assumptions.json"
)

with open(CONFIG_PATH, "r") as file:
    config = json.load(file)

OCV_TABLE = np.array(config["ocv_soc_table"])


# --------------------------------------------------
# 2. OCV FUNCTION
# --------------------------------------------------

def get_ocv(soc):

    return np.interp(
        np.clip(soc, 0.0, 1.0),
        OCV_TABLE[:, 0],
        OCV_TABLE[:, 1]
    )


# --------------------------------------------------
# 3. SINGLE CELL DISCHARGE MODEL
# --------------------------------------------------

def simulate_cell(actual_capacity_ah, cell_name):

    soc = INITIAL_SOC
    polarization = 0.0

    discharged_capacity = 0.0
    elapsed_time = 0.0

    records = []

    while soc > MINIMUM_SOC:

        current = DISCHARGE_CURRENT_A

        ocv = get_ocv(soc)

        terminal_voltage = (
            ocv
            - current * R0
            - polarization
        )

        records.append({
            "Time_s": elapsed_time,
            "Time_min": elapsed_time / 60.0,
            "Cell": cell_name,
            "Current_A": current,
            "SOC_percent": soc * 100.0,
            "OCV_V": ocv,
            "Terminal_voltage_V": terminal_voltage,
            "Discharged_capacity_Ah": discharged_capacity,
            "Polarization_voltage_V": polarization,
            "Temperature_C": TEMPERATURE_C
        })

        # Calculate exact remaining time to SOC boundary
        remaining_capacity = (
            (soc - MINIMUM_SOC) * actual_capacity_ah
        )

        step_time = min(
            DT,
            remaining_capacity * 3600.0 / current
        )

        # Update RC polarization
        decay = np.exp(-step_time / TAU)

        polarization = (
            decay * polarization
            + current * R1 * (1.0 - decay)
        )

        # Coulomb counting
        capacity_step = current * step_time / 3600.0

        discharged_capacity += capacity_step

        soc = max(
            MINIMUM_SOC,
            INITIAL_SOC - discharged_capacity / actual_capacity_ah
        )

        elapsed_time += step_time

    # Record the exact final operating point
    ocv = get_ocv(soc)

    terminal_voltage = (
        ocv
        - DISCHARGE_CURRENT_A * R0
        - polarization
    )

    records.append({
        "Time_s": elapsed_time,
        "Time_min": elapsed_time / 60.0,
        "Cell": cell_name,
        "Current_A": DISCHARGE_CURRENT_A,
        "SOC_percent": soc * 100.0,
        "OCV_V": ocv,
        "Terminal_voltage_V": terminal_voltage,
        "Discharged_capacity_Ah": discharged_capacity,
        "Polarization_voltage_V": polarization,
        "Temperature_C": TEMPERATURE_C
    })

    return pd.DataFrame(records)


# --------------------------------------------------
# 4. RUN HEALTHY AND DEGRADED SIMULATIONS
# --------------------------------------------------

print("=" * 60)
print("LFP CAPACITY DEGRADATION SIMULATION")
print("=" * 60)

healthy = simulate_cell(
    HEALTHY_ACTUAL_CAPACITY_AH,
    "Healthy"
)

degraded = simulate_cell(
    DEGRADED_ACTUAL_CAPACITY_AH,
    "Capacity_Degraded"
)

# --------------------------------------------------
# 5. ESTIMATE CAPACITY AND SOH
# --------------------------------------------------

def estimate_capacity(data):

    discharged_ah = (
        data["Discharged_capacity_Ah"].iloc[-1]
    )

    soc_change = (
        data["SOC_percent"].iloc[0]
        - data["SOC_percent"].iloc[-1]
    ) / 100.0

    if soc_change <= 0:
        raise ValueError("Invalid SOC change.")

    return discharged_ah / soc_change


healthy_estimated_capacity = estimate_capacity(healthy)
degraded_estimated_capacity = estimate_capacity(degraded)

healthy_soh = (
    healthy_estimated_capacity / RATED_CAPACITY_AH
) * 100.0

degraded_soh = (
    degraded_estimated_capacity / RATED_CAPACITY_AH
) * 100.0

# --------------------------------------------------
# 6. VALIDATION
# --------------------------------------------------

assert np.isclose(healthy["SOC_percent"].iloc[-1], 10.0)
assert np.isclose(degraded["SOC_percent"].iloc[-1], 10.0)

assert np.isclose(
    healthy_estimated_capacity,
    HEALTHY_ACTUAL_CAPACITY_AH,
    atol=1e-6
)

assert np.isclose(
    degraded_estimated_capacity,
    DEGRADED_ACTUAL_CAPACITY_AH,
    atol=1e-6
)

assert degraded_soh < healthy_soh

assert np.all(np.isfinite(healthy.select_dtypes("number")))
assert np.all(np.isfinite(degraded.select_dtypes("number")))

# --------------------------------------------------
# 7. EXPORT SIMULATION DATA
# --------------------------------------------------

metrics_dir = ROOT / "results" / "metrics"
figures_dir = ROOT / "results" / "figures"

metrics_dir.mkdir(parents=True, exist_ok=True)
figures_dir.mkdir(parents=True, exist_ok=True)

comparison = pd.concat(
    [healthy, degraded],
    ignore_index=True
)

csv_path = (
    metrics_dir / "capacity_degradation_comparison.csv"
)

comparison.to_csv(csv_path, index=False)

# --------------------------------------------------
# 8. PLOT SOC COMPARISON
# --------------------------------------------------

plt.figure(figsize=(10, 5))

plt.plot(
    healthy["Time_min"],
    healthy["SOC_percent"],
    label="Healthy cell (100 Ah)"
)

plt.plot(
    degraded["Time_min"],
    degraded["SOC_percent"],
    label="Capacity-degraded cell (80 Ah)"
)

plt.xlabel("Time (minutes)")
plt.ylabel("SOC (%)")
plt.title("LFP Capacity Degradation - SOC Comparison")
plt.grid(True)
plt.legend()
plt.tight_layout()

soc_plot = figures_dir / "capacity_degradation_soc.png"

plt.savefig(soc_plot, dpi=300)
plt.show()

# --------------------------------------------------
# 9. PLOT VOLTAGE COMPARISON
# --------------------------------------------------

plt.figure(figsize=(10, 5))

plt.plot(
    healthy["Time_min"],
    healthy["Terminal_voltage_V"],
    label="Healthy cell"
)

plt.plot(
    degraded["Time_min"],
    degraded["Terminal_voltage_V"],
    label="Capacity-degraded cell"
)

plt.xlabel("Time (minutes)")
plt.ylabel("Terminal voltage (V)")
plt.title("LFP Capacity Degradation - Voltage Comparison")
plt.grid(True)
plt.legend()
plt.tight_layout()

voltage_plot = (
    figures_dir / "capacity_degradation_voltage.png"
)

plt.savefig(voltage_plot, dpi=300)
plt.show()

# --------------------------------------------------
# 10. DIAGNOSTIC REPORT
# --------------------------------------------------

print("\nCAPACITY ESTIMATION RESULTS")
print("-" * 50)

print(
    f"Healthy estimated capacity: "
    f"{healthy_estimated_capacity:.4f} Ah"
)

print(
    f"Degraded estimated capacity: "
    f"{degraded_estimated_capacity:.4f} Ah"
)

print(f"\nHealthy capacity SOH: {healthy_soh:.2f}%")
print(f"Degraded capacity SOH: {degraded_soh:.2f}%")

print("\nDISCHARGE DURATION")
print("-" * 50)

print(
    f"Healthy: "
    f"{healthy['Time_min'].iloc[-1]:.2f} minutes"
)

print(
    f"Degraded: "
    f"{degraded['Time_min'].iloc[-1]:.2f} minutes"
)

print("\nVALIDATION CHECKS PASSED")

print("\nGenerated files:")
print(csv_path)
print(soc_plot)
print(voltage_plot)

print("\nCAPACITY DEGRADATION SIMULATION COMPLETE")
