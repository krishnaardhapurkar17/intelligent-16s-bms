
import json
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# MODEL CONFIGURATION
# ============================================================

CELL_COUNT = 16

CAPACITY_AH = 100.0

BALANCING_RESISTANCE_OHM = 100.0

BALANCE_START_DELTA_V = 0.015
BALANCE_STOP_DELTA_V = 0.005

MAX_BALANCING_TEMP_C = 45.0

AMBIENT_TEMP_C = 25.0

THERMAL_CAPACITY_J_PER_C = 100.0
COOLING_COEFFICIENT_W_PER_C = 0.5

TIME_STEP_S = 1.0
SIMULATION_DURATION_S = 3600

RANDOM_SEED = 20261031


# ============================================================
# ILLUSTRATIVE LFP VOLTAGE MODEL
# ============================================================

def soc_to_voltage(soc):
    """
    Simplified linear voltage mapping.

    This is an illustrative simulation relationship.
    It is NOT a calibrated LFP OCV-SOC curve.
    """

    return 3.0 + 0.6 * (soc / 100.0)


# ============================================================
# PASSIVE BALANCING CONTROLLER
# ============================================================

class PassiveBalancer:

    def __init__(self):

        self.balancing_active = np.zeros(
            CELL_COUNT, dtype=bool
        )

    def update_eligibility(
    self,
    cell_voltages,
    cell_temperatures,
    bdu_state,
    charge_mode,
    protection_fault
    ):

        # Global safety interlocks
        global_enable = (
            bdu_state == "CLOSED"
            and charge_mode
            and not protection_fault
        )

        if not global_enable:
            self.balancing_active[:] = False
            return self.balancing_active.copy()

        minimum_voltage = np.min(cell_voltages)

        for i in range(CELL_COUNT):

            # Thermal interlock for each cell
            if cell_temperatures[i] >= MAX_BALANCING_TEMP_C:
                self.balancing_active[i] = False
                continue

            voltage_difference = (
                cell_voltages[i] - minimum_voltage
            )

            if self.balancing_active[i]:

                # Hysteresis
                if voltage_difference <= BALANCE_STOP_DELTA_V:
                    self.balancing_active[i] = False

            else:

                if voltage_difference >= BALANCE_START_DELTA_V:
                    self.balancing_active[i] = True

        return self.balancing_active.copy()


# ============================================================
# CELL MODEL
# ============================================================

class CellBank:

    def __init__(
        self,
        initial_soc,
        initial_temperature=None
    ):

        self.soc = np.array(
            initial_soc, dtype=float
        )

        if initial_temperature is None:

            self.temperature = np.full(
                CELL_COUNT,
                AMBIENT_TEMP_C,
                dtype=float
            )

        else:

            self.temperature = np.array(
                initial_temperature,
                dtype=float
            )

        self.voltage = np.array([
            soc_to_voltage(value)
            for value in self.soc
        ])

        self.balancing_current = np.zeros(CELL_COUNT)
        self.balancing_power = np.zeros(CELL_COUNT)
        self.dissipated_energy_wh = np.zeros(CELL_COUNT)

    def update(self, balancing_active, dt_s):

        self.balancing_current[:] = 0.0
        self.balancing_power[:] = 0.0

        for i in range(CELL_COUNT):

            if balancing_active[i]:

                voltage = self.voltage[i]

                current = (
                    voltage / BALANCING_RESISTANCE_OHM
                )

                power = voltage * current

                # Capacity removed by bleed current
                discharged_ah = (
                    current * dt_s / 3600.0
                )

                soc_reduction = (
                    discharged_ah / CAPACITY_AH
                ) * 100.0

                self.soc[i] = max(
                    0.0,
                    self.soc[i] - soc_reduction
                )

                self.balancing_current[i] = current
                self.balancing_power[i] = power

                self.dissipated_energy_wh[i] += (
                    power * dt_s / 3600.0
                )

            # Lumped thermal model
            heat_generation = self.balancing_power[i]

            heat_loss = (
                COOLING_COEFFICIENT_W_PER_C
                * (
                    self.temperature[i]
                    - AMBIENT_TEMP_C
                )
            )

            temperature_change = (
                (heat_generation - heat_loss)
                / THERMAL_CAPACITY_J_PER_C
            ) * dt_s

            self.temperature[i] += temperature_change

            # Update voltage from illustrative SOC relationship
            self.voltage[i] = soc_to_voltage(
                self.soc[i]
            )


# ============================================================
# SCENARIO SIMULATOR
# ============================================================

