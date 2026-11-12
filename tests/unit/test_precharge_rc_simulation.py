import pytest

from models.electrical.precharge_rc import (
    PrechargeParameters,
    simulate_precharge,
)


def test_documented_precharge_example_reaches_delta_before_timeout():
    samples, metrics = simulate_precharge()

    assert metrics["state"] == "CLOSED"
    assert metrics["main_contactor_command"] is True
    assert metrics["theoretical_close_time_s"] == pytest.approx(0.5937, abs=0.001)
    assert metrics["simulated_close_time_s"] == pytest.approx(0.594, abs=0.001)
    assert metrics["initial_current_a"] == pytest.approx(0.584)
    assert metrics["initial_resistor_power_w"] == pytest.approx(34.1056)
    assert 2.9 < samples[-1].bus_delta_v <= 3.0
    assert 3.3 < metrics["resistor_energy_until_close_j"] < 3.5
    assert all(
        not sample.main_contactor_command or sample.bus_delta_v <= 3.0
        for sample in samples
    )


def test_failed_precharge_path_times_out_to_isolated_fault():
    samples, metrics = simulate_precharge(charging_path_available=False)

    assert metrics["state"] == "FAULT"
    assert metrics["main_contactor_command"] is False
    assert samples[-1].precharge_contactor_command is False
    assert samples[-1].time_s == pytest.approx(1.0)
    assert samples[-1].bus_voltage_v == 0.0


@pytest.mark.parametrize(
    "parameters",
    [
        PrechargeParameters(resistance_ohm=0.0),
        PrechargeParameters(capacitance_f=float("nan")),
        PrechargeParameters(close_delta_v=58.4),
        PrechargeParameters(initial_bus_voltage_v=60.0),
        PrechargeParameters(time_step_s=0.0),
    ],
)
def test_invalid_precharge_assumptions_are_rejected(parameters):
    with pytest.raises(ValueError):
        simulate_precharge(parameters)
