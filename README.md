# portlight-ships

Ship sprite packs for [Portlight](https://github.com/mcp-tool-shop-org/portlight) and the
2.5D client — one hull, five damage states, both sail rigs, eight headings.

## Why this exists

Ship sprites had failed three previous times. The root cause is documented: **diffusion
models cannot generate ship headings.** Characters work because faces and poses give the
model a strong directional signal; a ship is a symmetric object with no equivalent cue, so
"port bow view" and "starboard quarter view" both come back as the same flattering
broadside. RealVisXL, JuggernautXL + pixel-art-xl, and Zero123++ all failed this way.

The fix is not a better prompt. Rotational truth has to come from a **textured 3D model on
a deterministic turntable**. That is what this pipeline builds.

A second failure was subtler: generating each damage state independently re-rolled the
entire visual language every time, so a five-state "ladder" came back as five different
ships in five different rendering styles. The fix there is reference chaining — see below.

## Pipeline

```
        ┌─ STAGE 1 · reference-chained ladder ────────────────────────┐
        │  one text→image MASTER, every other state an EDIT carrying  │
        │  [master (identity+style)] + [previous state (continuity)]  │
        └──────────────────────────┬──────────────────────────────────┘
                                   │  8 plates
        ┌──────────────────────────▼──────────────────────────────────┐
        │  STAGE 2 · multiview → Tripo → GLB    ⚠ PROVEN, DO NOT EDIT │
        │  [no-bg front, port profile, stern] → Tripo v3.1 → textured │
        └──────────────────────────┬──────────────────────────────────┘
                                   │  8 meshes
        ┌──────────────────────────▼──────────────────────────────────┐
        │  STAGE 3 · turntable → 8 headings → cutout → pack           │
        └─────────────────────────────────────────────────────────────┘
```

Stages 1 and 2 live in one Comfy graph on purpose: the plates that feed Tripo **are** the
chained plates, so the 2D ladder and the 3D meshes cannot drift out of sync.

## Naming contract

Load-bearing — many hulls go through this.

```
subject id     <hull>__<state>__<rig>      galleon__03-moderate__sails-open
```

- kebab-case *within* a field, double underscore *between* fields, so a hull id containing
  a hyphen still parses with a plain `split("__")`
- state carries a numeric prefix, so lexical sort equals damage order
- rig is always present — `05-destroyed` uses `sails-none` — so the field count is fixed

| State | Rigs |
|---|---|
| `01-pristine` | `sails-open`, `sails-closed` |
| `02-light` | `sails-open`, `sails-closed` |
| `03-moderate` | `sails-open`, `sails-closed` |
| `04-heavy` | `sails-open` |
| `05-destroyed` | `sails-none` |

Pack layout matches the existing
[sprite-foundry-packs](https://github.com/mcp-tool-shop-org/sprite-foundry-packs) shape
exactly, with the hull/state/rig triple occupying the `subject` slot — so tooling that
globs `assets/*/albedo/*.png` keeps working unchanged:

```
assets/<subject-id>/albedo/{front,front_left,left,back_left,back,back_right,right,front_right}.png
assets/<subject-id>/depth/…   normal/…   manifest.json   preview/contact_sheet.png
```

## Meshes are not repo content

A single galleon GLB is ~58 MB (1.07M verts / 1.96M faces). A full hull line is 400 MB+.
Meshes are **build inputs** — they live in the mesh store and are re-derivable from the
saved Comfy workflow. Sprites are what this repo ships. `.gitignore` enforces this.

## Pipeline scripts

| Script | Does |
|---|---|
| `pipeline/build_ladder_workflow.py` | stage 1 graph — the chained damage ladder |
| `pipeline/build_mesh_workflow.py` | stage 2 graph — multiview → Tripo → GLB, one subject |
| `pipeline/build_full_workflow.py` | stages 1+2 in one graph, whole hull |
| `pipeline/cutout_plates.py` | deterministic background removal + scale normalisation |
| `pipeline/turntable.py` | Blender 8-view turntable (from sprite-foundry/3d-prerender) |
| `pipeline/validate_graph.py` | link integrity + "every plate chains to the master" |

```bash
python pipeline/build_full_workflow.py --hull galleon --out wf.json --manifest hulls/galleon.manifest.json
```

## Hard-won settings

Things that cost real time to learn. Change them deliberately, not casually.

- **Cutout is local, never cloud.** The `Remove the background` API call returns an opaque
  image with a re-shaded background — verified 0.0% transparent. `cutout_plates.py` does it
  for free and exactly. (The `Remove the background` node *inside stage 2* is different —
  it is Tripo's input prep and part of the proven path. Leave it.)
- **Flood fill must bridge rigging.** Rigging lines partition the sky into pockets that
  never touch the frame edge. Flood over a dilated mask, then intersect back with the
  strict mask so the rigging itself stays opaque.
- **Tolerance 8, not 26.** Pale sails fall within 26 of a mid-gray background and get
  punched through.
- **Background should be chroma key, not gray.** Both problems above exist only because the
  plate background is mid-gray. This is the outstanding fix.
- **Don't prompt for framing — normalise it.** Alpha-bbox fit after cutout is deterministic;
  prompting is not.
- **A contact sheet is not a gate.** Ship sprites are not "ready" until they pass an
  in-engine spin test.

## Status

| | |
|---|---|
| Hulls | `galleon` |
| States | 5 × 2 rigs → 8 subjects |
| Stage 1 | working |
| Stage 2 | working — identity holds across 8 headings |
| Stage 3 | turntable proven on one mesh; pack export not yet built |

## License

MIT
