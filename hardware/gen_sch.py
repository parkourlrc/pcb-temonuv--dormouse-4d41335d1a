#!/usr/bin/env python3
"""
Generate hardware/mgm210l_sensor.kicad_sch — the MGM210L temperature+humidity
sensor schematic — as a KiCad 8 S-expression.

Connectivity is by net labels: every used pin gets a short wire stub ending in a
local label, and same-named labels form a net. Stock symbols (R, C, Battery_Cell,
Antenna) are pulled from the KiCad Device library; U1/U2/J1 are custom box symbols.
"""
import re, uuid, os

KICAD_SYMBOLS = "/usr/share/kicad/symbols/Device.kicad_sym"
OUT = os.path.join(os.path.dirname(__file__), "mgm210l_sensor.kicad_sch")
TOP_UUID = str(uuid.uuid4())
PROJECT = "mgm210l_sensor"

def U():  # fresh uuid
    return str(uuid.uuid4())

# KiCad's default connection grid is 1.27 mm (50 mil). Placement origins must land
# on it, or every derived pin/wire/label endpoint is flagged endpoint_off_grid.
GRID = 1.27
def snap(v):
    return round(round(v / GRID) * GRID, 4)

def balance(t, i):
    d = 0
    for j in range(i, len(t)):
        if t[j] == '(': d += 1
        elif t[j] == ')':
            d -= 1
            if d == 0: return t[i:j+1]
    return t[i:]

# ---- pull a symbol definition out of a stock .kicad_sym, rename parent ----
_stock = open(KICAD_SYMBOLS).read()
def stock_symbol(name):
    i = _stock.find('(symbol "%s"' % name)
    if i < 0: raise SystemExit("stock symbol not found: " + name)
    blk = balance(_stock, i)
    # rename parent "Name" -> "Device:Name" (children like Name_0_1 stay)
    return blk.replace('(symbol "%s"' % name, '(symbol "Device:%s"' % name, 1)

# ---- custom box symbol builder ----
def pin_sexpr(number, name, x, y, angle, length=2.54, etype="passive"):
    return f'''      (pin {etype} line
        (at {x} {y} {angle})
        (length {length})
        (name "{name}" (effects (font (size 1.016 1.016))))
        (number "{number}" (effects (font (size 1.016 1.016))))
      )'''

def box_symbol(libname, w, h, pins):
    """pins: list of (number, name, x, y, angle). Body rectangle w x h centered."""
    hw, hh = w/2, h/2
    body = f'''    (symbol "{libname}_0_1"
      (rectangle (start {-hw} {hh}) (end {hw} {-hh})
        (stroke (width 0.254) (type default)) (fill (type background)))
    )'''
    pintxt = "\n".join(pin_sexpr(n, nm, x, y, a) for (n, nm, x, y, a) in pins)
    unit = f'''    (symbol "{libname}_1_1"
{pintxt}
    )'''
    return f'''  (symbol "mgm:{libname}"
    (pin_names (offset 0.508))
    (exclude_from_sim no) (in_bom yes) (on_board yes)
    (property "Reference" "U" (at 0 {hh+2.54} 0) (effects (font (size 1.27 1.27))))
    (property "Value" "{libname}" (at 0 {-hh-2.54} 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
{body}
{unit}
  )'''

# ---- custom symbols -------------------------------------------------------
# MGM210L: real 18-pin module pinout (datasheet Table 6.1). Integrated antenna.
# Left = GPIO/debug, right = power + PTI/UART GPIOs. Number = module pin number.
MGM_PINS = [
    ("1", "PA01",   -15.24, 20.32, 0), ("2", "PA02",  -15.24, 15.24, 0),
    ("3", "PA03",   -15.24, 10.16, 0), ("4", "PA04",  -15.24,  5.08, 0),
    ("11","RESETn", -15.24,  0.0,  0), ("7", "PC00",  -15.24, -5.08, 0),
    ("8", "PC01",   -15.24,-10.16, 0), ("10","PD00",  -15.24,-15.24, 0),
    ("9", "PD01",   -15.24,-20.32, 0),
    ("13","VDD",     15.24, 20.32,180),("6", "GND",    15.24, 15.24,180),
    ("14","GND",     15.24, 10.16,180),("5", "DEC",    15.24,  5.08,180),
    ("12","DNC",     15.24,  0.0, 180),("15","PC02",   15.24, -5.08,180),
    ("16","PC03",    15.24,-10.16,180),("17","PC04",   15.24,-15.24,180),
    ("18","PC05",    15.24,-20.32,180),
]
SHT_PINS = [
    ("1","SDA",-10.16, 5.08,0), ("2","SCL",-10.16,0,0),
    ("3","VDD", 10.16, 5.08,180),("4","VSS", 10.16,-5.08,180),
]
SWD_PINS = [
    ("1","VDD",  7.62, 7.62,180), ("2","SWCLK",7.62, 3.81,180),
    ("3","SWDIO",7.62, 0,   180), ("4","RESETn",7.62,-3.81,180),
    ("5","GND",  7.62,-7.62,180),
]
CUSTOM = {
    "MGM210L": box_symbol("MGM210L", 25.4, 45.72, MGM_PINS),
    "SHT40":   box_symbol("SHT40",   15.24, 15.24, SHT_PINS),
    "SWD":     box_symbol("SWD",     10.16, 20.32, SWD_PINS),
}

