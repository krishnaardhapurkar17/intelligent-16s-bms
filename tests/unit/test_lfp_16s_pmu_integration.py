import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from software.pmu.lfp_16s_pmu import PowerManagementUnit
from software.protection.lfp_16s_protection_bdu import (
    ProtectionBDU,
    make_inputs,
)
from software.protection.lfp_16s_pmu_integration import (
    PMUProtectionIntegration,
)


class TestPMUIntegration(unittest.TestCase):

    def setUp(self):
        self.pmu = PowerManagementUnit()
        self.bdu = ProtectionBDU()

        self.integration = PMUProtectionIntegration(
            pmu=self.pmu,
            bdu=self.bdu,
        )

    def test_normal_measurement(self):
        result = self.integration.update_protection(
            make_inputs(current=20.0),
            timestamp=100.0,
        )

        self.assertTrue(result["current_measurement_valid"])
        self.assertEqual(result["bdu_result"]["state"], "OPEN")

    def test_overcurrent_trips_bdu(self):
        result = self.integration.update_protection(
            make_inputs(current=110.0),
            timestamp=100.0,
        )

        self.assertEqual(
            result["pmu_reading"].overcurrent_state,
            "FAULT",
        )
        self.assertEqual(result["bdu_result"]["state"], "FAULT")

    def test_unavailable_sensor_trips_bdu(self):
        result = self.integration.update_protection(
            make_inputs(current=20.0),
            timestamp=100.0,
            sensor_available=False,
        )

        self.assertFalse(result["current_measurement_valid"])
        self.assertEqual(result["bdu_result"]["state"], "FAULT")
        self.assertIn(
            "PACK_CURRENT_SENSOR_INVALID",
            result["bdu_result"]["active_faults"],
        )


if __name__ == "__main__":
    unittest.main()