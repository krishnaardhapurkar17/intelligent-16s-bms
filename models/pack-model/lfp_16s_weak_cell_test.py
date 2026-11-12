
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pathlib import Path
from cell_configuration import PackConfiguration

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

PACK_CONFIGURATION = PackConfiguration.uniform(
    initial_soc=0.90,
    capacity_ah=100.0,
    resistance_ohm=config["R0_ohm"],
)
N_CELLS = len(PACK_CONFIGURATION.cells)
WEAK_CELL = 8

WEAK_CAPACITY_AH = 80.0

INITIAL_SOC = 0.90
MIN_SOC = 0.10

CURRENT_A = 50.0
DT = 1.0

R0 = config["R0_ohm"]
R1 = config["R1_ohm"]
TAU = config["tau_seconds"]

OCV_TABLE = np.array(config["ocv_soc_table"])

# --------------------------------------------------
# 2. INITIALISE 16 CELLS
# --------------------------------------------------

# Inject capacity degradation into Cell 8 through its per-cell configuration.
PACK_CONFIGURATION = PACK_CONFIGURATION.with_cell(WEAK_CELL, capacity_ah=WEAK_CAPACITY_AH)
capacities = np.array(PACK_CONFIGURATION.values("capacity_ah"), dtype=float)
soc = np.array(PACK_CONFIGURATION.values("initial_soc"), dtype=float)

polarization = np.zeros(N_CELLS, dtype=float)

resistances = np.array(PACK_CONFIGURATION.values("resistance_ohm"), dtype=float)

discharged_capacity = np.zeros(N_CELLS, dtype=float)

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
stop_reason = ""

print("=" * 60)
print("16S LFP PACK - WEAK CELL SIMULATION")
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

    # Record pack-level measurements
    row = {
        "Time_s": time,
        "Time_min": time / 60.0,
        "Pack_current_A": CURRENT_A,
        "Pack_voltage_V": pack_voltage,
        "Minimum_cell_SOC_percent": np.min(soc) * 100.0,
        "Maximum_cell_SOC_percent": np.max(soc) * 100.0,
        "SOC_spread_percent": (
            np.max(soc) - np.min(soc)
        ) * 100.0
    }

    # Record individual cell measurements
    for i in range(N_CELLS):

        row[f"Cell_{i+1}_voltage_V"] = cell_voltage[i]

        row[f"Cell_{i+1}_SOC_percent"] = (
            soc[i] * 100.0
        )

        row[f"Cell_{i+1}_discharged_Ah"] = (
            discharged_capacity[i]
        )

    records.append(row)

    # Stop when the first cell reaches minimum SOC
    if np.any(soc <= MIN_SOC + 1e-10):

        stop_reason = "Minimum operating SOC reached"
        break

    # Update RC polarization
    decay = np.exp(-DT / TAU)

    polarization = (
        decay * polarization
        + CURRENT_A * R1 * (1.0 - decay)
    )

    # Coulomb counting
    capacity_step = CURRENT_A * DT / 3600.0

    discharged_capacity += capacity_step

    # Update SOC individually
    soc = np.maximum(
        MIN_SOC,
        np.array(PACK_CONFIGURATION.values("initial_soc"))
        - discharged_capacity / capacities
    )

    time += DT

# --------------------------------------------------
# 5. IDENTIFY LIMITING CELL
# --------------------------------------------------

weakest_cell_index = int(np.argmin(soc))
weakest_cell_number = weakest_cell_index + 1

final_soc = soc * 100.0

final_ocv = np.array([
    get_ocv(value) for value in soc
])

final_cell_voltage = (
    final_ocv
    - CURRENT_A * resistances
    - polarization
)

final_pack_voltage = np.sum(final_cell_voltage)

# --------------------------------------------------
# 6. CREATE DATAFRAME
# --------------------------------------------------

results = pd.DataFrame(records)

# --------------------------------------------------
# 7. VALIDATION
# --------------------------------------------------

assert len(results) > 1

assert np.all(np.isfinite(results.select_dtypes("number")))

assert weakest_cell_number == WEAK_CELL

assert np.isclose(final_soc[WEAK_CELL - 1], 10.0)

assert np.allclose(
    final_soc[np.arange(N_CELLS) != WEAK_CELL - 1],
    final_soc[0]
)

assert np.isclose(
    final_pack_voltage,
    np.sum(final_cell_voltage)
)

