"""Create a component-level MCU and BDU interface draft in KiCad format."""
from pathlib import Path
import copy
import json
import sys
sys.path.insert(0, str(Path(__file__).parent))
import generate_afe_schematic as g

g.ROOT_UUID = "e05b3924-4684-4b46-9aa4-3a367b1b23c4"
g.PROJECT = "intelligent_16s_bms"

def add_smart_switch(s, ref, x, y, nets):
    # Reuse the ISO1050's standard 8-pin rectangle geometry, then replace every
    # visible pin name/type with the verified TPS1H200A-Q1 pin assignment.
    libid = "TI:TPS1H200A-Q1"
    if libid not in s.libdefs:
        custom = copy.deepcopy(g.get_lib("Interface_CAN_LIN:ISO1050DUB"))
        custom[1] = g.atom(libid)
        for child in g.children(custom, "symbol"):
            child[1] = g.atom(json.loads(child[1]).replace("ISO1050DUB", "TPS1H200A-Q1"))
        for prop in g.children(custom, "property"):
            if len(prop) > 2 and prop[1] == g.atom("Description"):
                prop[2] = g.atom("Automotive protected high-side switch, TI TPS1H200A-Q1")
            elif len(prop) > 2 and prop[1] == g.atom("Footprint"):
                prop[2] = g.atom("Package_SO:Texas_DGN0008D_VSSOP-8-1EP_3x3mm_P0.65mm_EP2x2.94mm_Mask1.57x1.89mm")
            elif len(prop) > 2 and prop[1] == g.atom("Datasheet"):
                prop[2] = g.atom("https://www.ti.com/lit/ds/symlink/tps1h200a-q1.pdf")
        mapping = {"1": ("input", "IN"), "2": ("input", "DIAG_EN"),
                   "3": ("open_collector", "FAULT"), "4": ("input", "CL"),
                   "5": ("passive", "DELAY"), "6": ("power_in", "GND"),
                   "7": ("power_out", "OUT"), "8": ("power_in", "VS")}
        for node in g.walk(custom):
            if node and node[0] == "pin":
                number = json.loads(g.children(node, "number")[0][1])
                node[1] = mapping[number][0]
                g.children(node, "name")[0][1] = g.atom(mapping[number][1])
        s.libdefs[libid] = custom
    s.add_symbol("Interface_CAN_LIN:ISO1050DUB", ref, "TPS1H200A-Q1", x, y,
                 "Package_SO:Texas_DGN0008D_VSSOP-8-1EP_3x3mm_P0.65mm_EP2x2.94mm_Mask1.57x1.89mm",
                 nets=nets)
    instance = s.objects[-1]
    g.children(instance, "lib_id")[0][1] = g.atom(libid)

def add_custom_device(s, source_lib, libid, ref, value, x, y, nets, names, types,
                      footprint="", datasheet="~"):
    """Clone a pin-grid symbol and replace its electrical pin names/types."""
    if libid not in s.libdefs:
        custom = copy.deepcopy(g.get_lib(source_lib))
        old_name = json.loads(custom[1]).split(":", 1)[1]
        custom[1] = g.atom(libid)
        new_name = libid.split(":", 1)[1]
        for child in g.children(custom, "symbol"):
            child[1] = g.atom(json.loads(child[1]).replace(old_name, new_name))
        for node in g.walk(custom):
            if node and node[0] == "pin":
                number = json.loads(g.children(node, "number")[0][1])
                g.children(node, "name")[0][1] = g.atom(names.get(number, "NC"))
                node[1] = types.get(number, "passive")
        for prop in g.children(custom, "property"):
            if len(prop) > 2 and prop[1] == g.atom("Description"):
                prop[2] = g.atom(value)
            elif len(prop) > 2 and prop[1] == g.atom("Value"):
                prop[2] = g.atom(value)
        s.libdefs[libid] = custom
    s.add_symbol(libid, ref, value, x, y, footprint, nets=nets)
    instance = s.objects[-1]
    for prop in g.children(instance, "property"):
        if len(prop) > 2 and prop[1] == g.atom("Datasheet"):
            prop[2] = g.atom(datasheet)

