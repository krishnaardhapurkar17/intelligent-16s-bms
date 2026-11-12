
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pathlib import Path

# --------------------------------------------------
# 1. LOAD MODEL CONFIGURATION
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = (
    ROOT / "models" / "battery-parameters"
    / "lf100la_ecm_assumptions.json"
)

with open(CONFIG_PATH, "r") as file:
    config = json.load(file)

capacity = config["capacity_Ah"]
current = config["discharge_current_A"]
initial_soc = config["initial_soc"]
cutoff_voltage = config["cutoff_voltage_V"]

R0 = config["R0_ohm"]
R1 = config["R1_ohm"]
tau = config["tau_seconds"]

dt = 1.0
max_time = 8000

ocv_table = np.array(config["ocv_soc_table"])

# --------------------------------------------------
# 2. OCV FUNCTION
# --------------------------------------------------

def get_ocv(soc):
    soc = np.clip(soc, 0.0, 1.0)

    return np.interp(
        soc,
        ocv_table[:, 0],
        ocv_table[:, 1]
    )


# --------------------------------------------------
# 3. INITIAL CONDITIONS
# --------------------------------------------------

soc = initial_soc
polarization_voltage = 0.0

time_values = []
soc_values = []
voltage_values = []
ocv_values = []
polarization_values = []
capacity_values = []
current_values = []

# RC time constant:
# tau = R1 * C1

C1 = tau / R1

print("=" * 55)
print("LF100LA PROVISIONAL ECM SIMULATION")
print("=" * 55)

print(f"Capacity: {capacity:.1f} Ah")
print(f"Discharge current: {current:.1f} A")
print(f"Discharge rate: {current / capacity:.2f} C")
print(f"R0: {R0:.6f} ohm")
print(f"R1: {R1:.6f} ohm")
print(f"C1: {C1:.1f} F")
print(f"RC time constant: {tau:.1f} seconds")


# --------------------------------------------------
# 4. SIMULATION LOOP
# --------------------------------------------------

discharged_capacity = 0.0

min_operating_soc = 0.10

for step in range(max_time + 1):

    time = step * dt

    # Calculate OCV from current SOC
    ocv = get_ocv(soc)

    # Calculate terminal voltage using current
    # polarization state BEFORE updating the RC branch
    terminal_voltage = (
        ocv
        - current * R0
        - polarization_voltage
    )

    # Save current state
    time_values.append(time)
    soc_values.append(soc)
    voltage_values.append(terminal_voltage)
    ocv_values.append(ocv)
    polarization_values.append(polarization_voltage)
    capacity_values.append(discharged_capacity)
    current_values.append(current)

    # Stop at absolute voltage cutoff
    if terminal_voltage <= cutoff_voltage:
        print("\nDischarge stopped: voltage cutoff reached.")
        break
            # Prevent the next integration step from crossing
    # the minimum operating SOC boundary.
    remaining_capacity = (
        (soc - min_operating_soc) * capacity
    )

    if remaining_capacity <= 0:
        print("\nDischarge stopped: minimum operating SOC reached.")
        break

    if current * dt / 3600 >= remaining_capacity:
        discharged_capacity += remaining_capacity
        soc = min_operating_soc

        time_values.append(time + remaining_capacity * 3600 / current)
        soc_values.append(soc)
        voltage_values.append(
            get_ocv(soc) - current * R0 - polarization_voltage
        )
        ocv_values.append(get_ocv(soc))
        polarization_values.append(polarization_voltage)
        capacity_values.append(discharged_capacity)
        current_values.append(current)

        print("\nDischarge stopped: minimum operating SOC reached.")
        break


    # Update RC polarization for next time step
    decay = np.exp(-dt / tau)

    polarization_voltage = (
        decay * polarization_voltage
        + current * R1 * (1 - decay)
    )

    # Coulomb counting
    discharged_capacity += current * dt / 3600

    soc = max(
        0.0,
        initial_soc - discharged_capacity / capacity
    )


# --------------------------------------------------
# 5. CREATE DATAFRAME
# --------------------------------------------------

results = pd.DataFrame({
    "Time_s": time_values,
    "SOC_percent": np.array(soc_values) * 100,
    "Current_A": current_values,
    "OCV_V": ocv_values,
    "Polarization_voltage_V": polarization_values,
    "Terminal_voltage_V": voltage_values,
    "Discharged_capacity_Ah": capacity_values
})

# --------------------------------------------------
# 6. VALIDATION
# --------------------------------------------------

assert len(results) > 1
assert np.all(np.isfinite(results.values))
assert np.all(np.diff(results["Time_s"]) > 0)
assert np.all(np.diff(results["SOC_percent"]) <= 0)
assert np.all(np.diff(results["Discharged_capacity_Ah"]) >= 0)

# --------------------------------------------------
# 7. EXPORT RESULTS
# --------------------------------------------------

metrics_dir = ROOT / "results" / "metrics"
figures_dir = ROOT / "results" / "figures"

metrics_dir.mkdir(parents=True, exist_ok=True)
figures_dir.mkdir(parents=True, exist_ok=True)

csv_path = metrics_dir / "lf100la_ecm_discharge.csv"

results.to_csv(csv_path, index=False)

# --------------------------------------------------
# 8. PLOT VOLTAGE
# --------------------------------------------------

plt.figure(figsize=(10, 5))

plt.plot(
    results["Time_s"] / 60,
    results["Terminal_voltage_V"],
    label="Terminal voltage"
)

plt.plot(
    results["Time_s"] / 60,
    results["OCV_V"],
    linestyle="--",
    label="Open-circuit voltage"
)

plt.axhline(
    cutoff_voltage,
    linestyle=":",
    label="Discharge cutoff"
)

plt.xlabel("Time (minutes)")
plt.ylabel("Voltage (V)")
plt.title("100 Ah LFP - Provisional ECM Discharge")
plt.grid(True)
plt.legend()
plt.tight_layout()

plt.savefig(
    figures_dir / "lf100la_ecm_voltage.png",
    dpi=300
)

plt.show()

# --------------------------------------------------
# 9. PLOT SOC
# --------------------------------------------------

plt.figure(figsize=(10, 5))

plt.plot(
    results["Time_s"] / 60,
    results["SOC_percent"]
)

plt.xlabel("Time (minutes)")
plt.ylabel("SOC (%)")
plt.title("100 Ah LFP - SOC During Discharge")
plt.grid(True)
plt.tight_layout()

plt.savefig(
    figures_dir / "lf100la_ecm_soc.png",
    dpi=300
)

plt.show()

# --------------------------------------------------
# 10. FINAL REPORT
# --------------------------------------------------

print("\nSIMULATION RESULTS")
print("-" * 40)

print(f"Initial voltage: {results['Terminal_voltage_V'].iloc[0]:.4f} V")
print(f"Final voltage: {results['Terminal_voltage_V'].iloc[-1]:.4f} V")
print(f"Final SOC: {results['SOC_percent'].iloc[-1]:.2f}%")
print(f"Discharged capacity: {results['Discharged_capacity_Ah'].iloc[-1]:.4f} Ah")
print(f"Duration: {results['Time_s'].iloc[-1] / 60:.2f} minutes")
print(f"Minimum operating SOC: {min_operating_soc * 100:.1f}%")

print("\nVALIDATION CHECKS PASSED")

print("\nGenerated files:")
print(csv_path)
print(figures_dir / "lf100la_ecm_voltage.png")
print(figures_dir / "lf100la_ecm_soc.png")
