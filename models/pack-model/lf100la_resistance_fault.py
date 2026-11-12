
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pathlib import Path

# --------------------------------------------------
# 1. LOAD BASELINE PARAMETERS
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

config_path = (
    ROOT / "models" / "battery-parameters"
    / "lf100la_ecm_assumptions.json"
)

with open(config_path, "r") as file:
    config = json.load(file)

CAPACITY = config["capacity_Ah"]
R0_HEALTHY = config["R0_ohm"]
R1 = config["R1_ohm"]
TAU = config["tau_seconds"]

INITIAL_SOC = 0.90
DT = 0.1

# Inject 50% increase in ohmic resistance
R0_DEGRADED = R0_HEALTHY * 1.50

# --------------------------------------------------
# 2. CURRENT PROFILE
# --------------------------------------------------

profile = [
    (60, 0),
    (10, 50),
    (60, 0),
    (10, 50),
    (60, 0)
]

total_time = sum(duration for duration, _ in profile)


def get_current(time):
    elapsed = 0

    for duration, current in profile:
        if time < elapsed + duration:
            return current

        elapsed += duration

    return 0


# --------------------------------------------------
# 3. OCV FUNCTION
# --------------------------------------------------

ocv_table = np.array(config["ocv_soc_table"])


def get_ocv(soc):
    return np.interp(
        np.clip(soc, 0, 1),
        ocv_table[:, 0],
        ocv_table[:, 1]
    )


# --------------------------------------------------
# 4. ECM SIMULATION FUNCTION
# --------------------------------------------------

def simulate_cell(R0):

    soc = INITIAL_SOC
    polarization = 0.0
    discharged_capacity = 0.0

    records = []

    steps = int(total_time / DT)

    for step in range(steps + 1):

        time = step * DT
        current = get_current(time)

        ocv = get_ocv(soc)

        terminal_voltage = (
            ocv
            - current * R0
            - polarization
        )

        records.append({
            "Time_s": time,
            "Current_A": current,
            "SOC_percent": soc * 100,
            "OCV_V": ocv,
            "Terminal_voltage_V": terminal_voltage,
            "Polarization_voltage_V": polarization
        })

        decay = np.exp(-DT / TAU)

        polarization = (
            decay * polarization
            + current * R1 * (1 - decay)
        )

        discharged_capacity += current * DT / 3600

        soc = max(
            0,
            INITIAL_SOC - discharged_capacity / CAPACITY
        )

    return pd.DataFrame(records)


# --------------------------------------------------
# 5. SIMULATE HEALTHY AND DEGRADED CELLS
# --------------------------------------------------

healthy = simulate_cell(R0_HEALTHY)
degraded = simulate_cell(R0_DEGRADED)

# --------------------------------------------------
# 6. ESTIMATE INTERNAL RESISTANCE
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

    current = data.loc[
        np.isclose(data["Time_s"], 60.0),
        "Current_A"
    ].iloc[0]

    return (before - after) / current


estimated_healthy = estimate_R0(healthy)
estimated_degraded = estimate_R0(degraded)

growth_percent = (
    (estimated_degraded / estimated_healthy) - 1
) * 100

# Illustrative diagnostic threshold.
# This is not a safety-certified threshold.
DIAGNOSTIC_THRESHOLD_PERCENT = 20.0

if growth_percent >= DIAGNOSTIC_THRESHOLD_PERCENT:
    diagnostic = "RESISTANCE GROWTH DETECTED"
else:
    diagnostic = "NO RESISTANCE GROWTH FLAG"

# --------------------------------------------------
# 7. VALIDATION
# --------------------------------------------------

assert np.all(np.isfinite(healthy.values))
assert np.all(np.isfinite(degraded.values))

assert estimated_healthy > 0
assert estimated_degraded > estimated_healthy

assert np.allclose(
    healthy["SOC_percent"],
    degraded["SOC_percent"]
)

# --------------------------------------------------
# 8. EXPORT DATA
# --------------------------------------------------

metrics_dir = ROOT / "results" / "metrics"
figures_dir = ROOT / "results" / "figures"

metrics_dir.mkdir(parents=True, exist_ok=True)
figures_dir.mkdir(parents=True, exist_ok=True)

comparison = pd.DataFrame({
    "Time_s": healthy["Time_s"],
    "Current_A": healthy["Current_A"],
    "Healthy_voltage_V": healthy["Terminal_voltage_V"],
    "Degraded_voltage_V": degraded["Terminal_voltage_V"],
    "Healthy_SOC_percent": healthy["SOC_percent"],
    "Degraded_SOC_percent": degraded["SOC_percent"]
})

csv_path = metrics_dir / "resistance_fault_comparison.csv"
comparison.to_csv(csv_path, index=False)

# --------------------------------------------------
# 9. PLOT VOLTAGE COMPARISON
# --------------------------------------------------

plt.figure(figsize=(11, 6))

plt.plot(
    healthy["Time_s"],
    healthy["Terminal_voltage_V"],
    label="Healthy cell"
)

plt.plot(
    degraded["Time_s"],
    degraded["Terminal_voltage_V"],
    label="Degraded cell"
)

plt.xlabel("Time (seconds)")
plt.ylabel("Terminal voltage (V)")
plt.title("LFP Cell - Internal Resistance Growth Simulation")
plt.grid(True)
plt.legend()
plt.tight_layout()

plot_path = figures_dir / "resistance_fault_comparison.png"

plt.savefig(plot_path, dpi=300)
plt.show()

# --------------------------------------------------
# 10. DIAGNOSTIC REPORT
# --------------------------------------------------

print("=" * 55)
print("INTERNAL RESISTANCE FAULT DIAGNOSTICS")
print("=" * 55)

print(f"Healthy configured R0: {R0_HEALTHY:.8f} ohm")
print(f"Degraded configured R0: {R0_DEGRADED:.8f} ohm")

print(f"\nEstimated healthy R0: {estimated_healthy:.8f} ohm")
print(f"Estimated degraded R0: {estimated_degraded:.8f} ohm")

print(f"\nResistance growth: {growth_percent:.2f}%")
print(f"Diagnostic threshold: {DIAGNOSTIC_THRESHOLD_PERCENT:.2f}%")

print("\nDIAGNOSTIC RESULT:")
print(diagnostic)

print("\nVALIDATION CHECKS PASSED")

print("\nGenerated files:")
print(csv_path)
print(plot_path)
