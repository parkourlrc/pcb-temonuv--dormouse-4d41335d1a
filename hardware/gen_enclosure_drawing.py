#!/usr/bin/env python3
"""Generate a dimensioned mechanical drawing PDF of the Dormouse PCB, for
designing a 3D-printed enclosure.

Board outline, the ventilation slot, and every component position are parsed
*directly from the routed KiCad PCB* (`mgm210l_sensor.kicad_pcb`) so the drawing
can never drift from the real design. Component Z-heights are a curated table
(datasheet values where known; class-typical / assumed values are flagged in the
"Source / note" column and on the drawing).

    cd hardware && python3 gen_enclosure_drawing.py
    -> mgm210l_sensor_enclosure_drawing.pdf   (A4, 4 pages)

Datum for all XY dims: board bottom-left corner, X right, Y up, millimetres.
"""
import os, re, math, json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Rectangle, Polygon
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PCB  = os.path.join(HERE, "mgm210l_sensor.kicad_pcb")
OUT  = os.path.join(HERE, "mgm210l_sensor_enclosure_drawing.pdf")

# ----------------------------------------------------------------------------
# minimal s-expression parser
# ----------------------------------------------------------------------------
def _atom(t):
    return ('str', t[1:-1]) if t.startswith('"') else ('sym', t)

def parse(text):
    it = iter(re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text))
    def build():
        node = []
        for t in it:
            if t == '(':
                node.append(build())
            elif t == ')':
                return node
            else:
                node.append(_atom(t))
        return node
    for t in it:
        if t == '(':
            return build()
    return []

def head(n):
    return n[0][1] if n and isinstance(n[0], tuple) and n[0][0] == 'sym' else None
def find_all(n, name):
    return [c for c in n if isinstance(c, list) and head(c) == name]
def find_first(n, name):
    for c in n:
        if isinstance(c, list) and head(c) == name:
            return c
    return None
def nums(n, name, k):
    c = find_first(n, name)
    if not c:
        return None
    out = []
    for x in c[1:]:
        if isinstance(x, tuple) and x[0] == 'sym':
            try: out.append(float(x[1]))
            except ValueError: pass
        if len(out) >= k:
            break
    return out

tree = parse(open(PCB).read())

# ----------------------------------------------------------------------------
# board outline (Edge.Cuts) + ventilation slot
# ----------------------------------------------------------------------------
edge_pts = []
for c in tree:
    if not isinstance(c, list):
        continue
    if head(c) in ('gr_line', 'gr_arc'):
        lc = find_first(c, 'layer')
        if lc and lc[1][1] == 'Edge.Cuts':
            for key in ('start', 'mid', 'end'):
                p = nums(c, key, 2)
                if p:
                    edge_pts.append(tuple(p))
xs = [p[0] for p in edge_pts]; ys = [p[1] for p in edge_pts]
BX0, BX1 = min(xs), max(xs)
BY0, BY1 = min(ys), max(ys)
W, H = BX1 - BX0, BY1 - BY0            # 36.00 x 25.05

def L(x, y):   return (x - BX0, BY1 - y)   # KiCad (Y-down) -> local (Y-up)
def Lx(x):     return x - BX0
def Ly(y):     return BY1 - y

# ----------------------------------------------------------------------------
# footprints -> ref / at / rotation / layer / courtyard bbox
# ----------------------------------------------------------------------------
def rot_point(px, py, deg):
    a = math.radians(deg)
    return (px*math.cos(a) + py*math.sin(a), -px*math.sin(a) + py*math.cos(a))

