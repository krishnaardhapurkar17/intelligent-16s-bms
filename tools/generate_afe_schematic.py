"""Generate the first component-level KiCad sheet from installed library symbols.

The sheet is a design draft, not a fabrication release. It captures the BQ76952
cell sense/filter interface and low-voltage interface components. The script
does not hide open pins or suppress ERC findings.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

KICAD = Path(r"D:\Kicad\share\kicad\symbols")
OUT = Path("hardware/kicad/afe_16s.kicad_sch")
PROJECT = "intelligent_16s_bms"
ROOT_UUID = "4cd29e41-3b89-4077-a90b-3f5a7fac7165"


def uid() -> str:
    return str(uuid.uuid4())


def tokenize(src: str) -> list[str]:
    return re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', src)


def parse(tokens: list[str]):
    def one(i: int):
        if tokens[i] != "(":
            return tokens[i], i + 1
        out = []
        i += 1
        while tokens[i] != ")":
            item, i = one(i)
            out.append(item)
        return out, i + 1
    tree, end = one(0)
    if end != len(tokens):
        raise ValueError("trailing S-expression tokens")
    return tree


def atom(v: str) -> str:
    return json.dumps(v, ensure_ascii=False)


def dump(x) -> str:
    if isinstance(x, list):
        return "(" + " ".join(dump(v) for v in x) + ")"
    return str(x)


def children(tree, head: str):
    return [x for x in tree if isinstance(x, list) and x and x[0] == head]


def prop(tree, name: str, default=None):
    for x in children(tree, "property"):
        if len(x) > 2 and x[1] == atom(name):
            return x[2]
    return default


def get_lib(symbol_id: str):
    library, name = symbol_id.split(":", 1)
    tree = parse(tokenize((KICAD / f"{library}.kicad_sym").read_text(encoding="utf-8")))
    found = next(x for x in children(tree, "symbol") if len(x) > 1 and x[1] == atom(name))
    copied = [x[:] if isinstance(x, list) else x for x in found]
    copied[1] = atom(symbol_id)
    return copied


def walk(node):
    if isinstance(node, list):
        yield node
        for child in node:
            yield from walk(child)


def pins(symbol):
    result = []
    for node in walk(symbol):
        if node and node[0] == "pin":
            at = children(node, "at")[0]
            num = json.loads(children(node, "number")[0][1])
            name = json.loads(children(node, "name")[0][1])
            result.append((num, name, float(at[1]), float(at[2])))
    # duplicate definitions may exist only for unit graphics; preserve unique pin numbers
    unique = {}
    for p in result:
        unique[p[0]] = p
    return list(unique.values())


def xy(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


class Sheet:
    def __init__(self):
        self.libdefs = {}
        self.objects = []
        self.refs = []
        self.paper = "A3"
        self.reference_offset = 0
        self.instance_path = "/" + ROOT_UUID
        self.page = "2"

    def add_symbol(self, libid, ref, value, x, y, footprint="", angle=0, nets=None):
        nets = nets or {}
        match = re.fullmatch(r"([A-Za-z]+)(\d+)", ref)
        if match and match.group(1) in {"C", "J", "R", "FLG"} and self.reference_offset:
            ref = f"{match.group(1)}{int(match.group(2)) + self.reference_offset}"
        lib = self.libdefs.get(libid)
        if lib is None:
            lib = get_lib(libid)
            self.libdefs[libid] = lib
        pinfo = pins(lib)
        # Keep symbol origins on KiCad's 1.27-mm electrical connection grid.
        x = round(x / 1.27) * 1.27
        y = round(y / 1.27) * 1.27
        iid = uid()
        inst = ["symbol", ["lib_id", atom(libid)], ["at", xy(x), xy(y), str(angle)],
                ["unit", "1"], ["exclude_from_sim", "no"], ["in_bom", "yes"],
                ["on_board", "yes"], ["dnp", "no"], ["uuid", atom(iid)]]
        # Put fields above/below the graphic; sheet is A3 landscape.
        for name, val, yy in [("Reference", ref, y - 3.0), ("Value", value, y + 3.0),
                              ("Footprint", footprint, y + 7.0), ("Datasheet", "~", y + 9.0)]:
            inst.append(["property", atom(name), atom(val), ["at", xy(x), xy(yy), "0"],
                         ["effects", ["font", ["size", "1.0", "1.0"]], ["justify", "left"],
                          ["hide", "yes"] if name in ("Footprint", "Datasheet") else ["justify", "left"]]])
        for number, name, px, py in pinfo:
            inst.append(["pin", atom(number), ["uuid", atom(uid())]])
            net = nets.get(number)
            if net and net != "NC":
                import math
                a = math.radians(angle)
                sx = x + px * math.cos(a) + py * math.sin(a)
                sy = y + px * math.sin(a) - py * math.cos(a)
                self.label(net, sx, sy)
            else:
                import math
                a = math.radians(angle)
                sx = x + px * math.cos(a) + py * math.sin(a)
                sy = y + px * math.sin(a) - py * math.cos(a)
                self.objects.append(["no_connect", ["at", xy(sx), xy(sy)], ["uuid", atom(uid())]])
        inst.append(["instances", ["project", atom(PROJECT),
                                   ["path", atom(self.instance_path),
                                    ["reference", atom(ref)], ["unit", "1"]]]])
        self.objects.append(inst)
        self.refs.append(ref)
        return pinfo

    def label(self, name, x, y, angle=0):
        self.objects.append([
            "global_label", atom(name), ["shape", "passive"],
            ["at", xy(x), xy(y), str(angle)], ["fields_autoplaced", "yes"],
            ["effects", ["font", ["size", "0.8", "0.8"]], ["justify", "left"]],
            ["uuid", atom(uid())],
            ["property", atom("Intersheetrefs"), atom("${INTERSHEET_REFS}"),
             ["at", xy(x), xy(y), str(angle)],
             ["effects", ["font", ["size", "0.8", "0.8"]], ["justify", "left"], ["hide", "yes"]]],
        ])

    def text(self, txt, x, y, size=1.0, bold=False):
        font = ["font", ["size", str(size), str(size)]]
        if bold:
            font.append(["bold", "yes"])
        self.objects.append(["text", atom(txt), ["exclude_from_sim", "no"], ["at", xy(x), xy(y), "0"],
                             ["effects", font, ["justify", "left"]], ["uuid", atom(uid())]])

    def wire(self, x1, y1, x2, y2):
        self.objects.append(["wire", ["pts", ["xy", xy(x1), xy(y1)], ["xy", xy(x2), xy(y2)]],
                             ["stroke", ["width", "0"], ["type", "default"]], ["uuid", atom(uid())]])

    def write(self):
        root = ["kicad_sch", ["version", "20250114"], ["generator", atom("eeschema")],
                ["generator_version", atom("10.0")], ["uuid", atom(ROOT_UUID)], ["paper", atom(self.paper)],
                ["lib_symbols", *self.libdefs.values()], *self.objects,
                ["sheet_instances", ["path", atom(self.instance_path), ["page", atom(self.page)]]]]
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(dump(root), encoding="utf-8")


def main():
    s = Sheet()
    s.instance_path = "/8d31a641-7242-46f2-80eb-7c122b5a6e15/cf14c7f7-8abc-4411-ae8d-a57cbec1cf13"
    s.page = "2"
    s.text("16S CELL MONITOR — BQ76952 AFE INTERFACE (DESIGN DRAFT)", 35, 24, 1.8, True)
    s.text("Cell-tap filter values follow TI's BQ76952EVM monitor reference: 20 ohm series / 220 nF differential per cell.", 35, 31)
    s.text("External contactor architecture: BQ76952 FET drivers unused; verify final component ratings before release.", 35, 36)
    bq_nets = {}
    # BQ76952 symbol pin number-to-net mapping. Pins follow TI data sheet pinout.
    pin_net_names = {
        1:"VC15",2:"VC14",3:"VC13",4:"VC12",5:"VC11",6:"VC10",7:"VC9",8:"VC8",
        9:"VC7",10:"VC6",11:"VC5",12:"VC4",13:"VC3",14:"VC2",15:"VC1",16:"VC0",
        17:"GND",18:"SRP_AFE",19:"NC",20:"SRN_AFE",21:"NTC1_SENSE",22:"NTC2_SENSE",23:"NTC3_SENSE",24:"REG18",
        25:"ALERT_AFE",26:"SCL_AFE",27:"SDA_AFE",28:"HDQ_NC",29:"CFETOFF_NC",30:"DFETOFF_NC",
        31:"DCHG_FAULT",32:"DDSG_FAULT",33:"GND",34:"REG2_NC",35:"REG1_NC",36:"NC",37:"BREG",
        38:"FUSE_NC",39:"PDSG_NC",40:"PCHG_NC",41:"GND",42:"PACK_SENSE",43:"DSG_NC",44:"NC",
        45:"CHG_NC",46:"BAT",47:"BAT",48:"VC16"
    }
    bq_nets = {str(k):v for k,v in pin_net_names.items() if not v.endswith("_NC") and v != "NC"}
    # Keyed, locking 18-circuit harness connector; pins 1-17 carry VC0-VC16
    # and pin 18 is reserved. Verify harness pin numbering against the pack drawing.
    j1map = {"1":"GND", **{str(i+1):f"TAP_{i}" for i in range(1,17)}, "18":"NC"}
    s.add_symbol("Connector_Generic:Conn_02x09_Odd_Even", "J1", "CELL_TAPS VC0..VC16; pin18 spare", 55, 115,
    "Connector_Molex:Molex_Micro-Fit_3.0_43045-1818_2x09-1MP_P3.00mm_Vertical", nets=j1map)
    # For AFE taps, cell node goes through the reference series resistor to VCn.
    # Values are represented as explicit components and net labels; differential capacitors span VCn/VC(n-1).
    res_lib="Device:R"; cap_lib="Device:C"
    for i in range(17):
        y=75 + i*5.0
        # Resistor symbols are rotated 90 degrees, pins are labeled to harness and filtered AFE node.
        left="GND" if i==0 else f"TAP_{i}"
        s.add_symbol(res_lib, f"R{i+1}", "20R", 120, y, "Resistor_SMD:R_0603_1608Metric", angle=90,
                     nets={"1":left, "2":f"VC{i}"})
    # Differential cell filters between adjacent filtered tap nets.
    for i in range(1,17):
        y=76 + (i-1)*5.0
        s.add_symbol(cap_lib, f"C{i}", "220nF", 150, y, "Capacitor_SMD:C_0603_1608Metric", angle=90,
                     nets={"1":f"VC{i}", "2":f"VC{i-1}"})
    s.add_symbol("Battery_Management:BQ76952PFB", "U1", "BQ76952PFB", 220, 120,
                 "Package_QFP:TQFP-48_7x7mm_P0.5mm", nets=bq_nets)
    # Stack-derived BAT supply: series diode plus the TI-recommended filter.
    s.text("AFE STACK SUPPLY / PACK SENSE / THERMISTORS", 185, 185, 1.0, True)
    s.add_symbol(res_lib, "R20", "20R", 105, 175, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"TAP_16", "2":"BAT_SRC"})
    s.add_symbol("Device:D_Schottky", "D1", "100V Schottky", 130, 175, "Diode_SMD:D_SOD-123", angle=0,
                 nets={"1":"BAT_DIODE", "2":"BAT_SRC"})
    s.add_symbol(res_lib, "R21", "20R", 155, 175, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"BAT_DIODE", "2":"BAT"})
    s.add_symbol(cap_lib, "C18", "1uF", 180, 180, "Capacitor_SMD:C_0603_1608Metric", angle=0,
                 nets={"1":"BAT", "2":"GND"})
    s.add_symbol(cap_lib, "C19", "1uF", 180, 190, "Capacitor_SMD:C_0603_1608Metric", angle=0,
                 nets={"1":"REG18", "2":"GND"})
    s.add_symbol("Power:PWR_FLAG", "FLG1", "PWR_FLAG", 90, 195, "", nets={"1":"GND"})
    # With external contactors and no BQ high-side protection FETs, TI's
    # guidance connects PACK to stack positive through 10 kOhm.
    s.add_symbol(res_lib, "R22", "10k PACK input", 110, 205,
                 "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"TAP_16", "2":"PACK_SENSE"})
    s.add_symbol(cap_lib, "C20", "100nF", 150, 210, "Capacitor_SMD:C_0603_1608Metric", angle=0,
                 nets={"1":"PACK_SENSE", "2":"GND"})
    s.add_symbol(res_lib, "R26", "10M BREG leakage path", 185, 210,
                 "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"BREG", "2":"GND"})
    for idx, y in enumerate((215, 230, 245), start=1):
        net=f"NTC{idx}_SENSE"
        s.add_symbol("Connector_Generic:Conn_01x02", f"J{4+idx}", f"NTC{idx}_CELL", 280, y,
                     "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
                     nets={"1":net, "2":"GND"})
        s.add_symbol("Device:Thermistor_NTC", f"RT{idx}", "10k NTC 103-AT", 320, y,
                     "Resistor_SMD:R_0603_1608Metric", angle=90, nets={"1":net, "2":"GND"})
        s.add_symbol(cap_lib, f"C{20+idx}", "220nF", 350, y,
                     "Capacitor_SMD:C_0603_1608Metric", angle=0, nets={"1":net, "2":"GND"})
    # Current-sense filter and Kelvin input connector: SRP/SRN signal polarity is positive on charge.
    s.text("KELVIN SHUNT INPUT — 100 uOhm external shunt target; verify direction and calibrate", 185, 225, 1.0, True)
    s.add_symbol("Connector_Generic:Conn_02x02_Odd_Even", "J2", "SHUNT_KELVIN", 55, 230,
                 "Connector_Molex:Molex_Micro-Fit_3.0_43045-0412_2x02_P3.00mm_Vertical",
                 nets={"1":"SHUNT_P", "2":"SHUNT_N", "3":"GND", "4":"GND"})
    s.add_symbol(res_lib, "R18", "100R", 110, 225, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"SHUNT_P", "2":"SRP_AFE"})
    s.add_symbol(res_lib, "R19", "100R", 110, 235, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"SHUNT_N", "2":"SRN_AFE"})
    s.add_symbol(cap_lib, "C17", "100nF", 145, 230, "Capacitor_SMD:C_0603_1608Metric", angle=90,
                 nets={"1":"SRP_AFE", "2":"SRN_AFE"})
    # User interfaces are brought to a connector pending MCU sheet capture.
    s.text("HOST INTERFACE — external 3V3 rail; ALERT is open-drain; BQ REG1 is not used to power the MCU", 185, 250, 1.0, True)
    s.add_symbol("Connector_Generic:Conn_01x07", "J8", "HOST_AFE", 55, 270,
                 "Connector_PinHeader_2.54mm:PinHeader_1x07_P2.54mm_Vertical",
                 nets={"1":"3V3", "2":"SDA_AFE", "3":"SCL_AFE", "4":"ALERT_AFE", "5":"DCHG_FAULT", "6":"DDSG_FAULT", "7":"GND"})
    s.add_symbol(res_lib, "R23", "4.7k", 105, 265, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"3V3", "2":"SDA_AFE"})
    s.add_symbol(res_lib, "R24", "4.7k", 105, 275, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"3V3", "2":"SCL_AFE"})
    s.add_symbol(res_lib, "R25", "10k", 105, 285, "Resistor_SMD:R_0603_1608Metric", angle=90,
                 nets={"1":"3V3", "2":"ALERT_AFE"})
    s.write()


if __name__ == "__main__":
    main()
