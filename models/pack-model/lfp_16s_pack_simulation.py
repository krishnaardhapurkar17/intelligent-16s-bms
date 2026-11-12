
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pathlib import Path
from cell_configuration import PackConfiguration

# --------------------------------------------------
# 1. PROJECT CONFIGURATION
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = (
    ROOT / "models" / "battery-parameters"
    / "lf100la_ecm_assumptions.json"
)

with open(CONFIG_PATH, "r") as file:
    config = json.load(file)

MIN_SOC = 0.10

CURRENT_A = 50.0

R0 = config["R0_ohm"]
R1 = config["R1_ohm"]
TAU = config["tau_seconds"]

PACK_CONFIGURATION = PackConfiguration.uniform(
    initial_soc=0.90,
    capacity_ah=100.0,
    resistance_ohm=R0,
)
N_CELLS = len(PACK_CONFIGURATION.cells)

DT = 1.0

OCV_TABLE = np.array(config["ocv_soc_table"])

# --------------------------------------------------
# 2. INITIALISE CELL STATES
# --------------------------------------------------

soc = np.array(PACK_CONFIGURATION.values("initial_soc"), dtype=float)
polarization = np.zeros(N_CELLS)

capacities = np.array(PACK_CONFIGURATION.values("capacity_ah"), dtype=float)
resistances = np.array(PACK_CONFIGURATION.values("resistance_ohm"), dtype=float)

discharged_capacity = np.zeros(N_CELLS)

# --------------------------------------------------
# 3. OCV FUNCTION
# --------------------------------------------------

def get_ocv(soc_value):

    return np.interp(
        np.clip(soc_value, 0.0, 1.0),
        OCV_TABLE[:, 0],
        OCV_TABLE[:, 1]
    )

# --------------------------------------------------
# 4. SIMULATION
# --------------------------------------------------

records = []

time = 0.0

print("=" * 60)
print("16S LFP BATTERY PACK SIMULATION")
print("=" * 60)

while True:

    ocv = np.array([
        get_ocv(value) for value in soc
    ])

    cell_voltage = (
        ocv
        - CURRENT_A * resistances
        - polarization
    )

    pack_voltage = np.sum(cell_voltage)

    # Record all individual cell states
    row = {
        "Time_s": time,
        "Time_min": time / 60.0,
        "Pack_current_A": CURRENT_A,
        "Pack_voltage_V": pack_voltage,
        "Pack_SOC_percent": np.mean(soc) * 100
    }

    for i in range(N_CELLS):

        row[f"Cell_{i+1}_voltage_V"] = cell_voltage[i]
        row[f"Cell_{i+1}_SOC_percent"] = soc[i] * 100

    records.append(row)

    # Stop if any cell reaches the minimum SOC
    # Stop if any cell reaches the minimum operating SOC
    if np.any(soc <= MIN_SOC):
        break

    # RC state update
    decay = np.exp(-DT / TAU)

    polarization = (
        decay * polarization
        + CURRENT_A * R1 * (1.0 - decay)
    )

    # Coulomb counting for every cell
    capacity_step = CURRENT_A * DT / 3600.0

    discharged_capacity += capacity_step

    soc = np.maximum(
        MIN_SOC,
        np.array(PACK_CONFIGURATION.values("initial_soc"))
        - discharged_capacity / capacities
    )

    time += DT

# --------------------------------------------------
# 5. EXPORT DATA
# --------------------------------------------------

results = pd.DataFrame(records)

metrics_dir = ROOT / "results" / "metrics"
figures_dir = ROOT / "results" / "figures"

metrics_dir.mkdir(parents=True, exist_ok=True)
figures_dir.mkdir(parents=True, exist_ok=True)

csv_path = metrics_dir / "lfp_16s_pack_baseline.csv"

results.to_csv(csv_path, index=False)

# --------------------------------------------------
# 6. VALIDATION
# --------------------------------------------------

assert len(results) > 1

assert np.all(np.isfinite(results.select_dtypes("number")))

final_cell_voltages = results.iloc[-1][
    [f"Cell_{i+1}_voltage_V" for i in range(N_CELLS)]
].to_numpy(dtype=float)

assert np.allclose(
    final_cell_voltages,
    final_cell_voltages[0]
)

assert np.isclose(
    results["Pack_voltage_V"].iloc[-1],
    np.sum(final_cell_voltages)
)

# --------------------------------------------------
# 7. PLOT PACK VOLTAGE
# --------------------------------------------------

plt.figure(figsize=(11, 5))

plt.plot(
    results["Time_min"],
    results["Pack_voltage_V"]
)

plt.xlabel("Time (minutes)")
plt.ylabel("Pack voltage (V)")
plt.title("16S LFP Battery Pack - Discharge Profile")

plt.grid(True)
plt.tight_layout()

pack_plot = figures_dir / "lfp_16s_pack_voltage.png"

plt.savefig(pack_plot, dpi=300)
plt.show()

# --------------------------------------------------
# 8. PLOT CELL VOLTAGES
# --------------------------------------------------

plt.figure(figsize=(11, 5))

for i in range(N_CELLS):

    plt.plot(
        results["Time_min"],
        results[f"Cell_{i+1}_voltage_V"],
        alpha=0.65
    )

plt.xlabel("Time (minutes)")
plt.ylabel("Cell voltage (V)")
plt.title("16S Pack - Individual Cell Voltages")

plt.grid(True)
plt.tight_layout()

cell_plot = figures_dir / "lfp_16s_cell_voltages.png"

plt.savefig(cell_plot, dpi=300)
plt.show()

# --------------------------------------------------
# 9. FINAL REPORT
# --------------------------------------------------

print("\nPACK RESULTS")
print("-" * 45)

print("Cell count:", N_CELLS)
print("Configuration: 16S1P")
print(f"Nominal pack voltage: {16 * 3.2:.2f} V")
print(f"Nominal pack energy: {16 * 3.2 * 100 / 1000:.2f} kWh")

print(f"Initial pack voltage: {results['Pack_voltage_V'].iloc[0]:.4f} V")
print(f"Final pack voltage: {results['Pack_voltage_V'].iloc[-1]:.4f} V")
print(f"Final pack SOC: {results['Pack_SOC_percent'].iloc[-1]:.2f}%")
print(f"Discharge duration: {time / 60:.2f} minutes")

print("\nCELL VOLTAGE CONSISTENCY")
print(
    "Maximum cell voltage difference:",
    f"{np.ptp(final_cell_voltages):.8f} V"
)

print("\nVALIDATION CHECKS PASSED")

print("\nGenerated files:")
print(csv_path)
print(pack_plot)
print(cell_plot)
