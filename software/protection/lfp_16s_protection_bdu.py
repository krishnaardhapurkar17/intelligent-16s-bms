
import math
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List


CELL_COUNT = 16


# ============================================================
# BDU STATES
# ============================================================

class BDUState(str, Enum):
    OPEN = "OPEN"
    PRECHARGE = "PRECHARGE"
    CLOSED = "CLOSED"
    FAULT = "FAULT"
    RECOVERY = "RECOVERY"


# ============================================================
# PROTECTION CONFIGURATION
# ============================================================

@dataclass
class ProtectionConfig:
    cell_uv_v: float = 2.0
    cell_ov_v: float = 3.6
    pack_oc_a: float = 100.0
    cell_ot_c: float = 65.0
    precharge_delta_v: float = 2.0
    precharge_timeout_s: float = 5.0


# ============================================================
# INPUT SIGNALS
# ============================================================

@dataclass
class ProtectionInputs:
    cell_voltages_v: List[float]
    pack_current_a: float
    cell_temperatures_c: List[float]
    pack_voltage_v: float
    bus_voltage_v: float

    start_request: bool = False
    stop_request: bool = False
    recovery_request: bool = False

    ai_available: bool = True
    communication_available: bool = True
    linux_available: bool = True
    telemetry_available: bool = True


# ============================================================
# PROTECTION AND BDU CONTROLLER
# ============================================================