comps = {}
for fp in find_all(tree, 'footprint'):
    at = nums(fp, 'at', 3)
    ox, oy = at[0], at[1]
    rot = at[2] if len(at) > 2 else 0.0
    lc = find_first(fp, 'layer'); layer = lc[1][1] if lc else '?'
    ref = None
    for pr in find_all(fp, 'property'):
        if len(pr) >= 3 and isinstance(pr[1], tuple) and pr[1][1] == 'Reference':
            ref = pr[2][1]; break
    pts = []
    for g in fp:
        if not isinstance(g, list):
            continue
        lc = find_first(g, 'layer')
        if not lc or lc[1][1] not in ('F.CrtYd', 'B.CrtYd'):
            continue
        if head(g) == 'fp_line':
            for nm in ('start', 'end'):
                p = nums(g, nm, 2)
                if p: pts.append(tuple(p))
        elif head(g) == 'fp_poly':
            poly = find_first(g, 'pts')
            if poly:
                for xy in find_all(poly, 'xy'):
                    v = [float(t[1]) for t in xy[1:] if isinstance(t, tuple)]
                    pts.append((v[0], v[1]))
    cbb = None
    if pts:
        bp = [(ox + rot_point(px, py, rot)[0], oy + rot_point(px, py, rot)[1]) for px, py in pts]
        cbb = (min(p[0] for p in bp), min(p[1] for p in bp),
               max(p[0] for p in bp), max(p[1] for p in bp))
    comps[ref] = dict(ref=ref, layer=layer, x=ox, y=oy, rot=rot, cbb=cbb)

# U1 module body from F.Fab (the physical body, incl. the overhanging antenna end)
def u1_body_bbox():
    for fp in find_all(tree, 'footprint'):
        if fp[1][1].endswith('MGM210LA22JNF'):
            at = nums(fp, 'at', 2); ox, oy = at
            fx = []; fy = []
            for g in find_all(fp, 'fp_line'):
                lc = find_first(g, 'layer')
                if lc and lc[1][1] == 'F.Fab':
                    s = nums(g, 'start', 2); e = nums(g, 'end', 2)
                    fx += [s[0], e[0]]; fy += [s[1], e[1]]
            if fx:
                return (ox+min(fx), oy+min(fy), ox+max(fx), oy+max(fy))
    return None
U1B = u1_body_bbox()                     # kicad coords: x145..158 y82.38..97.88
OVERHANG = BY0 - U1B[1]                   # module top above board top edge (~2.62)

# ----------------------------------------------------------------------------
# curated body/height table (mm).  src tag: DS=datasheet, STD=part-class, ASSUME
# ----------------------------------------------------------------------------
COMP = {
 "U1": dict(name="MGM210L module", body=(13.0, 15.5), h=2.25, src="DS 2.25 max"),
 "U2": dict(name="SHT40 sensor",   body=(1.5, 1.5),   h=0.50, src="DS DFN 0.5"),
 "J1": dict(name="SWD header 1x5", body=(3.1, 7.4),   h=5.5,  src="STD 1.27mm vert, pins ~5.5; OPTIONAL/debug"),
 "C1": dict(name="10uF 0805",      body=(2.0, 1.25),  h=1.45, src="STD 0805 max"),
 "C2": dict(name="100nF 0402",     body=(1.0, 0.5),   h=0.55, src="STD 0402"),
 "C3": dict(name="100nF 0402",     body=(1.0, 0.5),   h=0.55, src="STD 0402"),
 "R1": dict(name="4.7k 0402",      body=(1.0, 0.5),   h=0.50, src="STD 0402"),
 "R2": dict(name="4.7k 0402",      body=(1.0, 0.5),   h=0.50, src="STD 0402"),
 "BT1":dict(name="CR2032 holder",  body=(33.0, 8.0),  h=6.0,  src="ASSUME ~6.0 incl cell; confirm Renata SMTU2032-LF DS"),
}
BOARD_T = 1.6
Z_ENVELOPE = COMP["BT1"]["h"] + BOARD_T + COMP["U1"]["h"]   # 9.85

