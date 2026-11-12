import pytest

from software.protection.lfp_16s_protection_bdu import (
    BDUState,
    ProtectionBDU,
    ProtectionConfig,
    ProtectionInputs,
)


def inputs(**changes):
    values = dict(cell_voltages_v=[3.3] * 16, pack_current_a=10.0,
                  cell_temperatures_c=[25.0] * 16, pack_voltage_v=52.8,
                  bus_voltage_v=52.8)
    values.update(changes)
    return ProtectionInputs(**values)


def test_protection_detects_each_sensor_and_cell_limit_fault():
    bdu = ProtectionBDU()
    assert "INVALID_CELL_VOLTAGE_CHANNEL_COUNT" in bdu.evaluate_protection(inputs(cell_voltages_v=[3.3]))
    assert "INVALID_TEMPERATURE_CHANNEL_COUNT" in bdu.evaluate_protection(inputs(cell_temperatures_c=[25]))
    assert "PACK_CURRENT_SENSOR_INVALID" in bdu.evaluate_protection(inputs(pack_current_a=float("nan")))
    assert "PACK_VOLTAGE_SENSOR_INVALID" in bdu.evaluate_protection(inputs(pack_voltage_v=float("nan")))
    assert "BUS_VOLTAGE_SENSOR_INVALID" in bdu.evaluate_protection(inputs(bus_voltage_v=float("nan")))
    volts = [3.3] * 16
    volts[0], volts[1], volts[2] = 1.9, 3.7, float("nan")
    temps = [25.0] * 16
    temps[3], temps[4] = 66.0, float("nan")
    faults = bdu.evaluate_protection(inputs(cell_voltages_v=volts, cell_temperatures_c=temps,
                                             pack_current_a=101.0))
    assert {"CELL_1_UNDERVOLTAGE", "CELL_2_OVERVOLTAGE", "CELL_3_VOLTAGE_INVALID",
            "CELL_4_OVERTEMPERATURE", "CELL_5_TEMPERATURE_INVALID", "PACK_OVERCURRENT"}.issubset(faults)


def test_precharge_close_stop_and_isolation_outputs():
    bdu = ProtectionBDU()
    started = bdu.update(inputs(start_request=True))
    assert started["state"] == BDUState.PRECHARGE.value
    assert started["actuator_outputs"]["precharge_contactor_command"]
    closed = bdu.update(inputs(pack_voltage_v=52.8, bus_voltage_v=52.0))
    assert closed["state"] == BDUState.CLOSED.value
    assert closed["actuator_outputs"]["main_contactor_command"]
    opened = bdu.update(inputs(stop_request=True))
    assert opened["state"] == BDUState.OPEN.value
    assert not any(opened["actuator_outputs"].values())


def test_precharge_timeout_latches_until_recovery_and_reset():
    bdu = ProtectionBDU(ProtectionConfig(precharge_timeout_s=1.0, precharge_delta_v=0.1))
    bdu.update(inputs(start_request=True))
    timed_out = bdu.update(inputs(pack_voltage_v=52.8, bus_voltage_v=40.0), dt_s=1.0)
    assert timed_out["state"] == BDUState.FAULT.value
    assert "PRECHARGE_TIMEOUT" in timed_out["fault_history"]
    assert bdu.update(inputs(start_request=True))["state"] == BDUState.FAULT.value
    recovering = bdu.update(inputs(recovery_request=True))
    assert recovering["state"] == BDUState.RECOVERY.value
    reset = bdu.update(inputs(recovery_request=True))
    assert reset["state"] == BDUState.OPEN.value
    assert not reset["fault_latched"]


def test_active_fault_during_recovery_returns_to_fault():
    bdu = ProtectionBDU()
    bdu.update(inputs(start_request=True))
    fault = bdu.update(inputs(pack_current_a=120.0))
    assert fault["state"] == BDUState.FAULT.value
    recovering = bdu.update(inputs(recovery_request=True))
    assert recovering["state"] == BDUState.RECOVERY.value
    fault_again = bdu.update(inputs(pack_current_a=120.0, recovery_request=True))
    assert fault_again["state"] == BDUState.FAULT.value


@pytest.mark.parametrize("dt_s", [0, -1])
def test_nonpositive_time_step_is_rejected(dt_s):
    with pytest.raises(ValueError):
        ProtectionBDU().update(inputs(), dt_s=dt_s)
