
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pathlib import Path

# --------------------------------------------------
# 1. CONFIGURATION
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = (
    ROOT / "models" / "battery-parameters"
    / "lf100la_ecm_assumptions.json"
)

with open(CONFIG_PATH, "r") as file:
    config = json.load(file)

RATED_CAPACITY = 100.0

R1 = config["R1_ohm"]
TAU = config["tau_seconds"]

R0_HEALTHY = config["R0_ohm"]
R0_DEGRADED = R0_HEALTHY * 1.50

CAPACITY_HEALTHY = 100.0
CAPACITY_DEGRADED = 80.0

INITIAL_SOC = 0.90
MIN_SOC = 0.10

CURRENT = 50.0
DT = 0.1

OCV_TABLE = np.array(config["ocv_soc_table"])

# Test profile:
# (duration in seconds, current in amperes)
# First pulse allows R0 estimation.
# The final discharge measures capacity over the SOC window.

PROFILE = [
    (60.0, 0.0),
    (10.0, CURRENT),
    (60.0, 0.0),
    (None, CURRENT)
]

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
# 3. CURRENT PROFILE
# --------------------------------------------------

def get_current(time):

    elapsed = 0.0

    for duration, current in PROFILE:

        if duration is None:
            return current

        if time < elapsed + duration:
            return current

        elapsed += duration

    return 0.0


# --------------------------------------------------
# 4. SINGLE CELL SIMULATION
# --------------------------------------------------

def simulate_cell(actual_capacity, R0, name):

    soc = INITIAL_SOC
    polarization = 0.0
    discharged_ah = 0.0
    time = 0.0

    records = []

    while True:

        current = get_current(time)

        ocv = get_ocv(soc)

        terminal_voltage = (
            ocv
            - current * R0
            - polarization
        )

        records.append({
            "Time_s": time,
            "Time_min": time / 60.0,
            "Cell": name,
            "Current_A": current,
            "SOC_percent": soc * 100.0,
            "OCV_V": ocv,
            "Terminal_voltage_V": terminal_voltage,
            "Polarization_voltage_V": polarization,
            "Discharged_capacity_Ah": discharged_ah
        })

        if soc <= MIN_SOC:
            break

        remaining_capacity = (
            (soc - MIN_SOC) * actual_capacity
        )

        step_time = min(
            DT,
            remaining_capacity * 3600.0 / current
            if current > 0 else DT
        )

        # Update polarization branch
        decay = np.exp(-step_time / TAU)

        polarization = (
            decay * polarization
            + current * R1 * (1.0 - decay)
        )

        # Update discharged capacity
        capacity_step = current * step_time / 3600.0

        discharged_ah += capacity_step

        # Update SOC
        soc = max(
            MIN_SOC,
            INITIAL_SOC - discharged_ah / actual_capacity
        )

        time += step_time

    return pd.DataFrame(records)


# --------------------------------------------------
# 5. SIMULATE BOTH CELLS
# --------------------------------------------------

print("=" * 60)
print("COMBINED LFP BATTERY DEGRADATION EXPERIMENT")
print("=" * 60)

healthy = simulate_cell(
    CAPACITY_HEALTHY,
    R0_HEALTHY,
    "Healthy"
)

degraded = simulate_cell(
    CAPACITY_DEGRADED,
    R0_DEGRADED,
    "Combined_Degradation"
)

# --------------------------------------------------
# 6. ESTIMATE CAPACITY SOH
# --------------------------------------------------

def estimate_capacity_soh(data):

    discharged_ah = (
        data["Discharged_capacity_Ah"].iloc[-1]
    )

    soc_change = (
        data["SOC_percent"].iloc[0]
        - data["SOC_percent"].iloc[-1]
    ) / 100.0

    estimated_capacity = discharged_ah / soc_change

    soh = estimated_capacity / RATED_CAPACITY * 100.0

    return estimated_capacity, soh


healthy_capacity, healthy_soh = estimate_capacity_soh(healthy)

degraded_capacity, degraded_soh = estimate_capacity_soh(degraded)

# --------------------------------------------------
# 7. ESTIMATE R0 FROM FIRST PULSE
# --------------------------------------------------

def estimate_R0(data):

    before = data.loc[
        np.isclose(data["Time_s"], 59.9),
        "Terminal_voltage_V"
    ].iloc[0]

    after = data.loc[
        np.isclose(data["Time_s"], 60.0),
        "Terminal_voltage_V"
    ].iloc[0]

    pulse_current = data.loc[
        np.isclose(data["Time_s"], 60.0),
        "Current_A"
    ].iloc[0]

    return (before - after) / pulse_current