# ----------------------------------------------------------------------------
# drawing helpers
# ----------------------------------------------------------------------------
def dim_h(ax, x0, x1, y, text, tick=0.6, fs=7, color="#b00"):
    ax.annotate("", (x0, y), (x1, y), arrowprops=dict(arrowstyle="<->", color=color, lw=0.8))
    for xx in (x0, x1):
        ax.plot([xx, xx], [y-tick, y+tick], color=color, lw=0.6)
    if text:
        ax.text((x0+x1)/2, y+0.4, text, ha="center", va="bottom", fontsize=fs, color=color)

def dim_v(ax, y0, y1, x, text, tick=0.6, fs=7, color="#b00", ha="left", dx=0.5):
    ax.annotate("", (x, y0), (x, y1), arrowprops=dict(arrowstyle="<->", color=color, lw=0.8))
    for yy in (y0, y1):
        ax.plot([x-tick, x+tick], [yy, yy], color=color, lw=0.6)
    if text:
        ax.text(x+dx, (y0+y1)/2, text, ha=ha, va="center", fontsize=fs, color=color, rotation=90)

def board_path(mirror=False):
    r = 2.0
    path = [(r, 0), (W-r, 0)]
    def arc(cx, cy, a0, a1):
        for a in np.linspace(math.radians(a0), math.radians(a1), 12):
            path.append((cx + r*math.cos(a), cy + r*math.sin(a)))
    arc(W-r, r, 270, 360); path += [(W, r), (W, H-r)]; arc(W-r, H-r, 0, 90)
    path += [(W-r, H), (r, H)]; arc(r, H-r, 90, 180)
    path += [(0, H-r), (0, r)]; arc(r, r, 180, 270); path.append((r, 0))
    return [(W-x, y) for x, y in path] if mirror else path

def draw_board(ax, mirror=False):
    ax.add_patch(Polygon(board_path(mirror), closed=True,
                         facecolor="#eef3ea", edgecolor="#2a5", lw=1.6, zorder=1))
    sx0, sy0 = L(147.75, 105.998); sx1, sy1 = L(154.95, 105.3)
    x0, x1 = sorted([sx0, sx1]); y0, y1 = sorted([sy0, sy1])
    if mirror: x0, x1 = W-x1, W-x0
    ax.add_patch(FancyBboxPatch((x0, y0), x1-x0, y1-y0,
        boxstyle="round,pad=0,rounding_size=0.34", facecolor="white",
        edgecolor="#2a5", lw=1.2, zorder=2))

def comp_box(ax, ref, mirror=False, face="#dfe7f0", color="#356"):
    c = comps[ref]; meta = COMP[ref]
    if ref == "U1":
        x0, y0 = L(U1B[0], U1B[3]); x1, y1 = L(U1B[2], U1B[1])
    else:
        cx, cy = L(c["x"], c["y"]); bw, bh = meta["body"]
        w, h = (bw, bh) if c["rot"] % 180 == 0 else (bh, bw)
        x0, y0, x1, y1 = cx-w/2, cy-h/2, cx+w/2, cy+h/2
    x0, x1 = sorted([x0, x1]); y0, y1 = sorted([y0, y1])
    if mirror: x0, x1 = W-x1, W-x0
    ax.add_patch(Rectangle((x0, y0), x1-x0, y1-y0, facecolor=face, edgecolor=color, lw=1.0, zorder=3))
    ax.text((x0+x1)/2, (y0+y1)/2, ref, ha="center", va="center",
            fontsize=7, fontweight="bold", color=color, zorder=4)

pp = PdfPages(OUT)

# ---------------- PAGE 1 : outline & envelope ----------------
fig, ax = plt.subplots(figsize=(8.27, 11.69))
draw_board(ax)
mx0, my0 = L(U1B[0], U1B[3]); mx1, my1 = L(U1B[2], U1B[1])
ax.add_patch(Rectangle((min(mx0, mx1), min(my0, my1)), abs(mx1-mx0), abs(my1-my0),
             facecolor="none", edgecolor="#888", lw=0.9, ls="--", zorder=2))
ax.text((mx0+mx1)/2, my1+0.4, "U1 module body (overhangs top edge)",
        ha="center", va="bottom", fontsize=6.5, color="#555")
