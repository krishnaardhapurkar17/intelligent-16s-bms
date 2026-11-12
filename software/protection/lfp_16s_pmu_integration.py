"""
PMU-to-BDU and PMU-to-supervisory integration.

Simulation-only integration adapter.
The BDU retains independent protection authority.
"""

import math
from dataclasses import replace

from software.pmu.lfp_16s_pmu import (
    PowerManagementUnit,
    MeasurementQuality,
    OvercurrentState,
)

from software.protection.lfp_16s_protection_bdu import (
    ProtectionBDU,
)


class PMUProtectionIntegration:

    def __init__(self, pmu, bdu, supervisory_controller=None):
        self.pmu = pmu
        self.bdu = bdu
        self.supervisory_controller = supervisory_controller

        # Both protection layers must use the same current threshold.
        pmu_limit = pmu.config.continuous_current_limit
        bdu_limit = bdu.config.pack_oc_a

        if not math.isclose(pmu_limit, bdu_limit):
            raise ValueError(
                "PMU current limit and BDU overcurrent threshold "
                "must match."
            )

        self.last_pmu_reading = None
        self.last_bdu_result = None

    def update_protection(
        self,
        protection_inputs,
        timestamp=None,
        sensor_available=True,
        sensor_saturated=False,
        dt_s=1.0,
    ):
        """
        Process PMU measurement and update BDU.

        Invalid, unavailable or stale current measurements are
        passed to the BDU as invalid sensor input.

        The BDU independently evaluates valid current measurements
        against its own protection threshold.
        """

        reading = self.pmu.process_measurement(
            pack_voltage_v=protection_inputs.pack_voltage_v,
            pack_current_a=protection_inputs.pack_current_a,
            timestamp=timestamp,
            sensor_available=sensor_available,
            sensor_saturated=sensor_saturated,
        )

        self.last_pmu_reading = reading

        bdu_inputs = protection_inputs

        if reading.measurement_quality != MeasurementQuality.VALID.value:
            bdu_inputs = replace(
                protection_inputs,
                pack_current_a=float("nan"),
            )

        self.last_bdu_result = self.bdu.update(
            bdu_inputs,
            dt_s=dt_s,
        )

        return {
            "pmu_reading": reading,
            "bdu_result": self.last_bdu_result,
            "current_measurement_valid": (
                reading.measurement_quality
                == MeasurementQuality.VALID.value
            ),
            "protection_authority": "BDU",
        }

    def evaluate_supervisory(
        self,
        context_df,
        cell_voltages,
        cell_temperatures,
        charge_mode,
        suspect_voltage_cells=None,
        suspect_temperature_cells=None,
        current_sensor_suspect=False,
    ):
        """
        Forward PMU measurement quality to the existing
        supervisory controller.
        """

        if self.supervisory_controller is None:
            raise RuntimeError(
                "No supervisory controller was supplied."
            )

        if self.last_pmu_reading is None:
            raise RuntimeError(
                "Process a PMU measurement before supervisory evaluation."
            )

        reading = self.last_pmu_reading

        pmu_current_suspect = (
            reading.measurement_quality
            != MeasurementQuality.VALID.value
        )

        pack_current = (
            reading.pack_current_a
            if reading.pack_current_a is not None
            else 0.0
        )

        return self.supervisory_controller.evaluate_context(
            context_df=context_df,
            cell_voltages=cell_voltages,
            cell_temperatures=cell_temperatures,
            pack_current=pack_current,
            bdu_state=self.bdu.state.value,
            protection_fault=self.bdu.fault_latched,
            charge_mode=charge_mode,
            suspect_voltage_cells=suspect_voltage_cells,
            suspect_temperature_cells=suspect_temperature_cells,
            current_sensor_suspect=(
                current_sensor_suspect or pmu_current_suspect
            ),
        )