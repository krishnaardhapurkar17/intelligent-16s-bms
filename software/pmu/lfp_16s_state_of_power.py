
"""
16S Intelligent BMS - State of Power (SOP)

Simulation-only charge and discharge power capability estimator.

Uses:
- Per-cell terminal voltage
- Per-cell estimated resistance
- Per-cell estimated capacity
- Per-cell SOC
- Per-cell temperature
- Pack voltage and current
- TMU measurement quality and thermal state

Positive current = discharge.
Negative current = charge.

This is an advisory estimator, not a protection circuit.
The BDU retains exclusive protection authority.

Model limitations:
- First-order ohmic voltage model.
- No transient polarization or electrochemical dynamics.
- OCV is estimated from terminal voltage and measured current.
- All thresholds and C-rate limits are configurable simulation assumptions.
"""

from dataclasses import asdict, dataclass
from typing import Optional
import json
import math


CELL_COUNT = 16


@dataclass
class SOPConfig:
    minimum_cell_voltage_v: float = 2.5
    maximum_cell_voltage_v: float = 3.65

    maximum_pack_current_a: float = 100.0
    maximum_c_rate: float = 1.0

    minimum_discharge_soc_percent: float = 5.0
    discharge_derating_soc_percent: float = 20.0

    maximum_charge_soc_percent: float = 95.0
    charge_derating_soc_percent: float = 80.0

    warning_temperature_derating_factor: float = 0.5

    minimum_valid_temperature_c: float = -40.0
    maximum_valid_temperature_c: float = 100.0


@dataclass
class SOPReading:
    status: str
    measurement_quality: str

    maximum_discharge_current_a: float
    maximum_charge_current_a: float

    maximum_discharge_power_w: float
    maximum_charge_power_w: float

    discharge_limiting_cell: Optional[int]
    charge_limiting_cell: Optional[int]

    discharge_derating_factor: float
    charge_derating_factor: float

    estimated_ocv_min_v: Optional[float]
    estimated_ocv_max_v: Optional[float]

    thermal_state: str
    reasons: list


