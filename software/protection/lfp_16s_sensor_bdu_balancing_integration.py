import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from models.balancing.lfp_16s_passive_balancing import (
    CELL_COUNT,
    TIME_STEP_S,
    AMBIENT_TEMP_C,
    CellBank,
    PassiveBalancer,
)

from software.diagnostics.lfp_16s_sensor_safety_gate import (
    SensorQualityGate,
)

from software.protection.lfp_16s_protection_bdu import (
    ProtectionBDU,
    ProtectionInputs,
)


PACK_VOLTAGE = 53.6
NORMAL_CELL_VOLTAGE = 3.35
NORMAL_TEMPERATURE = 25.0
NORMAL_CURRENT = 10.0


def make_bdu_inputs(
    voltages=None,
    temperatures=None,
    current=NORMAL_CURRENT,
    start_request=False,
):
    if voltages is None:
        voltages = [NORMAL_CELL_VOLTAGE] * CELL_COUNT

    if temperatures is None:
        temperatures = [NORMAL_TEMPERATURE] * CELL_COUNT

    return ProtectionInputs(
        cell_voltages_v=list(voltages),
        pack_current_a=current,
        cell_temperatures_c=list(temperatures),
        pack_voltage_v=PACK_VOLTAGE,
        bus_voltage_v=PACK_VOLTAGE,
        start_request=start_request,
        stop_request=False,
        recovery_request=False,
        ai_available=True,
        communication_available=True,
    )


def initialize_bdu_closed(bdu):
    """Request startup and verify the BDU reaches CLOSED."""

    for _ in range(3):
        result = bdu.update(
            make_bdu_inputs(start_request=True),
            dt_s=TIME_STEP_S,
        )

        if result["state"] == "CLOSED":
            return result

    raise RuntimeError(
        "BDU failed to reach CLOSED during simulated startup."
    )


def run_integration_case(
    scenario,
    suspect_voltage_cells=None,
    suspect_temperature_cells=None,
    voltage_override=None,
    temperature_override=None,
    current_override=NORMAL_CURRENT,
    current_sensor_suspect=False,
    missing_voltage_channel=False,
    start_bdu_closed=True,
):
    voltages = [NORMAL_CELL_VOLTAGE] * CELL_COUNT
    temperatures = [NORMAL_TEMPERATURE] * CELL_COUNT
    initial_soc = np.full(CELL_COUNT, 85.0)

    # Create two independent balancing candidates.
    # This allows the test to verify that excluding
    # Cell 1 does not unnecessarily inhibit Cell 2.
    initial_soc[0] = 90.0
    initial_soc[1] = 90.0

    if voltage_override is not None:
        cell, value = voltage_override
        voltages[cell - 1] = value

    if temperature_override is not None:
        cell, value = temperature_override
        temperatures[cell - 1] = value

    if missing_voltage_channel:
        voltages = voltages[:-1]

    quality_gate = SensorQualityGate()

    quality = quality_gate.evaluate(
        cell_voltages=voltages,
        cell_temperatures=temperatures,
        pack_current=current_override,
        suspect_voltage_cells=suspect_voltage_cells,
        suspect_temperature_cells=suspect_temperature_cells,
        current_sensor_suspect=current_sensor_suspect,
    )

    bdu = ProtectionBDU()

    if start_bdu_closed:
        initialize_bdu_closed(bdu)

    bdu_result = bdu.update(
        make_bdu_inputs(
            voltages=voltages,
            temperatures=temperatures,
            current=current_override,
        ),
        dt_s=TIME_STEP_S,
    )

    bdu_state = bdu_result["state"]
    protection_fault = bdu_result["fault_latched"]

    cells = CellBank(
        initial_soc=initial_soc,
        initial_temperature=np.full(
            CELL_COUNT,
            AMBIENT_TEMP_C,
        ),
    )

    balancer = PassiveBalancer()

    # The BDU and global sensor quality gate must both permit balancing.
    global_enable = (
        bdu_state == "CLOSED"
        and not protection_fault
        and quality["global_balancing_eligible"]
    )

    if global_enable:
        active = balancer.update_eligibility(
            cell_voltages=cells.voltage,
            cell_temperatures=cells.temperature,
            bdu_state=bdu_state,
            charge_mode=True,
            protection_fault=protection_fault,
        )

        # Apply per-cell sensor validity after the balancer's
        # voltage/temperature eligibility calculation.
        active &= quality["cell_balancing_eligible"]

    else:
        balancer.balancing_active[:] = False
        active = balancer.balancing_active.copy()

    # Only eligible cells receive simulated bleed current.
    cells.update(active, TIME_STEP_S)

    return {
        "scenario": scenario,
        "bdu_state": bdu_state,
        "protection_fault": protection_fault,
        "global_sensor_enable": quality[
            "global_balancing_eligible"
        ],
        "invalid_voltage_cells": quality[
            "invalid_voltage_cells"
        ],
        "invalid_temperature_cells": quality[
            "invalid_temperature_cells"
        ],
        "balancing_active": active.copy(),
        "balancing_current": cells.balancing_current.copy(),
        "balancing_power": cells.balancing_power.copy(),
    }