def main():
    s = g.Sheet()
    s.paper = "A1"
    s.reference_offset = 100
    s.instance_path = "/8d31a641-7242-46f2-80eb-7c122b5a6e15/4dd50d72-32ee-49c5-b922-9e2a0955a8b1"
    s.page = "3"
    g.OUT = Path("hardware/kicad/controller_16s.kicad_sch")
    s.text("LOCAL CONTROLLER / ISOLATED CAN / CONTACTOR INTERFACE — DRAFT", 30, 25, 1.7, True)
    s.text("On-board BQ fault/watchdog permit gates all coil requests; pack switching remains external.", 30, 32)
    module_nets = {
        "1":"GND", "2":"3V3", "3":"MCU_EN", "4":"MAIN_POS_REQ", "5":"MAIN_NEG_REQ",
        "6":"PRECHARGE_REQ", "7":"MAIN_POS_FB", "8":"NC", "9":"NC", "10":"CAN_TX",
        "11":"CAN_RX", "12":"SDA_AFE", "13":"USB_MCU_D-", "14":"USB_MCU_D+", "15":"ISO_PWR_FAULT_N",
        "16":"NC", "17":"SCL_AFE", "18":"PRECHARGE_FB", "19":"MAIN_NEG_FB", "20":"ALERT_AFE", "21":"WATCHDOG_HEARTBEAT",
        "22":"NC", "23":"NC", "24":"NC", "25":"NC", "26":"NC", "27":"IO0_BOOT",
        "28":"MAIN_POS_DRIVER_FAULT_N", "29":"MAIN_NEG_DRIVER_FAULT_N", "30":"PRECHARGE_DRIVER_FAULT_N", "31":"NC", "32":"NC", "33":"NC", "34":"NC",
        "35":"NC", "36":"NC", "37":"NC", "38":"BOARD_TEMP_ADC", "39":"DC_LINK_ADC",
        "40":"GND", "41":"GND"
    }
    # Correct GPIO assignment: IO4/5/6 are control requests; IO7/10/11 feedback;
    # IO8/9 are AFE I2C; IO12 alert; IO13 watchdog; IO1/2 analog measurements.
    module_nets.update({"4":"MAIN_POS_REQ", "5":"MAIN_NEG_REQ", "6":"PRECHARGE_REQ",
                        "7":"MAIN_POS_FB", "18":"PRECHARGE_FB", "19":"MAIN_NEG_FB",
                        "17":"SCL_AFE", "12":"SDA_AFE", "39":"DC_LINK_ADC", "38":"BOARD_TEMP_ADC"})
    # Actual module pin naming in KiCad: pin 12=IO8, 17=IO9, 18=IO10, 19=IO11,
    # 20=IO12, 21=IO13, 38=IO2, 39=IO1.
    module_nets.update({
        "12":"SDA_AFE", "17":"SCL_AFE", "38":"BOARD_TEMP_ADC", "39":"DC_LINK_ADC",
        "8":"BAL_MOSI", "9":"BAL_CS30", "22":"BAL_SCK", "23":"BAL_CS31",
        "24":"BAL_CS32", "31":"BAL_SDO30", "32":"BAL_SDO31", "33":"BAL_SDO32",
        "34":"BAL_WDT_ANY", "35":"WD_REARM_N",
    })
    s.add_symbol("RF_Module:ESP32-S3-WROOM-1", "U2", "ESP32-S3-WROOM-1-N16R8", 170, 145,
                 "RF_Module:ESP32-S3-WROOM-1", nets=module_nets)
    s.text("3V3 MCU DOMAIN", 40, 65, 1.1, True)
    # Local decoupling and reset pull-up. The regulated rail is an external input
    # on this sheet, supplied by the automotive power sheet.
    s.add_symbol("Connector_Generic:Conn_01x03", "J1", "3V3_VSS_IN", 55, 85,
                 "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
                 nets={"1":"3V3", "2":"GND", "3":"MCU_EN"})
    s.add_symbol("Device:R", "R1", "10k MCU_EN pullup", 90, 85, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"3V3", "2":"MCU_EN"})
    s.add_symbol("Device:R", "R10", "10k IO0 strap pullup", 90, 95, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"3V3", "2":"IO0_BOOT"})
    s.add_symbol("Device:C", "C1", "100nF", 95, 115, "Capacitor_SMD:C_0603_1608Metric", nets={"1":"3V3", "2":"GND"})
    s.add_symbol("Device:C", "C2", "10uF", 115, 115, "Capacitor_SMD:C_0805_2012Metric", nets={"1":"3V3", "2":"GND"})
    s.add_symbol("Connector:USB_C_Receptacle_USB2.0_16P", "J2", "USB_SERVICE", 55, 135,
                 "Connector_USB:USB_C_Receptacle_Molex_105450-0101", nets={"A1":"GND", "A4":"USB_VBUS", "A5":"USB_CC1",
                  "A6":"USB_RAW_D+", "A7":"USB_RAW_D-", "A8":"NC", "A9":"USB_VBUS", "A12":"GND",
                  "B1":"GND", "B4":"USB_VBUS", "B5":"USB_CC2", "B6":"USB_RAW_D+", "B7":"USB_RAW_D-",
                  "B8":"NC", "B9":"USB_VBUS", "B12":"GND", "SH":"GND"})
    s.add_symbol("Device:R", "R11", "5.1k USB-C Rd", 90, 135, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"USB_CC1", "2":"GND"})
    s.add_symbol("Device:R", "R12", "5.1k USB-C Rd", 90, 145, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"USB_CC2", "2":"GND"})
    s.add_symbol("Power:GND", "#PWR01", "GND", 80, 100, nets={"1":"GND"})
    power_symbol = s.objects[-1]
    for item in power_symbol:
        if isinstance(item, list) and item and item[0] in ("in_bom", "on_board"):
            item[1] = "no"
    s.text("AUTOMOTIVE ISOLATED CAN — ISO1042-Q1 plus reinforced isolated 5V supply and CAN ESD protection", 245, 65, 1.0, True)
    iso_names = {"1":"VCC1", "2":"GND1", "3":"TXD", "4":"NC", "5":"RXD", "6":"NC", "7":"NC", "8":"GND1",
                 "9":"GND2", "10":"GND2", "11":"VCC2", "12":"CANL", "13":"CANH", "14":"NC", "15":"GND2", "16":"VCC2"}
    iso_types = {"1":"power_in", "2":"power_in", "3":"input", "4":"passive", "5":"output", "6":"passive", "7":"passive", "8":"power_in",
                 "9":"power_in", "10":"power_in", "11":"power_in", "12":"bidirectional", "13":"bidirectional", "14":"passive", "15":"power_in", "16":"power_in"}
    add_custom_device(s, "Connector_Generic:Conn_02x08_Odd_Even", "TI:ISO1042-Q1", "U3", "ISO1042DWRQ1", 310, 115,
                      {"1":"3V3", "2":"GND", "3":"CAN_TX", "4":"NC", "5":"CAN_RX", "6":"NC", "7":"NC", "8":"GND",
                       "9":"CAN_GND_ISO", "10":"CAN_GND_ISO", "11":"VISO_5V", "12":"CANL_ISO", "13":"CANH_ISO", "14":"NC",
                       "15":"CAN_GND_ISO", "16":"VISO_5V"}, iso_names, iso_types,
                      "Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm", "https://www.ti.com/lit/ds/symlink/iso1042-q1.pdf")
    add_custom_device(s, "Connector_Generic:Conn_01x03", "TI:ESD2CAN24-Q1", "D4", "ESD2CAN24DCKRQ1", 370, 155,
                      {"1":"CANL_ISO", "2":"CANH_ISO", "3":"CAN_GND_ISO"},
                      {"1":"CANL", "2":"CANH", "3":"GND"}, {"1":"passive", "2":"passive", "3":"passive"},
                      "Package_TO_SOT_SMD:SOT-323_SC-70", "https://www.ti.com/lit/ds/symlink/esd2can24-q1.pdf")
    s.add_symbol("Connector_Generic:Conn_01x04", "J3", "CAN_BUS_SHIELD", 395, 130,
                 "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-4-5.08_1x04_P5.08mm_Horizontal",
                 nets={"1":"CANH_ISO", "2":"CANL_ISO", "3":"CAN_GND_ISO", "4":"CAN_SHIELD"})
    s.add_symbol("Device:R", "R51", "1M shield bleed", 395, 165, "Resistor_SMD:R_1206_3216Metric",
                 angle=90, nets={"1":"CAN_SHIELD", "2":"CAN_GND_ISO"})
    s.add_symbol("Device:C", "C16", "1nF shield HF bond 2kV", 395, 180, "Capacitor_SMD:C_1206_3216Metric",
                 nets={"1":"CAN_SHIELD", "2":"CAN_GND_ISO"})
    s.add_symbol("Device:C", "C17", "1uF 5V_AUX local bypass", 335, 220,
                 "Capacitor_SMD:C_0805_2012Metric", nets={"1":"5V_AUX", "2":"GND"})
    s.text("Fit 120R only at a bus endpoint; CAN_SHIELD is a separate enclosure/chassis bond point.", 250, 180)
    s.text("BDU I/O — external 12V contactors; protected smart coil switches and independent permit logic are on this board", 30, 215, 1.0, True)
    s.add_symbol("Connector_Generic:Conn_01x10", "J4", "BDU_CONTROL_INTERFACE", 65, 250,
                 "Connector_PinHeader_2.54mm:PinHeader_1x10_P2.54mm_Vertical",
                 nets={"1":"MAIN_POS_REQ", "2":"MAIN_NEG_REQ", "3":"PRECHARGE_REQ", "4":"BMS_PERMIT",
                       "5":"MAIN_POS_FB_12V", "6":"MAIN_NEG_FB_12V", "7":"PRECHARGE_FB_12V",
                       "9":"WATCHDOG_HEARTBEAT", "10":"GND"})
    s.add_symbol("Connector_Generic:Conn_01x03", "J5", "AFE_I2C_ALERT", 140, 250,
                 "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
                 nets={"1":"SDA_AFE", "2":"SCL_AFE", "3":"ALERT_AFE"})
    # Automotive reinforced-isolation bias supply. UCC33421-Q1 takes the
    # dedicated regulated 5-V primary rail and generates isolated 5 V.
    iso_power_names = {"1":"EN_FLT", "2":"VINP", "3":"NC", "4":"GNDP", "5":"NC", "6":"NC", "7":"NC", "8":"NC",
                       "9":"SEL", "10":"VCC", "11":"NC", "12":"GNDS", "13":"NC", "14":"NC", "15":"NC", "16":"NC"}
    iso_power_types = {"1":"bidirectional", "2":"power_in", "3":"passive", "4":"power_in", "5":"passive", "6":"passive", "7":"passive", "8":"passive",
                       "9":"input", "10":"power_out", "11":"passive", "12":"power_in", "13":"passive", "14":"passive", "15":"passive", "16":"passive"}
    add_custom_device(s, "Connector_Generic:Conn_02x08_Odd_Even", "TI:UCC33421-Q1", "U17", "UCC33421QDHARQ1", 310, 205,
                      {"1":"ISO_PWR_FAULT_N", "2":"5V_AUX", "3":"NC", "4":"GND", "5":"NC", "6":"NC", "7":"NC", "8":"NC",
                       "9":"VISO_5V", "10":"VISO_5V", "11":"NC", "12":"CAN_GND_ISO", "13":"NC", "14":"NC", "15":"NC", "16":"NC"},
                      iso_power_names, iso_power_types, "", "https://www.ti.com/lit/ds/symlink/ucc33421-q1.pdf")
    s.add_symbol("Device:C", "C11", "15nF VINP bypass", 265, 185, "Capacitor_SMD:C_0402_1005Metric", nets={"1":"5V_AUX", "2":"GND"})
    s.add_symbol("Device:C", "C12", "10uF VINP bulk", 265, 215, "Capacitor_SMD:C_0805_2012Metric", nets={"1":"5V_AUX", "2":"GND"})
    s.add_symbol("Device:C", "C13", "15nF VCC bypass", 355, 185, "Capacitor_SMD:C_0402_1005Metric", nets={"1":"VISO_5V", "2":"CAN_GND_ISO"})
    s.add_symbol("Device:C", "C14", "22uF isolated output bulk", 355, 215, "Capacitor_SMD:C_1206_3216Metric", nets={"1":"VISO_5V", "2":"CAN_GND_ISO"})
    s.add_symbol("Device:R", "R50", "22k EN_FLT pullup", 265, 235, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"5V_AUX", "2":"ISO_PWR_FAULT_N"})
    # Fault is open-drain/active-low and is made visible to firmware on a spare GPIO.
    s.add_symbol("Power_Protection:TPD4E02B04DQA", "U18", "TPD4E02B04-Q1", 135, 155,
                 "Package_SON:USON-10_2.5x1.0mm_P0.5mm", nets={"1":"USB_RAW_D+", "2":"USB_RAW_D-", "3":"GND",
                 "4":"USB_MCU_D+", "5":"USB_MCU_D-", "6":"NC", "7":"NC", "8":"GND", "9":"NC", "10":"NC"})
    s.add_symbol("Device:D_TVS", "D5", "TPD1E10B06DYARQ1 VBUS ESD", 95, 165,
                 "Diode_SMD:D_SOD-523", nets={"1":"USB_VBUS", "2":"GND"})
    for prop in g.children(s.objects[-1], "property"):
        if len(prop) > 2 and prop[1] == g.atom("Datasheet"):
            prop[2] = g.atom("https://www.ti.com/lit/ds/symlink/tpd1e10b06-q1.pdf")
    s.add_symbol("Connector_Generic:Conn_01x02", "J7", "BOARD_NTC", 205, 250,
                 "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
                 nets={"1":"BOARD_TEMP_ADC", "2":"GND"})
    s.add_symbol("Device:R", "R23", "10k board NTC pullup", 235, 275,
                 "Resistor_SMD:R_0603_1608Metric", angle=90, nets={"1":"3V3", "2":"BOARD_TEMP_ADC"})
    s.add_symbol("Device:C", "C4", "100nF board NTC filter", 260, 275,
                 "Capacitor_SMD:C_0603_1608Metric", nets={"1":"BOARD_TEMP_ADC", "2":"GND"})
    s.add_symbol("Connector_Generic:Conn_01x02", "J8", "LOAD_SIDE_VOLTAGE_SENSE", 385, 225,
                 "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
                 nets={"1":"BDU_LOAD_PLUS", "2":"GND"})
    s.add_symbol("Device:R", "R24", "120R CAN termination DNP", 370, 130,
                 "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"CANH_ISO", "2":"CANL_ISO"})
    for node in s.objects:
        if node and node[0] == "symbol" and any(p[0] == "property" and p[1] == g.atom("Reference") and p[2] == g.atom("R24") for p in node if isinstance(p, list)):
            dnp = next((p for p in node if isinstance(p, list) and p and p[0] == "dnp"), None)
            if dnp:
                dnp[1] = "yes"
    # 12-V auxiliary-contact feedback is current-limited and optically translated
    # to MCU logic. Confirm aux-contact polarity and supply range with selected contactors.
    for i, (inp, out) in enumerate((("MAIN_POS_FB_12V","MAIN_POS_FB"),
                                     ("MAIN_NEG_FB_12V","MAIN_NEG_FB"),
                                     ("PRECHARGE_FB_12V","PRECHARGE_FB")), start=1):
        y = 185 + (i-1)*22
        s.add_symbol("Device:R", f"R{12+i}", "2.2k 12V opto input", 250, y,
                     "Resistor_SMD:R_0805_2012Metric", angle=90, nets={"1":inp, "2":f"FB{i}_LED"})
        s.add_symbol("Isolator:PC817", f"U{3+i}", "PC817 feedback optocoupler", 290, y,
                     "Package_DIP:DIP-4_W7.62mm", nets={"1":f"FB{i}_LED", "2":"GND",
                      "3":"GND", "4":out})
        s.add_symbol("Device:R", f"R{15+i}", "10k logic pullup", 330, y,
                     "Resistor_SMD:R_0603_1608Metric", angle=90, nets={"1":"3V3", "2":out})
    # Load-side pack voltage divider: two series resistors share voltage stress;
    # ratio yields about 2.7 V at the 58.4-V pack endpoint.
    s.add_symbol("Device:R", "R19", "280k 1% 0805", 235, 255, "Resistor_SMD:R_0805_2012Metric", angle=90,
                 nets={"1":"BDU_LOAD_PLUS", "2":"DIV_MID"})
    s.add_symbol("Device:R", "R20", "280k 1% 0805", 265, 255, "Resistor_SMD:R_0805_2012Metric", angle=90,
                 nets={"1":"DIV_MID", "2":"DIV_LOW"})
    s.add_symbol("Device:R", "R21", "27k 1%", 295, 255, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"DIV_LOW", "2":"GND"})
    s.add_symbol("Device:R", "R22", "10k ADC limiter", 325, 255, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"DIV_LOW", "2":"DC_LINK_ADC"})
    s.add_symbol("Device:C", "C3", "10nF ADC filter", 355, 255, "Capacitor_SMD:C_0603_1608Metric",
                 nets={"1":"DC_LINK_ADC", "2":"GND"})
    s.add_symbol("Device:D_Schottky", "D6", "BAT54H-Q upper ADC clamp", 330, 285,
                 "Diode_SMD:D_SOD-123", nets={"1":"3V3", "2":"DC_LINK_ADC"})
    s.add_symbol("Device:D_Schottky", "D7", "BAT54H-Q lower ADC clamp", 355, 285,
                 "Diode_SMD:D_SOD-123", nets={"1":"DC_LINK_ADC", "2":"GND"})
    for ref, net, x, y in (("FLG1","3V3",70,100),("FLG3","CAN_GND_ISO",375,180)):
        s.add_symbol("Power:PWR_FLAG", ref, "PWR_FLAG", x, y, nets={"1":net})
    # Safe-default request pull-downs at MCU output pins. External gate/driver
    # logic is on a separate interface and is not represented as a certified safety circuit.
    for i, net in enumerate(("MAIN_POS_REQ", "MAIN_NEG_REQ", "PRECHARGE_REQ")):
        s.add_symbol("Device:R", f"R{i+2}", "100k pulldown", 210, 235+i*12,
                     "Resistor_SMD:R_0603_1608Metric", angle=90, nets={"1":net, "2":"GND"})
    s.text("CONTACTOR COIL DRIVERS — active-high permit from BQ health supervisor AND automotive window watchdog", 30, 310, 1.0, True)
    gate_outputs = ("MAIN_POS_DRIVE_EN", "MAIN_NEG_DRIVE_EN", "PRECHARGE_DRIVE_EN")
    requests = ("MAIN_POS_REQ", "MAIN_NEG_REQ", "PRECHARGE_REQ")
    coils = ("MAIN_POS_COIL_P", "MAIN_NEG_COIL_P", "PRECHARGE_COIL_P")
    faults = ("MAIN_POS_DRIVER_FAULT_N", "MAIN_NEG_DRIVER_FAULT_N", "PRECHARGE_DRIVER_FAULT_N")
    for i, (req, gate, coil, fault) in enumerate(zip(requests, gate_outputs, coils, faults)):
        y = 335 + i*22
        s.add_symbol("74xGxx:74LVC1G08", f"U{12+i}", "SN74LVC1G08-Q1", 155, y,
                     "Package_TO_SOT_SMD:SOT-23-5", nets={"1":req, "2":"BMS_PERMIT", "3":"GND",
                      "4":gate, "5":"3V3"})
        add_smart_switch(s, f"U{7+i}", 260, y, nets={"1":gate, "2":"3V3", "3":fault,
                      "4":f"CL{i+1}", "5":f"DELAY{i+1}", "6":"GND", "7":coil, "8":"AUX_12V"})
        s.add_symbol("Device:R", f"R{31+i}", "1k smart-switch current limit 2A", 195, y-7,
                     "Resistor_SMD:R_0603_1608Metric", angle=90, nets={"1":f"CL{i+1}", "2":"GND"})
        s.add_symbol("Device:C", f"C{5+i}", "0.62uF latch-off delay", 220, y+7,
                     "Capacitor_SMD:C_0805_2012Metric", nets={"1":f"DELAY{i+1}", "2":"GND"})
        s.add_symbol("Device:R", f"R{34+i}", "10k driver fault pullup", 315, y,
                     "Resistor_SMD:R_0603_1608Metric", angle=90, nets={"1":"3V3", "2":fault})
    s.add_symbol("Device:R", "R30", "100k BMS_PERMIT default-off", 105, 330,
                 "Resistor_SMD:R_0603_1608Metric", angle=90, nets={"1":"BMS_PERMIT", "2":"GND"})
    s.add_symbol("Device:C", "C8", "10uF coil rail bulk", 355, 350,
                 "Capacitor_SMD:C_1206_3216Metric", nets={"1":"AUX_12V", "2":"GND"})
    s.add_symbol("Connector_Generic:Conn_01x04", "J9", "COIL_OUTPUTS", 385, 365,
                 "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-4-5.08_1x04_P5.08mm_Horizontal",
                 nets={"1":coils[0], "2":coils[1], "3":coils[2], "4":"GND"})
    s.text("Coils return to VSS. Driver current limit/latch timing are provisional 2A / 0.2s settings; confirm pull-in current and thermal rise from selected coil datasheets.", 30, 415)
    # AFE health requires both BQ ALERT inactive and BQ REG18 above the
    # supervisor threshold. The automotive window watchdog must also be healthy.
    s.add_symbol("74xGxx:74LVC1G08", "U10", "SN74LVC1G08-Q1 AFE health gate", 75, 335,
                 "Package_TO_SOT_SMD:SOT-23-5", nets={"1":"ALERT_AFE", "2":"AFE_PG_OK", "3":"GND",
                  "4":"AFE_OK", "5":"3V3"})
    s.add_symbol("74xGxx:74LVC1G08", "U11", "SN74LVC1G08-Q1 watchdog permit gate", 115, 335,
                 "Package_TO_SOT_SMD:SOT-23-5", nets={"1":"AFE_OK", "2":"WD_PERMIT", "3":"GND",
                  "4":"BMS_PERMIT", "5":"3V3"})
    # TPS3430-Q1: CWD=10k to VDD and SET0/SET1 low give typical 9/109 ms
    # window boundaries; the guaranteed valid WDI window is 10.35–92.7 ms.
    s.add_symbol("Power_Supervisor:TPS3430WDRC", "U15", "TPS3430WQDRCRQ1", 190, 335,
                 "Package_SON:Texas_DRC0010J", nets={"1":"3V3", "2":"WDT_CWD", "3":"GND",
                  "4":"WDT_CRST", "5":"GND", "6":"GND", "7":"WATCHDOG_HEARTBEAT",
                  "8":"WD_OK", "9":"NC", "10":"3V3", "11":"GND"})
    s.add_symbol("Device:R", "R40", "10k CWD timing select", 155, 350,
                 "Resistor_SMD:R_0603_1608Metric", angle=90, nets={"1":"3V3", "2":"WDT_CWD"})
    s.add_symbol("Device:C", "C9", "100nF CRST delay", 155, 375,
                 "Capacitor_SMD:C_0603_1608Metric", nets={"1":"WDT_CRST", "2":"GND"})
    s.add_symbol("Device:R", "R41", "10k WDO pullup", 230, 355,
                 "Resistor_SMD:R_0603_1608Metric", angle=90, nets={"1":"3V3", "2":"WD_OK"})
    s.add_symbol("Power_Supervisor:TPS3808DBV", "U16", "TPS3808G18QDBVRQ1", 340, 335,
                 "Package_TO_SOT_SMD:SOT-23-6", nets={"1":"AFE_PG_OK", "2":"GND", "3":"3V3",
                  "4":"AFE_PG_CT", "5":"REG18", "6":"3V3"})
    s.add_symbol("Device:R", "R42", "10k AFE supervisor pullup", 380, 345,
                 "Resistor_SMD:R_0603_1608Metric", angle=90, nets={"1":"3V3", "2":"AFE_PG_OK"})
    s.add_symbol("Device:C", "C10", "100nF supervisor delay", 380, 370,
                 "Capacitor_SMD:C_0603_1608Metric", nets={"1":"AFE_PG_CT", "2":"GND"})
    # Latch the TPS3430 active-low WDO pulse. AFE power-good also presets the
    # latch to fault at startup; firmware clears it only after heartbeat checks.
    s.add_symbol("74xGxx:74LVC1G00", "U23", "SN74LVC1G00-Q1 watchdog fault latch", 430, 335,
                 "Package_TO_SOT_SMD:SOT-23-5",
                 nets={"1":"WD_SET_N", "2":"WD_OK_LATCH", "3":"GND", "4":"WD_FAULT_LATCH", "5":"3V3"})
    s.add_symbol("74xGxx:74LVC1G00", "U24", "SN74LVC1G00-Q1 watchdog fault latch", 475, 335,
                 "Package_TO_SOT_SMD:SOT-23-5",
                 nets={"1":"WD_REARM_N", "2":"WD_FAULT_LATCH", "3":"GND", "4":"WD_OK_LATCH", "5":"3V3"})
    s.add_symbol("74xGxx:74LVC1G08", "U25", "SN74LVC1G08-Q1 startup/watchdog set", 430, 375,
                 "Package_TO_SOT_SMD:SOT-23-5",
                 nets={"1":"WD_OK", "2":"AFE_PG_OK", "3":"GND", "4":"WD_SET_N", "5":"3V3"})
    s.add_symbol("74xGxx:74LVC1G08", "U26", "SN74LVC1G08-Q1 latched watchdog permit", 475, 375,
                 "Package_TO_SOT_SMD:SOT-23-5",
                 nets={"1":"WD_OK", "2":"WD_OK_LATCH", "3":"GND", "4":"WD_PERMIT", "5":"3V3"})
    s.add_symbol("Device:R", "R43", "10k watchdog rearm default-high", 520, 350,
                 "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"3V3", "2":"WD_REARM_N"})
    s.text("TPS3430 WDO pulse and startup power fault set a cross-coupled NAND latch. GPIO42 must pulse WD_REARM_N low only after a healthy heartbeat; default is latched-off.", 30, 450)
    s.text("LTC3300 WDT status is diode-ORed to GPIO41; BMS_PERMIT is isolated to each balancer and forces its local WDT high on a hardware inhibit.", 30, 457)
    for i, status in enumerate(("BAL_WDT30", "BAL_WDT31", "BAL_WDT32")):
        s.add_symbol("Device:D_Schottky", f"D{8+i}", "BAT54H-Q WDT status OR", 560, 335 + i*10,
                     "Diode_SMD:D_SOD-123",
                     nets={"1":"BAL_WDT_ANY", "2":status})
    s.add_symbol("Device:R", "R44", "100k WDT status pulldown", 600, 345,
                 "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"BAL_WDT_ANY", "2":"GND"})
    s.text("Configure BQ ALERT active-low to match the permit gate. TPS3808-Q1 monitors BQ REG18.", 30, 464)
    s.write()

if __name__ == "__main__":
    main()