class ProtectionBDU:

    def __init__(self, config=None):
        self.config = config or ProtectionConfig()

        self.state = BDUState.OPEN
        self.fault_latched = False
        self.fault_history = []

        self.precharge_elapsed_s = 0.0

    # --------------------------------------------------------
    # PROTECTION EVALUATION
    # --------------------------------------------------------

    def evaluate_protection(self, inputs):

        faults = []

        if len(inputs.cell_voltages_v) != CELL_COUNT:
            faults.append("INVALID_CELL_VOLTAGE_CHANNEL_COUNT")

        if len(inputs.cell_temperatures_c) != CELL_COUNT:
            faults.append("INVALID_TEMPERATURE_CHANNEL_COUNT")

        if not math.isfinite(inputs.pack_current_a):
            faults.append("PACK_CURRENT_SENSOR_INVALID")

        if not math.isfinite(inputs.pack_voltage_v):
            faults.append("PACK_VOLTAGE_SENSOR_INVALID")

        if not math.isfinite(inputs.bus_voltage_v):
            faults.append("BUS_VOLTAGE_SENSOR_INVALID")

        if faults:
            return faults

        # Individual cell voltage monitoring
        for index, voltage in enumerate(
            inputs.cell_voltages_v, start=1
        ):

            if not math.isfinite(voltage):
                faults.append(
                    f"CELL_{index}_VOLTAGE_INVALID"
                )

            elif voltage < self.config.cell_uv_v:
                faults.append(
                    f"CELL_{index}_UNDERVOLTAGE"
                )

            elif voltage > self.config.cell_ov_v:
                faults.append(
                    f"CELL_{index}_OVERVOLTAGE"
                )

        # Individual cell temperature monitoring
        for index, temperature in enumerate(
            inputs.cell_temperatures_c, start=1
        ):

            if not math.isfinite(temperature):
                faults.append(
                    f"CELL_{index}_TEMPERATURE_INVALID"
                )

            elif temperature >= self.config.cell_ot_c:
                faults.append(
                    f"CELL_{index}_OVERTEMPERATURE"
                )

        # Pack current protection
        if abs(inputs.pack_current_a) >= self.config.pack_oc_a:
            faults.append("PACK_OVERCURRENT")

        return faults

    
    def get_actuator_outputs(self):

        if self.state == BDUState.PRECHARGE:
            return {
                "main_contactor_command": False,
                "precharge_contactor_command": True,
                "charge_enable": False,
                "discharge_enable": False,
            }

        elif self.state == BDUState.CLOSED:
            return {
                "main_contactor_command": True,
                "precharge_contactor_command": False,
                "charge_enable": True,
                "discharge_enable": True,
            }

        # OPEN, FAULT and RECOVERY all command isolation
        return {
            "main_contactor_command": False,
            "precharge_contactor_command": False,
            "charge_enable": False,
            "discharge_enable": False,
        }


    # --------------------------------------------------------
    # BDU STATE MACHINE
    # --------------------------------------------------------

    def update(self, inputs, dt_s=1.0):

        if dt_s <= 0:
            raise ValueError("dt_s must be positive")

        faults = self.evaluate_protection(inputs)

        # Protection faults have priority over all state transitions
        if faults:

            self.fault_latched = True
            self.state = BDUState.FAULT

            for fault in faults:
                if fault not in self.fault_history:
                    self.fault_history.append(fault)

        elif self.state == BDUState.OPEN:

            if inputs.start_request and not self.fault_latched:

                self.precharge_elapsed_s = 0.0
                self.state = BDUState.PRECHARGE

        elif self.state == BDUState.PRECHARGE:

            self.precharge_elapsed_s += dt_s

            voltage_difference = abs(
                inputs.pack_voltage_v - inputs.bus_voltage_v
            )

            if voltage_difference <= self.config.precharge_delta_v:

                self.state = BDUState.CLOSED

            elif (
                self.precharge_elapsed_s
                >= self.config.precharge_timeout_s
            ):

                self.fault_latched = True
                self.state = BDUState.FAULT

                if "PRECHARGE_TIMEOUT" not in self.fault_history:
                    self.fault_history.append(
                        "PRECHARGE_TIMEOUT"
                    )

        elif self.state == BDUState.CLOSED:

            if inputs.stop_request:
                self.state = BDUState.OPEN

        elif self.state == BDUState.FAULT:

            # Fault must clear before recovery can begin.
            # Recovery must be explicitly requested.
            if not faults and inputs.recovery_request:
                self.state = BDUState.RECOVERY

        elif self.state == BDUState.RECOVERY:

            if faults:

                self.state = BDUState.FAULT

            elif inputs.recovery_request:

                self.fault_latched = False
                self.precharge_elapsed_s = 0.0
                self.state = BDUState.OPEN

        
        return {
            "state": self.state.value,
            "fault_latched": self.fault_latched,
            "active_faults": faults,
            "fault_history": list(self.fault_history),

            "actuator_outputs": self.get_actuator_outputs(),

            "ai_available": inputs.ai_available,
            "communication_available":
                inputs.communication_available,
            "linux_available": inputs.linux_available,
            "telemetry_available": inputs.telemetry_available,
        }



# ============================================================
# INPUT GENERATOR WITH INDIVIDUAL CELL FAULT INJECTION
# ============================================================


def make_inputs(
    normal_cell_voltage=3.2,
    normal_temperature=25.0,
    current=20.0,
    pack_voltage=51.2,
    bus_voltage=51.0,
    cell_voltage_fault_cell=None,
    cell_voltage_fault_value=None,
    temperature_fault_cell=None,
    temperature_fault_value=None,
    **kwargs
):
    # Initialize all 16 cells with normal values
    voltages = [normal_cell_voltage] * CELL_COUNT
    temperatures = [normal_temperature] * CELL_COUNT

    # Inject voltage fault into exactly one cell
    if cell_voltage_fault_cell is not None:

        if not 1 <= cell_voltage_fault_cell <= CELL_COUNT:
            raise ValueError("Invalid voltage cell index")

        if cell_voltage_fault_value is None:
            raise ValueError("Voltage fault value not provided")

        voltages[cell_voltage_fault_cell - 1] = (
            cell_voltage_fault_value
        )

        print(
            "Voltage injection:",
            cell_voltage_fault_cell,
            voltages
        )

    # Inject temperature fault into exactly one cell
    if temperature_fault_cell is not None:

        if not 1 <= temperature_fault_cell <= CELL_COUNT:
            raise ValueError("Invalid temperature cell index")

        if temperature_fault_value is None:
            raise ValueError("Temperature fault value not provided")

        temperatures[temperature_fault_cell - 1] = (
            temperature_fault_value
        )

        print(
            "Temperature injection:",
            temperature_fault_cell,
            temperatures
        )

    return ProtectionInputs(
        cell_voltages_v=voltages,
        pack_current_a=current,
        cell_temperatures_c=temperatures,
        pack_voltage_v=pack_voltage,
        bus_voltage_v=bus_voltage,
        **kwargs
    )