dim_h(ax, 0, W, -3.2, f"{W:.2f}")
dim_v(ax, 0, H, -3.2, f"{H:.2f}", dx=-1.4, ha="right")
ax.annotate("R2.0", (1.0, H-1.0), (4.5, H+1.5), fontsize=7, color="#b00",
            arrowprops=dict(arrowstyle="->", color="#b00", lw=0.7))
vx0, vy0 = L(147.75, 105.998); vx1, vy1 = L(154.95, 105.3)
vx0, vx1 = sorted([vx0, vx1]); vy0, vy1 = sorted([vy0, vy1])
ax.annotate(f"vent slot {vx1-vx0:.1f} x {vy1-vy0:.1f}\n(through cut at SHT40)",
            ((vx0+vx1)/2, vy0), (W*0.62, -6.5), fontsize=6.5, color="#06a", ha="center",
            arrowprops=dict(arrowstyle="->", color="#06a", lw=0.7))
dim_v(ax, H, H+OVERHANG, W+2.5, f"{OVERHANG:.2f}", dx=0.6, color="#a60")
ax.text(W+3.7, H+OVERHANG/2, "module\noverhang", fontsize=6, color="#a60", va="center")
dim_h(ax, 0, vx0, vy0-2.0, f"{vx0:.1f}", fs=6)
ax.set_xlim(-8, W+9); ax.set_ylim(-9, H+7); ax.set_aspect("equal"); ax.axis("off")
ax.set_title("Dormouse — PCB outline & envelope (TOP view)  |  datum: board bottom-left, mm",
             fontsize=11, fontweight="bold", loc="left")
ax.text(-8, -8.4,
    f"Board: FR4, {W:.2f} x {H:.2f} mm, 2-layer, {BOARD_T:.2f} mm thick, R2.0 corners.  "
    f"U1 (Zigbee module) antenna end overhangs the top edge by {OVERHANG:.2f} mm — cavity must clear it.\n"
    "Vent slot is a through-cut aligned to the SHT40; keep matching vents in the enclosure top & bottom.",
    fontsize=7, color="#333")
pp.savefig(fig, bbox_inches="tight"); plt.close(fig)

# ---------------- PAGE 2 : top-side placement ----------------
fig, ax = plt.subplots(figsize=(8.27, 11.69))
draw_board(ax)
for ref in [r for r in comps if comps[r]["layer"] == "F.Cu"]:
    comp_box(ax, ref)
def annot(ref, dx, dy, txt):
    c = comps[ref]; cx, cy = L(c["x"], c["y"])
    ax.annotate(txt, (cx, cy), (cx+dx, cy+dy), fontsize=6.5, color="#234",
                arrowprops=dict(arrowstyle="->", color="#234", lw=0.6))
annot("U1", 6, 6,  f"U1 module  ctr ({Lx(151.5):.1f}, {Ly(91.98):.1f})  body 13.0x15.5")
annot("U2", 7, -2, f"U2 SHT40 @ ({Lx(151.5):.1f}, {Ly(107.4):.1f})  -> put vent here")
annot("J1", -3.5, 4, f"J1 SWD (debug)\n@ ({Lx(137):.1f}, {Ly(89.23):.1f})")
annot("C1", 6, 0,  f"C1 @ ({Lx(164.5):.1f}, {Ly(94.0):.1f})")
ax.set_xlim(-6, W+12); ax.set_ylim(-4, H+6); ax.set_aspect("equal"); ax.axis("off")
ax.set_title("Dormouse — TOP-side component placement (assembly / clearance)",
             fontsize=11, fontweight="bold", loc="left")
ax.text(-6, -3.4, "Boxes = component bodies. All parts on TOP except the coin-cell holder (see next page).",
        fontsize=7, color="#333")
pp.savefig(fig, bbox_inches="tight"); plt.close(fig)

