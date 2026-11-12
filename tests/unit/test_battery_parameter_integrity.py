import json
import math
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

MANUFACTURER_FILE = (
    PROJECT_ROOT
    / "models"
    / "battery-parameters"
    / "eve_lf100la_vA.json"
)

ECM_FILE = (
    PROJECT_ROOT
    / "models"
    / "battery-parameters"
    / "lf100la_ecm_assumptions.json"
)


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def main():

    manufacturer = load_json(MANUFACTURER_FILE)
    ecm = load_json(ECM_FILE)

    results = {}

    cell = manufacturer["cell"]
    rated = manufacturer["rated_parameters"]
    model = manufacturer["model_parameters"]
    provenance = manufacturer["provenance"]

    # Test 1: Manufacturer identity
    results["Manufacturer identity"] = (
        cell["manufacturer"] == "EVE Energy"
        and cell["model"] == "LF100LA"
        and cell["chemistry"] == "LFP"
    )

    # Test 2: Manufacturer rated parameters
    results["Rated parameter validity"] = all(
        math.isfinite(rated[key]) and rated[key] > 0
        for key in [
            "nominal_capacity_Ah",
            "nominal_voltage_V",
            "nominal_energy_Wh",
            "charge_cutoff_voltage_V",
            "discharge_cutoff_voltage_V",
        ]
    )

    # Test 3: Rated voltage and energy consistency
    results["Nominal energy consistency"] = math.isclose(
        rated["nominal_capacity_Ah"]
        * rated["nominal_voltage_V"],
        rated["nominal_energy_Wh"],
        rel_tol=1e-9
    )

    # Test 4: Manufacturer operating limits
    results["Operating limit consistency"] = (
        rated["discharge_cutoff_voltage_V"]
        < rated["nominal_voltage_V"]
        < rated["charge_cutoff_voltage_V"]
        and rated["recommended_soc_min"]
        < rated["recommended_soc_max"]
    )

    # Test 5: Manufacturer provenance
    results["Manufacturer provenance"] = (
        provenance["rated_parameters"]
        == "EVE LF100LA Version A product specification"
        and provenance["source"].startswith("https://")
    )

    # Test 6: Unidentified model parameters remain explicit
    results["Unidentified model parameters remain null"] = all(
        value is None for value in model.values()
    )

    # Test 7: ECM assumptions are explicitly synthetic
    results["ECM assumptions labelled synthetic"] = (
        "Synthetic" in ecm["status"]
        and "not manufacturer validated" in ecm["status"]
    )

    # Test 8: Shared rated parameters remain consistent
    results["ECM rated parameter consistency"] = (
        ecm["capacity_Ah"] == rated["nominal_capacity_Ah"]
        and ecm["nominal_voltage_V"] == rated["nominal_voltage_V"]
        and ecm["cutoff_voltage_V"]
        == rated["discharge_cutoff_voltage_V"]
    )

    # Test 9: ECM resistance and time constant validity
    results["ECM dynamic parameters valid"] = all(
        math.isfinite(ecm[key]) and ecm[key] > 0
        for key in ["R0_ohm", "R1_ohm", "tau_seconds"]
    )

    # Test 10: OCV-SOC table structure
    table = ecm["ocv_soc_table"]

    valid_structure = (
        isinstance(table, list)
        and len(table) >= 2
        and all(
            isinstance(point, list)
            and len(point) == 2
            and all(
                isinstance(value, (int, float))
                and math.isfinite(value)
                for value in point
            )
            for point in table
        )
    )

    results["OCV-SOC table structure"] = valid_structure

    # Test 11: OCV-SOC domain and ordering
    if valid_structure:
        soc_values = [point[0] for point in table]
        voltage_values = [point[1] for point in table]

        results["OCV-SOC domain and ordering"] = (
            all(0.0 <= soc <= 1.0 for soc in soc_values)
            and all(
                soc_values[i] < soc_values[i + 1]
                for i in range(len(soc_values) - 1)
            )
            and all(
                voltage_values[i] <= voltage_values[i + 1]
                for i in range(len(voltage_values) - 1)
            )
        )
    else:
        results["OCV-SOC domain and ordering"] = False

    # Test 12: AC impedance and ECM DC resistance are distinct fields
    results["AC impedance not relabelled as ECM resistance"] = (
        "ac_impedance_1kHz_max_ohm" in rated
        and "R0_ohm" in ecm
        and "dc_internal_resistance_ohm" in model
    )

    print("=" * 65)
    print("BATTERY PARAMETER INTEGRITY VALIDATION")
    print("=" * 65)

    for name, passed in results.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")

    overall = all(results.values())

    print("\nPASSED:", sum(results.values()), "/", len(results))
    print("OVERALL:", "PASS" if overall else "FAIL")

    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
