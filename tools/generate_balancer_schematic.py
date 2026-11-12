"""Generate the LTC3300-2 active-balancer draft sheet."""
from pathlib import Path
import copy
import json
import sys

sys.path.insert(0, str(Path(__file__).parent))
import generate_afe_schematic as g

g.ROOT_UUID = "1ab048b2-e072-4f66-9966-62e228c2d62f"
g.PROJECT = "intelligent_16s_bms"
g.OUT = Path("hardware/kicad/active_balancer_16s.kicad_sch")

LTC_PIN_NAMES = {
    1:"G6S", 2:"I6S", 3:"G5S", 4:"I5S", 5:"G4S", 6:"I4S",
    7:"G3S", 8:"I3S", 9:"G2S", 10:"I2S", 11:"G1S", 12:"I1S",
    13:"RTONS", 14:"RTONP", 15:"CTRL", 16:"CSBI", 17:"SCKI",
    18:"SDI", 19:"SDO", 20:"WDT", 21:"V-", 22:"I1P", 23:"G1P",
    24:"C1", 25:"I2P", 26:"G2P", 27:"C2", 28:"I3P", 29:"G3P",
    30:"C3", 31:"I4P", 32:"G4P", 33:"C4", 34:"I5P", 35:"G5P",
    36:"C5", 37:"I6P", 38:"G6P", 39:"C6", 40:"BOOST+",
    41:"BOOST-", 42:"BOOST", 43:"A0", 44:"A1", 45:"A2",
    46:"A3", 47:"A4", 48:"VREG", 49:"EPAD_V-", 50:"NC",
}

ISO_PIN_NAMES = {
    1:"VCC1", 2:"INA", 3:"INB", 4:"INC", 5:"IND",
    6:"OUTE", 7:"OUTF", 8:"GND1", 9:"GND2",
    10:"INF", 11:"INE", 12:"OUTD", 13:"OUTC",
    14:"OUTB", 15:"OUTA", 16:"VCC2",
}


def add_custom_symbol(sheet, source_lib, libid, ref, value, x, y, nets,
                      names, footprint, datasheet, pin_types=None):
    if libid not in sheet.libdefs:
        custom = copy.deepcopy(g.get_lib(source_lib))
        old_name = json.loads(custom[1]).split(":", 1)[1]
        custom[1] = g.atom(libid)
        new_name = libid.split(":", 1)[1]
        for child in g.children(custom, "symbol"):
            child[1] = g.atom(json.loads(child[1]).replace(old_name, new_name))
        for node in g.walk(custom):
            if node and node[0] == "pin":
                number = int(json.loads(g.children(node, "number")[0][1]))
                g.children(node, "name")[0][1] = g.atom(names.get(number, "NC"))
                node[1] = (pin_types or {}).get(number, "passive")
        for prop in g.children(custom, "property"):
            if len(prop) > 2 and prop[1] == g.atom("Value"):
                prop[2] = g.atom(value)
            elif len(prop) > 2 and prop[1] == g.atom("Footprint"):
                prop[2] = g.atom(footprint)
            elif len(prop) > 2 and prop[1] == g.atom("Datasheet"):
                prop[2] = g.atom(datasheet)
        sheet.libdefs[libid] = custom
    sheet.add_symbol(libid, ref, value, x, y, footprint, nets=nets)
    instance = sheet.objects[-1]
    for prop in g.children(instance, "property"):
        if len(prop) > 2 and prop[1] == g.atom("Datasheet"):
            prop[2] = g.atom(datasheet)