def run_scenario(
    scenario_name,
    initial_soc,
    bdu_state="CLOSED",
    charge_mode=True,
    protection_fault=False,
    initial_temperature=None
):

    cells = CellBank(
        initial_soc,
        initial_temperature
    )

    balancer = PassiveBalancer()

    history = []

    for step in range(
        int(SIMULATION_DURATION_S / TIME_STEP_S)
    ):

        time_s = step * TIME_STEP_S

        active = balancer.update_eligibility(
            cells.voltage,
            cells.temperature,
            bdu_state,
            charge_mode,
            protection_fault
        )

        cells.update(active, TIME_STEP_S)

        # Save data every 60 seconds and at final step
        if step % 60 == 0 or step == (
            SIMULATION_DURATION_S / TIME_STEP_S - 1
        ):

            for i in range(CELL_COUNT):

                history.append({

                    "Scenario": scenario_name,

                    "Time_s": time_s,

                    "Cell": i + 1,

                    "SOC_percent": cells.soc[i],

                    "Voltage_V": cells.voltage[i],

                    "Temperature_C": cells.temperature[i],

                    "Balancing_Active": bool(active[i]),

                    "Balancing_Current_A":
                        cells.balancing_current[i],

                    "Balancing_Power_W":
                        cells.balancing_power[i],

                    "Dissipated_Energy_Wh":
                        cells.dissipated_energy_wh[i],

                })

    return {
        "scenario": scenario_name,
        "final_soc": cells.soc.copy(),
        "final_voltage": cells.voltage.copy(),
        "final_temperature": cells.temperature.copy(),
        "final_balancing_active": balancer.balancing_active.copy(),
        "balancing_current": cells.balancing_current.copy(),
        "balancing_power": cells.balancing_power.copy(),
        "dissipated_energy_wh":
            cells.dissipated_energy_wh.copy(),
        "history": history,
    }

def json_serializer(obj):
    if isinstance(obj, np.generic):
        return obj.item()

    if isinstance(obj, np.ndarray):
        return obj.tolist()

    if isinstance(obj, Path):
        return str(obj)

    raise TypeError(
        f"Object of type {type(obj).__name__} "
        "is not JSON serializable"
    )

# ============================================================
# VALIDATION
# ============================================================

