import csv

from tools.prepare_lfp_dataset import prepare_uconn_rpt


def _write_rpt(path, records):
    columns = ["RPT Number", "Voltage (V)", "Current (A)", "Capacity (Ah)",
               "Segment Key", "Pulse SOC", "Pulse Type", "Step Number",
               "Num Cycles", "Time (s)",
               "Week Number", "Date (yyyy.mm.dd hh.mm.ss)"]
    path.parent.mkdir(parents=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)


def _row(rpt, capacity, cycles=100):
    return {
        "RPT Number": rpt, "Voltage (V)": 3.2, "Current (A)": -1.0,
        "Capacity (Ah)": capacity, "Segment Key": "ref_dchg", "Pulse SOC": "",
        "Pulse Type": "", "Step Number": "", "Num Cycles": cycles,
        "Time (s)": 0, "Week Number": rpt,
        "Date (yyyy.mm.dd hh.mm.ss)": "2022-01-01 00:00:00",
    }


def test_uconn_rpt_features_build_capacity_soh_and_observed_eol_rul(tmp_path):
    dataset = tmp_path / "uconn"
    pulse_start = {**_row(0, 0.0), "Voltage (V)": 3.3, "Current (A)": 0.2,
                   "Segment Key": "slowpulse", "Pulse SOC": 20, "Time (s)": 1200}
    pulse_end = {**pulse_start, "Voltage (V)": 3.3, "Current (A)": 0.4,
                 "Time (s)": 1201}
    rest = {**_row(0, 0.0), "Voltage (V)": 3.2, "Current (A)": 0.0,
            "Segment Key": "-", "Time (s)": 1199}
    _write_rpt(dataset / "rpt_data" / "rpt_cell_02_part0.csv", [
        _row(0, 1.2), rest, pulse_start, pulse_end, _row(1, 0.9),
    ])
    output = tmp_path / "out.csv"

    assert prepare_uconn_rpt(dataset, output) == 2
    with output.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert [float(row["soh_pct"]) for row in rows] == [100.0, 75.0]
    assert [float(row["rul_cycles_to_80pct"]) for row in rows] == [100.0, 0.0]
    assert abs(float(rows[0]["pulse_resistance_ohm_mean"]) - 0.5) < 1e-8


def test_uconn_rpt_leaves_rul_censored_when_eol_is_not_observed(tmp_path):
    dataset = tmp_path / "uconn"
    _write_rpt(dataset / "rpt_data" / "rpt_cell_02_part0.csv", [_row(0, 1.1)])
    output = tmp_path / "out.csv"

    assert prepare_uconn_rpt(dataset, output) == 1
    with output.open(newline="", encoding="utf-8") as stream:
        row = next(csv.DictReader(stream))
    assert row["rul_cycles_to_80pct"] == ""