def add_ltc(sheet, ref, address, x, cell_bottom, cell_indices, secondary_top,
            local_vreg, local_wdt, local_sdo, boost):
    pin_nets = {
        "21":f"BAL_TAP{cell_bottom}", "49":f"BAL_TAP{cell_bottom}",
        "13":f"BAL_RTONS_{ref}", "14":f"BAL_RTONP_{ref}",
        "15":f"BAL_TAP{cell_bottom}", "16":f"BAL_CS_LOCAL_{ref}",
        "17":f"BAL_SCK_LOCAL_{ref}", "18":f"BAL_MOSI_LOCAL_{ref}",
        "19":local_sdo, "20":local_wdt,
        "40":boost[0], "41":boost[1], "42":boost[2],
        "48":local_vreg,
    }
    for pin, net in zip(("43", "44", "45", "46", "47"), address):
        pin_nets[pin] = net
    for i in range(1, 7):
        cell = cell_indices.get(i)
        pin_nets[str(23 + (i - 1) * 3)] = f"BAL_G{i}P_{ref}" if cell else "NC"
        pin_nets[str(22 + (i - 1) * 3)] = f"BAL_PIS_{cell}" if cell else "NC"
        pin_nets[str(24 + (i - 1) * 3)] = f"BAL_TAP{cell}" if cell else f"BAL_TAP{cell_bottom}"
        pin_nets[str(11 - (i - 1) * 2)] = f"BAL_G{i}S_{ref}" if cell else "NC"
        pin_nets[str(12 - (i - 1) * 2)] = f"BAL_SIS_{cell}" if cell else "NC"
    pin_nets["40"] = boost[0]
    pin_nets["41"] = boost[1]
    pin_nets["42"] = boost[2]
    add_custom_symbol(
        sheet, "Connector_Generic:Conn_02x25_Odd_Even", "ADI:LTC3300-2",
        ref, "LTC3300ILXE-2#WPBF", x, 110, pin_nets, LTC_PIN_NAMES,
        "Package_QFP:LQFP-48-1EP_7x7mm_P0.5mm_EP3.6x3.6mm",
        "https://www.analog.com/media/en/technical-documentation/data-sheets/ltc3300-2.pdf",
    )
    sheet.text(f"{ref} address {address[4]}{address[3]}{address[2]}{address[1]}{address[0]} (A4..A0); "
               f"secondary span BAL_TAP{cell_bottom}..BAL_TAP{secondary_top}",
               x - 28, 155, 0.8)
    sheet.add_symbol("Device:R", f"R{340 + int(ref[2:]) * 2}", "20k RTONP", x - 42, 170,
                     "Resistor_SMD:R_0603_1608Metric", angle=90,
                     nets={"1":f"BAL_RTONP_{ref}", "2":f"BAL_TAP{cell_bottom}"})
    sheet.add_symbol("Device:R", f"R{341 + int(ref[2:]) * 2}", "15k RTONS", x - 18, 170,
                     "Resistor_SMD:R_0603_1608Metric", angle=90,
                     nets={"1":f"BAL_RTONS_{ref}", "2":f"BAL_TAP{cell_bottom}"})
    sheet.add_symbol("Device:R", f"R{350 + int(ref[2:])}", "10k WDT pull-up", x + 8, 170,
                     "Resistor_SMD:R_0603_1608Metric", angle=90,
                     nets={"1":local_vreg, "2":local_wdt})
    sheet.add_symbol("Device:R", f"R{353 + int(ref[2:])}", "10k SDO pull-up", x + 32, 170,
                     "Resistor_SMD:R_0603_1608Metric", angle=90,
                     nets={"1":local_vreg, "2":local_sdo})
    sheet.add_symbol("Device:C", f"C{320 + int(ref[2:])}", "10uF VREG bulk", x + 58, 168,
                     "Capacitor_SMD:C_0805_2012Metric",
                     nets={"1":local_vreg, "2":f"BAL_TAP{cell_bottom}"})
    permit_base = f"BAL_PERMIT_LOCAL_{ref}"
    sheet.add_symbol("Transistor_BJT:Q_PNP_BCE", f"Q{62 + int(ref[2:])}",
                     "BC857B-Q WDT pause", x + 84, 170,
                     "Package_TO_SOT_SMD:SOT-23",
                     nets={"1":f"BAL_PAUSE_BASE_{ref}", "2":local_wdt, "3":local_vreg})
    sheet.add_symbol("Device:R", f"R{356 + int(ref[2:]) * 2}", "10k WDT pause drive", x + 108, 165,
                     "Resistor_SMD:R_0603_1608Metric", angle=90,
                     nets={"1":permit_base, "2":f"BAL_PAUSE_BASE_{ref}"})
    sheet.add_symbol("Device:R", f"R{357 + int(ref[2:]) * 2}", "100k default inhibit", x + 132, 165,
                     "Resistor_SMD:R_0603_1608Metric", angle=90,
                     nets={"1":f"BAL_PAUSE_BASE_{ref}", "2":local_vreg})
    return permit_base


