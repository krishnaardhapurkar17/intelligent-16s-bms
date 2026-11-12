
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from software.diagnostics.lfp_16s_insulation_monitor import (
    InsulationMonitoringUnit,
    InsulationState,
    MeasurementQuality,
)


class TestInsulationMonitoringUnit(unittest.TestCase):

    def setUp(self):
        self.imu = InsulationMonitoringUnit()

    def test_normal_insulation(self):
        reading = self.imu.process_measurement(1_000_000)

        self.assertEqual(
            reading.insulation_state,
            InsulationState.NORMAL.value,
        )
        self.assertEqual(
            reading.measurement_quality,
            MeasurementQuality.VALID.value,
        )

    def test_warning_insulation(self):
        reading = self.imu.process_measurement(300_000)

        self.assertEqual(
            reading.insulation_state,
            InsulationState.WARNING.value,
        )

    def test_critical_insulation(self):
        reading = self.imu.process_measurement(50_000)

        self.assertEqual(
            reading.insulation_state,
            InsulationState.CRITICAL.value,
        )

    def test_sensor_unavailable(self):
        reading = self.imu.process_measurement(
            1_000_000,
            sensor_available=False,
        )

        self.assertEqual(
            reading.measurement_quality,
            MeasurementQuality.UNAVAILABLE.value,
        )
        self.assertEqual(
            reading.insulation_state,
            InsulationState.UNKNOWN.value,
        )

    def test_sensor_saturation(self):
        reading = self.imu.process_measurement(
            1_000_000,
            sensor_saturated=True,
        )

        self.assertEqual(
            reading.measurement_quality,
            MeasurementQuality.INVALID.value,
        )

    def test_stale_measurement(self):
        reading = self.imu.process_measurement(
            1_000_000,
            measurement_age_seconds=5.0,
        )

        self.assertEqual(
            reading.measurement_quality,
            MeasurementQuality.WARNING.value,
        )
        self.assertEqual(
            reading.insulation_state,
            InsulationState.UNKNOWN.value,
        )

    def test_invalid_measurement(self):
        reading = self.imu.process_measurement(float("nan"))

        self.assertEqual(
            reading.measurement_quality,
            MeasurementQuality.INVALID.value,
        )

    def test_missing_measurement(self):
        reading = self.imu.process_measurement(None)

        self.assertEqual(
            reading.measurement_quality,
            MeasurementQuality.INVALID.value,
        )

    def test_export_reading(self):
        self.imu.process_measurement(1_000_000)

        exported = self.imu.export_reading()

        self.assertEqual(
            exported["insulation_state"],
            InsulationState.NORMAL.value,
        )
        self.assertIn("diagnostic_message", exported)


if __name__ == "__main__":
    unittest.main(verbosity=2)
