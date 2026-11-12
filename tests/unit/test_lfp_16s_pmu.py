import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from software.pmu.lfp_16s_pmu import (
    PowerManagementUnit,
    PMUConfig,
)


class TestPMU(unittest.TestCase):

    def setUp(self):
        self.pmu = PowerManagementUnit(PMUConfig())

    def test_normal_measurement(self):
        reading = self.pmu.process_measurement(
            51.2, 20.0, timestamp=100.0
        )

        self.assertEqual(reading.measurement_quality, "VALID")
        self.assertEqual(reading.overcurrent_state, "NORMAL")
        self.assertAlmostEqual(reading.power_w, 1024.0)

    def test_overcurrent_detection(self):
        reading = self.pmu.process_measurement(
            51.2, 110.0, timestamp=100.0
        )

        self.assertEqual(reading.overcurrent_state, "FAULT")

    def test_current_sensor_unavailable(self):
        reading = self.pmu.process_measurement(
            51.2,
            20.0,
            timestamp=100.0,
            sensor_available=False,
        )

        self.assertEqual(
            reading.measurement_quality, "UNAVAILABLE"
        )

    def test_sensor_saturation(self):
        reading = self.pmu.process_measurement(
            51.2,
            20.0,
            timestamp=100.0,
            sensor_saturated=True,
        )

        self.assertEqual(reading.measurement_quality, "INVALID")

    def test_coulomb_counting(self):
        self.pmu.config.maximum_sample_age_seconds = 4000.0

        first = self.pmu.process_measurement(
            51.2, 10.0, timestamp=100.0
        )
        second = self.pmu.process_measurement(
            51.2, 10.0, timestamp=3700.0
        )

        self.assertEqual(first.measurement_quality, "VALID")
        self.assertEqual(second.measurement_quality, "VALID")

        self.assertAlmostEqual(
            self.pmu.get_accumulated_charge_ah(),
            10.0,
        )

    def test_current_sensor_bias_propagates_into_coulomb_counting(self):
        biased_pmu = PowerManagementUnit(
            PMUConfig(maximum_sample_age_seconds=4000.0)
        )
        reference_pmu = PowerManagementUnit(
            PMUConfig(maximum_sample_age_seconds=4000.0)
        )

        # True current is 10 A; the sensor reports a constant +2 A bias.
        for timestamp in (100.0, 3700.0):
            biased_reading = biased_pmu.process_measurement(
                51.2, 12.0, timestamp=timestamp
            )
            reference_reading = reference_pmu.process_measurement(
                51.2, 10.0, timestamp=timestamp
            )
            self.assertEqual(biased_reading.measurement_quality, "VALID")
            self.assertEqual(reference_reading.measurement_quality, "VALID")

        self.assertAlmostEqual(biased_pmu.get_accumulated_charge_ah(), 12.0)
        self.assertAlmostEqual(reference_pmu.get_accumulated_charge_ah(), 10.0)
        self.assertAlmostEqual(
            biased_pmu.get_accumulated_charge_ah()
            - reference_pmu.get_accumulated_charge_ah(),
            2.0,
        )


if __name__ == "__main__":
    unittest.main()
