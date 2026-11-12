import csv
import json
import struct
import zlib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
METRICS = PROJECT_ROOT / "results" / "metrics"
FIGURES = PROJECT_ROOT / "results" / "figures"


def load_json(filename):
    path = METRICS / filename

    if not path.is_file():
        raise AssertionError(f"Missing JSON report: {filename}")

    with path.open(encoding="utf-8") as file:
        return json.load(file)

def load_parameter_json(filename):
    path = (
        PROJECT_ROOT
        / "models"
        / "battery-parameters"
        / filename
    )

    check(path.is_file(), f"Missing parameter file: {filename}")

    with path.open(encoding="utf-8") as file:
        return json.load(file)


def validate_battery_parameters():
    manufacturer = load_parameter_json("eve_lf100la_vA.json")
    ecm = load_parameter_json("lf100la_ecm_assumptions.json")

    cell = manufacturer["cell"]
    rated = manufacturer["rated_parameters"]
    model = manufacturer["model_parameters"]
    provenance = manufacturer["provenance"]

    check(
        cell["manufacturer"] == "EVE Energy"
        and cell["model"] == "LF100LA"
        and cell["chemistry"] == "LFP",
        "Manufacturer identity mismatch",
    )

    check(
        rated["nominal_capacity_Ah"] == 100.0
        and rated["nominal_voltage_V"] == 3.2,
        "Manufacturer rated parameters mismatch",
    )

    check(
        provenance["rated_parameters"]
        == "EVE LF100LA Version A product specification",
        "Manufacturer provenance missing",
    )

    check(
        all(value is None for value in model.values()),
        "Unidentified model parameters must remain null",
    )

    check(
        "Synthetic" in ecm["status"]
        and "not manufacturer validated" in ecm["status"],
        "ECM assumptions are not labelled correctly",
    )

    check(
        ecm["capacity_Ah"] == rated["nominal_capacity_Ah"]
        and ecm["nominal_voltage_V"] == rated["nominal_voltage_V"]
        and ecm["cutoff_voltage_V"] == rated["discharge_cutoff_voltage_V"],
        "ECM and manufacturer rated parameters disagree",
    )

    check(
        "ac_impedance_1kHz_max_ohm" in rated
        and "R0_ohm" in ecm,
        "AC impedance and ECM resistance fields are not distinguished",
    )

    table = ecm["ocv_soc_table"]

    check(
        len(table) >= 2
        and all(
            len(point) == 2
            and 0.0 <= point[0] <= 1.0
            and point[1] > 0
            for point in table
        ),
        "Invalid OCV-SOC table",
    )

    return "Manufacturer provenance, ECM assumptions and parameter separation verified"


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def validate_protection_bdu():
    data = load_json("lfp_16s_protection_bdu_results.json")
    results = data["results"]

    check(data["overall"] == "PASS", "BDU overall status is not PASS")

    validation = data["validation"]
    check(bool(validation), "BDU validation dictionary is empty")
    check(all(value is True for value in validation.values()),
          "One or more BDU validation flags are false")

    expected = {
        "SIM-BDU-001_NORMAL_STARTUP": ("CLOSED", False),
        "SIM-BDU-002_CELL_UNDERVOLTAGE": ("FAULT", True),
        "SIM-BDU-003_CELL_OVERVOLTAGE": ("FAULT", True),
        "SIM-BDU-004_PACK_OVERCURRENT": ("FAULT", True),
        "SIM-BDU-005_CELL_OVERTEMPERATURE": ("FAULT", True),
        "SIM-BDU-006_PRECHARGE_TIMEOUT": ("FAULT", True),
        "SIM-BDU-007_PROTECTION_INDEPENDENCE": ("FAULT", True),
        "SIM-BDU-008_FAULT_LATCH_AND_RECOVERY": ("OPEN", None),
        "SIM-BDU-009_INVALID_CURRENT_SENSOR": ("FAULT", True),
        "SIM-BDU-010_MISSING_VOLTAGE_CHANNEL": ("FAULT", True),
    }

    actual_names = [item["scenario"] for item in results]

    check(len(results) == 10, "Expected 10 BDU scenarios")
    check(len(actual_names) == len(set(actual_names)),
          "Duplicate BDU scenario identifiers")
    check(set(actual_names) == set(expected),
          "BDU scenario identifiers do not match expected scenarios")

    by_name = {item["scenario"]: item for item in results}

    for name, (expected_state, expected_latched) in expected.items():
        item = by_name[name]

        check(item["final_state"] == expected_state,
              f"{name}: unexpected final state")

        if expected_latched is not None:
            check(item["fault_latched"] is expected_latched,
                  f"{name}: unexpected fault-latched value")

            if expected_latched:
                check(bool(item["fault_history"]),
                      f"{name}: expected non-empty fault history")

            else:
                check(not item["fault_history"],
                      f"{name}: healthy startup must have empty fault history")

            outputs = item["steps"][-1]["actuator_outputs"]

            if expected_latched:
                check(
                    not any(outputs.values()),
                    f"{name}: fault-state actuator outputs must all be disabled",
                )

    normal_outputs = by_name[
        "SIM-BDU-001_NORMAL_STARTUP"
    ]["steps"][-1]["actuator_outputs"]

    check(normal_outputs["main_contactor_command"] is True,
          "Normal startup: main contactor must be commanded")
    check(normal_outputs["precharge_contactor_command"] is False,
          "Normal startup: precharge contactor must be disabled")
    check(normal_outputs["charge_enable"] is True,
          "Normal startup: charge must be enabled")
    check(normal_outputs["discharge_enable"] is True,
          "Normal startup: discharge must be enabled")

    independence = by_name["SIM-BDU-007_PROTECTION_INDEPENDENCE"]
    final_inputs = independence["steps"][-1]
    check(independence["final_state"] == "FAULT",
          "Service outages must not prevent overcurrent protection")
    for service in ("ai_available", "communication_available", "linux_available", "telemetry_available"):
        check(final_inputs[service] is False,
              f"Protection independence scenario must disable {service}")

    recovery = by_name["SIM-BDU-008_FAULT_LATCH_AND_RECOVERY"]

    check(recovery["fault_state"] == "FAULT",
          "Recovery scenario must initially enter FAULT")
    check(recovery["state_after_fault_cleared"] == "FAULT",
          "Fault must remain latched after the condition clears")
    check(recovery["recovery_state"] == "RECOVERY",
          "Recovery state was not entered")
    check(recovery["final_state"] == "OPEN",
          "Recovery must return the BDU to OPEN")

    check(
        not any(recovery["recovery_outputs"].values()),
        "Recovery state must have all actuator outputs disabled",
    )

    return "10 BDU scenarios, fault latching, recovery and actuator outputs verified"