# ============================================================
# SCENARIO RUNNER
# ============================================================

def run_scenario(name, steps):

    controller = ProtectionBDU()
    outputs = []

    for inputs, dt_s in steps:

        outputs.append(
            controller.update(inputs, dt_s)
        )

    return {
        "scenario": name,
        "final_state": controller.state.value,
        "fault_latched": controller.fault_latched,
        "fault_history": controller.fault_history,
        "steps": outputs,
    }


# ============================================================
# MAIN SIMULATION
# ============================================================

def main():

    results = []

    # --------------------------------------------------------
    # SIM-BDU-001: NORMAL STARTUP
    # OPEN -> PRECHARGE -> CLOSED
    # --------------------------------------------------------

    results.append(run_scenario(
        "SIM-BDU-001_NORMAL_STARTUP",
        [
            (make_inputs(start_request=True), 1.0),
            (make_inputs(), 1.0),
        ],
    ))

    # --------------------------------------------------------
    # SIM-BDU-002: CELL 8 UNDERVOLTAGE
    # --------------------------------------------------------

    results.append(run_scenario(
        "SIM-BDU-002_CELL_UNDERVOLTAGE",
        [
            (make_inputs(start_request=True), 1.0),
            (make_inputs(), 1.0),
            (
                make_inputs(
                    cell_voltage_fault_cell=8,
                    cell_voltage_fault_value=1.9
                ),
                1.0,
            ),
        ],
    ))

    # --------------------------------------------------------
    # SIM-BDU-003: CELL 8 OVERVOLTAGE
    # --------------------------------------------------------

    results.append(run_scenario(
        "SIM-BDU-003_CELL_OVERVOLTAGE",
        [
            (make_inputs(start_request=True), 1.0),
            (make_inputs(), 1.0),
            (
                make_inputs(
                    cell_voltage_fault_cell=8,
                    cell_voltage_fault_value=3.7
                ),
                1.0,
            ),
        ],
    ))

    # --------------------------------------------------------
    # SIM-BDU-004: PACK OVERCURRENT
    # --------------------------------------------------------

    results.append(run_scenario(
        "SIM-BDU-004_PACK_OVERCURRENT",
        [
            (make_inputs(start_request=True), 1.0),
            (make_inputs(), 1.0),
            (make_inputs(current=110.0), 1.0),
        ],
    ))

    # --------------------------------------------------------
    # SIM-BDU-005: CELL 8 OVERTEMPERATURE
    # --------------------------------------------------------

    results.append(run_scenario(
        "SIM-BDU-005_CELL_OVERTEMPERATURE",
        [
            (make_inputs(start_request=True), 1.0),
            (make_inputs(), 1.0),
            (
                make_inputs(
                    temperature_fault_cell=8,
                    temperature_fault_value=70.0
                ),
                1.0,
            ),
        ],
    ))

    # --------------------------------------------------------
    # SIM-BDU-006: PRECHARGE TIMEOUT
    # --------------------------------------------------------

    results.append(run_scenario(
        "SIM-BDU-006_PRECHARGE_TIMEOUT",
        [
            (
                make_inputs(
                    start_request=True,
                    pack_voltage=51.2,
                    bus_voltage=40.0
                ),
                1.0,
            ),
            (
                make_inputs(
                    pack_voltage=51.2,
                    bus_voltage=40.0
                ),
                1.0,
            ),
            (
                make_inputs(
                    pack_voltage=51.2,
                    bus_voltage=40.0
                ),
                1.0,
            ),
            (
                make_inputs(
                    pack_voltage=51.2,
                    bus_voltage=40.0
                ),
                1.0,
            ),
            (
                make_inputs(
                    pack_voltage=51.2,
                    bus_voltage=40.0
                ),
                1.0,
            ),
            (
                make_inputs(
                    pack_voltage=51.2,
                    bus_voltage=40.0
                ),
                1.0,
            ),
        ],
    ))

    # --------------------------------------------------------
    # SIM-BDU-007: OPTIONAL-SERVICE INDEPENDENCE
    # --------------------------------------------------------

    results.append(run_scenario(
        "SIM-BDU-007_PROTECTION_INDEPENDENCE",
        [
            (make_inputs(start_request=True), 1.0),
            (make_inputs(), 1.0),
            (
                make_inputs(
                    current=110.0,
                    ai_available=False,
                    communication_available=False,
                    linux_available=False,
                    telemetry_available=False,
                ),
                1.0,
            ),
        ],
    ))

    # --------------------------------------------------------
    # SIM-BDU-008: FAULT LATCH AND RECOVERY
    # --------------------------------------------------------

    controller = ProtectionBDU()

    controller.update(make_inputs(start_request=True))
    controller.update(make_inputs())
    controller.update(make_inputs(current=110.0))

    fault_state = controller.state.value

    controller.update(make_inputs())
    cleared_without_request = controller.state.value

    controller.update(
        make_inputs(recovery_request=True)
    )
    recovery_state = controller.state.value
    recovery_outputs = controller.get_actuator_outputs()

    controller.update(
        make_inputs(recovery_request=True)
    )
    final_recovery_state = controller.state.value

    results.append({
        "scenario": "SIM-BDU-008_FAULT_LATCH_AND_RECOVERY",
        "fault_state": fault_state,
        "state_after_fault_cleared": cleared_without_request,
        "recovery_state": recovery_state,
        "recovery_outputs": recovery_outputs,
        "final_state": final_recovery_state,
        "fault_history": controller.fault_history,
    })

    # --------------------------------------------------------
    # SIM-BDU-009: INVALID CURRENT SENSOR
    # --------------------------------------------------------

    invalid_current = make_inputs()
    invalid_current.pack_current_a = float("nan")

    results.append(run_scenario(
        "SIM-BDU-009_INVALID_CURRENT_SENSOR",
        [
            (invalid_current, 1.0),
        ],
    ))

    # --------------------------------------------------------
    # SIM-BDU-010: MISSING CELL VOLTAGE CHANNEL
    # --------------------------------------------------------

    missing_voltage = make_inputs()
    missing_voltage.cell_voltages_v = [3.2] * 15

    results.append(run_scenario(
        "SIM-BDU-010_MISSING_VOLTAGE_CHANNEL",
        [
            (missing_voltage, 1.0),
        ],
    ))

    # ========================================================
    # VALIDATION
    # ========================================================

    checks = {

        "Normal startup reaches CLOSED":
            results[0]["final_state"] == "CLOSED",

        "Undervoltage localized to Cell 8":
            results[1]["fault_history"] == [
                "CELL_8_UNDERVOLTAGE"
            ],

        "Overvoltage localized to Cell 8":
            results[2]["fault_history"] == [
                "CELL_8_OVERVOLTAGE"
            ],

        "Overcurrent trips BDU":
            results[3]["final_state"] == "FAULT",

        "Overtemperature localized to Cell 8":
            results[4]["fault_history"] == [
                "CELL_8_OVERTEMPERATURE"
            ],

        "Precharge timeout trips BDU":
            results[5]["final_state"] == "FAULT",

        "Protection works without AI, Linux, communication or telemetry":
            results[6]["final_state"] == "FAULT",

        "Fault remains latched after condition clears":
            cleared_without_request == "FAULT",

        "Recovery enters RECOVERY state":
            recovery_state == "RECOVERY",

        "Recovery returns BDU to OPEN":
            final_recovery_state == "OPEN",

        "Invalid current sensor trips BDU":
            (
                results[8]["final_state"] == "FAULT"
                and "PACK_CURRENT_SENSOR_INVALID"
                in results[8]["fault_history"]
            ),

        "Missing voltage channel trips BDU":
            (
                results[9]["final_state"] == "FAULT"
                and "INVALID_CELL_VOLTAGE_CHANNEL_COUNT"
                in results[9]["fault_history"]
            ),

       
    }


    # --------------------------------------------------------
    # BDU ACTUATOR VALIDATION
    # --------------------------------------------------------

    normal_precharge = results[0]["steps"][0]["actuator_outputs"]
    normal_closed = results[0]["steps"][1]["actuator_outputs"]

    undervoltage_outputs = results[1]["steps"][-1]["actuator_outputs"]
    overcurrent_outputs = results[3]["steps"][-1]["actuator_outputs"]
    overtemperature_outputs = results[4]["steps"][-1]["actuator_outputs"]

    def all_actuators_off(outputs):
        return not any(outputs.values())

    checks.update({

        "Precharge state commands precharge contactor only":
            (
                normal_precharge["main_contactor_command"] is False
                and normal_precharge["precharge_contactor_command"] is True
                and normal_precharge["charge_enable"] is False
                and normal_precharge["discharge_enable"] is False
            ),

        "Closed state commands main contactor only":
            (
                normal_closed["main_contactor_command"] is True
                and normal_closed["precharge_contactor_command"] is False
                and normal_closed["charge_enable"] is True
                and normal_closed["discharge_enable"] is True
            ),

        "Undervoltage commands all actuators off":
            all_actuators_off(undervoltage_outputs),

        "Overcurrent commands all actuators off":
            all_actuators_off(overcurrent_outputs),

        "Overtemperature commands all actuators off":
            all_actuators_off(overtemperature_outputs),

        "Recovery state commands all actuators off":
            all_actuators_off(
                controller.get_actuator_outputs()
            ),

         "Recovery state commands all actuators off":
                    all_actuators_off(recovery_outputs),
    })


    # ========================================================
    # PRINT RESULTS
    # ========================================================

    print("\n" + "=" * 70)
    print("16S LFP PROTECTION AND BDU STATE MACHINE")
    print("=" * 70)

    for result in results:

        print(f"\n{result['scenario']}")
        print(f"  Final state: {result['final_state']}")
        print(f"  Fault history: {result['fault_history']}")

    print("\nVALIDATION RESULTS")

    for name, passed in checks.items():

        print(
            f"{name}: {'PASS' if passed else 'FAIL'}"
        )

    overall = all(checks.values())

    print(
        f"\nOVERALL: {'PASS' if overall else 'FAIL'}"
    )

    # ========================================================
    # SAVE REPORT
    # ========================================================

    output_path = Path(
        "results/metrics/lfp_16s_protection_bdu_results.json"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    report = {

        "project": "Simulation-First 16S Intelligent BMS",

        "test": "Protection and BDU State Machine",

        "thresholds": vars(ProtectionConfig()),

        "results": results,

        "validation": checks,

        "overall": "PASS" if overall else "FAIL",

        "limitations": [
            "Simulation only; no physical contactor validation.",
            "Protection thresholds are provisional assumptions.",
            "Precharge uses a simplified voltage-difference model.",
            "No contactor weld detection or hardware driver feedback.",
            "AI and communication independence tested at software logic level.",
            "No physical contactor switching time or arc model.",
            "Sensor plausibility and redundant-channel diagnostics are incomplete."
        ],
    }

    with output_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            report,
            file,
            indent=4
        )

    print(f"\nSaved: {output_path.resolve()}")

    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
