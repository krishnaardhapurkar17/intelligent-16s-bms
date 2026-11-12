"""Generic shared-capacitor-bank cell-to-cell equalization model.

This is an energy-transfer abstraction for algorithm studies, not a component-
level switched-capacitor circuit, controller model, or hardware claim.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


CELL_COUNT = 16
DEFAULT_CAPACITY_AH = 100.0
DEFAULT_MAX_TRANSFER_CURRENT_A = 1.0
DEFAULT_EQUIVALENT_RESISTANCE_OHM = 0.25
DEFAULT_START_DELTA_SOC = 0.01
DEFAULT_STOP_DELTA_SOC = 0.005
DEFAULT_MAX_TEMP_C = 45.0
DEFAULT_AMBIENT_TEMP_C = 25.0
DEFAULT_THERMAL_CAPACITY_J_PER_C = 100.0
DEFAULT_COOLING_W_PER_C = 0.5


def soc_to_voltage(soc_fraction: np.ndarray | float):
    """Illustrative linear voltage map; not a measured LFP OCV curve."""
    return 3.0 + 0.6 * np.asarray(soc_fraction, dtype=float)


@dataclass
class TransferStep:
    source_cell: int | None
    target_cell: int | None
    current_a: float
    charge_ah: float
    source_energy_wh: float
    target_energy_wh: float
    loss_energy_wh: float


class SwitchedCapacitorBalancer:
    """Select highest and lowest cells for one capacitor-bank transfer cycle."""

    def __init__(self, capacity_ah: float = DEFAULT_CAPACITY_AH,
                 max_current_a: float = DEFAULT_MAX_TRANSFER_CURRENT_A,
                 equivalent_resistance_ohm: float = DEFAULT_EQUIVALENT_RESISTANCE_OHM,
                 start_delta_soc: float = DEFAULT_START_DELTA_SOC,
                 stop_delta_soc: float = DEFAULT_STOP_DELTA_SOC,
                 max_temp_c: float = DEFAULT_MAX_TEMP_C):
        for name, value in (("capacity_ah", capacity_ah), ("max_current_a", max_current_a),
                            ("equivalent_resistance_ohm", equivalent_resistance_ohm),
                            ("start_delta_soc", start_delta_soc), ("stop_delta_soc", stop_delta_soc),
                            ("max_temp_c", max_temp_c)):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number")
        if stop_delta_soc >= start_delta_soc or start_delta_soc >= 1:
            raise ValueError("SOC thresholds must satisfy 0 < stop < start < 1")
        self.capacity_ah = capacity_ah
        self.max_current_a = max_current_a
        self.equivalent_resistance_ohm = equivalent_resistance_ohm
        self.start_delta_soc = start_delta_soc
        self.stop_delta_soc = stop_delta_soc
        self.max_temp_c = max_temp_c
        self.active = False

    def step(self, soc, temperature_c=None, *, dt_s: float = 60.0,
             bdu_closed: bool = True, protection_fault: bool = False,
             sensor_valid=None, charge_mode: bool = True) -> tuple[np.ndarray, TransferStep]:
        values = np.asarray(soc, dtype=float).copy()
        if values.shape != (CELL_COUNT,) or not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
            raise ValueError("soc must contain 16 finite fractions in [0, 1]")
        if not math.isfinite(dt_s) or dt_s <= 0:
            raise ValueError("dt_s must be a positive finite number")
        temps = np.full(CELL_COUNT, DEFAULT_AMBIENT_TEMP_C) if temperature_c is None else np.asarray(temperature_c, dtype=float)
        valid = np.ones(CELL_COUNT, dtype=bool) if sensor_valid is None else np.asarray(sensor_valid, dtype=bool)
        if temps.shape != (CELL_COUNT,) or valid.shape != (CELL_COUNT,):
            raise ValueError("temperature_c and sensor_valid must each contain 16 values")
        self.active = bool(np.ptp(values) >= (self.stop_delta_soc if self.active else self.start_delta_soc))
        permitted = (self.active and bdu_closed and charge_mode and not protection_fault
                     and valid.all() and np.isfinite(temps).all() and np.all(temps < self.max_temp_c))
        if not permitted:
            return values, TransferStep(None, None, 0.0, 0.0, 0.0, 0.0, 0.0)

        source = int(np.argmax(values))
        target = int(np.argmin(values))
        difference = float(values[source] - values[target])
        if difference < self.stop_delta_soc:
            return values, TransferStep(None, None, 0.0, 0.0, 0.0, 0.0, 0.0)
        voltage = soc_to_voltage(values)
        current = min(self.max_current_a, abs(float(voltage[source] - voltage[target])) / self.equivalent_resistance_ohm)
        charge_ah = min(current * dt_s / 3600.0,
                        max(0.0, (values[source] - values[target]) * self.capacity_ah / 2.0))
        q_c = charge_ah * 3600.0
        source_wh = float(voltage[source] * q_c / 3600.0)
        target_wh = float(voltage[target] * q_c / 3600.0)
        loss_wh = max(0.0, source_wh - target_wh)
        soc_delta = charge_ah / self.capacity_ah
        values[source] -= soc_delta
        values[target] += soc_delta
        return values, TransferStep(source + 1, target + 1, current, charge_ah,
                                    source_wh, target_wh, loss_wh)


def run_active(initial_soc, *, max_hours: float = 1000.0, dt_s: float = 60.0,
               temperature_c=None, protection_fault: bool = False,
               sensor_valid=None, max_temp_c: float = DEFAULT_MAX_TEMP_C) -> dict:
    soc = np.asarray(initial_soc, dtype=float).copy()
    balancer = SwitchedCapacitorBalancer(max_temp_c=max_temp_c)
    temperature = np.full(CELL_COUNT, DEFAULT_AMBIENT_TEMP_C) if temperature_c is None else np.asarray(temperature_c, dtype=float).copy()
    initial = soc.copy()
    transferred_wh = lost_wh = elapsed_s = 0.0
    steps = int(max_hours * 3600 / dt_s)
    for _ in range(steps):
        if float(np.ptp(soc)) <= balancer.stop_delta_soc:
            break
        before = soc
        soc, transfer = balancer.step(soc, temperature, dt_s=dt_s,
                                      protection_fault=protection_fault,
                                      sensor_valid=sensor_valid)
        if transfer.current_a == 0:
            break
        transferred_wh += transfer.target_energy_wh
        lost_wh += transfer.loss_energy_wh
        heat_w = transfer.loss_energy_wh * 3600.0 / dt_s
        temperature[(transfer.source_cell or 1) - 1] += heat_w * dt_s / DEFAULT_THERMAL_CAPACITY_J_PER_C
        temperature[(transfer.target_cell or 1) - 1] += heat_w * dt_s / DEFAULT_THERMAL_CAPACITY_J_PER_C
        temperature += (-DEFAULT_COOLING_W_PER_C * (temperature - DEFAULT_AMBIENT_TEMP_C)
                        * dt_s / DEFAULT_THERMAL_CAPACITY_J_PER_C)
        elapsed_s += dt_s
        if np.array_equal(before, soc):
            break
    return {"initial_soc": initial, "final_soc": soc, "elapsed_s": elapsed_s,
            "range_initial": float(np.ptp(initial)), "range_final": float(np.ptp(soc)),
            "delivered_energy_wh": transferred_wh, "loss_energy_wh": lost_wh,
            "charge_conservation_error_ah": float((np.sum(soc) - np.sum(initial)) * DEFAULT_CAPACITY_AH),
            "max_temperature_c": float(np.max(temperature)),
            "converged": float(np.ptp(soc)) <= balancer.stop_delta_soc}
