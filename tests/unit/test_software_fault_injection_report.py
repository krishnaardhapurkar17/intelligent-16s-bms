from tools.run_software_fault_injection_report import run_fault_injections


def test_software_fault_report_is_fail_safe_and_labels_its_boundary():
    report = run_fault_injections()

    assert len(report["scenarios"]) == 5
    assert all(scenario["pass"] for scenario in report["scenarios"])
    assert all(
        scenario["modeled_logic_latency_ms"] == 1.0
        for scenario in report["scenarios"]
    )
    assert "AFE open-wire detection" in report["not_demonstrated"][1]
