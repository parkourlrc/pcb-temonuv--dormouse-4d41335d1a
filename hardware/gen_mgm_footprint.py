#!/usr/bin/env python3
"""
Generate hardware/mgm.pretty/MGM210LA22JNF.kicad_mod — the land pattern for the
Silicon Labs MGM210LA22JNF module.

PADS are datasheet-exact: positions/sizes from the MGM210L Data Sheet Rev 1.5,
§8.2 "PCB Land Pattern", Table 8.1 (three castellated edges of 6 pads each; the
top edge carries the integrated antenna and has no pads):

  Left  (pads 1-6):  X=0.5,   Y 9.78 -> 1.23,  pitch 1.71, pad 1.1 x 1.6 mm
  Bottom(pads 7-12): Y=0.5,   X 2.23 -> 10.78, pitch 1.71, pad 1.1 x 1.6 mm
  Right (pads 13-18):X=14.67, Y 2.25 -> 11.75, pitch 1.90, pad 1.3 x 3.3 mm (power)
  VDD test point / keep-out on bottom layer at (2.65, 6.45), 1.4 x 1.4 mm.

Pad numbers match the module pinout (Data Sheet Table 6.1), so they line up with
the mgm:MGM210L schematic symbol pin numbers.

SILK / FAB / COURTYARD are an approximation of the 13.0 x 15.5 mm module body
(Fig 8.1) placed over the pad array with the antenna at the top edge; they are
documentation only (not solder-critical). Coordinates are recentred so the
footprint origin sits at the centre of the pad array, with datasheet +Y (antenna
end) mapped to KiCad -Y (up).
"""
import os, uuid

OUT_DIR = os.path.join(os.path.dirname(__file__), "mgm.pretty")
OUT = os.path.join(OUT_DIR, "MGM210LA22JNF.kicad_mod")

# --- datasheet Table 8.1 pad geometry (mm), origo at package corner ----------
MIDX, MIDY = 7.585, 6.125            # centre of pad-array bounding box
def rc(x, y):                        # recentre + flip Y (antenna -> -Y / up)
    return round(x - MIDX, 4), round(MIDY - y, 4)

PADS = []                            # (number, kx, ky, sx, sy)
for i, n in enumerate((1, 2, 3, 4, 5, 6)):          # left edge, outward -X
    x, y = rc(0.5, 9.78 - i * 1.71)
    PADS.append((str(n), x, y, 1.6, 1.1))
for i, n in enumerate((7, 8, 9, 10, 11, 12)):       # bottom edge, outward +Y(ds)
    x, y = rc(2.23 + i * 1.71, 0.5)
    PADS.append((str(n), x, y, 1.1, 1.6))
for i, n in enumerate((13, 14, 15, 16, 17, 18)):    # right edge, outward +X
    x, y = rc(14.67, 2.25 + i * 1.90)
    PADS.append((str(n), x, y, 3.3, 1.3))

VDD_TP = rc(2.65, 6.45)              # bottom-layer VDD test point keep-out centre

# --- module body (13.0 x 15.5), centred in X, antenna band at top ------------
BODY_X0, BODY_X1 = -6.5, 6.5
BODY_Y1 = 5.9                        # bottom edge (just outside bottom pad row)
BODY_Y0 = BODY_Y1 - 15.5            # top edge (antenna end)
ANT_Y = -5.9                        # boundary of the antenna keep-out band
CRT = (-8.15, -9.85, 9.0, 6.7)      # courtyard x0,y0,x1,y1

def U():
    return str(uuid.uuid4())

def line(x0, y0, x1, y1, layer, w):
    return (f'  (fp_line (start {x0} {y0}) (end {x1} {y1})\n'
            f'    (stroke (width {w}) (type solid)) (layer "{layer}") (uuid "{U()}"))')

def rect(x0, y0, x1, y1, layer, w):
    return "\n".join([line(x0, y0, x1, y0, layer, w), line(x1, y0, x1, y1, layer, w),
                      line(x1, y1, x0, y1, layer, w), line(x0, y1, x0, y0, layer, w)])

