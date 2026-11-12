"""
16S Intelligent BMS - Power Management Unit (PMU)

Simulation-only PMU model.

Functions:
- Pack current measurement
- Voltage and power calculation
- Coulomb-counting input
- Current sensor quality assessment
- Overcurrent detection
- Sensor fault handling

This is not a physical protection circuit.
"""

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional
import json
import time


class MeasurementQuality(Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"


class OvercurrentState(Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    FAULT = "FAULT"
    UNKNOWN = "UNKNOWN"


@dataclass
class PMUConfig:
    nominal_pack_voltage: float = 51.2
    continuous_current_limit: float = 100.0
    warning_current_fraction: float = 0.90
    maximum_sensor_current: float = 200.0
    maximum_sample_age_seconds: float = 2.0


@dataclass
class PMUReading:
    timestamp: float
    pack_voltage_v: Optional[float]
    pack_current_a: Optional[float]
    power_w: Optional[float]
    measurement_quality: str
    overcurrent_state: str
    coulomb_counting_available: bool
    fault_reason: Optional[str]


class PowerManagementUnit:

    def __init__(self, config: Optional[PMUConfig] = None):
        self.config = config or PMUConfig()

        if self.config.continuous_current_limit <= 0:
            raise ValueError("Current limit must be positive")

        if not 0 < self.config.warning_current_fraction < 1:
            raise ValueError("Warning fraction must be between 0 and 1")

        if self.config.maximum_sensor_current <= 0:
            raise ValueError("Maximum sensor current must be positive")

        self.accumulated_charge_ah = 0.0
        self.previous_timestamp = None
        self.previous_current = None
        self.last_reading = None

    def process_measurement(
        self,
        pack_voltage_v: Optional[float],
        pack_current_a: Optional[float],
        timestamp: Optional[float] = None,
        sensor_available: bool = True,
        sensor_saturated: bool = False,
    ) -> PMUReading:

        now = time.time() if timestamp is None else float(timestamp)

        quality = MeasurementQuality.VALID
        overcurrent = OvercurrentState.UNKNOWN
        fault_reason = None

        if not sensor_available:
            quality = MeasurementQuality.UNAVAILABLE
            fault_reason = "Current sensor unavailable"

        elif sensor_saturated:
            quality = MeasurementQuality.INVALID
            fault_reason = "Current sensor saturated"

        elif pack_voltage_v is None or pack_current_a is None:
            quality = MeasurementQuality.INVALID
            fault_reason = "Missing voltage or current measurement"

        elif not all(
            map(
                lambda value: isinstance(value, (int, float))
                and __import__("math").isfinite(value),
                (pack_voltage_v, pack_current_a),
            )
        ):
            quality = MeasurementQuality.INVALID
            fault_reason = "Non-finite measurement"

        elif pack_voltage_v <= 0:
            quality = MeasurementQuality.INVALID
            fault_reason = "Invalid pack voltage"

        elif abs(pack_current_a) > self.config.maximum_sensor_current:
            quality = MeasurementQuality.INVALID
            fault_reason = "Current exceeds sensor measurement range"

        elif self.previous_timestamp is not None and now <= self.previous_timestamp:
            quality = MeasurementQuality.INVALID
            fault_reason = "Non-increasing measurement timestamp"

        elif (
            self.previous_timestamp is not None
            and now - self.previous_timestamp
            > self.config.maximum_sample_age_seconds
        ):
            quality = MeasurementQuality.WARNING
            fault_reason = "Measurement interval exceeds configured limit"

        power = None
        coulomb_available = False

        if quality in (
            MeasurementQuality.VALID,
            MeasurementQuality.WARNING,
        ):

            voltage = float(pack_voltage_v)
            current = float(pack_current_a)

            power = voltage * current

            if abs(current) >= self.config.continuous_current_limit:
                overcurrent = OvercurrentState.FAULT

            elif abs(current) >= (
                self.config.continuous_current_limit
                * self.config.warning_current_fraction
            ):
                overcurrent = OvercurrentState.WARNING

            else:
                overcurrent = OvercurrentState.NORMAL

            if quality == MeasurementQuality.VALID:

                if self.previous_timestamp is not None:
                    dt = now - self.previous_timestamp

                    average_current = (
                        current + self.previous_current
                    ) / 2.0

                    # Positive current represents discharge.
                    self.accumulated_charge_ah += (
                        average_current * dt / 3600.0
                    )

                self.previous_timestamp = now
                self.previous_current = current
                coulomb_available = True

        reading = PMUReading(
            timestamp=now,
            pack_voltage_v=(
                float(pack_voltage_v)
                if pack_voltage_v is not None
                else None
            ),
            pack_current_a=(
                float(pack_current_a)
                if pack_current_a is not None
                else None
            ),
            power_w=power,
            measurement_quality=quality.value,
            overcurrent_state=overcurrent.value,
            coulomb_counting_available=coulomb_available,
            fault_reason=fault_reason,
        )

        self.last_reading = reading
        return reading

    def get_accumulated_charge_ah(self) -> float:
        return self.accumulated_charge_ah

    def export_reading(self) -> dict:
        if self.last_reading is None:
            raise RuntimeError("No PMU measurement available")

        return asdict(self.last_reading)

    def export_json(self) -> str:
        return json.dumps(self.export_reading(), indent=4)