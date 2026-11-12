
import ast
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIRECTORY = PROJECT_ROOT / "results" / "regression"
EXPECTED_ARTIFACTS_PATH = PROJECT_ROOT / "tests" / "regression" / "expected_artifacts.json"
EXPECTED_ARTIFACTS = json.loads(EXPECTED_ARTIFACTS_PATH.read_text(encoding="utf-8-sig"))

# Execution order preserves the unified diagnostic dependency.
TESTS = [
    {
        "name": "PMU unit tests",
        "category": "unit",
        "path": "tests/unit/test_lfp_16s_pmu.py",
    },
    {
        "name": "PMU-BDU integration",
        "category": "integration",
        "path": "tests/unit/test_lfp_16s_pmu_integration.py",
    },
    {
        "name": "Insulation monitoring unit tests",
        "category": "unit",
        "path": "tests/unit/test_lfp_16s_insulation_monitor.py",
    }, 
    {
        "name": "IMU supervisory integration",
        "category": "integration",
        "path": "tests/unit/test_lfp_16s_imu_supervisory_integration.py",
    },
    {
        "name": "Thermal management unit tests",
        "category": "unit",
        "path": "tests/unit/test_lfp_16s_thermal_management.py",
    },
    {
        "name": "TMU supervisory integration",
        "category": "integration",
        "path": "tests/unit/test_lfp_16s_tmu_supervisory_integration.py",
    },
    {
        "name": "Sensor safety gate",
        "category": "unit",
        "path": "tests/unit/test_lfp_16s_sensor_safety_gate.py",
    },
        {
        "name": "Battery parameter integrity",
        "category": "unit",
        "path": "tests/unit/test_battery_parameter_integrity.py",
    },
    {
        "name": "Interface, authorization and lifecycle contracts",
        "category": "unit",
        "path": "tests/unit/test_project_interfaces_and_lifecycle.py",
        "command": [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_project_interfaces_and_lifecycle.py",
            "-q",
        ],
    },
    {
        "name": "State-of-safety summary",
        "category": "unit",
        "path": "tests/unit/test_lfp_16s_state_of_safety.py",
        "command": [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_lfp_16s_state_of_safety.py",
            "-q",
        ],
    },
    {
        "name": "BDU operating mode state transitions",
        "category": "unit",
        "path": "tests/unit/test_lfp_16s_bdu_operating_mode.py",
        "command": [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_lfp_16s_bdu_operating_mode.py",
            "-q",
        ],
    },
    {
        "name": "Passive balancing energy and interlocks",
        "category": "unit",
        "path": "tests/unit/test_lfp_16s_passive_balancing.py",
        "command": [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_lfp_16s_passive_balancing.py",
            "-q",
        ],
    },
    {
        "name": "16S pack baseline simulation",
        "category": "module",
        "path": "models/pack-model/lfp_16s_pack_simulation.py",
    },
    {
        "name": "Voltage sensor bias injection",
        "category": "module",
        "path": "models/pack-model/lfp_16s_sensor_bias_test.py",
    },
    {
        "name": "Noisy and missing sensor robustness",
        "category": "module",
        "path": "models/pack-model/lfp_16s_robustness_test.py",
    },
    {
        "name": "Temperature sensor bias and noise injection",
        "category": "module",
        "path": "models/pack-model/lfp_16s_temperature_sensor_fault.py",
    },
    {
        "name": "Seeded 16S Monte Carlo validation",
        "category": "module",
        "path": "models/pack-model/lfp_16s_monte_carlo_validation.py",
    },
    {
        "name": "Monte Carlo metric audit",
        "category": "module",
        "path": "models/pack-model/lfp_16s_monte_carlo_audit.py",
        "requires": ["results/metrics/lfp_16s_monte_carlo_runs.csv"],
    },
    {
        "name": "Seeded simulation reproducibility",
        "category": "verification",
        "path": "tests/regression/check_reproducibility.py",
    },
    {
        "name": "16S weak-cell capacity injection",
        "category": "module",
        "path": "models/pack-model/lfp_16s_weak_cell_test.py",
    },
    {
        "name": "Baseline voltage deviation diagnostic",
        "category": "module",
        "path": "software/diagnostics/lfp_voltage_deviation_diagnostic.py",
    },
    {
        "name": "Capacity degradation injection and estimate",
        "category": "module",
        "path": "models/pack-model/lf100la_capacity_fault.py",
    },
    {
        "name": "Resistance growth injection and estimate",
        "category": "module",
        "path": "models/pack-model/lf100la_resistance_fault.py",
    },
    {
        "name": "LF100LA equivalent-circuit simulation",
        "category": "module",
        "path": "models/pack-model/lf100la_ecm_simulation.py",
    },
    {
        "name": "LF100LA HPPC experiment",
        "category": "module",
        "path": "models/pack-model/lf100la_hppc_test.py",
    },
    {
        "name": "LF100LA combined degradation experiment",
        "category": "module",
        "path": "models/pack-model/lf100la_combined_degradation.py",
    },
    {
        "name": "LF100LA parameter identification",
        "category": "module",
        "path": "models/pack-model/lf100la_parameter_identification.py",
    },
    {
        "name": "Single-cell discharge model",
        "category": "module",
        "path": "models/pack-model/single_cell_discharge.py",
    },
    {
        "name": "Combined-fault localization and explicit unknown result",
        "category": "module",
        "path": "models/pack-model/lfp_16s_combined_fault_diagnostic.py",
    },
    {
        "name": "LFP multi-signal fault-isolation experiment",
        "category": "module",
        "path": "models/pack-model/lfp_16s_fault_isolation_test.py",
    },
    {
        "name": "Voltage baseline versus multi-signal diagnostic metrics",
        "category": "validation",
        "path": "models/pack-model/evaluate_fault_baselines.py",
        "requires": ["results/metrics/lfp_16s_fault_isolation.csv"],
    },
    {
        "name": "Temperature variation diagnostics",
        "category": "module",
        "path": "models/pack-model/lfp_16s_temperature_diagnostic.py",
    },
    {
        "name": "SOC estimator scenarios and metrics",
        "category": "module",
        "path": "models/pack-model/lfp_16s_soc_estimator.py",
    },
    {
        "name": "LFP coulomb-counting and OCV SOC fusion",
        "category": "module",
        "path": "models/pack-model/lfp_16s_ocv_soc_fusion.py",
    },
    {
        "name": "Supplied SOC/SOH/RUL AI models and MATLAB export fidelity",
        "category": "unit",
        "path": "tests/unit/test_ai_model_integration.py",
        "model_assets": [
            "models/ai/soc_cnn_lstm.keras",
            "models/ai/soh_ensemble.json",
            "models/ai/rul_ensemble.json",
            "AI models/battery_guardian_mk2-main/models_lstm/soc_lstm_model.keras",
            "AI models/battery_guardian_mk2-main/battery_data/liion_features.csv",
            "AI models/battery_guardian_mk2-main/models/soh_liion_model.mat",
            "AI models/battery_guardian_mk2-main/models/rul_liion_model.mat",
            "AI models/battery_guardian_mk2-main/models_lstm/sequences_X.npy",
            "AI models/battery_guardian_mk2-main/models_lstm/sequences_y.npy",
            "AI models/battery_guardian_mk2-main/models_lstm/seq_metadata.csv",
        ],
        "command": [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_ai_model_integration.py",
            "-q",
        ],
    },
    {
        "name": "SOH estimator scenarios and metrics",
        "category": "module",
        "path": "models/pack-model/lfp_16s_soh_estimator.py",
    },
    {
        "name": "RUL estimator scenarios and metrics",
        "category": "module",
        "path": "models/pack-model/lfp_16s_rul_estimator.py",
    },
    {
        "name": "State-of-power validity and derating",
        "category": "unit",
        "path": "tests/unit/test_lfp_16s_state_of_power.py",
    },
    {
        "name": "BDU independence",
        "category": "unit",
        "path": "tests/unit/test_lfp_16s_bdu_independence.py",
    },
    {
        "name": "Supervisory fault injection",
        "category": "unit",
        "path": "tests/unit/test_lfp_16s_supervisory_fault_injection.py",
    },
    {
        "name": "Protection BDU",
        "category": "module",
        "path": "software/protection/lfp_16s_protection_bdu.py",
    },
    {
        "name": "Passive balancing",
        "category": "module",
        "path": "models/balancing/lfp_16s_passive_balancing.py",
    },
    {
        "name": "BDU and balancing integration",
        "category": "integration",
        "path": "software/protection/lfp_16s_bdu_balancing_integration.py",
    },
    {
        "name": "Sensor BDU balancing integration",
        "category": "integration",
        "path": "software/protection/lfp_16s_sensor_bdu_balancing_integration.py",
    },
    {
        "name": "Unified diagnostics",
        "category": "integration",
        "path": "software/diagnostics/lfp_16s_unified_diagnostic.py",
        "requires": [
            "results/metrics/lfp_16s_ocv_soc_fusion.csv",
            "results/metrics/lfp_16s_soh_estimation.csv",
            "results/metrics/lfp_16s_rul_estimation.csv",
        ],
    },
    {
        "name": "Supervisory controller",
        "category": "integration",
        "path": "software/diagnostics/lfp_16s_supervisory_controller.py",
        "requires": [
            "results/metrics/lfp_16s_unified_diagnostics.csv",
        ],
    },
]


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_artifacts():
    snapshot = {}
    for directory in (
        PROJECT_ROOT / "results" / "metrics",
        PROJECT_ROOT / "results" / "figures",
        PROJECT_ROOT / "docs" / "figures",
    ):
        if directory.exists():
            for path in directory.rglob("*"):
                if path.is_file():
                    stat = path.stat()
                    snapshot[path] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def extract_configuration_constants(source_path):
    """Collect bounded literal settings without executing project code."""
    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return {}, [], [], []

    constants = {}
    seeds = {}
    runtime_literals = []
    scenario_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function_name = (node.func.id if isinstance(node.func, ast.Name)
                             else node.func.attr if isinstance(node.func, ast.Attribute) else "")
            if any(token in function_name.lower() for token in ("simulate", "scenario", "configuration", "config")):
                positional = []
                for arg in node.args:
                    try:
                        positional.append(ast.literal_eval(arg))
                    except (ValueError, TypeError, RecursionError):
                        positional.append(None)
                keywords = {}
                for keyword in node.keywords:
                    if keyword.arg is None:
                        continue
                    try:
                        value = ast.literal_eval(keyword.value)
                        if len(json.dumps(value)) <= 2000:
                            keywords[keyword.arg] = value
                    except (ValueError, TypeError, RecursionError):
                        continue
                if positional or keywords:
                    scenario_calls.append({"line": node.lineno, "function": function_name,
                                           "literal_arguments": positional,
                                           "literal_options": keywords})
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        value_node = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        if value_node is None:
            continue
        try:
            value = ast.literal_eval(value_node)
            serialized = json.dumps(value)
        except (ValueError, TypeError, RecursionError):
            continue
        if len(serialized) > 2000:
            continue
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if node in tree.body and target.id.isupper():
                constants[target.id] = value
                if "SEED" in target.id:
                    seeds[target.id] = value
            else:
                runtime_literals.append({"line": node.lineno, "name": target.id, "value": value})
    return constants, seeds, runtime_literals[:500], scenario_calls[:200]


