"""Stream raw public LFP datasets into compact, documented model tables.

This command does not modify or copy the raw downloads. UConn RPT files are
processed incrementally; the Seville dataset is small enough to convert into
per-sample discharge records. Outputs are research labels derived from test
protocols, not independent laboratory SOC measurements.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
import re
import sys


UCONN_GLOB = "UConn*LFP*"
SEVILLE_GLOB = "Seville*"
INDUSTRIAL_GLOB = "Industrial*"
NOMINAL_CAPACITY_AH = 1.2
EOL_SOH = 80.0


def find_directory(root: Path, pattern: str) -> Path | None:
    matches = sorted(path for path in root.glob(pattern) if path.is_dir())
    if len(matches) > 1:
        raise RuntimeError(f"More than one dataset folder matches {pattern!r}: {matches}")
    return matches[0] if matches else None


def cell_number(path: Path) -> str | None:
    match = re.search(r"cell_(\d+)", path.name, flags=re.IGNORECASE)
    return match.group(1) if match else None


def prepare_uconn_rpt(dataset_dir: Path, output_path: Path) -> int:
    """Summarize RPT capacities and pulse-start resistance by cell and RPT."""
    rpt_dir = dataset_dir / "rpt_data"
    files = sorted(rpt_dir.rglob("rpt_cell_*.csv"))
    if not files:
        raise FileNotFoundError(f"No rpt_cell_*.csv files found under {rpt_dir}")

    # Each key is one cell/RPT. Only compact aggregates remain in memory.
    groups: dict[tuple[str, int], dict] = {}
    for file_index, path in enumerate(files, start=1):
        cell = cell_number(path)
        if cell is None:
            continue
        print(f"[{file_index}/{len(files)}] {path.name}", file=sys.stderr)
        with path.open("r", newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            required = {"RPT Number", "Voltage (V)", "Current (A)", "Capacity (Ah)",
                        "Segment Key", "Pulse SOC", "Pulse Type", "Step Number",
                        "Num Cycles", "Time (s)"}
            if not required.issubset(reader.fieldnames or ()):
                raise ValueError(f"Unexpected UConn RPT schema in {path}")
            for row in reader:
                try:
                    rpt = int(float(row["RPT Number"]))
                    capacity = float(row["Capacity (Ah)"])
                    voltage = float(row["Voltage (V)"])
                    current = float(row["Current (A)"])
                    cycles = float(row["Num Cycles"] or 0.0)
                    elapsed = float(row["Time (s)"] or 0.0)
                except (TypeError, ValueError):
                    continue
                key = (cell, rpt)
                item = groups.setdefault(key, {
                    "week": None, "date": "", "cycles_since_rpt": 0.0,
                    "capacity_ah": None, "pulses": defaultdict(dict),
                    "previous_sample": None,
                })
                item["week"] = row.get("Week Number", "")
                item["date"] = row.get("Date (yyyy.mm.dd hh.mm.ss)", "")
                item["cycles_since_rpt"] = max(item["cycles_since_rpt"], cycles)
                if row.get("Segment Key", "").strip().lower() == "ref_dchg":
                    old = item["capacity_ah"]
                    item["capacity_ah"] = capacity if old is None else max(old, capacity)
                if row.get("Segment Key", "").strip().lower() in {"slowpulse", "fastpulse"}:
                    raw_soc = row.get("Pulse SOC", "")
                    try:
                        soc = round(float(raw_soc), 3)
                    except (TypeError, ValueError):
                        continue
                    pulse_key = (row["Segment Key"].strip().lower(), soc,
                                 row.get("Pulse Type", "").strip().lower(),
                                 row.get("Step Number", ""))
                    pulse = item["pulses"][pulse_key]
                    # Resistance comes from the voltage/current step at pulse start.
                    if "first" not in pulse or elapsed < pulse["first"][0]:
                        pulse["first"] = (elapsed, voltage, current)
                        pulse["baseline"] = item["previous_sample"]
                item["previous_sample"] = (elapsed, voltage, current)

    # Derive per-cell cumulative cycles and the first observed 80%-SOH point.
    by_cell: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for (cell, rpt), record in groups.items():
        by_cell[cell].append((rpt, record))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    columns = ["cell_id", "rpt_number", "week_number", "date", "cumulative_cycles",
               "capacity_ah", "soh_pct", "capacity_fade_pct", "delta_capacity_ah",
               "pulse_resistance_ohm_mean", "pulse_soc_count", "rul_cycles_to_80pct",
               "label_notes"]
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for cell, records in sorted(by_cell.items()):
            records.sort(key=lambda entry: entry[0])
            cumulative = 0.0
            history = []
            for rpt, record in records:
                cumulative += record["cycles_since_rpt"]
                capacity = record["capacity_ah"]
                if capacity is None or capacity <= 0:
                    continue
                soh = 100.0 * capacity / NOMINAL_CAPACITY_AH
                resistances = []
                for pulse in record["pulses"].values():
                    first = pulse.get("first")
                    baseline = pulse.get("baseline")
                    if first is None or baseline is None:
                        continue
                    delta_i = first[2] - baseline[2]
                    if abs(delta_i) >= 0.05:
                        resistance = abs((first[1] - baseline[1]) / delta_i)
                        if 0 < resistance < 5:
                            resistances.append(resistance)
                history.append({"rpt": rpt, "record": record, "cycle": cumulative,
                                "capacity": capacity, "soh": soh,
                                "resistance": (sum(resistances) / len(resistances)
                                               if resistances else "")})
            eol = next((row["cycle"] for row in history if row["soh"] <= EOL_SOH), None)
            previous_capacity = None
            for row in history:
                record = row["record"]
                capacity = row["capacity"]
                fade = 100.0 - row["soh"]
                writer.writerow({
                    "cell_id": cell,
                    "rpt_number": row["rpt"],
                    "week_number": record["week"],
                    "date": record["date"],
                    "cumulative_cycles": f"{row['cycle']:.6f}",
                    "capacity_ah": f"{capacity:.8f}",
                    "soh_pct": f"{row['soh']:.6f}",
                    "capacity_fade_pct": f"{fade:.6f}",
                    "delta_capacity_ah": "" if previous_capacity is None else
                        f"{capacity - previous_capacity:.8f}",
                    "pulse_resistance_ohm_mean": row["resistance"],
                    "pulse_soc_count": len(record["pulses"]),
                    "rul_cycles_to_80pct": "" if eol is None else f"{max(0.0, eol-row['cycle']):.6f}",
                    "label_notes": "capacity SOH from ref_dchg; RUL to first observed <=80% SOH; pulse resistance is an approximate 1 s deltaV/deltaI",
                })
                previous_capacity = capacity
                rows_written += 1
    return rows_written


def prepare_seville_discharge(dataset_dir: Path, output_path: Path) -> int:
    """Convert discharge traces to rows with within-cycle coulomb-count labels."""
    files = sorted((dataset_dir / "ENSAYOSBATERIA").rglob("DESCARGA*.txt"))
    if not files:
        files = sorted(dataset_dir.rglob("DESCARGA*.TXT"))
    if not files:
        raise FileNotFoundError(f"No Seville DESCARGA*.txt files found under {dataset_dir}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["cycle_id", "sample_index", "voltage_v", "current_charge_a",
               "current_discharge_a", "temperature_c", "timestamp_s", "soc_protocol_pct",
               "discharge_capacity_ah", "label_notes"]
    rows_written = 0
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for file_index, path in enumerate(files, start=1):
            print(f"[{file_index}/{len(files)}] {path.name}", file=sys.stderr)
            trace = []
            with path.open("r", encoding="utf-8-sig") as stream:
                for line in stream:
                    fields = line.split()
                    if len(fields) < 5:
                        continue
                    try:
                        voltage, charge_i, discharge_i, temp, timestamp = map(float, fields[:5])
                    except ValueError:
                        continue
                    trace.append((voltage, charge_i, discharge_i, temp, timestamp))
            if len(trace) < 2:
                continue
            # The published protocol discharges to 2.5 V. Normalize the measured
            # discharge throughput to that cycle's full observed discharge.
            increments = []
            total_ah = 0.0
            for previous, current in zip(trace, trace[1:]):
                dt = max(0.0, min(current[4] - previous[4], 10.0))
                amps = max(0.0, (previous[2] + current[2]) / 2.0)
                delta_ah = amps * dt / 3600.0
                increments.append(delta_ah)
                total_ah += delta_ah
            if total_ah <= 0:
                continue
            remaining = total_ah
            cycle_match = re.search(r"(\d+)", path.stem)
            cycle_id = cycle_match.group(1) if cycle_match else path.stem
            for index, sample in enumerate(trace):
                if index:
                    remaining -= increments[index - 1]
                soc = min(100.0, max(0.0, 100.0 * remaining / total_ah))
                writer.writerow({
                    "cycle_id": cycle_id,
                    "sample_index": index,
                    "voltage_v": f"{sample[0]:.7f}",
                    "current_charge_a": f"{sample[1]:.7f}",
                    "current_discharge_a": f"{sample[2]:.7f}",
                    "temperature_c": f"{sample[3]:.7f}",
                    "timestamp_s": f"{sample[4]:.3f}",
                    "soc_protocol_pct": f"{soc:.6f}",
                    "discharge_capacity_ah": f"{total_ah:.8f}",
                    "label_notes": "SOC normalized from current integration over this measured discharge; protocol-derived, not independent ground truth",
                })
                rows_written += 1
    return rows_written


def inspect_industrial_csv(dataset_dir: Path) -> tuple[Path, int, list[str]]:
    candidates = list(dataset_dir.rglob("GMP_LFP_40Ah_3000Cycle.csv"))
    if len(candidates) != 1:
        raise FileNotFoundError(f"Expected one industrial CSV, found {len(candidates)}")
    path = candidates[0]
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        columns = list(reader.fieldnames or [])
        count = sum(1 for _ in reader)
    return path, count, columns


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets-root", type=Path, default=Path("datasets"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/raw/lfp"))
    parser.add_argument("--uconn", action="store_true", help="process UConn RPT files")
    parser.add_argument("--seville", action="store_true", help="process Seville discharge traces")
    parser.add_argument("--industrial", action="store_true", help="inspect industrial pack table")
    parser.add_argument("--all", action="store_true", help="run all available dataset steps")
    args = parser.parse_args()
    do_all = args.all or not (args.uconn or args.seville or args.industrial)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if do_all or args.uconn:
        path = find_directory(args.datasets_root, UCONN_GLOB)
        if path is None:
            raise FileNotFoundError(f"UConn dataset not found under {args.datasets_root}")
        count = prepare_uconn_rpt(path, args.output_dir / "uconn_rpt_features.csv")
        print(f"UConn RPT rows written: {count}")
    if do_all or args.seville:
        path = find_directory(args.datasets_root, SEVILLE_GLOB)
        if path is None:
            raise FileNotFoundError(f"Seville dataset not found under {args.datasets_root}")
        count = prepare_seville_discharge(path, args.output_dir / "seville_discharge_soc.csv")
        print(f"Seville discharge samples written: {count}")
    if do_all or args.industrial:
        path = find_directory(args.datasets_root, INDUSTRIAL_GLOB)
        if path is None:
            raise FileNotFoundError(f"Industrial dataset not found under {args.datasets_root}")
        csv_path, count, columns = inspect_industrial_csv(path)
        print(f"Industrial rows: {count}; columns: {', '.join(columns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
