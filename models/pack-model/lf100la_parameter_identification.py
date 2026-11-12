
import numpy as np
import pandas as pd

from pathlib import Path
from scipy.optimize import curve_fit

# --------------------------------------------------
# 1. LOAD HPPC DATA
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

DATA_PATH = (
    ROOT / "results" / "metrics"
    / "lf100la_hppc_test.csv"
)

df = pd.read_csv(DATA_PATH)

time = df["Time_s"].to_numpy()
current = df["Current_A"].to_numpy()
voltage = df["Terminal_voltage_V"].to_numpy()

print("=" * 55)
print("ECM PARAMETER IDENTIFICATION")
print("=" * 55)

# --------------------------------------------------
# 2. IDENTIFY R0 FROM FIRST PULSE
# --------------------------------------------------

pulse_start = 60.0
pulse_end = 70.0

pre_idx = np.argmin(np.abs(time - 59.9))
start_idx = np.argmin(np.abs(time - pulse_start))

pulse_current = current[start_idx]

if pulse_current <= 0:
    raise ValueError("Discharge pulse not found.")

voltage_before = voltage[pre_idx]
voltage_after = voltage[start_idx]

delta_voltage = voltage_before - voltage_after

R0_estimated = delta_voltage / pulse_current

# --------------------------------------------------
# 3. EXTRACT FIRST RELAXATION PERIOD
# --------------------------------------------------

relax_start = pulse_end
relax_end = 130.0

mask = (
    (time >= relax_start)
    & (time <= relax_end)
    & (current == 0)
)

relax_time = time[mask] - relax_start
relax_voltage = voltage[mask]

if len(relax_time) < 10:
    raise ValueError("Insufficient relaxation samples.")

# --------------------------------------------------
# 4. FIT EXPONENTIAL RELAXATION
# --------------------------------------------------

def relaxation_model(t, v_inf, amplitude, tau):
    return v_inf - amplitude * np.exp(-t / tau)

initial_guess = [
    relax_voltage[-1],
    relax_voltage[-1] - relax_voltage[0],
    30.0
]

bounds = (
    [3.0, 0.0, 0.1],
    [4.0, 0.1, 1000.0]
)

popt, _ = curve_fit(
    relaxation_model,
    relax_time,
    relax_voltage,
    p0=initial_guess,
    bounds=bounds,
    maxfev=20000
)

v_inf, amplitude, tau_estimated = popt

# --------------------------------------------------
# 5. ESTIMATE R1 AND C1
# --------------------------------------------------

pulse_duration = pulse_end - pulse_start

polarization_at_pulse_end = amplitude

R1_estimated = (
    polarization_at_pulse_end
    /
    (
        pulse_current
        * (1 - np.exp(-pulse_duration / tau_estimated))
    )
)

C1_estimated = tau_estimated / R1_estimated

# --------------------------------------------------
# 6. DISPLAY RESULTS
# --------------------------------------------------

print("\nIDENTIFIED PARAMETERS")
print("-" * 45)

print(f"R0: {R0_estimated:.8f} ohm")
print(f"R1: {R1_estimated:.8f} ohm")
print(f"Tau: {tau_estimated:.4f} seconds")
print(f"C1: {C1_estimated:.2f} F")

print("\nREFERENCE PARAMETERS")
print("-" * 45)

print("R0: 0.00050000 ohm")
print("R1: 0.00020000 ohm")
print("Tau: 30.0000 seconds")
print("C1: 150000.00 F")

# --------------------------------------------------
# 7. SAVE IDENTIFICATION RESULTS
# --------------------------------------------------

output = {
    "identification_method": (
        "R0 from pulse edge; R1 and tau from "
        "single exponential relaxation fit"
    ),
    "data_source": "Synthetic HPPC-style ECM simulation",
    "R0_estimated_ohm": R0_estimated,
    "R1_estimated_ohm": R1_estimated,
    "tau_estimated_s": tau_estimated,
    "C1_estimated_F": C1_estimated,
    "validated_against_physical_cell": False,
    "limitations": [
        "Parameters are identified from synthetic HPPC-style ECM data.",
        "Estimates are not manufacturer specifications or physical-cell measurements.",
        "The first-order equivalent-circuit form is an illustrative modeling assumption.",
    ],
}

output_path = (
    ROOT / "results" / "metrics"
    / "lf100la_identified_parameters.json"
)

import json

with open(output_path, "w") as file:
    json.dump(output, file, indent=4)

print("\nSaved:", output_path)
print("\nPARAMETER IDENTIFICATION COMPLETE")
