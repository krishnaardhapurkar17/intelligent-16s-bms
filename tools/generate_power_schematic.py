"""Generate the low-voltage auxiliary buck schematic draft."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
import generate_afe_schematic as g

g.ROOT_UUID = "5ee629e3-79f2-4315-a091-b369b3c0cc1a"
g.PROJECT = "intelligent_16s_bms"

def main():
    g.OUT = Path("hardware/kicad/power_aux_12v.kicad_sch")
    s = g.Sheet()
    s.reference_offset = 200
    s.instance_path = "/8d31a641-7242-46f2-80eb-7c122b5a6e15/98a8aed2-bd7a-448d-980d-f89ab2300362"
    s.page = "4"
    s.text("AUXILIARY POWER — INPUT PROTECTION, 3V3 MCU RAIL AND 5V ISOLATOR RAIL", 30, 25, 1.7, True)
    s.text("12V input protection and conversion are captured; fuse/TVS energy and thermal ratings remain application review items.", 30, 32)
    s.add_symbol("Connector_Generic:Conn_01x02", "J1", "VEHICLE_AUX_12V_RAW", 55, 90,
                 "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal", nets={"1":"AUX12_RAW", "2":"GND"})
    s.add_symbol("Device:Fuse", "F1", "10A AUX fuse placeholder", 95, 90, "", angle=90,
                 nets={"1":"AUX12_RAW", "2":"AUX12_FUSED"})
    s.add_symbol("Device:D_Zener", "D2", "SM8S33A unidirectional TVS", 125, 90, "",
                 nets={"1":"AUX12_FUSED", "2":"GND"})
    s.add_symbol("Power_Management:LM74700", "U22", "LM74700QDBVRQ1", 170, 90,
                 "Package_TO_SOT_SMD:SOT-23-6", nets={"1":"REV_FET_VCAP", "2":"GND", "3":"AUX12_FUSED",
                 "4":"AUX_12V", "5":"REV_FET_GATE", "6":"AUX12_FUSED"})
    s.add_symbol("Transistor_FET:Q_NMOS_GSD", "Q1", "BUK9Y22-100E 100V AEC-Q101", 215, 90,
                 "Package_TO_SOT_SMD:LFPAK56", nets={"1":"REV_FET_GATE", "2":"AUX12_FUSED", "3":"AUX_12V"})
    s.add_symbol("Device:C", "C5", "100nF VCAP", 145, 120, "Capacitor_SMD:C_0603_1608Metric",
                 nets={"1":"REV_FET_VCAP", "2":"AUX12_FUSED"})
    s.add_symbol("Device:C", "C6", "100nF raw input bypass", 80, 120, "Capacitor_SMD:C_0603_1608Metric",
                 nets={"1":"AUX12_FUSED", "2":"GND"})
    s.add_symbol("Device:C", "C7", "47uF 63V protected rail bulk", 250, 120, "Capacitor_SMD:C_1210_3225Metric",
                 nets={"1":"AUX_12V", "2":"GND"})
    s.text("Input stage: 10A fuse + 33V load-dump TVS + LM74700-Q1 ideal-diode/reverse-polarity FET. Confirm TVS clamping/energy and fuse coordination.", 30, 140)
    s.add_symbol("Regulator_Switching:LM5164DDA", "U20", "LM5164-Q1 3V3", 190, 120,
                 "Package_SO:TI_SO-PowerPAD-8", nets={"1":"GND", "2":"AUX_12V", "3":"AUX_EN",
                  "4":"RON_SET", "5":"FB_3V3", "6":"PWR_GOOD", "7":"BST", "8":"SW", "9":"GND"})
    s.add_symbol("Device:C", "C1", "2.2uF 100V", 110, 95, "Capacitor_SMD:C_1210_3225Metric", nets={"1":"AUX_12V", "2":"GND"})
    s.add_symbol("Device:C", "C2", "2.2nF bootstrap", 240, 95, "Capacitor_SMD:C_0603_1608Metric", nets={"1":"BST", "2":"SW"})
    s.add_symbol("Device:L", "L1", "47uH Isat >=1.5A", 270, 120, "Inductor_SMD:L_12x12mm_H6mm", nets={"1":"SW", "2":"3V3"})
    s.add_symbol("Device:C", "C3", "47uF 10V low ESR", 310, 145, "Capacitor_SMD:C_1210_3225Metric", nets={"1":"3V3", "2":"GND"})
    s.add_symbol("Device:C", "C4", "100nF", 330, 145, "Capacitor_SMD:C_0603_1608Metric", nets={"1":"3V3", "2":"GND"})
    s.add_symbol("Device:R", "R1", "100k RON", 120, 145, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"AUX_12V", "2":"RON_SET"})
    s.add_symbol("Device:R", "R2", "499k UVLO upper", 95, 175, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"AUX_12V", "2":"AUX_EN"})
    s.add_symbol("Device:R", "R3", "100k UVLO lower", 125, 175, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"AUX_EN", "2":"GND"})
    s.add_symbol("Device:R", "R4", "88.7k FB upper", 355, 100, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"3V3", "2":"FB_3V3"})
    s.add_symbol("Device:R", "R5", "49.9k FB lower", 355, 130, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"FB_3V3", "2":"GND"})
    s.add_symbol("Device:R", "R6", "10k PGOOD pullup", 230, 160, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"3V3", "2":"PWR_GOOD"})
    s.add_symbol("Connector_Generic:Conn_01x03", "J2", "3V3_CONTROLLER_RAIL", 390, 125,
                 "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
                 nets={"1":"3V3", "2":"GND", "3":"PWR_GOOD"})
    s.text("Layout constraints: minimize VIN/SW loop, place CIN at VIN/GND, keep FB quiet, use thermal pad copper/vias; exact layout per TI datasheet.", 30, 220)
    for ref, net, x, y in (("FLG1","AUX_12V",75,65),):
        s.add_symbol("Power:PWR_FLAG", ref, "PWR_FLAG", x, y, nets={"1":net})
    s.add_symbol("Power:PWR_FLAG", "FLG3", "PWR_FLAG", 80, 155, nets={"1":"AUX12_FUSED"})
    # Dedicated 5-V primary rail for the isolated CAN bias converter. A second
    # LM5164-Q1 channel avoids loading the 3.3-V rail and remains within its 100-V input class.
    s.text("DEDICATED 5V AUX RAIL FOR UCC33421-Q1 REINFORCED CAN ISOLATION SUPPLY", 30, 155, 1.2, True)
    s.add_symbol("Regulator_Switching:LM5164DDA", "U21", "LM5164-Q1 5V_AUX", 130, 185,
                 "Package_SO:TI_SO-PowerPAD-8", nets={"1":"GND", "2":"AUX_12V", "3":"AUX_EN",
                 "4":"RON_5V", "5":"FB_5V", "6":"PGOOD_5V", "7":"BST_5V", "8":"SW_5V", "9":"GND"})
    s.add_symbol("Device:C", "C8", "2.2uF 100V input", 65, 170, "Capacitor_SMD:C_1210_3225Metric", nets={"1":"AUX_12V", "2":"GND"})
    s.add_symbol("Device:C", "C9", "2.2nF bootstrap", 165, 165, "Capacitor_SMD:C_0603_1608Metric", nets={"1":"BST_5V", "2":"SW_5V"})
    s.add_symbol("Device:L", "L2", "47uH Isat >=1.5A", 205, 185, "Inductor_SMD:L_12x12mm_H6mm", nets={"1":"SW_5V", "2":"5V_AUX"})
    s.add_symbol("Device:C", "C10", "47uF 10V low ESR", 245, 205, "Capacitor_SMD:C_1210_3225Metric", nets={"1":"5V_AUX", "2":"GND"})
    s.add_symbol("Device:C", "C15", "100nF output bypass", 270, 205, "Capacitor_SMD:C_0603_1608Metric", nets={"1":"5V_AUX", "2":"GND"})
    s.add_symbol("Device:R", "R7", "100k RON", 65, 205, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"AUX_12V", "2":"RON_5V"})
    s.add_symbol("Device:R", "R8", "158k FB upper", 245, 165, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"5V_AUX", "2":"FB_5V"})
    s.add_symbol("Device:R", "R9", "49.9k FB lower", 270, 165, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"FB_5V", "2":"GND"})
    s.add_symbol("Device:R", "R10", "10k PGOOD pullup", 165, 215, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"3V3", "2":"PGOOD_5V"})
    s.add_symbol("Power:PWR_FLAG", "FLG4", "PWR_FLAG", 315, 185, nets={"1":"5V_AUX"})
    s.add_symbol("Connector_Generic:Conn_01x03", "J3", "5V_AUX_RAIL_CHECK", 350, 200,
                 "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", nets={"1":"5V_AUX", "2":"GND", "3":"PGOOD_5V"})
    s.write()

if __name__ == "__main__":
    main()