def validate_passive_balancing():
    data = load_json("lfp_16s_passive_balancing_summary.json")

    check(data["overall"] == "PASS", "Balancing overall status is not PASS")

    validation = data["validation"]
    check(bool(validation), "Balancing validation dictionary is empty")
    check(all(value is True for value in validation.values()),
          "One or more balancing validation flags are false")

    scenarios = data["scenarios"]
    check(len(scenarios) == 5, "Expected 5 balancing scenarios")

    for name, item in scenarios.items():
        for field in (
            "final_soc_percent",
            "final_voltage_V",
            "final_temperature_C",
            "final_balancing_active",
        ):
            check(len(item[field]) == 16,
                  f"{name}: {field} must contain 16 cells")

    check(
        scenarios["SIM-BAL-001_HEALTHY"]["active_balancing_cells"] == [],
        "Healthy scenario unexpectedly balances cells",
    )

    check(
        7 not in scenarios["SIM-BAL-002_CELL_8_IMBALANCE"]["active_balancing_cells"],
        "Low-SOC Cell 8 must not be discharged",
    )

    for name in ("SIM-BAL-003_BDU_OPEN", "SIM-BAL-004_PROTECTION_FAULT"):
        check(
            scenarios[name]["active_balancing_cells"] == [],
            f"{name}: balancing must be disabled",
        )

    return "5 balancing scenarios, validation flags and cell arrays verified"


def validate_unified_diagnostics():
    data = load_json("lfp_16s_unified_summary.json")

    check(data["all_checks_passed"] is True,
          "Unified diagnostic all_checks_passed is not true")

    validation = data["validation"]
    check(bool(validation), "Unified validation dictionary is empty")
    check(all(value is True for value in validation.values()),
          "Unified diagnostic contains failed validation flags")

    check(data["record_count"] == 128, "Expected 128 unified records")
    check(data["cell_count"] == 16, "Expected 16 cells")
    check(len(data["scenario_summaries"]) == 8,
          "Expected 8 unified scenario summaries")

    return "Unified diagnostic: 128 records, 16 cells, 8 scenarios verified"