def build_run_metadata(test, artifact_snapshot):
    source_path = PROJECT_ROOT / test["path"]
    if not source_path.is_file():
        return {"source_status": "missing"}

    constants, seeds, runtime_literals, scenario_calls = extract_configuration_constants(source_path)
    generated = []
    for path in sorted(set(snapshot_artifacts()) | set(artifact_snapshot), key=str):
        if not path.is_file():
            continue
        stat = path.stat()
        if artifact_snapshot.get(path) != (stat.st_mtime_ns, stat.st_size):
            generated.append({
                "path": str(path.relative_to(PROJECT_ROOT)),
                "size_bytes": stat.st_size,
                "sha256": file_sha256(path),
            })

    model_assets = []
    for relative_path in test.get("model_assets", []):
        path = PROJECT_ROOT / relative_path
        model_assets.append({
            "path": relative_path,
            "present": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else None,
            "sha256": file_sha256(path) if path.is_file() else None,
        })

    configuration_snapshots = []
    configuration_keys = {
        "configuration", "config", "parameters", "model_parameters", "scenario",
        "scenarios", "current_profile", "random_seed", "seed", "thresholds",
        "operating_conditions", "initial_conditions", "fault_injections",
    }
    for artifact in generated:
        artifact_path = PROJECT_ROOT / artifact["path"]
        if artifact_path.suffix.lower() != ".json":
            continue
        try:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        selected = {key: value for key, value in payload.items()
                    if key.lower() in configuration_keys}
        if not selected:
            continue
        serialized = json.dumps(selected, ensure_ascii=False)
        if len(serialized) > 12000:
            selected = {key: value for key, value in selected.items()
                        if len(json.dumps(value, ensure_ascii=False)) <= 6000}
        if selected:
            configuration_snapshots.append({"path": artifact["path"],
                                            "sha256": artifact["sha256"],
                                            "configuration": selected})

    return {
        "python_version": sys.version,
        "model_version_sha256": file_sha256(source_path),
        "configuration_constants": constants,
        "random_seed_constants": seeds,
        "runtime_configuration_literals": runtime_literals,
        "static_scenario_calls": scenario_calls,
        "runtime_configuration_snapshots": configuration_snapshots[:50],
        "invocation": {
            "command": test.get("command", [sys.executable, str(source_path)]),
            "working_directory": ".",
        },
        "generated_artifacts": generated,
        "tested_model_assets": model_assets,
    }


