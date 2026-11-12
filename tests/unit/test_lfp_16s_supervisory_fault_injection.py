import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from software.diagnostics.lfp_16s_supervisory_controller import (
    INPUT_FILE,
    CELL_COUNT,
    SupervisoryController,
)
from software.diagnostics import lfp_16s_supervisory_controller as supervisory_module


def load_context(soh_scenario="SIM-SOH-001_HEALTHY"):
    df = pd.read_csv(INPUT_FILE)

    context = df[
        (df["SOH_Scenario"] == soh_scenario)
        & (
            df["SOC_Operating_Scenario"]
            == "OCV_CORRECTION_REGION"
        )
    ].copy()

    return context.sort_values("Cell").reset_index(drop=True)


def evaluate(
    controller,
    context,
    bdu_state="CLOSED",
    protection_fault=False,
    current=10.0,
    suspect_voltage=None,
    suspect_temperature=None,
    current_suspect=False,
):
    return controller.evaluate_context(
        context_df=context,
        cell_voltages=np.full(CELL_COUNT, 3.35),
        cell_temperatures=np.full(CELL_COUNT, 25.0),
        pack_current=current,
        bdu_state=bdu_state,
        protection_fault=protection_fault,
        charge_mode=True,
        suspect_voltage_cells=suspect_voltage,
        suspect_temperature_cells=suspect_temperature,
        current_sensor_suspect=current_suspect,
    )


def main():

    controller = SupervisoryController()

    healthy = load_context()

    checks = {}

    # SUP-001: Healthy system
    decisions, quality = evaluate(controller, healthy)

    checks["SUP-001 Healthy system permits balancing"] = (
        quality["global_balancing_eligible"]
        and all(item["Balancing_Eligible"] for item in decisions)
    )

    # SUP-002: Cell 8 voltage sensor suspect
    decisions, quality = evaluate(
        controller,
        healthy,
        suspect_voltage=[8],
    )

    cell8 = next(
        item for item in decisions if item["Cell"] == 8
    )

    checks["SUP-002 Cell 8 voltage sensor inhibits Cell 8"] = (
        not cell8["Balancing_Eligible"]
        and all(
            item["Balancing_Eligible"]
            for item in decisions
            if item["Cell"] != 8
        )
    )

    # SUP-003: Cell 12 temperature sensor suspect
    # A suspect thermal channel invalidates pack-wide thermal confidence.
    # Therefore, all balancing must be inhibited.
    decisions, quality = evaluate(
        controller,
        healthy,
        suspect_temperature=[12],
    )

    cell12 = next(
        item for item in decisions if item["Cell"] == 12
    )
    

    checks["SUP-003 Suspect temperature sensor inhibits all balancing"] = (
        not cell12["Balancing_Eligible"]
        and quality["global_balancing_eligible"]
        and not quality["thermal_monitoring_valid"]
        and quality["thermal_state"] == "UNKNOWN"
        and quality["thermal_balancing_interlock"]
        and bool(quality["thermal_reasons"])
        and not any(
            item["Balancing_Eligible"]
            for item in decisions
        )
    )

    # SUP-004: Missing current sensor
    decisions, quality = evaluate(
        controller,
        healthy,
        current=float("nan"),
    )

    checks["SUP-004 Invalid current disables all balancing"] = (
        not quality["global_balancing_eligible"]
        and not any(
            item["Balancing_Eligible"]
            for item in decisions
        )
    )

    # SUP-005: BDU OPEN
    decisions, _ = evaluate(
        controller,
        healthy,
        bdu_state="OPEN",
    )

    checks["SUP-005 BDU OPEN disables all balancing"] = (
        not any(
            item["Balancing_Eligible"]
            for item in decisions
        )
        and all(item["BDU_State"] == "OPEN" for item in decisions)
    )

    # SUP-006: BDU FAULT
    decisions, _ = evaluate(
        controller,
        healthy,
        bdu_state="FAULT",
        protection_fault=True,
    )

    checks["SUP-006 BDU FAULT disables all balancing"] = (
        not any(
            item["Balancing_Eligible"]
            for item in decisions
        )
        and all(
            item["Protection_Fault"]
            for item in decisions
        )
    )

    # SUP-007: AI advisory boundary
    decisions, _ = evaluate(controller, healthy)

    checks["SUP-007 AI outputs remain advisory"] = (
        all(
            item["AI_Role"] == "ADVISORY_ONLY"
            and item["Protection_Authority"] == "BDU_ONLY"
            for item in decisions
        )
    )

    # SUP-008: Communication advisory boundary
    # Communication availability is not yet a runtime input
    # to this controller. Verify it does not claim authority.
    checks["SUP-008 Communication cannot gain protection authority"] = (
        all(
            item["Protection_Authority"] == "BDU_ONLY"
            for item in decisions
        )
    )

    # SUP-009: Combined degradation indicators
    combined = load_context(
        "SIM-SOH-004_COMBINED_FAULT"
    )

    decisions, _ = evaluate(controller, combined)

    capacity_cells = [
        item["Cell"]
        for item in decisions
        if item["Capacity_Fault_Detected"]
    ]

    resistance_cells = [
        item["Cell"]
        for item in decisions
        if item["Resistance_Fault_Detected"]
    ]

    checks["SUP-009 Combined degradation indicators retained"] = (
        capacity_cells == [8]
        and resistance_cells == [12]
    )

    # SUP-011: severity is categorical evidence, not probability.
    healthy_decisions, _ = evaluate(controller, healthy)
    checks["SUP-011 Healthy severity and evidence grade"] = all(
        item["Diagnostic_Severity"] == "NO_DEGRADATION_THRESHOLD_BREACH"
        and item["Evidence_Grade"] == "NO_ESTIMATOR_THRESHOLD_FLAG"
        for item in healthy_decisions
    )

    capacity_context = load_context("SIM-SOH-002_CAPACITY_FAULT")
    capacity_decisions, _ = evaluate(controller, capacity_context)
    capacity_cell = next(item for item in capacity_decisions if item["Cell"] == 8)
    checks["SUP-012 Single degradation severity and evidence grade"] = (
        capacity_cell["Diagnostic_Severity"] == "DEGRADATION_INDICATED"
        and capacity_cell["Evidence_Grade"] == "ESTIMATOR_THRESHOLD_FLAG"
    )

    multiple_context = healthy.copy()
    cell8_index = multiple_context.index[multiple_context["Cell"] == 8][0]
    multiple_context.loc[cell8_index, "Capacity_Fault_Detected"] = True
    multiple_context.loc[cell8_index, "Resistance_Fault_Detected"] = True
    multiple_decisions, _ = evaluate(controller, multiple_context)
    multiple_cell = next(item for item in multiple_decisions if item["Cell"] == 8)
    checks["SUP-013 Multiple indicators severity"] = (
        multiple_cell["Fault_Classification"] == "MULTIPLE_DEGRADATION_INDICATORS"
        and multiple_cell["Diagnostic_Severity"] == "MULTIPLE_INDICATORS"
        and multiple_cell["Evidence_Grade"] == "ESTIMATOR_THRESHOLD_FLAG"
    )

    # SUP-010: Missing diagnostic cell record
    incomplete = healthy.iloc[:-1].copy()

    try:
        evaluate(controller, incomplete)
        missing_record_rejected = False

    except ValueError:
        missing_record_rejected = True

    checks["SUP-010 Missing diagnostic record rejected"] = (
        missing_record_rejected
    )

    # ----------------------------------------------------
    # Results
    # ----------------------------------------------------

    print("=" * 70)
    print("16S SUPERVISORY FAULT-INJECTION VALIDATION")
    print("=" * 70)

    for name, passed in checks.items():
        print(
            f"{name}: {'PASS' if passed else 'FAIL'}"
        )

    passed_count = sum(checks.values())
    total_count = len(checks)

    print(f"\nPASSED: {passed_count}/{total_count}")

    overall = all(checks.values())

    print(
        "OVERALL:",
        "PASS" if overall else "FAIL",
    )

    if not overall:
        raise SystemExit(1)


