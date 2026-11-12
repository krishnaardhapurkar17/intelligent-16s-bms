import pytest

from software.estimation.soc_drive_cycle import (
    run_soc_initialization_scenario,
    synthetic_current_profile,
)


def test_synthetic_profile_contains_drive_and_regeneration_segments():
    time_s, current_a = synthetic_current_profile(240)

    assert len(time_s) == len(current_a)
    assert current_a.min() == -30.0
    assert current_a.max() == 100.0


def test_rest_ocv_correction_reduces_initial_error_where_curve_is_observable():
    _, metrics = run_soc_initialization_scenario(
        name="high_soc",
        true_initial_soc=0.95,
        estimated_initial_soc=0.80,
    )

    assert metrics["initial_soc_error_percentage_points"] == pytest.approx(-15.0)
    assert metrics["rest_ocv_correction_applied"] is True
    assert abs(metrics["final_ocv_fused_error_percentage_points"]) < abs(
        metrics["final_coulomb_count_error_percentage_points"]
    )


def test_rest_ocv_correction_is_rejected_on_flat_lfp_plateau():
    _, metrics = run_soc_initialization_scenario(
        name="mid_soc",
        true_initial_soc=0.55,
        estimated_initial_soc=0.70,
    )

    assert metrics["rest_ocv_correction_applied"] is False
    assert metrics["rest_ocv_correction_reason"] == "OCV_SLOPE_TOO_LOW"
    assert metrics["final_ocv_fused_error_percentage_points"] == pytest.approx(
        metrics["final_coulomb_count_error_percentage_points"]
    )