def run_test(test):
    test_path = PROJECT_ROOT / test["path"]

    missing = [
        item for item in test.get("requires", [])
        if not (PROJECT_ROOT / item).exists()
    ]

    if missing:
        return {
            "name": test["name"],
            "category": test["category"],
            "path": test["path"],
            "status": "BLOCKED",
            "duration_seconds": 0,
            "return_code": None,
            "stdout": "",
            "stderr": "",
            "error": "Missing dependencies: " + ", ".join(missing),
        }

    if not test_path.exists():
        return {
            "name": test["name"],
            "category": test["category"],
            "path": test["path"],
            "status": "MISSING",
            "duration_seconds": 0,
            "return_code": None,
            "stdout": "",
            "stderr": "",
            "error": "Test script does not exist",
        }

    start = time.perf_counter()

    try:
        process = subprocess.run(
            test.get("command", [sys.executable, str(test_path)]),
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )

        duration = time.perf_counter() - start

        status = "PASS" if process.returncode == 0 else "FAIL"

        return {
            "name": test["name"],
            "category": test["category"],
            "path": test["path"],
            "status": status,
            "duration_seconds": round(duration, 3),
            "return_code": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "error": None,
        }

    except subprocess.TimeoutExpired as error:
        return {
            "name": test["name"],
            "category": test["category"],
            "path": test["path"],
            "status": "TIMEOUT",
            "duration_seconds": round(time.perf_counter() - start, 3),
            "return_code": None,
            "stdout": error.stdout or "",
            "stderr": error.stderr or "",
            "error": "Exceeded 300-second timeout",
        }

    except Exception as error:
        return {
            "name": test["name"],
            "category": test["category"],
            "path": test["path"],
            "status": "ERROR",
            "duration_seconds": round(time.perf_counter() - start, 3),
            "return_code": None,
            "stdout": "",
            "stderr": "",
            "error": str(error),
        }


