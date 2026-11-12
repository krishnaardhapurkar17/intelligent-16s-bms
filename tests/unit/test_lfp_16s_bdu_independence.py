import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from software.protection.lfp_16s_protection_bdu import (
    ProtectionBDU,
    ProtectionInputs,
)

CELL_COUNT = 16

NORMAL_VOLTAGES = [3.35] * CELL_COUNT
NORMAL_TEMPERATURES = [25.0] * CELL_COUNT
NORMAL_PACK_VOLTAGE = 53.6


def make_inputs(
    ai_available=True,
    communication_available=True,
    linux_available=True,
    telemetry_available=True,
    pack_current=10.0,
    start_request=False,
):
    return ProtectionInputs(
        cell_voltages_v=NORMAL_VOLTAGES.copy(),
        pack_current_a=pack_current,
        cell_temperatures_c=NORMAL_TEMPERATURES.copy(),
        pack_voltage_v=NORMAL_PACK_VOLTAGE,
        bus_voltage_v=NORMAL_PACK_VOLTAGE,
        start_request=start_request,
        stop_request=False,
        recovery_request=False,
        ai_available=ai_available,
        communication_available=communication_available,
        linux_available=linux_available,
        telemetry_available=telemetry_available,
    )


def initialize_closed(bdu, ai=True, communication=True):
    result = None

    for _ in range(3):
        result = bdu.update(
            make_inputs(
                ai_available=ai,
                communication_available=communication,
                start_request=True,
            ),
            dt_s=1.0,
        )

        if result["state"] == "CLOSED":
            return result

    raise RuntimeError("BDU did not reach CLOSED state.")


def main():

    checks = {}

    # --------------------------------------------------
    # TEST 1: Normal operation
    # --------------------------------------------------

    bdu_normal = ProtectionBDU()

    normal_result = initialize_closed(
        bdu_normal,
        ai=True,
        communication=True,
    )



    checks["BDU reaches CLOSED during normal operation"] = (
        normal_result["state"] == "CLOSED"
        and normal_result["actuator_outputs"]["main_contactor_command"]
    )

    

    # --------------------------------------------------
    # TEST 2: AI unavailable
    # --------------------------------------------------

    bdu_no_ai = ProtectionBDU()

    ai_result = initialize_closed(
        bdu_no_ai,
        ai=False,
        communication=True,
    )

    checks["AI unavailable does not prevent BDU startup"] = (
        ai_result["state"] == "CLOSED"
        and ai_result["actuator_outputs"]["main_contactor_command"]
    )

    # --------------------------------------------------
    # TEST 3: Communication unavailable
    # --------------------------------------------------

    bdu_no_comm = ProtectionBDU()

    comm_result = initialize_closed(
        bdu_no_comm,
        ai=True,
        communication=False,
    )

    checks["Communication unavailable does not prevent BDU startup"] = (
        comm_result["state"] == "CLOSED"
        and comm_result["actuator_outputs"]["main_contactor_command"]
    )

    # --------------------------------------------------
    # TEST 4: Both unavailable
    # --------------------------------------------------

    bdu_no_external = ProtectionBDU()

    both_result = initialize_closed(
        bdu_no_external,
        ai=False,
        communication=False,
    )

    checks["Both AI and communication unavailable"] = (
        both_result["state"] == "CLOSED"
        and both_result["actuator_outputs"]["main_contactor_command"]
    )

    # --------------------------------------------------
    # TEST 5: Overcurrent while AI unavailable
    # --------------------------------------------------

    bdu_fault_ai = ProtectionBDU()

    initialize_closed(bdu_fault_ai)

    fault_ai_result = bdu_fault_ai.update(
        make_inputs(
            ai_available=False,
            communication_available=True,
            pack_current=120.0,
        ),
        dt_s=1.0,
    )

    checks["Overcurrent protection works without AI"] = (
        fault_ai_result["state"] == "FAULT"
        and fault_ai_result["fault_latched"]
        and not any(
            fault_ai_result["actuator_outputs"].values()
        )
    )

    # --------------------------------------------------
    # TEST 6: Overcurrent while communication unavailable
    # --------------------------------------------------

    bdu_fault_comm = ProtectionBDU()

    initialize_closed(bdu_fault_comm)

    fault_comm_result = bdu_fault_comm.update(
        make_inputs(
            ai_available=True,
            communication_available=False,
            pack_current=120.0,
        ),
        dt_s=1.0,
    )

    checks["Overcurrent protection works without communication"] = (
        fault_comm_result["state"] == "FAULT"
        and fault_comm_result["fault_latched"]
        and not any(
            fault_comm_result["actuator_outputs"].values()
        )
    )

    # --------------------------------------------------
    # TEST 7: Both unavailable during overcurrent
    # --------------------------------------------------

    bdu_fault_both = ProtectionBDU()

    initialize_closed(bdu_fault_both)

    fault_both_result = bdu_fault_both.update(
        make_inputs(
            ai_available=False,
            communication_available=False,
            linux_available=False,
            telemetry_available=False,
            pack_current=120.0,
        ),
        dt_s=1.0,
    )

    checks["Protection works when both systems are unavailable"] = (
        fault_both_result["state"] == "FAULT"
        and fault_both_result["fault_latched"]
        and not any(
            fault_both_result["actuator_outputs"].values()
        )
        and not fault_both_result["linux_available"]
        and not fault_both_result["telemetry_available"]
    )

    # --------------------------------------------------
    # PRINT RESULTS
    # --------------------------------------------------

    print("=" * 70)
    print("16S BDU INDEPENDENCE VALIDATION")
    print("=" * 70)
   

    for name, passed in checks.items():
        print(
            f"{name}: {'PASS' if passed else 'FAIL'}"
        )

    passed_count = sum(checks.values())

    print(
        f"\nPASSED: {passed_count}/{len(checks)}"
    )

    overall = all(checks.values())

    print(
        "OVERALL:",
        "PASS" if overall else "FAIL",
    )

    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
