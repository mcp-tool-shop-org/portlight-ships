# portlight-ships

**A canon-driven pipeline that teaches a diffusion model ship anatomy.** Fourteen hulls,
each traceable to a documented vessel, rendered from textured 3D so rotation is *true*
rather than prompted — then distilled into a LoRA that knows what a xebec is.

![The fleet — 14 ratified hulls](https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/assets/portlight-ships/fleet.png)

Sprites for [Portlight](https://github.com/mcp-tool-shop-org/portlight) and its 2.5D client.

---

## The problem this exists to solve

Ship sprites failed three times before this. The root cause is specific: **diffusion models
cannot generate ship headings.** Characters work because faces and poses give a strong
directional signal. A ship is a near-symmetric object with no equivalent cue, so "port bow
view" and "starboard quarter view" both come back as the same flattering broadside.
RealVisXL, JuggernautXL + pixel-art-xl, and Zero123++ all failed this way.

**The fix is not a better prompt.** Rotational truth has to come from a textured 3D model on
a deterministic turntable. Identity then holds across every heading because it is the same
mesh:

![8-heading turnaround](https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/assets/portlight-ships/turnaround.png)

## The thing worth knowing

Before training, base Qwen-Image renders a **xebec**, a **brig**, a **brigantine** and a
**junk** as four versions of the same generic square-rigger. The lateens, the battened
lugsails, the rig distinctions simply are not in the model.

But it renders a *wrecked* ship convincingly with no help at all.

![Base vs trained](https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/assets/portlight-ships/before-after.png)

So the base model **has damage and lacks anatomy** — and that asymmetry is the whole design.
Teach it the anatomy from 336 pristine renders; borrow the damage it already owns.

It works. Every image in the training set is pristine — there is not one damaged example —
and the adapter still infers damage correctly:

![Damage generalisation](https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/assets/portlight-ships/damage-generalisation.png)

Verified with an external verifier (SigLIP2, a different model family from the generator):
`wrecked 0.982` vs `intact 0.255` on the trained output, and `0.069 / 0.118` on a pristine
render. Concept bleed checked the same way — a control prompt for a wooden chair scores
`0.000` for "sailing ship" at every checkpoint.

## Known limitations

Stated plainly, because a pipeline that hides its failures is not reusable.

- **The brig and brigantine are not separated.** At matched seeds they render as the same
  vessel at every checkpoint — under-squared early, over-squared late, moving together. The
  model learned one "two-masted square-ish ship" concept that both captions map onto. This
  is a **data** problem, not a training one: their captions differ by a single clause, they
  have 24 images each, and the visual difference is one mast's rig. More steps and more rank
  both fail to fix it. 12 of the 14 hulls are cleanly separated; this is the only bad pair.
- **The junk's battens do not survive.** Patina generalises (a "weathered" junk renders
  greyed and sun-bleached with no weathered training image), but the full-length horizontal
  battens that define the rig do not appear.
- **Tripo desaturates by ~13 points**, uniformly. Hull-to-hull ordering is preserved, so it
  does not teach a false distinction, but renders are cooler than the canon palettes.

## The fleet

Fourteen hulls, all Director-ratified. `tradition` replaced a real-world `era` field because
the fleet spanned two actual centuries and the world is not tied to a date — anatomy stays
sourced to real vessels, only context is invented.

| Tradition | Hulls | Reads as |
|---|---|---|
| `cold-coast` | carrack, fluyt, cog | rounded cargo hulls, castles, high sterns |
| `crown-naval` | galleon, frigate, brig, barque | tall square rig, gun decks, ornament |
| `longshore` | brigantine, schooner, sloop | small, fore-and-aft, unadorned |
| `sunward-sea` | caravel, xebec, galley | low and sharp, lateens, oars |
| `far-trade` | junk | battened lugsails, slab stern, no bowsprit |

`patina` (`new` / `seasoned` / `weathered` / `ancient`) is a **separate axis from damage**.
Folding age into `01-pristine` was rejected: it would blur the reference point the damage
ladder is measured against, and bake weathering permanently into the mesh texture. Damage
says *this ship had a bad day*; patina says *this ship has a history*.

## Pipeline