def add_iso(sheet, ref, chip_ref, x, local_vreg, local_vminus, cs, sdo, wdt,
            local_sdo, local_wdt, permit_base, cap_ref):
    pin_nets = {
        "1":"3V3", "2":cs, "3":"BAL_SCK", "4":"BAL_MOSI", "5":"BMS_PERMIT",
        "6":sdo, "7":wdt, "8":"GND", "9":local_vminus,
        "10":local_wdt, "11":local_sdo,
        "12":permit_base, "13":f"BAL_MOSI_LOCAL_{chip_ref}",
        "14":f"BAL_SCK_LOCAL_{chip_ref}", "15":f"BAL_CS_LOCAL_{chip_ref}",
        "16":local_vreg,
    }
    add_custom_symbol(
        sheet, "Connector_Generic:Conn_02x08_Odd_Even", "TI:ISO7762F-Q1",
        ref, "ISO7762F-Q1", x, 180, pin_nets, ISO_PIN_NAMES,
        "Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm",
        "https://www.ti.com/lit/ds/symlink/iso7762-q1.pdf",
    )
    sheet.add_symbol("Device:C", cap_ref, "100nF isolator bypass", x + 32, 205,
                     "Capacitor_SMD:C_0603_1608Metric",
                     nets={"1":"3V3", "2":"GND"})
    extra = f"C{int(cap_ref[1:]) + 1}"
    sheet.add_symbol("Device:C", extra, "100nF local isolator bypass", x + 56, 205,
                     "Capacitor_SMD:C_0603_1608Metric",
                     nets={"1":local_vreg, "2":local_vminus})
    sheet.text(f"{ref}: default-low isolation; BMS_PERMIT low drives {permit_base} low and forces LTC WDT high.",
               x - 26, 215, 0.75)


def add_wurth_transformer(sheet, ref, x, y, nets):
    libid = "Wurth:WE_750312504"
    datasheet = "https://www.we-online.com/components/products/datasheet/750312504.pdf"
    if libid not in sheet.libdefs:
        custom = copy.deepcopy(g.get_lib("Device:Transformer_1P_1S"))
        custom[1] = g.atom(libid)
        for child in g.children(custom, "symbol"):
            child[1] = g.atom(json.loads(child[1]).replace(
                "Transformer_1P_1S", "WE_750312504"))
        sub_symbol = next(
            node for node in g.children(custom, "symbol")
            if any(child and child[0] == "pin" for child in g.walk(node))
        )
        original_pins = {}
        for node in g.walk(sub_symbol):
            if node and node[0] == "pin":
                number = int(json.loads(g.children(node, "number")[0][1]))
                original_pins[number] = node
        terminal_map = {
            1: (1, "N1_A"), 2: (4, "N1_B"),
            3: (6, "N2_A"), 4: (9, "N2_B"),
        }
        duplicate_map = {
            1: (2, "N1_A", "-10.16", "2.54"),
            2: (5, "N1_B", "-10.16", "-2.54"),
            3: (7, "N2_A", "10.16", "-2.54"),
            4: (10, "N2_B", "10.16", "2.54"),
        }
        for old_number, (new_number, name) in terminal_map.items():
            pin = original_pins[old_number]
            g.children(pin, "number")[0][1] = g.atom(str(new_number))
            g.children(pin, "name")[0][1] = g.atom(name)
        for old_number, (new_number, name, px, py) in duplicate_map.items():
            duplicate = copy.deepcopy(original_pins[old_number])
            g.children(duplicate, "number")[0][1] = g.atom(str(new_number))
            g.children(duplicate, "name")[0][1] = g.atom(name)
            at = g.children(duplicate, "at")[0]
            at[1], at[2] = px, py
            g.children(duplicate, "length")[0][1] = "3.81"
            sub_symbol.append(duplicate)
        for prop in g.children(custom, "property"):
            if len(prop) > 2 and prop[1] == g.atom("Value"):
                prop[2] = g.atom("WE-FLYLT 750312504")
            elif len(prop) > 2 and prop[1] == g.atom("Datasheet"):
                prop[2] = g.atom(datasheet)
        sheet.libdefs[libid] = custom
    sheet.add_symbol(libid, ref, "WE-FLYLT 750312504", x, y, nets=nets)
    instance = sheet.objects[-1]
    for prop in g.children(instance, "property"):
        if len(prop) > 2 and prop[1] == g.atom("Datasheet"):
            prop[2] = g.atom(datasheet)


