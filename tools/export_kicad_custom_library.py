"""Export embedded project-specific symbols into local KiCad libraries."""
from pathlib import Path
import copy
import json
import sys

sys.path.insert(0, str(Path(__file__).parent))
import generate_afe_schematic as g

SCHEMATICS = (
    Path("hardware/kicad/controller_16s.kicad_sch"),
    Path("hardware/kicad/active_balancer_16s.kicad_sch"),
)
LIBRARIES = {
    "TI": Path("hardware/kicad/TI.kicad_sym"),
    "ADI": Path("hardware/kicad/ADI.kicad_sym"),
    "Wurth": Path("hardware/kicad/Wurth.kicad_sym"),
}


def main():
    symbols_by_library = {name: {} for name in LIBRARIES}
    for schematic in SCHEMATICS:
        root = g.parse(g.tokenize(schematic.read_text(encoding="utf-8")))
        lib_symbols = next(x for x in g.children(root, "lib_symbols"))
        for symbol in g.children(lib_symbols, "symbol"):
            full_name = json.loads(symbol[1])
            if ":" not in full_name:
                continue
            namespace, short = full_name.split(":", 1)
            if namespace not in symbols_by_library or short in symbols_by_library[namespace]:
                continue
            copied = copy.deepcopy(symbol)
            copied[1] = g.atom(short)
            for child in g.children(copied, "symbol"):
                child[1] = g.atom(json.loads(child[1]).replace(full_name, short))
            symbols_by_library[namespace][short] = copied
    for namespace, path in LIBRARIES.items():
        symbols = [symbols_by_library[namespace][name]
                   for name in sorted(symbols_by_library[namespace])]
        if not symbols:
            raise RuntimeError(f"No embedded {namespace} project symbols found")
        library = ["kicad_symbol_lib", ["version", "20231120"],
                   ["generator", g.atom("kicad_symbol_editor")], *symbols]
        path.write_text(g.dump(library), encoding="utf-8")
        print(f"Exported {len(symbols)} {namespace} project symbols to {path}")


if __name__ == "__main__":
    main()