```
  CANON  ────────────────────────────────────────────────────────────────
  style-dataset-lab/projects/portlight-ships/canon/ships/<hull>.md
  rig_plan names every mast and sail. Prompts are ASSEMBLED from this,
  never hand-written — a wrong rig is wrong in canon and fixed once.
                              │
  STAGE 1 · plate ────────────▼──────────────────────────────────────────
  one text→image plate per hull.  THE PLATE IS THE GATE — review before
  paying for a mesh (`--plate-only`).
                              │
  STAGE 2 · mesh ─────────────▼─────────────────  ⚠ PROVEN, DO NOT EDIT
  [no-bg front, port profile, stern] → Tripo v3.1 → textured GLB
  `--from-plate` meshes the APPROVED plate; the default regenerates a
  different one and silently discards the reviewed image.
                              │
  STAGE 3 · render ───────────▼──────────────────────────────────────────
  Blender turntable · 8 headings × 3 elevations · true alpha
  captions DERIVED from rig_plan → 336 image/caption pairs
                              │
  STAGE 4 · train ────────────▼──────────────────────────────────────────
  Qwen-Image LoRA, bf16, rank 16, lr 1e-4, 6000 steps
```

## Naming contract

Load-bearing — many hulls go through this.

```
subject id     <hull>__<state>__<rig>      galleon__03-moderate__sails-open
training pair  <hull>__<elev>__<heading>   xebec__mid__front_left
```

kebab-case *within* a field, double underscore *between* fields, so a hull id containing a
hyphen still parses with a plain `split("__")`. State carries a numeric prefix so lexical
sort equals damage order. Rig is always present — `05-destroyed` uses `sails-none` — so the
field count is fixed.

## Hard-won settings

Things that cost real time. Change them deliberately.

- **`--frame` is fleet-dependent.** It is the smallest frame fitting the *tallest* hull at
  the highest elevation, so it moves when a hull is added — the junk pushed it from 12.04 to
  12.78. `check_no_clipping()` fails the build and prints the correct value, because a
  clipped ship is a caption that lies about what is in the image.
- **Measure the thing, not a proxy.** Framing was once set from bounding-box *span* assuming
  a centred subject. It is not centred — a hull's mass sits low and its masts are thin — and
  15 of 240 renders clipped. Reach from frame centre is the constraint; span is not.
- **Cutout is local, never cloud.** The cloud `Remove the background` call returns an opaque
  image with a re-shaded background — verified 0.0% transparent. (The node *inside stage 2*
  is different: that is Tripo's input prep and part of the proven path. Leave it.)
- **Flood fill must bridge rigging.** Rigging partitions the sky into pockets that never
  touch the frame edge. Flood a dilated mask, then intersect back with the strict mask.
- **Tolerance 8, not 26.** Pale sails fall within 26 of a mid-grey background.
- **Lighting is measured, not eyeballed.** `--light 0.35 --world 0.18`. The inherited rig was
  tuned to lift black armour on character models and washed ships out — 46–78% of plate
  saturation lost.
- **Two prompt laws.** (1) Describe the *result*, not the manoeuvre, plus an explicit
  negative. (2) A topology change must be the *dominant* instruction on its own isolated
  pass, chained off the already-good plate.
- **A contact sheet is not a gate.** Sprites are not ready until an in-engine spin test.

## Meshes are not repo content

One galleon GLB is ~58 MB; a full hull line is 400 MB+. Meshes are **build inputs** — they
live in the mesh store and are re-derivable from the saved workflow. Sprites are what this
repo ships. `.gitignore` enforces it. Plates *are* versioned: each is a paid generation.

## Reproduce

```bash
# prove the camera before paying for a mesh
python pipeline/build_pristine_workflow.py --hull xebec --plate-only --out wf.json

# mesh an approved plate (NOT the default, which regenerates it)
python pipeline/build_pristine_workflow.py --hull xebec --from-plate <cloud-file> --out wf.json

# normalise every mesh onto the fleet's length invariant
python pipeline/normalize_meshes.py --src <in> --out <out>

# build the training set (fails loudly if anything clips)
python pipeline/build_training_set.py --out E:/AI/_staging/ship-training
```

## Model and dataset

The trained adapter and the 336-pair dataset are being published to HuggingFace under
[`mcp-tool-shop`](https://huggingface.co/mcp-tool-shop). Recommended checkpoint: **step
6000**, rank 16, lr 1e-4. Trigger token `plsvessel`.

## License

MIT