def main():

    results = []

    # 1. Healthy sensor channels: Cell 1 should balance.
    results.append(
        run_integration_case("HEALTHY")
    )

    # 2. Suspect voltage channel on an otherwise eligible cell.
    results.append(
        run_integration_case(
            "SUSPECT_CELL_1_VOLTAGE",
            suspect_voltage_cells=[1],
        )
    )

    # 3. Suspect temperature channel on an otherwise eligible cell.
    results.append(
        run_integration_case(
            "SUSPECT_CELL_1_TEMPERATURE",
            suspect_temperature_cells=[1],
        )
    )

    # 4. Missing voltage channel: global balancing inhibited.
    results.append(
        run_integration_case(
            "MISSING_VOLTAGE_CHANNEL",
            missing_voltage_channel=True,
        )
    )

    # 5. Invalid temperature: BDU should enter FAULT.
    results.append(
        run_integration_case(
            "INVALID_CELL_8_TEMPERATURE",
            temperature_override=(8, float("nan")),
        )
    )

    # 6. Invalid current: BDU and quality gate inhibit balancing.
    results.append(
        run_integration_case(
            "INVALID_PACK_CURRENT",
            current_override=float("nan"),
        )
    )

    # 7. Suspect current sensor: quality gate inhibits globally.
    results.append(
        run_integration_case(
            "SUSPECT_CURRENT_SENSOR",
            current_sensor_suspect=True,
        )
    )

    checks = {
        "Healthy system permits balancing":
            results[0]["bdu_state"] == "CLOSED"
            and results[0]["balancing_active"][0],

        "Suspect voltage channel is excluded":
            not results[1]["balancing_active"][0]
            and np.any(results[1]["balancing_active"][1:]),

        "Suspect temperature channel is excluded":
            not results[2]["balancing_active"][0]
            and np.any(results[2]["balancing_active"][1:]),

        "Missing voltage channel disables all balancing":
            not np.any(results[3]["balancing_active"]),

        "Invalid temperature trips BDU":
            results[4]["bdu_state"] == "FAULT"
            and not np.any(results[4]["balancing_active"]),

        "Invalid pack current trips BDU":
            results[5]["bdu_state"] == "FAULT"
            and not np.any(results[5]["balancing_active"]),

        "Suspect current sensor disables balancing":
            not results[6]["global_sensor_enable"]
            and not np.any(results[6]["balancing_active"]),

        "No current flows through inactive channels":
            all(
                np.all(
                    result["balancing_current"][
                        ~result["balancing_active"]
                    ] == 0.0
                )
                for result in results
            ),

        "No power is dissipated by inactive channels":
            all(
                np.all(
                    result["balancing_power"][
                        ~result["balancing_active"]
                    ] == 0.0
                )
                for result in results
            ),
    }

    print("=" * 70)
    print("16S SENSOR + BDU + PASSIVE BALANCING INTEGRATION")
    print("=" * 70)

    for result in results:
        active_cells = (
            np.where(result["balancing_active"])[0] + 1
        ).tolist()

        print(f"\n{result['scenario']}")
        print("BDU state:", result["bdu_state"])
        print("Protection fault:", result["protection_fault"])
        print("Global sensor enable:", result["global_sensor_enable"])
        print("Active balancing cells:", active_cells)

    print("\nVALIDATION RESULTS")

    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")

    overall = all(checks.values())
    print(f"\nOVERALL: {'PASS' if overall else 'FAIL'}")

    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()