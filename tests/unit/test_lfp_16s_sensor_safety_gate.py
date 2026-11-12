import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from software.diagnostics.lfp_16s_sensor_safety_gate import (
    SensorQualityGate
)


def main():

    gate = SensorQualityGate()

    voltage = np.full(16, 3.3)
    temperature = np.full(16, 25.0)
    current = 20.0

    results = {}

    # Test 1: Healthy measurements
    results["Healthy sensors"] = gate.evaluate(
        voltage,
        temperature,
        current
    )["cell_balancing_eligible"].all()

    # Test 2: Missing voltage channel
    missing_voltage = voltage[:15]

    result = gate.evaluate(
        missing_voltage,
        temperature,
        current
    )

    results["Missing voltage channel"] = (
        not result["voltage_count_valid"]
        and not result["global_balancing_eligible"]
        and not result["cell_balancing_eligible"].any()
    )

    # Test 3: Invalid temperature channel
    invalid_temperature = temperature.copy()
    invalid_temperature[7] = np.nan

    result = gate.evaluate(
        voltage,
        invalid_temperature,
        current
    )

    results["Invalid Cell 8 temperature"] = (
        not result["temperature_valid"][7]
        and not result["cell_balancing_eligible"][7]
    )

    # Test 4: Suspect voltage channel
    result = gate.evaluate(
        voltage,
        temperature,
        current,
        suspect_voltage_cells=[8]
    )

    results["Suspect Cell 8 voltage"] = (
        not result["cell_balancing_eligible"][7]
        and result["cell_balancing_eligible"][6]
    )

    # Test 5: Suspect temperature channel
    result = gate.evaluate(
        voltage,
        temperature,
        current,
        suspect_temperature_cells=[12]
    )

    results["Suspect Cell 12 temperature"] = (
        not result["cell_balancing_eligible"][11]
        and result["cell_balancing_eligible"][10]
    )

    # Test 6: Invalid current measurement
    result = gate.evaluate(
        voltage,
        temperature,
        float("nan")
    )

    results["Invalid pack current"] = (
        not result["global_balancing_eligible"]
        and not result["cell_balancing_eligible"].any()
    )

    # Test 7: Suspect current sensor
    result = gate.evaluate(
        voltage,
        temperature,
        current,
        current_sensor_suspect=True
    )

    results["Suspect current sensor"] = (
        not result["global_balancing_eligible"]
        and not result["cell_balancing_eligible"].any()
    )

    print("=" * 65)
    print("16S SENSOR QUALITY GATE VALIDATION")
    print("=" * 65)

    for name, passed in results.items():
        print(
            f"{name}: {'PASS' if passed else 'FAIL'}"
        )

    overall = all(results.values())

    print("\nOVERALL:", "PASS" if overall else "FAIL")

    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()