class StateOfPowerEstimator:

    def __init__(self, config=None):

        self.config = config or SOPConfig()

        self._validate_config()

        self.last_reading = None

    def _validate_config(self):

        config = self.config

        if config.minimum_cell_voltage_v <= 0:
            raise ValueError("Minimum cell voltage must be positive")

        if (
            config.minimum_cell_voltage_v
            >= config.maximum_cell_voltage_v
        ):
            raise ValueError("Invalid cell voltage limits")

        if config.maximum_pack_current_a <= 0:
            raise ValueError("Maximum pack current must be positive")

        if config.maximum_c_rate <= 0:
            raise ValueError("Maximum C-rate must be positive")

        if not (
            0 <= config.minimum_discharge_soc_percent
            < config.discharge_derating_soc_percent
            <= 100
        ):
            raise ValueError("Invalid discharge SOC thresholds")

        if not (
            0 <= config.charge_derating_soc_percent
            < config.maximum_charge_soc_percent
            <= 100
        ):
            raise ValueError("Invalid charge SOC thresholds")

        if not (
            0 < config.warning_temperature_derating_factor <= 1
        ):
            raise ValueError("Invalid thermal derating factor")

        if (
            config.minimum_valid_temperature_c
            >= config.maximum_valid_temperature_c
        ):
            raise ValueError("Invalid temperature measurement range")

    @staticmethod
    def _is_finite_number(value):

        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )

    @staticmethod
    def _linear_factor(value, lower, upper):

        if value <= lower:
            return 0.0

        if value >= upper:
            return 1.0

        return (value - lower) / (upper - lower)

    def _unavailable(self, reason, thermal_state="UNKNOWN"):

        reading = SOPReading(
            status="UNAVAILABLE",
            measurement_quality="INVALID",

            maximum_discharge_current_a=0.0,
            maximum_charge_current_a=0.0,

            maximum_discharge_power_w=0.0,
            maximum_charge_power_w=0.0,

            discharge_limiting_cell=None,
            charge_limiting_cell=None,

            discharge_derating_factor=0.0,
            charge_derating_factor=0.0,

            estimated_ocv_min_v=None,
            estimated_ocv_max_v=None,

            thermal_state=thermal_state,
            reasons=[reason],
        )

        self.last_reading = reading

        return reading

    def process_measurements(
        self,
        cell_voltages_v,
        cell_resistances_ohm,
        cell_capacities_ah,
        cell_soc_percent,
        cell_temperatures_c,
        pack_voltage_v,
        pack_current_a,
        thermal_state,
        thermal_measurement_quality="VALID",
        pmu_measurement_quality="VALID",
    ):

        # ----------------------------------------------------
        # Validate measurement quality
        # ----------------------------------------------------

        if pmu_measurement_quality != "VALID":
            return self._unavailable(
                "PMU_MEASUREMENT_NOT_VALID",
                thermal_state,
            )

        if thermal_measurement_quality != "VALID":
            return self._unavailable(
                "THERMAL_MEASUREMENT_NOT_VALID",
                thermal_state,
            )

        if thermal_state not in {"NORMAL", "WARNING", "CRITICAL"}:
            return self._unavailable(
                "THERMAL_STATE_UNKNOWN",
                thermal_state,
            )

        # ----------------------------------------------------
        # Validate pack measurements
        # ----------------------------------------------------

        if not self._is_finite_number(pack_voltage_v):
            return self._unavailable("INVALID_PACK_VOLTAGE")

        if not self._is_finite_number(pack_current_a):
            return self._unavailable("INVALID_PACK_CURRENT")

        if pack_voltage_v <= 0:
            return self._unavailable("NONPOSITIVE_PACK_VOLTAGE")

        if abs(pack_current_a) > self.config.maximum_pack_current_a:
            return self._unavailable("PACK_CURRENT_EXCEEDS_CONFIGURED_LIMIT")

        # ----------------------------------------------------
        # Validate per-cell arrays
        # ----------------------------------------------------

        arrays = {
            "cell_voltages_v": cell_voltages_v,
            "cell_resistances_ohm": cell_resistances_ohm,
            "cell_capacities_ah": cell_capacities_ah,
            "cell_soc_percent": cell_soc_percent,
            "cell_temperatures_c": cell_temperatures_c,
        }

        validated = {}

        for name, values in arrays.items():

            try:
                values = list(values)
            except (TypeError, ValueError):
                return self._unavailable(
                    f"INVALID_INPUT_ARRAY_{name.upper()}"
                )

            if len(values) != CELL_COUNT:
                return self._unavailable(
                    f"INVALID_CHANNEL_COUNT_{name.upper()}"
                )

            if not all(self._is_finite_number(v) for v in values):
                return self._unavailable(
                    f"NONFINITE_VALUE_{name.upper()}"
                )

            validated[name] = [float(v) for v in values]

        voltages = validated["cell_voltages_v"]
        resistances = validated["cell_resistances_ohm"]
        capacities = validated["cell_capacities_ah"]
        soc_values = validated["cell_soc_percent"]
        temperatures = validated["cell_temperatures_c"]

        # ----------------------------------------------------
        # Validate physical ranges
        # ----------------------------------------------------

        for index in range(CELL_COUNT):

            if not 0 < voltages[index] <= 5.0:
                return self._unavailable(
                    f"INVALID_CELL_VOLTAGE_CELL_{index + 1}"
                )

            if resistances[index] <= 0:
                return self._unavailable(
                    f"INVALID_CELL_RESISTANCE_CELL_{index + 1}"
                )

            if capacities[index] <= 0:
                return self._unavailable(
                    f"INVALID_CELL_CAPACITY_CELL_{index + 1}"
                )

            if not 0 <= soc_values[index] <= 100:
                return self._unavailable(
                    f"INVALID_CELL_SOC_CELL_{index + 1}"
                )

            if not (
                self.config.minimum_valid_temperature_c
                <= temperatures[index]
                <= self.config.maximum_valid_temperature_c
            ):
                return self._unavailable(
                    f"INVALID_CELL_TEMPERATURE_CELL_{index + 1}"
                )

        reasons = []

        # ----------------------------------------------------
        # Estimate OCV for each cell
        #
        # Vterminal = OCV - I * R
        # OCV = Vterminal + I * R
        #
        # Positive current means discharge.
        # ----------------------------------------------------

        estimated_ocv = [
            voltages[i] + pack_current_a * resistances[i]
            for i in range(CELL_COUNT)
        ]

        # ----------------------------------------------------
        # Calculate per-cell current limits
        # ----------------------------------------------------

        discharge_limits = []
        charge_limits = []

        for index in range(CELL_COUNT):

            resistance = resistances[index]
            ocv = estimated_ocv[index]
            capacity = capacities[index]
            soc = soc_values[index]

            # Voltage-constrained current limits.
            discharge_voltage_limit = max(
                0.0,
                (ocv - self.config.minimum_cell_voltage_v)
                / resistance,
            )

            charge_voltage_limit = max(
                0.0,
                (self.config.maximum_cell_voltage_v - ocv)
                / resistance,
            )

            # Capacity-based current limit.
            capacity_current_limit = (
                capacity * self.config.maximum_c_rate
            )

            # SOC-based derating.
            discharge_soc_factor = self._linear_factor(
                soc,
                self.config.minimum_discharge_soc_percent,
                self.config.discharge_derating_soc_percent,
            )

            charge_soc_factor = self._linear_factor(
                self.config.maximum_charge_soc_percent - soc,
                0.0,
                (
                    self.config.maximum_charge_soc_percent
                    - self.config.charge_derating_soc_percent
                ),
            )

            discharge_limit = min(
                discharge_voltage_limit,
                capacity_current_limit,
            ) * discharge_soc_factor

            charge_limit = min(
                charge_voltage_limit,
                capacity_current_limit,
            ) * charge_soc_factor

            discharge_limits.append(discharge_limit)
            charge_limits.append(charge_limit)

        # ----------------------------------------------------
        # Identify weakest cell in each direction
        # ----------------------------------------------------

        discharge_limiting_index = min(
            range(CELL_COUNT),
            key=lambda i: discharge_limits[i],
        )

        charge_limiting_index = min(
            range(CELL_COUNT),
            key=lambda i: charge_limits[i],
        )

        discharge_current = min(
            discharge_limits[discharge_limiting_index],
            self.config.maximum_pack_current_a,
        )

        charge_current = min(
            charge_limits[charge_limiting_index],
            self.config.maximum_pack_current_a,
        )

        # ----------------------------------------------------
        # Thermal derating
        # ----------------------------------------------------

        discharge_thermal_factor = 1.0
        charge_thermal_factor = 1.0

        if thermal_state == "WARNING":

            discharge_thermal_factor = (
                self.config.warning_temperature_derating_factor
            )

            charge_thermal_factor = (
                self.config.warning_temperature_derating_factor
            )

            reasons.append("THERMAL_WARNING_DERATING_APPLIED")

        elif thermal_state == "CRITICAL":

            discharge_thermal_factor = 0.0
            charge_thermal_factor = 0.0

            reasons.append("CRITICAL_THERMAL_STATE_POWER_INHIBITED")

        discharge_current *= discharge_thermal_factor
        charge_current *= charge_thermal_factor

        # ----------------------------------------------------
        # Calculate pack power capability
        # ----------------------------------------------------

        discharge_power = pack_voltage_v * discharge_current
        charge_power = pack_voltage_v * charge_current

        if discharge_current == 0:
            reasons.append("DISCHARGE_POWER_UNAVAILABLE")

        if charge_current == 0:
            reasons.append("CHARGE_POWER_UNAVAILABLE")

        if (
            discharge_current >= self.config.maximum_pack_current_a
            or charge_current >= self.config.maximum_pack_current_a
        ):
            reasons.append("PACK_CURRENT_LIMIT_ACTIVE")

        reading = SOPReading(
            status="AVAILABLE",
            measurement_quality="VALID",

            maximum_discharge_current_a=discharge_current,
            maximum_charge_current_a=charge_current,

            maximum_discharge_power_w=discharge_power,
            maximum_charge_power_w=charge_power,

            discharge_limiting_cell=discharge_limiting_index + 1,
            charge_limiting_cell=charge_limiting_index + 1,

            discharge_derating_factor=discharge_thermal_factor,
            charge_derating_factor=charge_thermal_factor,

            estimated_ocv_min_v=min(estimated_ocv),
            estimated_ocv_max_v=max(estimated_ocv),

            thermal_state=thermal_state,
            reasons=reasons,
        )

        self.last_reading = reading

        return reading

    def export_reading(self):

        if self.last_reading is None:
            raise RuntimeError("No SOP measurement available")

        return asdict(self.last_reading)

    def export_json(self):

        return json.dumps(
            self.export_reading(),
            indent=4,
        )
