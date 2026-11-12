
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from software.pmu.lfp_16s_state_of_power import (
    StateOfPowerEstimator,
    SOPConfig,
)


class TestStateOfPowerEstimator(unittest.TestCase):

    def setUp(self):
        self.estimator = StateOfPowerEstimator()

        self.voltages = [3.2] * 16
        self.resistances = [0.0005] * 16
        self.capacities = [100.0] * 16
        self.soc = [50.0] * 16
        self.temperatures = [25.0] * 16

    def calculate(self, **overrides):

        inputs = {
            "cell_voltages_v": self.voltages,
            "cell_resistances_ohm": self.resistances,
            "cell_capacities_ah": self.capacities,
            "cell_soc_percent": self.soc,
            "cell_temperatures_c": self.temperatures,
            "pack_voltage_v": 51.2,
            "pack_current_a": 0.0,
            "thermal_state": "NORMAL",
        }

        inputs.update(overrides)

        return self.estimator.process_measurements(**inputs)

    def test_normal_operation(self):

        reading = self.calculate()

        self.assertEqual(reading.status, "AVAILABLE")
        self.assertEqual(reading.measurement_quality, "VALID")

        self.assertAlmostEqual(
            reading.maximum_discharge_current_a, 100.0
        )

        self.assertAlmostEqual(
            reading.maximum_charge_current_a, 100.0
        )

        self.assertAlmostEqual(
            reading.maximum_discharge_power_w, 5120.0
        )

        self.assertAlmostEqual(
            reading.maximum_charge_power_w, 5120.0
        )

    def test_discharge_limiting_cell_identification(self):

        self.voltages[7] = 2.52

        reading = self.calculate()

        self.assertEqual(reading.discharge_limiting_cell, 8)
        self.assertAlmostEqual(
            reading.maximum_discharge_current_a, 40.0
        )

    def test_charge_limiting_cell_identification(self):

        self.voltages[11] = 3.64

        reading = self.calculate()

        self.assertEqual(reading.charge_limiting_cell, 12)
        self.assertAlmostEqual(
            reading.maximum_charge_current_a, 20.0
        )

    def test_capacity_degradation_reduces_power(self):

        self.capacities[7] = 80.0

        reading = self.calculate()

        self.assertEqual(reading.discharge_limiting_cell, 8)
        self.assertEqual(reading.charge_limiting_cell, 8)

        self.assertAlmostEqual(
            reading.maximum_discharge_current_a, 80.0
        )

        self.assertAlmostEqual(
            reading.maximum_charge_current_a, 80.0
        )

    def test_resistance_increase_reduces_voltage_limited_power(self):

        self.voltages[4] = 2.55
        self.resistances[4] = 0.001

        reading = self.calculate()

        self.assertEqual(reading.discharge_limiting_cell, 5)

        self.assertAlmostEqual(
            reading.maximum_discharge_current_a, 50.0
        )

    def test_low_soc_inhibits_discharge(self):

        self.soc[0] = 5.0

        reading = self.calculate()

        self.assertEqual(
            reading.maximum_discharge_current_a, 0.0
        )

    def test_high_soc_inhibits_charge(self):

        self.soc[0] = 95.0

        reading = self.calculate()

        self.assertEqual(
            reading.maximum_charge_current_a, 0.0
        )

    def test_warning_temperature_derates_power(self):

        reading = self.calculate(thermal_state="WARNING")

        self.assertAlmostEqual(
            reading.maximum_discharge_current_a, 50.0
        )

        self.assertAlmostEqual(
            reading.maximum_charge_current_a, 50.0
        )

        self.assertIn(
            "THERMAL_WARNING_DERATING_APPLIED",
            reading.reasons,
        )

    def test_critical_temperature_inhibits_power(self):

        reading = self.calculate(thermal_state="CRITICAL")

        self.assertEqual(
            reading.maximum_discharge_current_a, 0.0
        )

        self.assertEqual(
            reading.maximum_charge_current_a, 0.0
        )

        self.assertIn(
            "CRITICAL_THERMAL_STATE_POWER_INHIBITED",
            reading.reasons,
        )

    def test_invalid_thermal_quality_makes_sop_unavailable(self):

        reading = self.calculate(
            thermal_measurement_quality="INVALID"
        )

        self.assertEqual(reading.status, "UNAVAILABLE")
        self.assertEqual(
            reading.maximum_discharge_power_w, 0.0
        )
        self.assertEqual(
            reading.maximum_charge_power_w, 0.0
        )

    def test_invalid_cell_channel_count_rejected(self):

        reading = self.calculate(
            cell_voltages_v=[3.2] * 15
        )

        self.assertEqual(reading.status, "UNAVAILABLE")
        self.assertEqual(
            reading.maximum_discharge_power_w, 0.0
        )

    def test_nonfinite_measurement_rejected(self):

        voltages = [3.2] * 16
        voltages[3] = float("nan")

        reading = self.calculate(
            cell_voltages_v=voltages
        )

        self.assertEqual(reading.status, "UNAVAILABLE")
        self.assertIn(
            "NONFINITE_VALUE_CELL_VOLTAGES_V",
            reading.reasons,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
