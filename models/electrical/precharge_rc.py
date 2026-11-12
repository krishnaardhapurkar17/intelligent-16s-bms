"""Analytical precharge model for the documented external R-C example."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PrechargeParameters:
    pack_voltage_v: float = 58.4
    capacitance_f: float = 0.002
    resistance_ohm: float = 100.0
    close_delta_v: float = 3.0
    timeout_s: float = 1.0
    time_step_s: float = 0.001
    initial_bus_voltage_v: float = 0.0


@dataclass(frozen=True)
class PrechargeSample:
    time_s: float
    bus_voltage_v: float
    bus_delta_v: float
    precharge_current_a: float
    resistor_power_w: float
    state: str
    precharge_contactor_command: bool
    main_contactor_command: bool


def _validate(parameters: PrechargeParameters) -> None:
    positive = {
        "pack_voltage_v": parameters.pack_voltage_v,
        "capacitance_f": parameters.capacitance_f,
        "resistance_ohm": parameters.resistance_ohm,
        "close_delta_v": parameters.close_delta_v,
        "timeout_s": parameters.timeout_s,
        "time_step_s": parameters.time_step_s,
    }
    for name, value in positive.items():
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if parameters.close_delta_v >= parameters.pack_voltage_v:
        raise ValueError("close_delta_v must be below pack_voltage_v")
    if (
        not math.isfinite(parameters.initial_bus_voltage_v)
        or not 0 <= parameters.initial_bus_voltage_v <= parameters.pack_voltage_v
    ):
        raise ValueError("initial_bus_voltage_v must be within pack-voltage bounds")


def simulate_precharge(
    parameters: PrechargeParameters = PrechargeParameters(),
    *,
    charging_path_available: bool = True,
) -> tuple[list[PrechargeSample], dict[str, float | bool | str | None]]:
    """Simulate an ideal source, series precharge resistor, and DC-link capacitor.

    The model omits source impedance, DC-link load/leakage, component tolerance,
    switching transients, contactor dynamics, and thermal coupling.
    """
    _validate(parameters)
    if type(charging_path_available) is not bool:
        raise ValueError("charging_path_available must be a bool")

    voltage = parameters.pack_voltage_v
    resistance = parameters.resistance_ohm
    capacitance = parameters.capacitance_f
    initial_voltage = parameters.initial_bus_voltage_v
    time_constant = resistance * capacitance
    initial_delta_v = voltage - initial_voltage
    theoretical_close_time = (
        0.0
        if initial_delta_v <= parameters.close_delta_v
        else time_constant * math.log(initial_delta_v / parameters.close_delta_v)
    )
    max_steps = math.ceil(parameters.timeout_s / parameters.time_step_s)
    samples: list[PrechargeSample] = []
    state = "PRECHARGE"
    close_time_s: float | None = None

    for step in range(max_steps + 1):
        time_s = min(step * parameters.time_step_s, parameters.timeout_s)
        if charging_path_available:
            bus_voltage = voltage - (voltage - initial_voltage) * math.exp(
                -time_s / time_constant
            )
        else:
            bus_voltage = initial_voltage

        delta_v = voltage - bus_voltage
        current = delta_v / resistance if charging_path_available else 0.0

        if delta_v <= parameters.close_delta_v:
            state = "CLOSED"
            close_time_s = time_s
        elif time_s >= parameters.timeout_s:
            state = "FAULT"

        samples.append(
            PrechargeSample(
                time_s=time_s,
                bus_voltage_v=bus_voltage,
                bus_delta_v=delta_v,
                precharge_current_a=current,
                resistor_power_w=current * current * resistance,
                state=state,
                precharge_contactor_command=state == "PRECHARGE",
                main_contactor_command=state == "CLOSED",
            )
        )

        if state in {"CLOSED", "FAULT"}:
            break

    final = samples[-1]
    energy_dissipated_j: float | None = None
    if close_time_s is not None:
        energy_dissipated_j = 0.5 * capacitance * (
            (voltage - initial_voltage) ** 2 - final.bus_delta_v**2
        )

    metrics: dict[str, float | bool | str | None] = {
        "state": state,
        "charging_path_available": charging_path_available,
        "theoretical_close_time_s": theoretical_close_time,
        "simulated_close_time_s": close_time_s,
        "initial_current_a": (
            (voltage - initial_voltage) / resistance
            if charging_path_available
            else 0.0
        ),
        "initial_resistor_power_w": (
            (voltage - initial_voltage) ** 2 / resistance
            if charging_path_available
            else 0.0
        ),
        "resistor_energy_until_close_j": energy_dissipated_j,
        "final_bus_voltage_v": final.bus_voltage_v,
        "final_bus_delta_v": final.bus_delta_v,
        "main_contactor_command": final.main_contactor_command,
    }
    return samples, metrics


def parameters_as_dict(parameters: PrechargeParameters) -> dict[str, float]:
    return asdict(parameters)
