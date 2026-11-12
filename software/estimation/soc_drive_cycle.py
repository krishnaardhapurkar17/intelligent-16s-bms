"""Synthetic dynamic-load SOC experiment using the project's provisional ECM."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
ECM_CONFIG_PATH = ROOT / "models" / "battery-parameters" / "lf100la_ecm_assumptions.json"
OCV_WEIGHT = 0.70
MIN_OCV_SLOPE_V_PER_PERCENT = 0.0025
REST_DURATION_S = 300


def synthetic_current_profile(duration_s: int, dt_s: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Return a deterministic pulse/regen profile; it is not WLTP/UDDS data."""
    if type(duration_s) is not int or duration_s <= 0:
        raise ValueError("duration_s must be a positive integer")
    if type(dt_s) is not int or dt_s <= 0 or duration_s % dt_s:
        raise ValueError("dt_s must be a positive integer divisor of duration_s")

    time_s = np.arange(0, duration_s + dt_s, dt_s, dtype=float)
    phase_s = np.mod(time_s, 120.0)
    current_a = np.select(
        [
            phase_s < 30,
            phase_s < 45,
            phase_s < 50,
            phase_s < 60,
            phase_s < 90,
            phase_s < 105,
        ],
        [0.0, 50.0, 100.0, -30.0, 20.0, 70.0],
        default=0.0,
    )
    return time_s, current_a


def _ocv_and_slope(soc: float, table: np.ndarray) -> tuple[float, float]:
    soc_fraction = float(np.clip(soc, 0.0, 1.0))
    index = int(
        np.clip(np.searchsorted(table[:, 0], soc_fraction, side="right") - 1, 0, len(table) - 2)
    )
    low_soc, high_soc = table[index : index + 2, 0]
    low_voltage, high_voltage = table[index : index + 2, 1]
    slope = float((high_voltage - low_voltage) / (high_soc - low_soc) / 100.0)
    voltage = float(np.interp(soc_fraction, table[:, 0], table[:, 1]))
    return voltage, slope


def _soc_from_ocv(voltage: float, table: np.ndarray) -> float:
    return float(np.interp(voltage, table[:, 1], table[:, 0]))


def run_soc_initialization_scenario(
    *,
    name: str,
    true_initial_soc: float,
    estimated_initial_soc: float,
    drive_duration_s: int = 1800,
    dt_s: int = 1,
    rest_duration_s: int = REST_DURATION_S,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compare coulomb counting and one rest-time OCV correction.

    Current sensing and OCV measurements are ideal to isolate initial-SOC error.
    """
    for label, value in (
        ("true_initial_soc", true_initial_soc),
        ("estimated_initial_soc", estimated_initial_soc),
    ):
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"{label} must be finite and between 0 and 1")
    if type(rest_duration_s) is not int or rest_duration_s <= 0:
        raise ValueError("rest_duration_s must be a positive integer")

    config = json.loads(ECM_CONFIG_PATH.read_text(encoding="utf-8"))
    capacity_ah = float(config["capacity_Ah"])
    r0_ohm = float(config["R0_ohm"])
    r1_ohm = float(config["R1_ohm"])
    time_constant_s = float(config["tau_seconds"])
    ocv_table = np.asarray(config["ocv_soc_table"], dtype=float)
    drive_time_s, drive_current_a = synthetic_current_profile(drive_duration_s, dt_s)

    time_s = np.arange(
        0,
        drive_duration_s + rest_duration_s + dt_s,
        dt_s,
        dtype=float,
    )
    current_a = np.zeros_like(time_s)
    current_a[: len(drive_current_a)] = drive_current_a
    true_soc = np.empty_like(time_s)
    coulomb_counted_soc = np.empty_like(time_s)
    fused_soc = np.empty_like(time_s)
    terminal_voltage_v = np.empty_like(time_s)

    true_soc[0] = true_initial_soc
    coulomb_counted_soc[0] = estimated_initial_soc
    fused_soc[0] = estimated_initial_soc
    polarization_v = 0.0
    decay = math.exp(-dt_s / time_constant_s)

    for index in range(len(time_s)):
        if index:
            previous_current = current_a[index - 1]
            soc_delta = previous_current * dt_s / (3600.0 * capacity_ah)
            true_soc[index] = float(np.clip(true_soc[index - 1] - soc_delta, 0.0, 1.0))
            coulomb_counted_soc[index] = float(
                np.clip(coulomb_counted_soc[index - 1] - soc_delta, 0.0, 1.0)
            )
            fused_soc[index] = float(
                np.clip(fused_soc[index - 1] - soc_delta, 0.0, 1.0)
            )
            polarization_v = (
                decay * polarization_v
                + previous_current * r1_ohm * (1.0 - decay)
            )

        ocv_v, _ = _ocv_and_slope(true_soc[index], ocv_table)
        terminal_voltage_v[index] = (
            ocv_v - current_a[index] * r0_ohm - polarization_v
        )

    correction_index = len(time_s) - 1
    if time_s[correction_index] < drive_duration_s + rest_duration_s:
        raise RuntimeError("SOC scenario did not include the full rest period")

    measured_rest_ocv_v, slope_v_per_percent = _ocv_and_slope(
        true_soc[correction_index],
        ocv_table,
    )
    correction_attempted = True
    if slope_v_per_percent >= MIN_OCV_SLOPE_V_PER_PERCENT:
        ocv_soc = _soc_from_ocv(measured_rest_ocv_v, ocv_table)
        fused_soc[correction_index] = (
            (1.0 - OCV_WEIGHT) * fused_soc[correction_index]
            + OCV_WEIGHT * ocv_soc
        )
        correction_applied = True
        correction_reason = "OCV_SLOPE_ACCEPTED"
    else:
        correction_applied = False
        correction_reason = "OCV_SLOPE_TOO_LOW"

    records: list[dict[str, Any]] = []
    for index, timestamp in enumerate(time_s):
        records.append(
            {
                "scenario": name,
                "time_s": float(timestamp),
                "current_a": float(current_a[index]),
                "true_soc_percent": float(true_soc[index] * 100.0),
                "coulomb_count_soc_percent": float(coulomb_counted_soc[index] * 100.0),
                "ocv_fused_soc_percent": float(fused_soc[index] * 100.0),
                "terminal_voltage_v": float(terminal_voltage_v[index]),
                "rest_ocv_correction_applied": (
                    correction_applied and index == correction_index
                ),
            }
        )

    metrics = {
        "scenario": name,
        "initial_soc_error_percentage_points": (
            estimated_initial_soc - true_initial_soc
        )
        * 100.0,
        "final_true_soc_percent": float(true_soc[-1] * 100.0),
        "final_coulomb_count_soc_percent": float(coulomb_counted_soc[-1] * 100.0),
        "final_ocv_fused_soc_percent": float(fused_soc[-1] * 100.0),
        "final_coulomb_count_error_percentage_points": float(
            (coulomb_counted_soc[-1] - true_soc[-1]) * 100.0
        ),
        "final_ocv_fused_error_percentage_points": float(
            (fused_soc[-1] - true_soc[-1]) * 100.0
        ),
        "rest_ocv_slope_v_per_soc_percentage_point": slope_v_per_percent,
        "rest_ocv_correction_attempted": correction_attempted,
        "rest_ocv_correction_applied": correction_applied,
        "rest_ocv_correction_reason": correction_reason,
    }
    return records, metrics