def validate_expected_artifacts(test, result):
    expected = EXPECTED_ARTIFACTS.get(test["name"])
    if expected is None:
        return
    generated = {
        item["path"] for item in result.get("run_metadata", {}).get("generated_artifacts", [])
    }
    missing = [path for path in expected if not (PROJECT_ROOT / path).is_file()]
    not_regenerated = [path for path in expected if path not in generated]
    result["expected_artifact_check"] = {
        "expected": expected,
        "missing": missing,
        "not_regenerated": not_regenerated,
        "passed": not missing and not not_regenerated,
    }
    if not missing and not not_regenerated:
        return
    result["status"] = "FAIL"
    details = []
    if missing:
        details.append("missing expected outputs: " + ", ".join(missing))
    if not_regenerated:
        details.append("outputs were not regenerated: " + ", ".join(not_regenerated))
    result["error"] = "; ".join(details)


def main():
    REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("16S INTELLIGENT BMS - REGRESSION TEST SUITE")
    print("=" * 70)

    results = []

    TESTS.append({
        "name": "Generated report validation",
        "category": "validation",
        "path": "tests/regression/validate_reports.py",
    })
    TESTS.append({
        "name": "Requirement evidence traceability",
        "category": "validation",
        "path": "tests/regression/validate_traceability.py",
    })
    TESTS.append({
        "name": "Active versus passive balancing comparison",
        "category": "module",
        "path": "models/balancing/run_active_passive_comparison.py",
    })
    TESTS.append({
        "name": "Desktop AI inference resource profile",
        "category": "verification",
        "path": "tools/profile_ai_inference.py",
    })
    TESTS.append({
        "name": "Complete unit test suite",
        "category": "unit",
        "path": "tests/unit",
        "command": [sys.executable, "-m", "pytest", "tests/unit", "-q"],
    })
    TESTS.append({
        "name": "LFP RUL slope baseline comparison",
        "category": "verification",
        "path": "tools/evaluate_lfp_rul_baselines.py",
    })
    TESTS.append({
        "name": "LFP RUL grouped cross-validation",
        "category": "verification",
        "path": "tools/evaluate_lfp_rul_group_cross_validation.py",
    })
    TESTS.append({
        "name": "Diagnostic scenario grid stress evaluation",
        "category": "verification",
        "path": "tools/evaluate_fault_diagnostic_grid.py",
    })
    TESTS.append({
        "name": "LFP RUL external pack stress test",
        "category": "verification",
        "path": "tools/evaluate_lfp_rul_external_pack.py",
    })
    TESTS.extend([
        {
            "name": "Precharge R-C assumption model",
            "category": "verification",
            "path": "tools/run_precharge_assumption_sim.py",
        },
        {
            "name": "SOC drive-cycle initialization experiment",
            "category": "verification",
            "path": "tools/run_soc_drive_cycle_experiment.py",
        },
        {
            "name": "Software protection fault injection report",
            "category": "verification",
            "path": "tools/run_software_fault_injection_report.py",
        },
    ])

    for test in TESTS:
        print(f"\n[{test['category'].upper()}] {test['name']}")

        artifacts_before = snapshot_artifacts()
        result = run_test(test)
        result["run_metadata"] = build_run_metadata(test, artifacts_before)
        validate_expected_artifacts(test, result)
        results.append(result)

        print(
            f"[{result['status']}] "
            f"{result['duration_seconds']} seconds"
        )

        if result["stdout"]:
            print(result["stdout"])

        if result["stderr"]:
            print("STDERR:")
            print(result["stderr"])

        if result["error"]:
            print("ERROR:", result["error"])

    counts = {
        status: sum(r["status"] == status for r in results)
        for status in ("PASS", "FAIL", "ERROR", "TIMEOUT", "MISSING", "BLOCKED")
    }

    total_duration = round(
        sum(r["duration_seconds"] for r in results), 3
    )

    overall = (
        "PASS"
        if all(r["status"] == "PASS" for r in results)
        else "FAIL"
    )
    artifact_checks = [
        result["expected_artifact_check"]
        for result in results
        if "expected_artifact_check" in result
    ]
    artifact_summary = {
        "experiment_stages_checked": len(artifact_checks),
        "passed": sum(item["passed"] for item in artifact_checks),
        "failed": sum(not item["passed"] for item in artifact_checks),
        "expected_files": sum(len(item["expected"]) for item in artifact_checks),
    }

    report = {
        "project": "Simulation-First 16S Intelligent BMS",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "total_scripts": len(results),
        "counts": counts,
        "total_execution_seconds": total_duration,
        "overall_status": overall,
        "expected_artifact_summary": artifact_summary,
        "results": results,
    }

    json_path = REPORT_DIRECTORY / "regression_report.json"
    json_path.write_text(
        json.dumps(report, indent=4),
        encoding="utf-8",
    )

    summary = [
        "16S INTELLIGENT BMS - REGRESSION SUMMARY",
        "=" * 55,
        f"Timestamp UTC: {report['timestamp_utc']}",
        f"Total scripts: {len(results)}",
        f"Passed: {counts['PASS']}",
        f"Failed: {counts['FAIL']}",
        f"Errors: {counts['ERROR']}",
        f"Timeouts: {counts['TIMEOUT']}",
        f"Missing: {counts['MISSING']}",
        f"Blocked: {counts['BLOCKED']}",
        f"Experiment artifact manifests: {artifact_summary['passed']}/{artifact_summary['experiment_stages_checked']} stages passed; {artifact_summary['expected_files']} expected files",
        f"Execution time: {total_duration} seconds",
        f"Overall: {overall}",
        "",
        "INDIVIDUAL RESULTS",
        "-" * 55,
    ]

    for result in results:
        summary.append(
            f"{result['status']}: {result['name']} "
            f"({result['duration_seconds']} seconds)"
        )

    summary_path = REPORT_DIRECTORY / "regression_summary.txt"
    summary_path.write_text(
        "\n".join(summary),
        encoding="utf-8",
    )

    print("\n" + "=" * 70)
    print("FINAL REGRESSION SUMMARY")
    print("=" * 70)

    for status, count in counts.items():
        print(f"{status:10}: {count}")

    print(f"Execution time: {total_duration} seconds")
    print(f"OVERALL: {overall}")
    print(f"\nJSON: {json_path}")
    print(f"TXT : {summary_path}")

    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