def text(kind, s, x, y, layer, size=1.0, th=0.15, mirror=False):
    j = " (justify mirror)" if mirror else ""      # back-layer text must be mirrored
    return (f'  (fp_text {kind} "{s}" (at {x} {y} 0) (layer "{layer}") (uuid "{U()}")\n'
            f'    (effects (font (size {size} {size}) (thickness {th})){j}))')

graphics = []
# fab body outline + antenna band divider
graphics.append(rect(BODY_X0, BODY_Y0, BODY_X1, BODY_Y1, "F.Fab", 0.1))
graphics.append(line(BODY_X0, ANT_Y, BODY_X1, ANT_Y, "F.Fab", 0.1))
graphics.append(text("user", "ANTENNA - KEEP COPPER/GND CLEAR",
                     0, (BODY_Y0 + ANT_Y) / 2, "F.Fab", 0.7, 0.1))
# silk: top (antenna) edge + short side ticks that avoid the pads
graphics.append(line(BODY_X0, BODY_Y0, BODY_X1, BODY_Y0, "F.SilkS", 0.12))
# pin-1 marker (dot clear of pad 1, top-left)
_, p1x, p1y, _, _ = PADS[0]
graphics.append(f'  (fp_circle (center {round(p1x-1.5,3)} {p1y}) (end {round(p1x-1.25,3)} {p1y})\n'
                f'    (stroke (width 0.2) (type solid)) (fill solid) (layer "F.SilkS") (uuid "{U()}"))')
# courtyard
graphics.append(rect(CRT[0], CRT[1], CRT[2], CRT[3], "F.CrtYd", 0.05))
# VDD test-point keep-out (bottom layer) as documentation on B.Fab
tx, ty = VDD_TP
graphics.append(rect(tx-0.7, ty-0.7, tx+0.7, ty+0.7, "B.Fab", 0.1))
graphics.append(text("user", "VDD TP keepout", tx, ty+1.1, "B.Fab", 0.5, 0.08, mirror=True))
# invisible ${REFERENCE} echo on the fab layer (KiCad convention)
graphics.append(text("user", "${REFERENCE}", 0, 0, "F.Fab", 1.0, 0.15))

pads = []
for num, x, y, sx, sy in PADS:
    pads.append(f'  (pad "{num}" smd roundrect (at {x} {y}) (size {sx} {sy})\n'
                f'    (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.1)\n'
                f'    (uuid "{U()}"))')

out = f'''(footprint "MGM210LA22JNF"
  (version 20240108)
  (generator "gen_mgm_footprint.py")
  (generator_version "9.0")
  (layer "F.Cu")
  (descr "Silicon Labs MGM210LA22JNF Wireless Gecko module. 3-sided castellated land pattern per MGM210L Data Sheet Rev 1.5, Table 8.1. Top edge = integrated antenna keep-out. Pads = datasheet-exact; silk/courtyard approximate the 13.0 x 15.5 mm body.")
  (tags "silabs mgm210l mgm210la22jnf efr32mg21 zigbee module castellated")
  (attr smd)
  (property "Reference" "REF**" (at 0 {BODY_Y0-0.9} 0) (layer "F.SilkS") (uuid "{U()}")
    (effects (font (size 1 1) (thickness 0.15))))
  (property "Value" "MGM210LA22JNF" (at 0 {BODY_Y1+0.9} 0) (layer "F.Fab") (uuid "{U()}")
    (effects (font (size 1 1) (thickness 0.15))))
  (property "Footprint" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{U()}")
    (effects (font (size 1.27 1.27))))
  (property "Datasheet" "https://www.silabs.com/documents/public/data-sheets/mgm210l-datasheet.pdf" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{U()}")
    (effects (font (size 1.27 1.27))))
  (property "Description" "Silicon Labs MGM210LA22JNF Zigbee/Multiprotocol module" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{U()}")
    (effects (font (size 1.27 1.27))))
{chr(10).join(graphics)}
{chr(10).join(pads)}
)
'''
os.makedirs(OUT_DIR, exist_ok=True)
open(OUT, "w").write(out)
print("wrote", OUT, "(%d pads, %d bytes)" % (len(PADS), len(out)))