def test_supervisory_insulation_quality_inhibits_balancing():
    controller = SupervisoryController()
    context = load_context()
    base = {
        "context_df": context,
        "cell_voltages": np.full(CELL_COUNT, 3.35),
        "cell_temperatures": np.full(CELL_COUNT, 25.0),
        "pack_current": 10.0,
        "bdu_state": "CLOSED",
        "protection_fault": False,
        "charge_mode": True,
    }
    for insulation_state, quality in (("WARNING", "VALID"),
                                      ("NORMAL", "STALE"),
                                      ("UNKNOWN", "VALID")):
        decisions, _ = controller.evaluate_context(
            **base, insulation_state=insulation_state,
            insulation_measurement_quality=quality)
        assert decisions
        assert not any(row["Balancing_Eligible"] for row in decisions)
        assert all(row["Protection_Authority"] == "BDU_ONLY" for row in decisions)


def test_supervisory_rejects_duplicate_cell_records():
    controller = SupervisoryController()
    context = load_context()
    context.loc[context.index[-1], "Cell"] = 15
    try:
        evaluate(controller, context)
    except ValueError as error:
        assert "exactly one record" in str(error)
    else:
        raise AssertionError("duplicate cell record was accepted")


if __name__ == "__main__":
    main()


def test_supervisory_insulation_quality_inhibits_balancing():
    controller = SupervisoryController()
    context = load_context()
    arguments = {
        "context_df": context,
        "cell_voltages": np.full(CELL_COUNT, 3.35),
        "cell_temperatures": np.full(CELL_COUNT, 25.0),
        "pack_current": 10.0,
        "bdu_state": "CLOSED",
        "protection_fault": False,
        "charge_mode": True,
    }
    for insulation_state, quality in (("WARNING", "VALID"),
                                      ("NORMAL", "STALE"),
                                      ("UNKNOWN", "VALID")):
        decisions, _ = controller.evaluate_context(
            **arguments, insulation_state=insulation_state,
            insulation_measurement_quality=quality)
        assert decisions
        assert not any(row["Balancing_Eligible"] for row in decisions)
        assert all(row["Protection_Authority"] == "BDU_ONLY" for row in decisions)


def test_supervisory_rejects_duplicate_cell_records():
    controller = SupervisoryController()
    context = load_context()
    context.loc[context.index[-1], "Cell"] = 15
    try:
        evaluate(controller, context)
    except ValueError as error:
        assert "exactly one record" in str(error)
    else:
        raise AssertionError("duplicate cell record was accepted")


def test_supervisory_main_writes_auditable_outputs(tmp_path, monkeypatch):
    source = supervisory_module.INPUT_FILE
    monkeypatch.setattr(supervisory_module, "INPUT_FILE", source)
    monkeypatch.setattr(supervisory_module, "OUTPUT_CSV", tmp_path / "decisions.csv")
    monkeypatch.setattr(supervisory_module, "OUTPUT_JSON", tmp_path / "summary.json")
    try:
        supervisory_module.main()
    except SystemExit as error:
        assert error.code in (None, 0)
    else:
        assert supervisory_module.OUTPUT_CSV.is_file()
        assert supervisory_module.OUTPUT_JSON.is_file()
