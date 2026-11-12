import sys
from pathlib import Path

# Add project root to Python module search path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np


from models.balancing.lfp_16s_passive_balancing import (
    CellBank,
    PassiveBalancer,
    CELL_COUNT,
    AMBIENT_TEMP_C
)

from software.protection.lfp_16s_protection_bdu import (
    ProtectionBDU,
    make_inputs
)


def run_step(controller, balancer, cells, inputs):

    # 1. Update the actual BDU protection state machine
    bdu_output = controller.update(inputs, dt_s=1.0)

    bdu_state = bdu_output["state"]

    # 2. Read actual protection and actuator status
    protection_fault = (
        bdu_output["fault_latched"]
        or bool(bdu_output["active_faults"])
    )

    charge_mode = (
        bdu_output["actuator_outputs"]["charge_enable"]
    )

    # 3. Update passive balancing eligibility
    balancing_active = balancer.update_eligibility(
        cells.voltage,
        cells.temperature,
        bdu_state,
        charge_mode,
        protection_fault
    )

    # 4. Update cell model
    cells.update(balancing_active, 1.0)

    return {
        "bdu_state": bdu_state,
        "fault_latched": bdu_output["fault_latched"],
        "charge_mode": charge_mode,
        "balancing_active": balancing_active.copy(),
        "balancing_current": cells.balancing_current.copy(),
        "balancing_power": cells.balancing_power.copy()
    }


def main():

    print("=" * 70)
    print("16S BDU + PASSIVE BALANCING INTEGRATION")
    print("=" * 70)

    initial_soc = np.full(CELL_COUNT, 85.0)
    initial_soc[7] = 80.0

    cells = CellBank(initial_soc)
    balancer = PassiveBalancer()
    controller = ProtectionBDU()

    results = {}

    # --------------------------------------------------------
    # TEST 1: OPEN -> PRECHARGE
    # --------------------------------------------------------

    precharge = run_step(
        controller,
        balancer,
        cells,
        make_inputs(start_request=True)
    )

    results["PRECHARGE"] = precharge

    # --------------------------------------------------------
    # TEST 2: PRECHARGE -> CLOSED
    # --------------------------------------------------------

    closed = run_step(
        controller,
        balancer,
        cells,
        make_inputs()
    )

    results["CLOSED"] = closed

    # --------------------------------------------------------
    # TEST 3: PROTECTION FAULT DURING BALANCING
    # --------------------------------------------------------

    fault = run_step(
        controller,
        balancer,
        cells,
        make_inputs(
            cell_voltage_fault_cell=8,
            cell_voltage_fault_value=1.9
        )
    )

    results["FAULT"] = fault

    # --------------------------------------------------------
    # TEST 4: FAULT CLEARED WITHOUT RECOVERY REQUEST
    # --------------------------------------------------------

    fault_cleared = run_step(
        controller,
        balancer,
        cells,
        make_inputs()
    )

    results["FAULT_CLEARED_NO_REQUEST"] = fault_cleared

    # --------------------------------------------------------
    # TEST 5: EXPLICIT RECOVERY REQUEST
    # --------------------------------------------------------

    recovery = run_step(
        controller,
        balancer,
        cells,
        make_inputs(recovery_request=True)
    )

    results["RECOVERY"] = recovery

    # --------------------------------------------------------
    # TEST 6: RECOVERY -> OPEN
    # --------------------------------------------------------

    reopened = run_step(
        controller,
        balancer,
        cells,
        make_inputs(recovery_request=True)
    )

    results["OPEN_AFTER_RECOVERY"] = reopened

    # --------------------------------------------------------
    # TEST 7: THERMAL INTERLOCK WHILE BDU IS CLOSED
    # --------------------------------------------------------

    thermal_cells = CellBank(
        initial_soc,
        initial_temperature=np.array(
            [50.0] + [AMBIENT_TEMP_C] * 15
        )
    )

    thermal_controller = ProtectionBDU()
    thermal_balancer = PassiveBalancer()

    run_step(
        thermal_controller,
        thermal_balancer,
        thermal_cells,
        make_inputs(start_request=True)
    )

    thermal = run_step(
        thermal_controller,
        thermal_balancer,
        thermal_cells,
        make_inputs()
    )

    results["THERMAL_INTERLOCK"] = thermal

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    checks = {

        "PRECHARGE disables balancing":
            not np.any(precharge["balancing_active"]),

        "CLOSED permits eligible balancing":
            closed["bdu_state"] == "CLOSED"
            and np.any(closed["balancing_active"]),

        "Protection fault trips BDU":
            fault["bdu_state"] == "FAULT",

        "Protection fault disables balancing":
            not np.any(fault["balancing_active"]),

        "Protection fault immediately stops bleed current":
            np.all(fault["balancing_current"] == 0.0),

        "Fault remains latched":
            fault_cleared["bdu_state"] == "FAULT"
            and not np.any(
                fault_cleared["balancing_active"]
            ),

        "RECOVERY disables balancing":
            recovery["bdu_state"] == "RECOVERY"
            and not np.any(recovery["balancing_active"]),

        "Recovery returns BDU to OPEN":
            reopened["bdu_state"] == "OPEN"
            and not np.any(reopened["balancing_active"]),

        "Thermal interlock works while BDU is CLOSED":
            thermal["bdu_state"] == "CLOSED"
            and not thermal["balancing_active"][0]
            and thermal["balancing_current"][0] == 0.0,

        "Other eligible cells can balance":
            np.all(thermal["balancing_active"][1:7])
            and np.all(thermal["balancing_active"][8:]),

    }

    print("\nINTEGRATION VALIDATION")

    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")

    overall = all(checks.values())

    print("\nOVERALL:", "PASS" if overall else "FAIL")

    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()