# --------------------------------------------------
# 8. EXPORT DATA
# --------------------------------------------------

metrics_dir = ROOT / "results" / "metrics"
figures_dir = ROOT / "results" / "figures"

metrics_dir.mkdir(parents=True, exist_ok=True)
figures_dir.mkdir(parents=True, exist_ok=True)

csv_path = metrics_dir / "lfp_16s_weak_cell.csv"

results.to_csv(csv_path, index=False)

# --------------------------------------------------
# 9. PLOT INDIVIDUAL CELL SOC
# --------------------------------------------------

plt.figure(figsize=(12, 6))

for i in range(N_CELLS):

    label = (
        f"Cell {i+1} (degraded)"
        if i == WEAK_CELL - 1
        else f"Cell {i+1}"
    )

    plt.plot(
        results["Time_min"],
        results[f"Cell_{i+1}_SOC_percent"],
        label=label,
        linewidth=2 if i == WEAK_CELL - 1 else 1
    )

plt.axhline(
    MIN_SOC * 100,
    linestyle="--",
    label="Minimum operating SOC"
)

plt.xlabel("Time (minutes)")
plt.ylabel("SOC (%)")
plt.title("16S LFP Pack - Individual Cell SOC")

plt.grid(True)
plt.legend(ncol=3, fontsize=8)
plt.tight_layout()

soc_plot = figures_dir / "lfp_16s_weak_cell_soc.png"

plt.savefig(soc_plot, dpi=300)
plt.show()

# --------------------------------------------------
# 10. PLOT INDIVIDUAL CELL VOLTAGE
# --------------------------------------------------

plt.figure(figsize=(12, 6))

for i in range(N_CELLS):

    label = (
        f"Cell {i+1} (degraded)"
        if i == WEAK_CELL - 1
        else f"Cell {i+1}"
    )

    plt.plot(
        results["Time_min"],
        results[f"Cell_{i+1}_voltage_V"],
        label=label,
        linewidth=2 if i == WEAK_CELL - 1 else 1
    )

plt.xlabel("Time (minutes)")
plt.ylabel("Cell voltage (V)")
plt.title("16S LFP Pack - Individual Cell Voltage")

plt.grid(True)
plt.legend(ncol=3, fontsize=8)
plt.tight_layout()

voltage_plot = figures_dir / "lfp_16s_weak_cell_voltage.png"

plt.savefig(voltage_plot, dpi=300)
plt.show()

# --------------------------------------------------
# 11. PLOT PACK VOLTAGE
# --------------------------------------------------

plt.figure(figsize=(10, 5))

plt.plot(
    results["Time_min"],
    results["Pack_voltage_V"]
)

plt.xlabel("Time (minutes)")
plt.ylabel("Pack voltage (V)")
plt.title("16S LFP Pack - Weak Cell Discharge")

plt.grid(True)
plt.tight_layout()

pack_plot = figures_dir / "lfp_16s_weak_cell_pack_voltage.png"

plt.savefig(pack_plot, dpi=300)
plt.show()

# --------------------------------------------------
# 12. FINAL REPORT
# --------------------------------------------------

print("\nSIMULATION RESULTS")
print("-" * 50)

print("Cell count: 16")
print("Configuration: 16S1P")
print(f"Discharge current: {CURRENT_A:.2f} A")
print(f"Limiting cell: Cell {weakest_cell_number}")

print(f"\nDischarge duration: {time / 60.0:.2f} minutes")

print(f"Final pack voltage: {final_pack_voltage:.4f} V")

print("\nINDIVIDUAL CELL SOC")
print("-" * 50)

for i in range(N_CELLS):

    status = "WEAK CELL" if i == WEAK_CELL - 1 else "HEALTHY"

    print(
        f"Cell {i+1:02d}: "
        f"SOC = {final_soc[i]:.2f}% "
        f"| Capacity = {capacities[i]:.2f} Ah "
        f"| {status}"
    )

print("\nDIAGNOSTIC RESULT")
print("-" * 50)

print(f"Weakest cell identified: Cell {weakest_cell_number}")
print(f"Actual injected weak cell: Cell {WEAK_CELL}")
print(f"Stop reason: {stop_reason}")

print("\nVALIDATION CHECKS PASSED")

print("\nGENERATED FILES")
print(csv_path)
print(soc_plot)
print(voltage_plot)
print(pack_plot)

print("\nWEAK CELL SIMULATION COMPLETE")
