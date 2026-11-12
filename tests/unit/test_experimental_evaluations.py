from tools.evaluate_fault_diagnostic_grid import classify, simulate


def test_diagnostic_grid_simulation_detects_injected_faults_without_healthy_alarm():
    _, current, voltage = simulate(None, "healthy", 0.0, 20261110)
    baseline, resistance, labels = classify(current, voltage)
    assert not baseline.any()
    assert not resistance.any()
    assert set(labels) == {"none"}

    _, current, voltage = simulate(5, "resistance_growth", 0.25, 20261113)
    _, _, labels = classify(current, voltage)
    assert labels[5] == "resistance_degradation"
    assert sum(label != "none" for label in labels) == 1

    _, current, voltage = simulate(7, "voltage_sensor_bias", 20.0, 20261234)
    _, _, labels = classify(current, voltage)
    assert labels[7] == "voltage_sensor_bias"
    assert sum(label != "none" for label in labels) == 1