# ---- parse pin (number -> (x,y)) from any embedded symbol text ------------
def parse_pins(sym_text):
    pins = {}
    for m in re.finditer(r'\(pin\b', sym_text):
        blk = balance(sym_text, m.start())
        at = re.search(r'\(at (-?[\d.]+) (-?[\d.]+) (-?\d+)\)', blk)
        num = re.search(r'\(number "([^"]+)"', blk)
        if at and num:
            pins[num.group(1)] = (float(at.group(1)), float(at.group(2)))
    return pins

# ---- component instances --------------------------------------------------
# (ref, lib_id, symdef_key_or_stockname, value, x, y, {pin#: net})
COMPS = [
    ("BT1","Device:Battery_Cell","Battery_Cell","CR2032", 55,120,{"1":"VDD","2":"GND"}),
    # MGM210L: pins mapped by module pin number. None -> no-connect flag.
    ("U1", "mgm:MGM210L","MGM210L","MGM210LA22JNF",140,120,{
        "1":"SWCLK","2":"SWDIO","3":None,"4":None,"11":"RESETn",
        "7":"SCL","8":"SDA","10":None,"9":None,
        "13":"VDD","6":"GND","14":"GND","5":None,"12":None,
        "15":None,"16":None,"17":None,"18":None}),
    ("U2", "mgm:SHT40","SHT40","SHT40",235,115,{"1":"SDA","2":"SCL","3":"VDD","4":"GND"}),
    ("R1", "Device:R","R","4.7k",195, 80,{"1":"VDD","2":"SDA"}),
    ("R2", "Device:R","R","4.7k",212, 80,{"1":"VDD","2":"SCL"}),
    ("C1", "Device:C","C","10uF", 85,160,{"1":"VDD","2":"GND"}),
    ("C2", "Device:C","C","100nF",100,160,{"1":"VDD","2":"GND"}),
    ("C3", "Device:C","C","100nF",235,150,{"1":"VDD","2":"GND"}),
    ("J1", "mgm:SWD","SWD","SWD hdr",150,190,
        {"1":"VDD","2":"SWCLK","3":"SWDIO","4":"RESETn","5":"GND"}),
]

# Footprints (land patterns). Standard KiCad libs for passives/battery/header;
# SHT40 uses Sensirion's official part footprint; U1 uses the custom mgm.pretty
# land pattern (gen_mgm_footprint.py) registered via the project fp-lib-table.
FOOTPRINTS = {
    "BT1": "Battery:BatteryHolder_Renata_SMTU2032-LF_1x2032",
    "U1":  "mgm:MGM210LA22JNF",
    "U2":  "Sensor_Humidity:Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad",
    "R1":  "Resistor_SMD:R_0402_1005Metric",
    "R2":  "Resistor_SMD:R_0402_1005Metric",
    "C1":  "Capacitor_SMD:C_0805_2012Metric",   # 10uF bulk
    "C2":  "Capacitor_SMD:C_0402_1005Metric",   # 100nF
    "C3":  "Capacitor_SMD:C_0402_1005Metric",   # 100nF
    "J1":  "Connector_PinHeader_1.27mm:PinHeader_1x05_P1.27mm_Vertical",
}

# collect symbol defs actually used
lib_defs, seen = [], set()
def add_stock(name):
    if name in seen: return
    seen.add(name); lib_defs.append(stock_symbol(name))
for key in ("Battery_Cell","R","C"):
    add_stock(key)
lib_defs += list(CUSTOM.values())

# map lib_id -> symbol text (for pin parsing)
symtext = {}
for d in lib_defs:
    m = re.match(r'\s*\(symbol "([^"]+)"', d)
    symtext[m.group(1)] = d

def prop(name, val, x, y, hide=False, size=1.27, just=None):
    h = " (hide yes)" if hide else ""
    j = f' (justify {just})' if just else ""
    return (f'    (property "{name}" "{val}" (at {x} {y} 0)\n'
            f'      (effects (font (size {size} {size})){j}{h}))')

# half-height (mm) of each custom box, so Ref/Value sit clear of the body
HALFH = {"mgm:MGM210L": 22.86, "mgm:SHT40": 7.62, "mgm:SWD": 10.16}