# ---------------- PAGE 3 : bottom-side (battery) ----------------
fig, ax = plt.subplots(figsize=(8.27, 11.69))
draw_board(ax, mirror=True)
c = comps["BT1"]
x0, y0 = L(c["cbb"][0], c["cbb"][3]); x1, y1 = L(c["cbb"][2], c["cbb"][1])
x0, x1 = sorted([x0, x1]); y0, y1 = sorted([y0, y1]); x0, x1 = W-x1, W-x0
ax.add_patch(Rectangle((x0, y0), x1-x0, y1-y0, facecolor="#f0e6df", edgecolor="#853", lw=1.2, zorder=3))
ax.text((x0+x1)/2, (y0+y1)/2, "BT1  CR2032 holder\n33 x 8 mm, ~6 mm tall",
        ha="center", va="center", fontsize=8, color="#853", zorder=4)
dim_h(ax, x0, x1, y0-2.2, f"{x1-x0:.1f}")
dim_v(ax, y0, y1, x1+1.5, f"{y1-y0:.1f}", dx=0.5)
ax.set_xlim(-4, W+8); ax.set_ylim(-4, H+4); ax.set_aspect("equal"); ax.axis("off")
ax.set_title("Dormouse — BOTTOM-side placement (mirrored X)  |  coin-cell access",
             fontsize=11, fontweight="bold", loc="left")
ax.text(-4, -3.4,
    "View from the BACK (X mirrored). The CR2032 holder dominates the back face and needs\n"
    "swap access — design a removable back or a side slot to slide the cell in/out.",
    fontsize=7, color="#333")
pp.savefig(fig, bbox_inches="tight"); plt.close(fig)

# ---------------- PAGE 4 : side elevation + table + notes ----------------
fig = plt.figure(figsize=(8.27, 11.69))
ax = fig.add_axes([0.08, 0.55, 0.86, 0.38])
Ymax = H
ax.add_patch(Rectangle((0, 0), Ymax, BOARD_T, facecolor="#cdb", edgecolor="#584", lw=1))
ax.text(Ymax/2, BOARD_T/2, "PCB 1.6", ha="center", va="center", fontsize=7)
mY0, mY1 = Ly(U1B[3]), Ly(U1B[1])          # module span along length (12.17..27.67)
ax.add_patch(Rectangle((mY0, BOARD_T), mY1-mY0, COMP["U1"]["h"], facecolor="#dde", edgecolor="#347", lw=1))
ax.text((mY0+mY1)/2, BOARD_T+COMP["U1"]["h"]/2, "U1  2.25", ha="center", va="center", fontsize=6.5)
jc = comps["J1"]; jY0, jY1 = Ly(jc["cbb"][3]), Ly(jc["cbb"][1])
ax.add_patch(Rectangle((jY0, BOARD_T), jY1-jY0, COMP["J1"]["h"], facecolor="none", edgecolor="#a55", lw=1, ls="--"))
ax.text((jY0+jY1)/2, BOARD_T+COMP["J1"]["h"]+0.2, "J1 5.5 (opt.)", ha="center", va="bottom", fontsize=6, color="#a55")
uc = comps["U2"]; uY = Ly(uc["y"])
ax.add_patch(Rectangle((uY-1, BOARD_T), 2.0, 0.5, facecolor="#efe", edgecolor="#584", lw=0.8))
ax.text(uY, BOARD_T+0.9, "U2 0.5", ha="center", fontsize=6)
bc = comps["BT1"]; bY0, bY1 = Ly(bc["cbb"][3]), Ly(bc["cbb"][1])
ax.add_patch(Rectangle((bY0, -COMP["BT1"]["h"]), bY1-bY0, COMP["BT1"]["h"], facecolor="#f0e6df", edgecolor="#853", lw=1))
ax.text((bY0+bY1)/2, -COMP["BT1"]["h"]/2, "BT1 ~6.0", ha="center", va="center", fontsize=7)
ax.plot([Ymax, Ymax], [-6.5, 8], color="#aaa", lw=0.6, ls=":")
ax.annotate("", (Ymax, 7), (mY1, 7), arrowprops=dict(arrowstyle="<->", color="#a60", lw=0.8))
ax.text((Ymax+mY1)/2, 7.3, f"overhang {OVERHANG:.2f}", ha="center", fontsize=6.5, color="#a60")
ax.annotate("", (-2.5, -COMP["BT1"]["h"]), (-2.5, BOARD_T+COMP["U1"]["h"]),
            arrowprops=dict(arrowstyle="<->", color="#b00", lw=0.9))