def add_channel(sheet, ref, cell, local_index, local_ref, cell_low, sec_top,
                x, y):
    t_ref = f"T{30 + cell - 1}"
    qp_ref = f"Q{30 + 2 * (cell - 1)}"
    qs_ref = f"Q{31 + 2 * (cell - 1)}"
    rp_ref = f"R{301 + 2 * (cell - 1)}"
    rs_ref = f"R{302 + 2 * (cell - 1)}"
    cp_ref = f"C{300 + cell}"
    p_sw = f"BAL_PSW_{cell}"
    p_sense = f"BAL_PIS_{cell}"
    s_sw = f"BAL_SSW_{cell}"
    s_sense = f"BAL_SIS_{cell}"
    p_gate = f"BAL_G{local_index}P_{local_ref}"
    s_gate = f"BAL_G{local_index}S_{local_ref}"
    sheet.text(f"Cell {cell} / {local_ref} channel {local_index}", x, y - 10, 0.75, True)
    add_wurth_transformer(
        sheet, t_ref, x + 12, y + 15,
        {"1":f"BAL_TAP{cell}", "2":f"BAL_TAP{cell}",
         "4":p_sw, "5":p_sw, "6":f"BAL_TAP{sec_top}",
         "7":f"BAL_TAP{sec_top}", "9":s_sw, "10":s_sw})
    sheet.add_symbol(
        "Transistor_FET:Q_NMOS_GSD", qp_ref, "BUK9Y22-100E 100V",
        x + 30, y + 15, "Package_TO_SOT_SMD:LFPAK56",
        nets={"1":p_gate, "2":p_sense, "3":p_sw})
    sheet.add_symbol(
        "Device:R", rp_ref, "25mR 1% primary peak sense",
        x + 30, y + 42, "Resistor_SMD:R_2512_6332Metric", angle=90,
        nets={"1":p_sense, "2":f"BAL_TAP{cell - 1}"})
    sheet.add_symbol(
        "Transistor_FET:Q_NMOS_GSD", qs_ref, "BUK9Y22-100E 100V",
        x + 48, y + 15, "Package_TO_SOT_SMD:LFPAK56",
        nets={"1":s_gate, "2":s_sense, "3":s_sw})
    sheet.add_symbol(
        "Device:R", rs_ref, "25mR 1% secondary peak sense",
        x + 48, y + 42, "Resistor_SMD:R_2512_6332Metric", angle=90,
        nets={"1":s_sense, "2":f"BAL_TAP{cell_low}"})
    sheet.add_symbol(
        "Device:C", cp_ref, "47uF 16V X7R; Ceff >= 12uF",
        x + 10, y + 55, "Capacitor_SMD:C_1210_3225Metric",
        nets={"1":f"BAL_TAP{cell}", "2":f"BAL_TAP{cell - 1}"})


