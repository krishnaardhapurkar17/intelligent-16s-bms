
import pybamm
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# --------------------------------------------------
# 1. PROJECT CONFIGURATION
# --------------------------------------------------

CELL_CAPACITY_AH = 2.3
DISCHARGE_CURRENT_A = 2.3
INITIAL_SOC = 1.0
AMBIENT_TEMPERATURE_K = 298.15
SIMULATION_TIME_S = 3700
SAMPLE_INTERVAL_S = 10

OUTPUT_DIR = Path("results")
FIGURE_DIR = OUTPUT_DIR / "figures"
METRICS_DIR = OUTPUT_DIR / "metrics"

FIGURE_DIR.mkdir(parents=True, exist_ok=True)
METRICS_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------
# 2. LOAD LFP REFERENCE PARAMETERS
# --------------------------------------------------

print("=" * 55)
print("SINGLE CELL LFP DISCHARGE SIMULATION")
print("=" * 55)

parameters = pybamm.ParameterValues("Prada2013")

parameters.update({
    "Current function [A]": DISCHARGE_CURRENT_A,
    "Ambient temperature [K]": AMBIENT_TEMPERATURE_K,
    "Initial temperature [K]": AMBIENT_TEMPERATURE_K,
})

print("\nChemistry: LFP")
print("Parameter set: Prada2013")
print("Model: SPMe")
print(f"Capacity: {CELL_CAPACITY_AH} Ah")
print(f"Discharge current: {DISCHARGE_CURRENT_A} A")
print(f"Discharge rate: {DISCHARGE_CURRENT_A / CELL_CAPACITY_AH:.2f} C")
print(f"Initial SOC: {INITIAL_SOC * 100:.0f}%")
print("Temperature: 25 C")

# --------------------------------------------------
# 3. CREATE ELECTROCHEMICAL MODEL
# --------------------------------------------------

model = pybamm.lithium_ion.SPMe()

simulation = pybamm.Simulation(
    model,
    parameter_values=parameters
)

# --------------------------------------------------
# 4. SOLVE
# --------------------------------------------------

print("\nRunning simulation...")

time_points = np.arange(
    0,
    SIMULATION_TIME_S + SAMPLE_INTERVAL_S,
    SAMPLE_INTERVAL_S
)

solution = simulation.solve(
    t_eval=time_points,
    initial_soc=INITIAL_SOC
)

print("\nSimulation completed.")
print("Termination:", solution.termination)

# --------------------------------------------------
# 5. EXTRACT RESULTS
# --------------------------------------------------

time_seconds = solution["Time [s]"].entries
voltage = solution["Terminal voltage [V]"].entries
capacity = solution["Discharge capacity [A.h]"].entries

results = pd.DataFrame({
    "Time_s": time_seconds,
    "Time_min": time_seconds / 60,
    "Terminal_voltage_V": voltage,
    "Discharge_capacity_Ah": capacity,
})

csv_path = METRICS_DIR / "single_cell_discharge.csv"
results.to_csv(csv_path, index=False)

# --------------------------------------------------
# 6. BASIC VALIDATION
# --------------------------------------------------

assert len(results) > 1, "Simulation returned insufficient data."
assert np.all(np.isfinite(voltage)), "Non-finite voltage values detected."
assert np.all(np.isfinite(capacity)), "Non-finite capacity values detected."
assert np.all(np.diff(time_seconds) > 0), "Time is not strictly increasing."

print("\nSIMULATION RESULTS")
print("-" * 40)
print(f"Initial voltage: {voltage[0]:.4f} V")
print(f"Final voltage: {voltage[-1]:.4f} V")
print(f"Simulated discharge capacity: {capacity[-1]:.4f} Ah")
print(f"Simulation duration: {time_seconds[-1]:.2f} seconds")

# --------------------------------------------------
# 7. PLOT VOLTAGE PROFILE
# --------------------------------------------------

plt.figure(figsize=(10, 5))
plt.plot(time_seconds / 60, voltage, linewidth=2)

plt.xlabel("Time (minutes)")
plt.ylabel("Terminal Voltage (V)")
plt.title("LFP Single Cell - 1C Discharge Profile")
plt.grid(True)
plt.tight_layout()

plot_path = FIGURE_DIR / "single_cell_voltage.png"
plt.savefig(plot_path, dpi=300)
plt.show()

print("\nFILES GENERATED")
print("CSV:", csv_path)
print("Plot:", plot_path)

print("\nSINGLE CELL SIMULATION COMPLETE")