def main():

    # --------------------------------------------------------
    # SCENARIO 1: HEALTHY BALANCED CELLS
    # --------------------------------------------------------

    healthy_soc = np.full(CELL_COUNT, 85.0)

    healthy = run_scenario(
        "SIM-BAL-001_HEALTHY",
        healthy_soc
    )

    # --------------------------------------------------------
    # SCENARIO 2: CELL 8 HAS LOWER SOC
    # --------------------------------------------------------

    imbalanced_soc = np.full(CELL_COUNT, 85.0)
    imbalanced_soc[7] = 80.0

    imbalance = run_scenario(
        "SIM-BAL-002_CELL_8_IMBALANCE",
        imbalanced_soc
    )

    # --------------------------------------------------------
    # SCENARIO 3: BDU OPEN
    # --------------------------------------------------------

    bdu_open = run_scenario(
        "SIM-BAL-003_BDU_OPEN",
        imbalanced_soc,
        bdu_state="OPEN"
    )

    # --------------------------------------------------------
    # SCENARIO 4: PROTECTION FAULT ACTIVE
    # --------------------------------------------------------

    protection_active = run_scenario(
        "SIM-BAL-004_PROTECTION_FAULT",
        imbalanced_soc,
        protection_fault=True
    )

    # --------------------------------------------------------
    # SCENARIO 5: ONE CELL EXCEEDS THERMAL LIMIT
    # --------------------------------------------------------

    initial_temperatures = np.full(
        CELL_COUNT,
        AMBIENT_TEMP_C
    )

    initial_temperatures[0] = 50.0

    thermal = run_scenario(
        "SIM-BAL-005_THERMAL_INTERLOCK",
        imbalanced_soc,
        initial_temperature=initial_temperatures
    )

    scenarios = [
        healthy,
        imbalance,
        bdu_open,
        protection_active,
        thermal,
    ]

    # --------------------------------------------------------
    # VALIDATION CHECKS
    # --------------------------------------------------------

    checks = {

        "Healthy cells do not require balancing":
            not np.any(
                healthy["final_balancing_active"]
            ),

        "Imbalanced cells trigger balancing":
            np.any(
                imbalance["final_balancing_active"]
            ),

        "Cell 8 lower-SOC cell is not discharged":
            imbalance["final_soc"][7] == 80.0,

        "Higher-SOC cells are selected":
            np.all(
                imbalance["final_balancing_active"][
                    [i for i in range(CELL_COUNT) if i != 7]
                ]
            ),

        "Balancing disabled when BDU is OPEN":
            not np.any(
                bdu_open["final_balancing_active"]
            ),

        "Balancing disabled during protection fault":
            not np.any(
                protection_active["final_balancing_active"]
            ),

        "Overtemperature cell excluded": (
            any(
                row["Cell"] == 1
                and row["Temperature_C"] >= MAX_BALANCING_TEMP_C
                for row in thermal["history"]
            )
            and all(
                not row["Balancing_Active"]
                and row["Balancing_Current_A"] == 0.0
                and row["Balancing_Power_W"] == 0.0
                for row in thermal["history"]
                if (
                    row["Cell"] == 1
                    and row["Temperature_C"] >= MAX_BALANCING_TEMP_C
                )
            )
        ),

        "Balancing current is non-negative":
            all(
                np.all(result["balancing_current"] >= 0)
                for result in scenarios
            ),

        "Balancing power is non-negative":
            all(
                np.all(result["balancing_power"] >= 0)
                for result in scenarios
            ),

        "Energy dissipation is non-negative":
            all(
                np.all(result["dissipated_energy_wh"] >= 0)
                for result in scenarios
            ),

        "SOC remains within physical limits":
            all(
                np.all(result["final_soc"] >= 0)
                and np.all(result["final_soc"] <= 100)
                for result in scenarios
            ),

        "Temperature remains finite":
            all(
                np.all(np.isfinite(result["final_temperature"]))
                for result in scenarios
            ),
    }

    # --------------------------------------------------------
    # EXPORT DATA
    # --------------------------------------------------------

    all_history = []

    for result in scenarios:
        all_history.extend(result["history"])

    dataframe = pd.DataFrame(all_history)

    output_directory = Path("results/metrics")
    output_directory.mkdir(parents=True, exist_ok=True)

    csv_path = (
        output_directory
        / "lfp_16s_passive_balancing.csv"
    )

    dataframe.to_csv(csv_path, index=False)

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary = {
        "project": "Simulation-First 16S Intelligent BMS",
        "test": "Passive Cell Balancing",
        "cell_count": CELL_COUNT,
        "capacity_Ah": CAPACITY_AH,
        "balancing_resistance_ohm":
            BALANCING_RESISTANCE_OHM,
        "start_delta_voltage_V":
            BALANCE_START_DELTA_V,
        "stop_delta_voltage_V":
            BALANCE_STOP_DELTA_V,
        "simulation_duration_s":
            SIMULATION_DURATION_S,
        "scenarios": {},
        "validation": checks,
        "overall": "PASS" if all(checks.values()) else "FAIL",
        "limitations": [
            "Illustrative linear LFP voltage-SOC relationship.",
            "No calibrated LFP OCV curve.",
            "No cell-to-cell capacity or resistance variation.",
            "Lumped thermal approximation.",
            "No physical balancing resistor validation.",
            "No active balancing or energy transfer between cells.",
            "Balancing is permitted only in the simulated CLOSED charging state.",
        ],
    }

    for result in scenarios:

        summary["scenarios"][result["scenario"]] = {

            "final_soc_percent":
                result["final_soc"].tolist(),

            "final_voltage_V":
                result["final_voltage"].tolist(),

            "final_temperature_C":
                result["final_temperature"].tolist(),

            "final_balancing_active":
                result["final_balancing_active"].tolist(),

            "total_dissipated_energy_Wh":
                float(np.sum(result["dissipated_energy_wh"])),

            "active_balancing_cells":
                np.where(
                    result["final_balancing_active"]
                )[0].astype(int).tolist(),

        }

    json_path = (
        output_directory
        / "lfp_16s_passive_balancing_summary.json"
    )

    with json_path.open("w", encoding="utf-8") as file:

        json.dump(
            summary,
            file,
            indent=4,
            default=json_serializer
        )

    # --------------------------------------------------------
    # PRINT RESULTS
    # --------------------------------------------------------

    print("=" * 70)
    print("16S LFP PASSIVE BALANCING SIMULATION")
    print("=" * 70)

    for result in scenarios:

        print(f"\n{result['scenario']}")

        print(
            "Final SOC:",
            np.round(result["final_soc"], 4)
        )

        print(
            "Final voltage:",
            np.round(result["final_voltage"], 4)
        )

        print(
            "Final balancing active:",
            result["final_balancing_active"]
        )

        print(
            "Total dissipated energy (Wh):",
            round(
                np.sum(result["dissipated_energy_wh"]),
                6
            )
        )

    print("\nVALIDATION RESULTS")

    for name, passed in checks.items():

        print(
            f"{name}: {'PASS' if passed else 'FAIL'}"
        )

    overall = all(checks.values())

    print(
        f"\nOVERALL: {'PASS' if overall else 'FAIL'}"
    )

    print(f"\nSaved: {csv_path.resolve()}")
    print(f"Saved: {json_path.resolve()}")

    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
