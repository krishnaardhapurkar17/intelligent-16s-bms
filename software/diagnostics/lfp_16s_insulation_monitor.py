
"""
16S LFP Battery Pack - Insulation Monitoring Unit.

Simulation-only model for monitoring insulation resistance
between the high-voltage battery pack and chassis.

The IMU provides diagnostic information only.
It does not directly control or replace BDU protection.
"""

from dataclasses import dataclass, asdict
from enum import Enum
import json
import math


class MeasurementQuality(str, Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"


class InsulationState(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class IMUConfig:
    # Provisional simulation thresholds, not certified limits.
    warning_threshold_ohm: float = 500_000.0
    critical_threshold_ohm: float = 100_000.0

    maximum_sample_age_seconds: float = 2.0
    minimum_valid_resistance_ohm: float = 1.0
    maximum_valid_resistance_ohm: float = 100_000_000.0


@dataclass
class IMUReading:
    insulation_resistance_ohm: float | None
    measurement_quality: str
    insulation_state: str
    measurement_age_seconds: float | None
    diagnostic_message: str


class InsulationMonitoringUnit:

    def __init__(self, config=None):
        self.config = config or IMUConfig()

        if (
            self.config.critical_threshold_ohm
            >= self.config.warning_threshold_ohm
        ):
            raise ValueError(
                "Critical threshold must be lower than warning threshold."
            )

        if self.config.minimum_valid_resistance_ohm <= 0:
            raise ValueError("Minimum valid resistance must be positive.")

        if (
            self.config.maximum_valid_resistance_ohm
            <= self.config.warning_threshold_ohm
        ):
            raise ValueError(
                "Maximum valid resistance must exceed warning threshold."
            )

        self.last_reading = None

    def process_measurement(
        self,
        insulation_resistance_ohm,
        measurement_age_seconds=0.0,
        sensor_available=True,
        sensor_saturated=False,
    ):

        if not sensor_available:
            return self._create_reading(
                None,
                MeasurementQuality.UNAVAILABLE,
                InsulationState.UNKNOWN,
                measurement_age_seconds,
                "Insulation sensor unavailable.",
            )

        if sensor_saturated:
            return self._create_reading(
                None,
                MeasurementQuality.INVALID,
                InsulationState.UNKNOWN,
                measurement_age_seconds,
                "Insulation sensor saturation detected.",
            )

        if insulation_resistance_ohm is None:
            return self._create_reading(
                None,
                MeasurementQuality.INVALID,
                InsulationState.UNKNOWN,
                measurement_age_seconds,
                "Insulation resistance measurement missing.",
            )

        try:
            resistance = float(insulation_resistance_ohm)
            age = float(measurement_age_seconds)
        except (TypeError, ValueError):
            return self._create_reading(
                None,
                MeasurementQuality.INVALID,
                InsulationState.UNKNOWN,
                None,
                "Non-numeric measurement or sample age.",
            )

        if not math.isfinite(age) or age < 0:
            return self._create_reading(
                None,
                MeasurementQuality.INVALID,
                InsulationState.UNKNOWN,
                None,
                "Invalid measurement age.",
            )

        if age > self.config.maximum_sample_age_seconds:
            return self._create_reading(
                resistance if math.isfinite(resistance) else None,
                MeasurementQuality.WARNING,
                InsulationState.UNKNOWN,
                age,
                "Insulation measurement is stale.",
            )

        if not math.isfinite(resistance):
            return self._create_reading(
                None,
                MeasurementQuality.INVALID,
                InsulationState.UNKNOWN,
                age,
                "Non-finite insulation resistance.",
            )

        if not (
            self.config.minimum_valid_resistance_ohm
            <= resistance
            <= self.config.maximum_valid_resistance_ohm
        ):
            return self._create_reading(
                resistance,
                MeasurementQuality.INVALID,
                InsulationState.UNKNOWN,
                age,
                "Insulation resistance outside valid measurement range.",
            )

        if resistance <= self.config.critical_threshold_ohm:
            return self._create_reading(
                resistance,
                MeasurementQuality.VALID,
                InsulationState.CRITICAL,
                age,
                "Critical insulation resistance detected.",
            )

        if resistance <= self.config.warning_threshold_ohm:
            return self._create_reading(
                resistance,
                MeasurementQuality.VALID,
                InsulationState.WARNING,
                age,
                "Insulation resistance below warning threshold.",
            )

        return self._create_reading(
            resistance,
            MeasurementQuality.VALID,
            InsulationState.NORMAL,
            age,
            "Insulation resistance within configured limits.",
        )

    def _create_reading(
        self,
        resistance,
        quality,
        state,
        age,
        message,
    ):
        reading = IMUReading(
            insulation_resistance_ohm=resistance,
            measurement_quality=quality.value,
            insulation_state=state.value,
            measurement_age_seconds=age,
            diagnostic_message=message,
        )

        self.last_reading = reading
        return reading

    def export_reading(self):
        if self.last_reading is None:
            raise RuntimeError("No IMU measurement has been processed.")

        return asdict(self.last_reading)

    def export_json(self):
        return json.dumps(self.export_reading(), indent=4)


if __name__ == "__main__":
    imu = InsulationMonitoringUnit()

    test_values = [
        ("Healthy", 1_000_000),
        ("Warning", 300_000),
        ("Critical", 50_000),
    ]

    print("16S LFP INSULATION MONITORING SIMULATION")

    for scenario, resistance in test_values:
        reading = imu.process_measurement(resistance)

        print(
            f"{scenario}: "
            f"{reading.insulation_state} | "
            f"{reading.measurement_quality} | "
            f"{resistance / 1000:.1f} kOhm"
        )
