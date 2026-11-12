import numpy as np

CELL_COUNT = 16


class SensorQualityGate:

    def evaluate(
        self,
        cell_voltages,
        cell_temperatures,
        pack_current,
        suspect_voltage_cells=None,
        suspect_temperature_cells=None,
        current_sensor_suspect=False
    ):

        suspect_voltage_cells = set(
            suspect_voltage_cells or []
        )

        suspect_temperature_cells = set(
            suspect_temperature_cells or []
        )

        voltage = np.asarray(
            cell_voltages,
            dtype=float
        )

        temperature = np.asarray(
            cell_temperatures,
            dtype=float
        )

        # Validate channel counts
        voltage_count_valid = (
            voltage.shape == (CELL_COUNT,)
        )

        temperature_count_valid = (
            temperature.shape == (CELL_COUNT,)
        )

        # Invalid global current measurement
        current_valid = (
            np.isscalar(pack_current)
            and np.isfinite(pack_current)
            and not current_sensor_suspect
        )

        # Initialize all channels as unavailable
        voltage_valid = np.zeros(
            CELL_COUNT,
            dtype=bool
        )

        temperature_valid = np.zeros(
            CELL_COUNT,
            dtype=bool
        )

        if voltage_count_valid:
            voltage_valid = np.isfinite(voltage)

        if temperature_count_valid:
            temperature_valid = np.isfinite(
                temperature
            )

        # Mark diagnostically suspect channels
        for cell in suspect_voltage_cells:
            if 1 <= cell <= CELL_COUNT:
                voltage_valid[cell - 1] = False

        for cell in suspect_temperature_cells:
            if 1 <= cell <= CELL_COUNT:
                temperature_valid[cell - 1] = False

        # A balancing channel requires valid voltage
        # and temperature measurements.
        cell_balancing_eligible = (
            voltage_valid & temperature_valid
        )

        # All mandatory sensor groups must be valid
        # before balancing is globally permitted.
        global_balancing_eligible = (
            voltage_count_valid
            and temperature_count_valid
            and current_valid
        )

        if not global_balancing_eligible:
            cell_balancing_eligible[:] = False

        return {

            "voltage_count_valid":
                voltage_count_valid,

            "temperature_count_valid":
                temperature_count_valid,

            "current_valid":
                bool(current_valid),

            "voltage_valid":
                voltage_valid,

            "temperature_valid":
                temperature_valid,

            "cell_balancing_eligible":
                cell_balancing_eligible,

            "global_balancing_eligible":
                bool(global_balancing_eligible),

            "invalid_voltage_cells": [
                int(i + 1)
                for i in range(CELL_COUNT)
                if not voltage_valid[i]
            ],

            "invalid_temperature_cells": [
                int(i + 1)
                for i in range(CELL_COUNT)
                if not temperature_valid[i]
            ]

        }