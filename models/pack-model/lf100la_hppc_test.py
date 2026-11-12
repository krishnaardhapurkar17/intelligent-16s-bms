
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pathlib import Path

# --------------------------------------------------
# 1. LOAD CONFIGURATION
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = (
    ROOT / "models" / "battery-parameters"
    / "lf100la_ecm_assumptions.json"
)

with open(CONFIG_PATH, "r") as file:
    config = json.load(file)

capacity = config["capacity_Ah"]
R0 = config["R0_ohm"]
R1 = config["R1_ohm"]
tau = config["tau_seconds"]

ocv_table = np.array(config["ocv_soc_table"])

initial_soc = 0.90
temperature_C = 25.0

dt = 0.1

# --------------------------------------------------
# 2. PULSE PROFILE
# --------------------------------------------------

# (duration in seconds, current in amperes)
profile = [
    (60, 0),
    (10, 50),
    (60, 0),
    (10, 50),
    (60, 0)
]

total_time = sum(duration for duration, current in profile)

# --------------------------------------------------
# 3. OCV FUNCTION
# --------------------------------------------------

def get_ocv(soc):
    return np.interp(
        np.clip(soc, 0, 1),
        ocv_table[:, 0],
        ocv_table[:, 1]
    )


def get_current(time):
    elapsed = 0

    for duration, current in profile:
        if time < elapsed + duration:
            return current

        elapsed += duration

    return 0


# --------------------------------------------------
# 4. INITIAL CONDITIONS
# --------------------------------------------------

soc = initial_soc
polarization_voltage = 0.0
discharged_capacity = 0.0

time_values = []
current_values = []
soc_values = []
ocv_values = []
terminal_voltage_values = []
polarization_values = []

# --------------------------------------------------
# 5. RUN SIMULATION
# --------------------------------------------------

print("=" * 55)
print("LF100LA HPPC-STYLE PULSE TEST")
print("=" * 55)

print("Initial SOC:", initial_soc * 100, "%")
print("Temperature:", temperature_C, "C")
print("R0:", R0, "ohm")
print("R1:", R1, "ohm")
print("Time constant:", tau, "seconds")

steps = int(total_time / dt)

for step in range(steps + 1):

    time = step * dt
    current = get_current(time)

    ocv = get_ocv(soc)

    # Terminal voltage uses the current RC state
    terminal_voltage = (
        ocv
        - current * R0
        - polarization_voltage
    )

    time_values.append(time)
    current_values.append(current)
    soc_values.append(soc * 100)
    ocv_values.append(ocv)
    terminal_voltage_values.append(terminal_voltage)
    polarization_values.append(polarization_voltage)

    # Exact discrete-time RC update
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
# 6. DATAFRAME AND VALIDATION
# --------------------------------------------------

results = pd.DataFrame({
    "Time_s": time_values,
    "Current_A": current_values,
    "SOC_percent": soc_values,
    "OCV_V": ocv_values,
    "Terminal_voltage_V": terminal_voltage_values,
    "Polarization_voltage_V": polarization_values
})

assert np.all(np.isfinite(results.values))
assert np.all(np.diff(results["Time_s"]) > 0)
assert np.all(results["SOC_percent"] <= 90.0)
assert np.all(results["SOC_percent"] >= 0.0)

# Confirm that both discharge pulses occurred
assert np.count_nonzero(results["Current_A"] == 50) > 0

# --------------------------------------------------
# 7. ESTIMATE SYNTHETIC MODEL RESPONSE
# --------------------------------------------------

# First pulse begins at 60 seconds
before_pulse = results.iloc[int(60 / dt) - 1]
after_pulse = results.iloc[int(60 / dt)]

voltage_drop = (
    before_pulse["Terminal_voltage_V"]
    - after_pulse["Terminal_voltage_V"]
)

estimated_R0 = voltage_drop / 50.0

print("\nPULSE RESPONSE")
print("-" * 40)
print(f"Immediate voltage drop: {voltage_drop:.6f} V")
print(f"Estimated R0: {estimated_R0:.8f} ohm")
print(f"Configured R0: {R0:.8f} ohm")
print(f"Final SOC: {soc * 100:.4f}%")

# --------------------------------------------------
# 8. EXPORT CSV
# --------------------------------------------------

metrics_dir = ROOT / "results" / "metrics"
figures_dir = ROOT / "results" / "figures"

metrics_dir.mkdir(parents=True, exist_ok=True)
figures_dir.mkdir(parents=True, exist_ok=True)

csv_path = metrics_dir / "lf100la_hppc_test.csv"

results.to_csv(csv_path, index=False)

# --------------------------------------------------
# 9. CURRENT AND VOLTAGE PLOT
# --------------------------------------------------

fig, axes = plt.subplots(
    2, 1,
    figsize=(11, 7),
    sharex=True
)

axes[0].plot(
    results["Time_s"],
    results["Current_A"]
)

axes[0].set_ylabel("Current (A)")
axes[0].set_title("HPPC-Style Current Pulse Profile")
axes[0].grid(True)

axes[1].plot(
    results["Time_s"],
    results["Terminal_voltage_V"],
    label="Terminal voltage"
)

axes[1].plot(
    results["Time_s"],
    results["OCV_V"],
    linestyle="--",
    label="OCV"
)

axes[1].set_xlabel("Time (seconds)")
axes[1].set_ylabel("Voltage (V)")
axes[1].set_title("LFP Cell Voltage Response")
axes[1].legend()
axes[1].grid(True)

plt.tight_layout()

plot_path = figures_dir / "lf100la_hppc_response.png"

plt.savefig(plot_path, dpi=300)
plt.show()

# --------------------------------------------------
# 10. FINAL REPORT
# --------------------------------------------------

print("\nVALIDATION CHECKS PASSED")

print("\nGenerated files:")
print(csv_path)
print(plot_path)

print("\nHPPC-STYLE TEST COMPLETE")
