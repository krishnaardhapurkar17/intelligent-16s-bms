
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from software.diagnostics.lfp_16s_insulation_monitor import (
    InsulationMonitoringUnit,
)
from software.diagnostics.lfp_16s_supervisory_controller import (
    SupervisoryController,
)


class TestIMUSupervisoryIntegration(unittest.TestCase):

    def setUp(self):
        self.controller = SupervisoryController()
        self.imu = InsulationMonitoringUnit()

        self.context = pd.DataFrame({
            "SOH_Scenario": ["SIM-SOH-001_HEALTHY"] * 16,
            "RUL_Scenario": ["SIM-RUL-001"] * 16,
            "SOC_Operating_Scenario": ["LFP_FLAT_REGION"] * 16,
            "Cell": list(range(1, 17)),
            "Capacity_Fault_Detected": [False] * 16,
            "Resistance_Fault_Detected": [False] * 16,
            "Estimated_SOC_percent": [85.0] * 16,
            "Estimated_Capacity_SOH_percent": [100.0] * 16,
            "Estimated_Resistance_Growth_percent": [0.0] * 16,
            "Capacity_RUL_cycles": [1800.0] * 16,
            "Resistance_RUL_cycles": [1800.0] * 16,
            "Estimated_Total_RUL_cycles": [1800.0] * 16,
            "Limiting_Mechanism": ["Capacity"] * 16,
        })

    def evaluate(self, resistance=None, available=True):
        reading = self.imu.process_measurement(
            insulation_resistance_ohm=resistance,
            sensor_available=available,
        )

        decisions, quality = self.controller.evaluate_context(
            context_df=self.context,
            cell_voltages=np.full(16, 3.35),
            cell_temperatures=np.full(16, 25.0),
            pack_current=10.0,
            bdu_state="CLOSED",
            protection_fault=False,
            charge_mode=True,
            insulation_state=reading.insulation_state,
            insulation_measurement_quality=(
                reading.measurement_quality
            ),
        )

        return decisions, quality

    def test_normal_insulation_allows_balancing(self):
        decisions, _ = self.evaluate(1_000_000)

        self.assertTrue(
            all(item["Balancing_Eligible"] for item in decisions)
        )
        self.assertTrue(
            all(item["Insulation_State"] == "NORMAL"
                for item in decisions)
        )

    def test_warning_insulation_inhibits_balancing(self):
        decisions, _ = self.evaluate(300_000)

        self.assertTrue(
            all(not item["Balancing_Eligible"] for item in decisions)
        )
        self.assertTrue(
            all(item["Insulation_State"] == "WARNING"
                for item in decisions)
        )

    def test_critical_insulation_inhibits_balancing(self):
        decisions, _ = self.evaluate(50_000)

        self.assertTrue(
            all(not item["Balancing_Eligible"] for item in decisions)
        )
        self.assertTrue(
            all(item["Insulation_State"] == "CRITICAL"
                for item in decisions)
        )

    def test_unavailable_imu_inhibits_balancing(self):
        decisions, _ = self.evaluate(
            resistance=None,
            available=False,
        )

        self.assertTrue(
            all(not item["Balancing_Eligible"] for item in decisions)
        )
        self.assertTrue(
            all(item["Insulation_State"] == "UNKNOWN"
                for item in decisions)
        )

    def test_bdu_authority_remains_unchanged(self):
        decisions, _ = self.evaluate(50_000)

        self.assertTrue(
            all(item["Protection_Authority"] == "BDU_ONLY"
                for item in decisions)
        )
        self.assertTrue(
            all(item["AI_Role"] == "ADVISORY_ONLY"
                for item in decisions)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