body_parts, wires, labels, no_connects = [], [], [], []

for ref, lib_id, symkey, value, px, py, netmap in COMPS:
    px, py = snap(px), snap(py)          # land the symbol on the connection grid
    pins = parse_pins(symtext[lib_id])
    # placed symbol — Ref above / Value below custom boxes; to the right for
    # the small stock parts (matches KiCad's usual passive layout).
    if lib_id in HALFH:
        hh = HALFH[lib_id]
        refp = prop("Reference", ref, px, py - hh - 2.54)
        valp = prop("Value", value, px, py + hh + 2.54)
    else:
        refp = prop("Reference", ref, px + 2.79, py - 1.27, just="left")
        valp = prop("Value", value, px + 2.79, py + 1.27, just="left")
    pin_uuids = "\n".join(f'    (pin "{n}" (uuid "{U()}"))' for n in pins)
    sym = f'''  (symbol
    (lib_id "{lib_id}")
    (at {px} {py} 0)
    (unit 1)
    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
    (uuid "{U()}")
{refp}
{valp}
{prop("Footprint", FOOTPRINTS.get(ref, ""), px, py, hide=True, size=1.016)}
{prop("Datasheet", "", px, py, hide=True, size=1.016)}
{pin_uuids}
    (instances
      (project "{PROJECT}"
        (path "/{TOP_UUID}" (reference "{ref}") (unit 1))))
  )'''
    body_parts.append(sym)

    # wire stub + label per pin (or a no-connect flag when net is None)
    for num, net in netmap.items():
        lx, ly = pins[num]
        ax, ay = px + lx, py - ly           # KiCad Y-flip for placed symbol
        if net is None:
            no_connects.append(f'  (no_connect (at {ax} {ay}) (uuid "{U()}"))')
            continue
        # outward direction from symbol center, axis-aligned
        dx = 1 if lx > 0.1 else (-1 if lx < -0.1 else 0)
        dy = 1 if (-ly) > 0.1 else (-1 if (-ly) < -0.1 else 0)
        if dx == 0 and dy == 0: dx = 1
        ex, ey = ax + dx*3.81, ay + dy*3.81
        wires.append(f'  (wire (pts (xy {ax} {ay}) (xy {ex} {ey}))\n'
                     f'    (stroke (width 0) (type default)) (uuid "{U()}"))')
        just = "left" if dx >= 0 else "right"
        labels.append(f'  (label "{net}" (at {ex} {ey} 0)\n'
                      f'    (effects (font (size 1.27 1.27)) (justify {just}))\n'
                      f'    (uuid "{U()}"))')

out = f'''(kicad_sch
  (version 20231120)
  (generator "eeschema")
  (generator_version "8.0")
  (uuid "{TOP_UUID}")
  (paper "A3")
  (title_block
    (title "MGM210L Zigbee Temperature + Humidity Sensor")
    (company "DIY")
    (comment 1 "CR2032 sleepy end device — SHT40 over I2C (PC00/PC01)")
    (comment 2 "MGM210LA22JNF: integrated-antenna module, no external RF parts")
  )
  (lib_symbols
{chr(10).join(lib_defs)}
  )
{chr(10).join(body_parts)}
{chr(10).join(wires)}
{chr(10).join(labels)}
{chr(10).join(no_connects)}
  (sheet_instances
    (path "/" (page "1"))
  )
)
'''
open(OUT, "w").write(out)
print("wrote", OUT, "(%d bytes)" % len(out))

# standalone mgm symbol library, so the project sym-lib-table can resolve the
# lib_id "mgm:*" references (clears the ERC lib_symbol_issues warnings). In a
# library file the symbols are named without the "mgm:" lib prefix.
SYM = os.path.join(os.path.dirname(OUT), "mgm.kicad_sym")
mgm_syms = [sdef.replace('(symbol "mgm:%s"' % name, '(symbol "%s"' % name, 1)
            for name, sdef in CUSTOM.items()]
open(SYM, "w").write('(kicad_symbol_lib\n'
                     '  (version 20231120)\n'
                     '  (generator "gen_sch.py")\n'
                     '  (generator_version "8.0")\n'
                     + "\n".join(mgm_syms) + "\n)\n")
print("wrote", SYM)

# minimal KiCad project file so it opens as a project (root sheet = schematic uuid)
PRO = OUT.replace(".kicad_sch", ".kicad_pro")
import json
json.dump({
    "meta": {"filename": os.path.basename(PRO), "version": 1},
    "sheets": [[TOP_UUID, "Root"]],
    "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
    "text_variables": {},
}, open(PRO, "w"), indent=2)
print("wrote", PRO)
# debug: show parsed pins per stock part to confirm pin numbers
for k in ("Battery_Cell",):
    print(k, "pins:", parse_pins(symtext["Device:"+k]))