healthy_R0 = estimate_R0(healthy)
degraded_R0 = estimate_R0(degraded)

resistance_growth = (
    degraded_R0 / healthy_R0 - 1.0
) * 100.0

capacity_loss = 100.0 - degraded_soh

# --------------------------------------------------
# 8. DIAGNOSTIC DECISIONS
# --------------------------------------------------

CAPACITY_LOSS_THRESHOLD = 10.0
RESISTANCE_GROWTH_THRESHOLD = 20.0

capacity_fault = (
    capacity_loss >= CAPACITY_LOSS_THRESHOLD
)

resistance_fault = (
    resistance_growth >= RESISTANCE_GROWTH_THRESHOLD
)

if capacity_fault and resistance_fault:
    diagnostic = "MULTIPLE DEGRADATION MECHANISMS DETECTED"
elif capacity_fault:
    diagnostic = "CAPACITY DEGRADATION DETECTED"
elif resistance_fault:
    diagnostic = "RESISTANCE GROWTH DETECTED"
else:
    diagnostic = "NO DEGRADATION FLAGGED"

# --------------------------------------------------
# 9. VALIDATION
# --------------------------------------------------

assert np.isclose(healthy_soh, 100.0, atol=0.01)
assert np.isclose(degraded_soh, 80.0, atol=0.01)

assert np.isclose(healthy_R0, R0_HEALTHY, atol=1e-8)
assert np.isclose(degraded_R0, R0_DEGRADED, atol=1e-8)

assert capacity_fault
assert resistance_fault

assert np.all(np.isfinite(healthy.select_dtypes("number")))
assert np.all(np.isfinite(degraded.select_dtypes("number")))

# --------------------------------------------------
# 10. EXPORT DATA
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
    metrics_dir / "combined_degradation_comparison.csv"
)

comparison.to_csv(csv_path, index=False)

# --------------------------------------------------
# 11. PLOT VOLTAGE
# --------------------------------------------------

plt.figure(figsize=(11, 6))

plt.plot(
    healthy["Time_min"],
    healthy["Terminal_voltage_V"],
    label="Healthy cell"
)

plt.plot(
    degraded["Time_min"],
    degraded["Terminal_voltage_V"],
    label="Combined degradation"
)

plt.xlabel("Time (minutes)")
plt.ylabel("Terminal voltage (V)")
plt.title("LFP Combined Degradation - Voltage Comparison")
plt.grid(True)
plt.legend()
plt.tight_layout()

voltage_path = figures_dir / "combined_degradation_voltage.png"

plt.savefig(voltage_path, dpi=300)
plt.show()

# --------------------------------------------------
# 12. PLOT SOC
# --------------------------------------------------

plt.figure(figsize=(11, 6))

plt.plot(
    healthy["Time_min"],
    healthy["SOC_percent"],
    label="Healthy cell"
)

plt.plot(
    degraded["Time_min"],
    degraded["SOC_percent"],
    label="Combined degradation"
)

plt.xlabel("Time (minutes)")
plt.ylabel("SOC (%)")
plt.title("LFP Combined Degradation - SOC Comparison")
plt.grid(True)
plt.legend()
plt.tight_layout()

soc_path = figures_dir / "combined_degradation_soc.png"

plt.savefig(soc_path, dpi=300)
plt.show()

# --------------------------------------------------
# 13. DIAGNOSTIC REPORT
# --------------------------------------------------

print("\nCAPACITY DIAGNOSTICS")
print("-" * 45)

print(f"Healthy capacity SOH: {healthy_soh:.2f}%")
print(f"Degraded capacity SOH: {degraded_soh:.2f}%")
print(f"Capacity loss: {capacity_loss:.2f}%")

print("\nRESISTANCE DIAGNOSTICS")
print("-" * 45)

print(f"Healthy R0: {healthy_R0:.8f} ohm")
print(f"Degraded R0: {degraded_R0:.8f} ohm")
print(f"Resistance growth: {resistance_growth:.2f}%")

print("\nFINAL DIAGNOSTIC")
print("-" * 45)

print(diagnostic)

print("\nVALIDATION CHECKS PASSED")

print("\nGENERATED FILES")
print(csv_path)
print(voltage_path)
print(soc_path)

print("\nCOMBINED DEGRADATION EXPERIMENT COMPLETE")