def validate_supervisory_controller():
    data = load_json("lfp_16s_supervisory_summary.json")

    check(data["overall"] == "PASS",
          "Supervisory overall status is not PASS")

    validation = data["validation"]
    check(bool(validation), "Supervisory validation dictionary is empty")
    check(all(value is True for value in validation.values()),
          "Supervisory controller contains failed validation flags")

    check(data["record_count"] == 128,
          "Expected 128 supervisory records")
    check(data["context_count"] == 8,
          "Expected 8 supervisory contexts")
    check(data["cell_count"] == 16,
          "Expected 16 cells")

    return "Supervisory controller: 128 records, 8 contexts, 16 cells verified"


def validate_csv(filename, expected_rows, required_columns):
    path = METRICS / filename

    check(path.is_file(), f"Missing CSV report: {filename}")

    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames
        rows = sum(1 for _ in reader)

    check(columns is not None, f"{filename}: missing header")
    check(len(columns) == len(set(columns)),
          f"{filename}: duplicate column names")

    missing = set(required_columns) - set(columns)
    check(not missing, f"{filename}: missing columns {sorted(missing)}")

    if expected_rows is not None:
        check(rows == expected_rows,
              f"{filename}: expected {expected_rows} rows, found {rows}")

    return f"{filename}: {rows} rows, {len(columns)} columns verified"


def validate_generated_artifacts():
    required_cell_columns = [f"Cell_{cell}_voltage_V" for cell in range(1, 17)]
    csv_result = validate_csv(
        "lfp_16s_pack_baseline.csv",
        None,
        ["Time_s", "Pack_current_A", "Pack_voltage_V", *required_cell_columns],
    )

    figures = [
        "lfp_16s_pack_voltage.png",
        "lfp_16s_cell_voltages.png",
        "lfp_16s_weak_cell_soc.png",
        "lfp_16s_robustness_diagnostics.png",
        "lfp_16s_temperature_diagnostic.png",
        "lfp_sensor_bias_diagnostic.png",
    ]
    for filename in figures:
        path = FIGURES / filename
        check(path.is_file() and path.stat().st_size > 100,
              f"Missing or empty generated figure: {filename}")
        with path.open("rb") as file:
            check(file.read(8) == b"\x89PNG\r\n\x1a\n",
                  f"Invalid PNG signature: {filename}")

    for filename in (
        "lfp_16s_combined_fault_summary.json",
        "lfp_16s_robustness_summary.json",
        "lfp_16s_temperature_summary.json",
    ):
        data = load_json(filename)
        check(isinstance(data, dict) and bool(data),
              f"Empty or invalid machine-readable report: {filename}")

    return f"{csv_result}; 6 PNG artifacts and 3 JSON outputs verified"


