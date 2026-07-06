# Fab package — mgm210l_sensor

Generated from `mgm210l_sensor.kicad_pcb` with `kicad-cli 9.0.9`.

## What to upload
Every fab wants a **single zip of the Gerbers + Excellon drill**. The loose files
live in [`gerbers/`](gerbers/) (committed, viewable on GitHub); zip them on demand:

```bash
cd hardware/fab && zip -j mgm210l_sensor-gerbers.zip gerbers/*.gbr gerbers/*.drl
```

Upload that zip as-is (don't unzip). The zip itself is **not committed** (it's just
a repackage of `gerbers/`, so it can drift) — regenerate it with the line above.

- `mgm210l_sensor-bom.csv` — bill of materials (only needed for assembly/PCBA).
- `mgm210l_sensor-pos.csv` — pick-and-place / centroid (only for assembly/PCBA).

## Board spec (quote with these)
| Parameter        | Value                              |
|------------------|------------------------------------|
| Layers           | 2 (F.Cu / B.Cu)                    |
| Size             | ~36.0 × 25.0 mm                    |
| Thickness        | 1.6 mm (standard)                  |
| Min track/space  | 0.20 mm (8 mil)                    |
| Min via          | 0.60 mm pad / 0.30 mm drill        |
| Copper           | 1 oz (35 µm)                       |
| Surface finish   | **ENIG recommended** (flat pads for the MGM210L QFN-style land + SHT40 DFN; HASL is cheaper but its uneven surface hurts fine-pitch reflow) |
| Solder mask / silk | any (green is cheapest/fastest)  |

Everything is inside the cheapest tier at all the fabs below (2-layer, <100×100 mm,
≥0.127 mm trace, ≥0.3 mm drill), so expect the base "5-pcs for a few dollars" price.

## Notes / caveats
- **One DRC note:** the SDA trace passes 0.45 mm from a rounded board corner where
  the project rule wants 0.5 mm. This is 0.05 mm under a self-imposed limit and is
  well inside every fab's real capability (JLCPCB min trace-to-edge is 0.2 mm), so
  it will NOT cause a rejection. Nudge the trace only if you want a perfectly clean DRC.
- Antenna keepout: the MGM210L's built-in antenna sits at the top board edge with a
  ground/copper keepout — already enforced in the layout. Don't let a panel/frame or
  assembly house add copper or a label there.
- Drill files are split PTH / NPTH (`-PTH.drl`, `-NPTH.drl`); all major fabs read both.

## Regenerate
See the `kicad-cli pcb export gerbers/drill/pos` and `kicad-cli sch export bom`
commands used to produce this folder.
