
from dataclasses import asdict, dataclass
from enum import Enum
import json
import math


CELL_COUNT = 16


class ThermalState(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class MeasurementQuality(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class TMUConfig:
    warning_temperature_c: float = 45.0
    critical_temperature_c: float = 55.0
    maximum_temperature_spread_c: float = 10.0
    critical_temperature_spread_c: float = 15.0
    minimum_valid_temperature_c: float = -40.0
    maximum_valid_temperature_c: float = 100.0


@dataclass
class TMUReading:
    thermal_state: str
    measurement_quality: str
    hottest_cell: int | None
    hottest_temperature_c: float | None
    coldest_cell: int | None
    coldest_temperature_c: float | None
    temperature_spread_c: float | None
    charge_derating_recommended: bool
    discharge_derating_recommended: bool
    balancing_permitted: bool
    reasons: list


class ThermalManagementUnit:

    def __init__(self, config=None):
        self.config = config or TMUConfig()

        if (
            self.config.warning_temperature_c
            >= self.config.critical_temperature_c
        ):
            raise ValueError("Warning threshold must be below critical threshold.")

        if (
            self.config.maximum_temperature_spread_c
            >= self.config.critical_temperature_spread_c
        ):
            raise ValueError("Warning spread must be below critical spread.")

    def process_measurements(
        self,
        cell_temperatures_c,
        measurement_available=True,
        suspect_cells=None,
    ):

        reasons = []
        suspect_cells = set(suspect_cells or [])

        if not measurement_available:
            return self._unknown("TEMPERATURE_SENSOR_UNAVAILABLE")

        try:
            temperatures = list(cell_temperatures_c)
        except (TypeError, ValueError):
            return self._unknown("INVALID_TEMPERATURE_INPUT")

        if len(temperatures) != CELL_COUNT:
            return self._unknown("INVALID_TEMPERATURE_CHANNEL_COUNT")

        if any(
            not isinstance(cell, int) or not 1 <= cell <= CELL_COUNT
            for cell in suspect_cells
        ):
            return self._unknown("INVALID_SUSPECT_CELL_INDEX")

        validated = []

        for index, value in enumerate(temperatures, start=1):
            if index in suspect_cells:
                return self._unknown(
                    f"TEMPERATURE_SENSOR_SUSPECT_CELL_{index}"
                )

            if isinstance(value, bool):
                return self._unknown(
                    f"INVALID_TEMPERATURE_CELL_{index}"
                )

            try:
                temperature = float(value)
            except (TypeError, ValueError):
                return self._unknown(
                    f"INVALID_TEMPERATURE_CELL_{index}"
                )

            if not math.isfinite(temperature):
                return self._unknown(
                    f"NONFINITE_TEMPERATURE_CELL_{index}"
                )

            if not (
                self.config.minimum_valid_temperature_c
                <= temperature
                <= self.config.maximum_valid_temperature_c
            ):
                return self._unknown(
                    f"TEMPERATURE_OUT_OF_RANGE_CELL_{index}"
                )

            validated.append(temperature)

        hottest_index = max(
            range(CELL_COUNT),
            key=lambda index: validated[index]
        )

        coldest_index = min(
            range(CELL_COUNT),
            key=lambda index: validated[index]
        )

        hottest = validated[hottest_index]
        coldest = validated[coldest_index]
        spread = hottest - coldest

        state = ThermalState.NORMAL

        if hottest >= self.config.critical_temperature_c:
            state = ThermalState.CRITICAL
            reasons.append("CELL_TEMPERATURE_CRITICAL")

        elif hottest >= self.config.warning_temperature_c:
            state = ThermalState.WARNING
            reasons.append("CELL_TEMPERATURE_WARNING")

        if spread >= self.config.critical_temperature_spread_c:
            state = ThermalState.CRITICAL
            reasons.append("PACK_TEMPERATURE_SPREAD_CRITICAL")

        elif spread >= self.config.maximum_temperature_spread_c:
            if state != ThermalState.CRITICAL:
                state = ThermalState.WARNING
            reasons.append("PACK_TEMPERATURE_SPREAD_WARNING")

        return TMUReading(
            thermal_state=state.value,
            measurement_quality=MeasurementQuality.VALID.value,
            hottest_cell=hottest_index + 1,
            hottest_temperature_c=hottest,
            coldest_cell=coldest_index + 1,
            coldest_temperature_c=coldest,
            temperature_spread_c=spread,
            charge_derating_recommended=(
                state in {ThermalState.WARNING, ThermalState.CRITICAL}
            ),
            discharge_derating_recommended=(
                state in {ThermalState.WARNING, ThermalState.CRITICAL}
            ),
            balancing_permitted=(state == ThermalState.NORMAL),
            reasons=reasons,
        )

    @staticmethod
    def _unknown(reason):

        return TMUReading(
            thermal_state=ThermalState.UNKNOWN.value,
            measurement_quality=MeasurementQuality.INVALID.value,
            hottest_cell=None,
            hottest_temperature_c=None,
            coldest_cell=None,
            coldest_temperature_c=None,
            temperature_spread_c=None,
            charge_derating_recommended=True,
            discharge_derating_recommended=True,
            balancing_permitted=False,
            reasons=[reason],
        )

    @staticmethod
    def export_reading(reading):
        return asdict(reading)

    @staticmethod
    def export_json(reading):
        return json.dumps(
            asdict(reading),
            indent=4
        )


if __name__ == "__main__":

    tmu = ThermalManagementUnit()

    scenarios = {
        "NORMAL": [25.0] * CELL_COUNT,

        "WARNING": [47.0] * CELL_COUNT,

        "CRITICAL": [57.0] * CELL_COUNT,

        "THERMAL_IMBALANCE": [
            40.0, 28.0
        ] + [30.0] * 14,
    }

    for name, temperatures in scenarios.items():

        reading = tmu.process_measurements(temperatures)

        print(f"\n{name}")
        print(tmu.export_json(reading))