def validate_all_result_formats():
    """Check syntax and basic integrity for every existing result artifact."""
    csv_count = json_count = png_count = 0
    for path in sorted((PROJECT_ROOT / "results").rglob("*")):
        if not path.is_file() or path.stat().st_size == 0:
            continue
        suffix = path.suffix.lower()
        if suffix == ".csv":
            with path.open(newline="", encoding="utf-8-sig") as file:
                reader = csv.reader(file)
                header = next(reader, None)
                check(header is not None and len(header) > 0,
                      f"Empty CSV header: {path.relative_to(PROJECT_ROOT)}")
                check(len(header) == len(set(header)),
                      f"Duplicate CSV column: {path.relative_to(PROJECT_ROOT)}")
                for line_number, row in enumerate(reader, start=2):
                    check(len(row) == len(header),
                          f"Malformed CSV row {line_number}: {path.relative_to(PROJECT_ROOT)}")
            csv_count += 1
        elif suffix == ".json":
            def reject_constant(value):
                raise ValueError(f"Non-standard JSON number: {value}")
            try:
                with path.open(encoding="utf-8") as file:
                    data = json.load(file, parse_constant=reject_constant)
            except (ValueError, json.JSONDecodeError) as error:
                raise AssertionError(
                    f"Invalid JSON output {path.relative_to(PROJECT_ROOT)}: {error}"
                ) from error
            if path.parent == METRICS:
                # coverage.py emits its own standard JSON schema. It is a
                # diagnostic measurement rather than an experiment summary,
                # so validate it by its native shape and documented limits.
                if path.name == "unit_test_coverage.json":
                    check(
                        isinstance(data, dict)
                        and isinstance(data.get("files"), dict)
                        and isinstance(data.get("totals"), dict),
                        "Invalid coverage.py JSON report structure",
                    )
                    continue
                check(
                    isinstance(data, dict)
                    and isinstance(data.get("limitations"), list)
                    and bool(data["limitations"]),
                    f"Missing explicit limitations: {path.relative_to(PROJECT_ROOT)}",
                )
            json_count += 1
        elif suffix == ".png":
            data = path.read_bytes()
            check(data[:8] == b"\x89PNG\r\n\x1a\n",
                  f"Invalid PNG signature: {path.relative_to(PROJECT_ROOT)}")
            offset = 8
            saw_header = saw_end = False
            while offset + 12 <= len(data):
                length = struct.unpack(">I", data[offset:offset + 4])[0]
                chunk_type = data[offset + 4:offset + 8]
                end = offset + 12 + length
                check(end <= len(data),
                      f"Truncated PNG chunk: {path.relative_to(PROJECT_ROOT)}")
                chunk_data = data[offset + 8:offset + 8 + length]
                checksum = struct.unpack(">I", data[offset + 8 + length:end])[0]
                check(zlib.crc32(chunk_type + chunk_data) & 0xffffffff == checksum,
                      f"PNG CRC mismatch: {path.relative_to(PROJECT_ROOT)}")
                if chunk_type == b"IHDR":
                    width, height = struct.unpack(">II", chunk_data[:8])
                    check(width > 0 and height > 0,
                          f"Invalid PNG dimensions: {path.relative_to(PROJECT_ROOT)}")
                    saw_header = True
                if chunk_type == b"IEND":
                    saw_end = True
                    check(end == len(data),
                          f"Trailing data after PNG IEND: {path.relative_to(PROJECT_ROOT)}")
                    break
                offset = end
            check(saw_header and saw_end,
                  f"Incomplete PNG structure: {path.relative_to(PROJECT_ROOT)}")
            png_count += 1
    check(csv_count > 0 and json_count > 0 and png_count > 0,
          "Expected CSV, JSON and PNG results")
    return f"{csv_count} CSV, {json_count} JSON, {png_count} PNG outputs passed integrity checks"


def main():
    validators = [
        ("Protection BDU", validate_protection_bdu),
        ("Passive balancing", validate_passive_balancing),
        ("Unified diagnostics", validate_unified_diagnostics),
        ("Supervisory controller", validate_supervisory_controller),
        ("Battery parameter provenance", validate_battery_parameters),
        ("Simulation artifacts", validate_generated_artifacts),
        ("All result file formats", validate_all_result_formats),
    ]

    print("=" * 65)
    print("16S BMS - GENERATED REPORT VALIDATION")
    print("=" * 65)

    failures = []

    for name, validator in validators:
        try:
            result = validator()
            print(f"[PASS] {name}: {result}")
        except Exception as error:
            failures.append((name, str(error)))
            print(f"[FAIL] {name}: {error}")

    csv_checks = [
        (
            "lfp_16s_unified_diagnostics.csv",
            128,
            ["SOH_Scenario", "SOC_Operating_Scenario"],
        ),
        (
            "lfp_16s_supervisory_decisions.csv",
            128,
            ["SOH_Scenario", "SOC_Operating_Scenario"],
        ),
    ]

    for filename, expected_rows, columns in csv_checks:
        try:
            result = validate_csv(filename, expected_rows, columns)
            print(f"[PASS] CSV: {result}")
        except Exception as error:
            failures.append((filename, str(error)))
            print(f"[FAIL] CSV: {filename}: {error}")

    print("\n" + "=" * 65)
    print(f"REPORT CHECKS PASSED: {len(validators) + len(csv_checks) - len(failures)}")
    print(f"REPORT CHECKS FAILED: {len(failures)}")

    if failures:
        raise SystemExit(1)

    print("REPORT VALIDATION: PASS")


if __name__ == "__main__":
    main()
