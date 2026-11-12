
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from software.diagnostics.lfp_16s_thermal_management import (
    ThermalManagementUnit,
    TMUConfig,
)


def run_tests():

    tmu = ThermalManagementUnit()
    passed = 0
    failed = 0

    def check(name, condition):
        nonlocal passed, failed

        if condition:
            print(f"PASS: {name}")
            passed += 1
        else:
            print(f"FAIL: {name}")
            failed += 1

    # 1. Normal thermal condition
    reading = tmu.process_measurements([25.0] * 16)

    check(
        "Normal temperature classification",
        reading.thermal_state == "NORMAL"
        and reading.balancing_permitted
    )

    # 2. Absolute temperature warning
    reading = tmu.process_measurements([47.0] * 16)

    check(
        "Temperature warning classification",
        reading.thermal_state == "WARNING"
        and reading.charge_derating_recommended
        and not reading.balancing_permitted
    )

    # 3. Absolute temperature critical
    reading = tmu.process_measurements([57.0] * 16)

    check(
        "Temperature critical classification",
        reading.thermal_state == "CRITICAL"
        and reading.discharge_derating_recommended
    )

    # 4. Temperature spread warning
    reading = tmu.process_measurements(
        [40.0, 28.0] + [30.0] * 14
    )

    check(
        "Thermal spread warning",
        reading.thermal_state == "WARNING"
        and reading.temperature_spread_c == 12.0
    )

    # 5. Temperature spread critical
    reading = tmu.process_measurements(
        [40.0, 25.0] + [30.0] * 14
    )

    check(
        "Thermal spread critical",
        reading.thermal_state == "CRITICAL"
        and reading.temperature_spread_c == 15.0
    )

    # 6. Incorrect number of temperature channels
    reading = tmu.process_measurements([25.0] * 15)

    check(
        "Invalid temperature channel count",
        reading.thermal_state == "UNKNOWN"
        and not reading.balancing_permitted
    )

    # 7. Missing sensor data
    reading = tmu.process_measurements(
        [25.0] * 16,
        measurement_available=False
    )

    check(
        "Unavailable temperature sensors",
        reading.thermal_state == "UNKNOWN"
    )

    # 8. Non-finite sensor value
    invalid_values = [25.0] * 16
    invalid_values[3] = float("nan")

    reading = tmu.process_measurements(invalid_values)

    check(
        "Non-finite temperature rejection",
        reading.thermal_state == "UNKNOWN"
    )

    # 9. Temperature outside configured range
    invalid_values = [25.0] * 16
    invalid_values[5] = 120.0

    reading = tmu.process_measurements(invalid_values)

    check(
        "Out-of-range temperature rejection",
        reading.thermal_state == "UNKNOWN"
    )

    # 10. Suspect temperature sensor
    reading = tmu.process_measurements(
        [25.0] * 16,
        suspect_cells=[4]
    )

    check(
        "Suspect sensor inhibits balancing",
        reading.thermal_state == "UNKNOWN"
        and not reading.balancing_permitted
    )

    # 11. Hottest and coldest cell identification
    reading = tmu.process_measurements(
        [25.0, 26.0, 27.0, 28.0] + [30.0] * 12
    )

    check(
        "Hottest and coldest cell identification",
        reading.hottest_cell == 5
        and reading.coldest_cell == 1
    )

    # 12. Invalid configuration
    invalid_config_rejected = False

    try:
        ThermalManagementUnit(
            TMUConfig(
                warning_temperature_c=60.0,
                critical_temperature_c=55.0
            )
        )
    except ValueError:
        invalid_config_rejected = True

    check(
        "Invalid threshold configuration rejected",
        invalid_config_rejected
    )

    print("\nTMU TEST SUMMARY")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
