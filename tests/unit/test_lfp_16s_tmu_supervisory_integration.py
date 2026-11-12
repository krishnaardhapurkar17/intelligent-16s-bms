
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from software.diagnostics.lfp_16s_supervisory_controller import (
    SupervisoryController,
)


def make_context():

    return pd.DataFrame({
        "Cell": list(range(1, 17)),
        "SOH_Scenario": ["TEST"] * 16,
        "RUL_Scenario": ["TEST"] * 16,
        "SOC_Operating_Scenario": ["TEST"] * 16,
        "Estimated_SOC_percent": [80.0] * 16,
        "Estimated_Capacity_SOH_percent": [100.0] * 16,
        "Estimated_Resistance_Growth_percent": [0.0] * 16,
        "Capacity_RUL_cycles": [1000.0] * 16,
        "Resistance_RUL_cycles": [1000.0] * 16,
        "Estimated_Total_RUL_cycles": [1000.0] * 16,
        "Limiting_Mechanism": ["NONE"] * 16,
        "Capacity_Fault_Detected": [False] * 16,
        "Resistance_Fault_Detected": [False] * 16,
    })


def evaluate(temperatures, suspect_temperature_cells=None):

    controller = SupervisoryController()

    return controller.evaluate_context(
        context_df=make_context(),
        cell_voltages=[3.35] * 16,
        cell_temperatures=temperatures,
        pack_current=10.0,
        bdu_state="CLOSED",
        protection_fault=False,
        charge_mode=True,
        suspect_temperature_cells=suspect_temperature_cells,
        insulation_state="NORMAL",
        insulation_measurement_quality="VALID",
    )


def run_tests():

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

    # 1. Normal thermal conditions
    decisions, quality = evaluate([25.0] * 16)

    check(
        "Normal thermal state permits eligible balancing",
        quality["thermal_state"] == "NORMAL"
        and any(item["Balancing_Eligible"] for item in decisions)
    )

    # 2. Temperature warning
    decisions, quality = evaluate([47.0] * 16)

    check(
        "Thermal warning inhibits balancing",
        quality["thermal_state"] == "WARNING"
        and not any(item["Balancing_Eligible"] for item in decisions)
    )

    # 3. Temperature critical
    decisions, quality = evaluate([57.0] * 16)

    check(
        "Thermal critical inhibits balancing",
        quality["thermal_state"] == "CRITICAL"
        and not any(item["Balancing_Eligible"] for item in decisions)
    )

    # 4. Thermal imbalance warning
    decisions, quality = evaluate(
        [40.0, 28.0] + [30.0] * 14
    )

    check(
        "Thermal imbalance inhibits balancing",
        quality["thermal_state"] == "WARNING"
        and quality["thermal_temperature_spread_c"] == 12.0
        and not any(item["Balancing_Eligible"] for item in decisions)
    )

    # 5. Invalid temperature channel
    decisions, quality = evaluate([25.0] * 15)

    check(
        "Invalid thermal channels inhibit balancing",
        quality["thermal_state"] == "UNKNOWN"
        and not any(item["Balancing_Eligible"] for item in decisions)
    )

    # 6. Suspect temperature sensor
    decisions, quality = evaluate(
        [25.0] * 16,
        suspect_temperature_cells=[3]
    )

    check(
        "Suspect temperature sensor inhibits balancing",
        quality["thermal_state"] == "UNKNOWN"
        and not any(item["Balancing_Eligible"] for item in decisions)
    )

    # 7. Charge derating recommendation
    decisions, quality = evaluate([47.0] * 16)

    check(
        "Thermal warning recommends charge derating",
        quality["thermal_charge_derating_recommended"]
    )

    # 8. Discharge derating recommendation
    check(
        "Thermal warning recommends discharge derating",
        quality["thermal_discharge_derating_recommended"]
    )

    # 9. BDU remains protection authority
    check(
        "BDU remains exclusive protection authority",
        all(
            item["Protection_Authority"] == "BDU_ONLY"
            for item in decisions
        )
    )

    # 10. AI remains advisory
    check(
        "AI remains advisory only",
        all(
            item["AI_Role"] == "ADVISORY_ONLY"
            for item in decisions
        )
    )

    # 11. Thermal state exported per cell
    check(
        "Thermal state included in supervisory records",
        all(
            item["Thermal_State"] == "WARNING"
            for item in decisions
        )
        if quality["thermal_state"] == "WARNING"
        else True
    )

    print("\nTMU-SUPERVISORY INTEGRATION SUMMARY")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