def main():
    s = g.Sheet()
    s.paper = "A1"
    s.instance_path = "/8d31a641-7242-46f2-80eb-7c122b5a6e15/1ab048b2-e072-4f66-9966-62e228c2d62f"
    s.page = "5"
    s.text("16S TRANSFORMER-COUPLED ACTIVE BALANCER — ENGINEERING DRAFT", 25, 20, 1.7, True)
    s.text("Not a fabrication release. LTC3300-2 Rev. B application topology adapted to 16S; no PCB/physical validation.", 25, 28)
    s.text("Separate high-current J30 harness: pins 1-17 = BAL_TAP0..16, pins 18-20 spare. Connect taps at the cell stack; keep balance current out of the AFE sense harness/filter.", 25, 35)
    s.text("16 channels: U30 cells 1-6 / 12S secondary; U31 cells 7-12 / 10S secondary; U32 cells 13-16 / 4S secondary.", 25, 42)
    s.text("25mR sense gives 2A peak. With 1:1 turns and S=4..12, first-order cell transfer is below 1A; tune/verify with actual magnetics.", 25, 49)
    s.text("Only one cell channel stack-wide at a time in firmware. Charge-only policy; require closed BDU, valid sensors, no fault, and all cell temperatures <45C.", 25, 56)
    s.text("WE 750312504 pairs: 1+2, 4+5, 6+7, 9+10 are common terminals. Not automotive-qualified; confirm permitted use and replace/approve before release.", 25, 63)

    tap_nets = {str(i + 1):f"BAL_TAP{i}" for i in range(17)}
    tap_nets.update({"18":"NC", "19":"NC", "20":"NC"})
    s.add_symbol("Connector_Generic:Conn_02x10_Odd_Even", "J30",
                 "BALANCE POWER TAPS VC0..VC16; 3 spare", 55, 105,
                 "Connector_Molex:Molex_Mini-Fit_Jr_5566-20A_2x10_P4.20mm_Vertical",
                 nets=tap_nets)
    s.text("Harness ampacity, individual tap fusing, mating contacts and connector thermal derating are open release items.", 25, 130)

    groups = [
        ("U30", 0, {i:i for i in range(1,7)}, 12, 0, 0),
        ("U31", 6, {i:i+6 for i in range(1,7)}, 16, 1, 1),
        ("U32", 12, {i:i+10 for i in range(3,7)}, 16, 2, 2),
    ]
    positions = {"U30":135, "U31":315, "U32":495}
    permit_bases = {}
    for ref, bottom, cell_map, secondary_top, address_value, iso_index in groups:
        vreg = f"BAL_VREG_{ref}"
        iso_ref = f"U{int(ref[1:]) + 3}"
        wdt = f"BAL_WDT_LOCAL_{iso_ref}"
        sdo = f"BAL_SDO_LOCAL_{iso_ref}"
        if ref == "U30":
            address = ["BAL_TAP0"] * 5
            boost = ("BAL_TAP7", "NC", f"BAL_TAP{bottom}")
        elif ref == "U31":
            address = ["BAL_VREG_U31"] + ["BAL_TAP6"] * 4
            boost = ("BAL_TAP13", "NC", f"BAL_TAP{bottom}")
        else:
            address = ["BAL_TAP12", "BAL_VREG_U32", "BAL_TAP12", "BAL_TAP12", "BAL_TAP12"]
            boost = ("BAL_BOOST_PLUS_U32", "BAL_BOOST_MINUS_U32", vreg)
        local_indices = {i:cell for i, cell in cell_map.items()}
        permit_bases[ref] = add_ltc(
            s, ref, address, positions[ref], bottom, local_indices, secondary_top,
            vreg, wdt, sdo, boost)
        add_iso(
            s, iso_ref, ref, positions[ref], vreg,
            f"BAL_TAP{bottom}", f"BAL_CS{int(ref[1:])}", f"BAL_SDO{int(ref[1:])}",
            f"BAL_WDT{int(ref[1:])}", sdo, wdt, permit_bases[ref],
            f"C{330 + iso_index * 2}")
        s.text(f"{ref}: CTRL=V- multi-transformer mode; address {address_value}.", positions[ref]-45, 225, 0.8)

    channel_positions = {
        "U30":(25, 240), "U31":(205, 240), "U32":(385, 240),
    }
    for ref, bottom, cell_map, secondary_top, _, _ in groups:
        x0, y0 = channel_positions[ref]
        for row, local_indices in enumerate((range(1,4), range(4,7))):
            for col, local_index in enumerate(local_indices):
                cell = cell_map.get(local_index)
                if cell:
                    add_channel(
                        s, ref, cell, local_index, ref, bottom, secondary_top,
                        x0 + col * 60, y0 + row * 74)

    # Top sub-stack only has four cells, mapped to C3-C6; the two unused
    # low-side cell inputs are shorted to V- by the controller pin map.
    s.add_symbol("Device:R", "R349", "6.8R boost inrush", 535, 145,
                 "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"BAL_TAP16", "2":"BAL_BOOST_DIODE_IN"})
    s.add_symbol("Device:D_Schottky", "D30", "Schottky; VRRM>6V, surge>=1A", 555, 145,
                 "Diode_SMD:D_SOD-123",
                 nets={"1":"BAL_BOOST_PLUS_U32", "2":"BAL_BOOST_DIODE_IN"})
    s.add_symbol("Device:C", "C336", "100nF boost capacitor", 575, 145,
                 "Capacitor_SMD:C_0603_1608Metric",
                 nets={"1":"BAL_BOOST_PLUS_U32", "2":"BAL_BOOST_MINUS_U32"})
    s.text("Top U32 uses BOOST=VREG and the datasheet Schottky/flying-capacitor circuit; U30/U31 use the next higher cell rail.", 405, 228, 0.8)
    s.text("Primary/secondary snubbers (ADI starting point: 330R + 100pF in series per winding) are not populated; determine by ringing/thermal analysis.", 25, 405)
    s.text("Cell bypass capacitors require >=12uF effective per cell at bias/temperature for the 1A broken-connection design target; 47uF nominal is provisional.", 25, 412)
    s.write()


if __name__ == "__main__":
    main()
