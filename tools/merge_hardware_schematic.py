"""Build the top-level KiCad schematic as a single project sheet with child sheets.

This keeps the detailed blocks in their own .kicad_sch files while making the
root schematic a clean orchestration sheet that can be opened as the project
entry point. The individual block sheets remain editable and can be routed in
PCB layout independently.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
import generate_afe_schematic as g

ROOT = Path("hardware/kicad/intelligent_16s_bms.kicad_sch")
CHILD_SHEETS = [
    ("AFE_16S", Path("hardware/kicad/afe_16s.kicad_sch"), 0.0, 30.48,
     "cf14c7f7-8abc-4411-ae8d-a57cbec1cf13", "2"),
    ("CONTROLLER", Path("hardware/kicad/controller_16s.kicad_sch"), 250.0, 30.48,
     "4dd50d72-32ee-49c5-b922-9e2a0955a8b1", "3"),
    ("POWER_AUX", Path("hardware/kicad/power_aux_12v.kicad_sch"), 0.0, 200.0,
     "98a8aed2-bd7a-448d-980d-f89ab2300362", "4"),
    ("ACTIVE_BALANCER", Path("hardware/kicad/active_balancer_16s.kicad_sch"), 250.0, 200.0,
     "1ab048b2-e072-4f66-9966-62e228c2d62f", "5"),
]
ROOT_UUID = "8d31a641-7242-46f2-80eb-7c122b5a6e15"


def build_child_sheet(name: str, sheet_path: Path, x: float, y: float,
                      sheet_uuid: str, page: str):
    return [
        "sheet",
        ["at", g.xy(x), g.xy(y)],
        ["size", "190.5", "127.0"],
        ["exclude_from_sim", "no"],
        ["in_bom", "yes"],
        ["on_board", "yes"],
        ["dnp", "no"],
        ["stroke", ["width", "0"], ["type", "solid"]],
        ["fill", ["color", "0", "0", "0", "0"]],
        ["uuid", g.atom(sheet_uuid)],
        ["property", g.atom("Sheetname"), g.atom(name),
            ["at", g.xy(x), g.xy(y - 0.762), "0"],
            ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "bottom"]]],
        ["property", g.atom("Sheetfile"), g.atom(sheet_path.name),
            ["at", g.xy(x), g.xy(y + 127.762), "0"],
            ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "top"]]],
        ["instances", ["project", g.atom("intelligent_16s_bms"),
            ["path", g.atom(f"/{ROOT_UUID}/{sheet_uuid}"), ["page", g.atom(page)]]]],
    ]


def main():
    root = [
        "kicad_sch",
        ["version", "20250114"],
        ["generator", g.atom("eeschema")],
        ["generator_version", g.atom("10.0")],
        ["uuid", g.atom(ROOT_UUID)],
        ["paper", g.atom("A1")],
        ["title_block",
            ["title", g.atom("INTELLIGENT 16S BMS")],
            ["rev", g.atom("0.2")],
            ["company", g.atom("Project")],
            ["comment", "1", g.atom("Single schematic entry point with child sheets")],
            ["comment", "2", g.atom("Use the block sheets for detailed edits")],
            ["comment", "3", g.atom("Not a fabrication release")],
        ],
        ["text", g.atom("INTELLIGENT 16S BMS — HIERARCHICAL SCHEMATIC"),
            ["exclude_from_sim", "no"], ["at", "25", "15", "0"],
            ["effects", ["font", ["size", "2", "2"], ["bold", "yes"]], ["justify", "left"]],
            ["uuid", g.atom(str(g.uuid.uuid4()))]],
        ["text", g.atom("Child sheets are kept in separate KiCad files for easier editing and PCB ownership."),
            ["exclude_from_sim", "no"], ["at", "25", "20", "0"],
            ["effects", ["font", ["size", "1.0", "1.0"]], ["justify", "left"]],
            ["uuid", g.atom(str(g.uuid.uuid4()))]],
        *[build_child_sheet(name, path, x, y, sheet_uuid, page)
          for name, path, x, y, sheet_uuid, page in CHILD_SHEETS],
        ["sheet_instances", ["path", g.atom("/"), ["page", g.atom("1")]]],
    ]
    ROOT.write_text(g.dump(root), encoding="utf-8")


if __name__ == "__main__":
    main()