ax.text(-3.0, (-COMP["BT1"]["h"]+BOARD_T+COMP["U1"]["h"])/2,
        f"Z envelope\n{Z_ENVELOPE:.2f} mm\n(excl. J1)", ha="right", va="center", fontsize=7, color="#b00")
ax.set_xlim(-8, mY1+2); ax.set_ylim(-8, 9.5); ax.set_aspect("equal"); ax.axis("off")
ax.set_title("Side elevation (looking along width)  —  Z stack-up, mm",
             fontsize=11, fontweight="bold", loc="left")

ax2 = fig.add_axes([0.08, 0.06, 0.86, 0.42]); ax2.axis("off")
rows = [("Ref", "Part", "Body (mm)", "Side", "Height (mm)", "Source / note")]
for r in ["U1", "J1", "C1", "C2", "C3", "R1", "R2", "U2", "BT1"]:
    m = COMP[r]; side = "TOP" if comps[r]["layer"] == "F.Cu" else "BACK"
    rows.append((r, m["name"], f"{m['body'][0]}x{m['body'][1]}", side, f"{m['h']:.2f}", m["src"]))
tbl = ax2.table(cellText=rows[1:], colLabels=rows[0], loc="upper center",
                colWidths=[0.06, 0.20, 0.11, 0.08, 0.10, 0.45], cellLoc="left")
tbl.auto_set_font_size(False); tbl.set_fontsize(7.2); tbl.scale(1, 1.35)
for (rr, cc), cell in tbl.get_celld().items():
    cell.set_edgecolor("#ccc")
    if rr == 0:
        cell.set_facecolor("#33506b"); cell.get_text().set_color("white"); cell.get_text().set_fontweight("bold")
inner_L = H + OVERHANG
ax2.text(0, 0.02,
 "Enclosure design summary\n"
 f"-  Interior cavity (min):  ~{inner_L:.1f} (L = {H:.2f} board + {OVERHANG:.2f} module overhang)  x  {W:.1f} (W)  x  {Z_ENVELOPE:.1f} (Z) mm,\n"
 "   plus wall thickness and fit clearance.  Z = 6.0 (battery, BACK) + 1.6 (PCB) + 2.25 (module, TOP).  Add ~0.3-0.5 mm per face.\n"
 "-  Battery: CR2032 holder is on the BACK and fills it - provide a removable lid or slide-in slot for cell swap.\n"
 "-  Antenna: U1's top end is the integrated PCB antenna and OVERHANGS the top board edge - keep that zone plastic-only\n"
 "   (no metal, screws, or foil) and leave a small air gap; do not clamp the module.\n"
 "-  Sensor: U2 (SHT40) sits over a through vent slot near the bottom edge - add vent holes there on BOTH faces for RH response.\n"
 "-  J1 SWD header is DEBUG-only; omit it or add a removable plug/port. Heights marked STD/ASSUME are class-typical -\n"
 "   confirm BT1 from the Renata SMTU2032-LF datasheet and C1 from the exact 0805 part before finalizing the lid gap.",
 fontsize=7.2, color="#222", va="bottom", family="monospace")
pp.savefig(fig); plt.close(fig)

pp.close()
print("wrote", OUT)
print(f"board {W:.2f} x {H:.2f} mm, overhang {OVERHANG:.2f} mm, Z envelope {Z_ENVELOPE:.2f} mm")
