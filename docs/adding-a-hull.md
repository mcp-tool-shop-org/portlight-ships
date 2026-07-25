# Adding a new hull

Everything except the ship's own description is shared across hulls. That is
deliberate — the shared spine (damage ladder, framing, palette, style, the
`STOWED` clause) is what makes different ships look like they belong to the same
game. A new hull should be a **config change plus five commands**.

Budget per hull: **29 Nano Banana calls + 8 Tripo**, in two paid steps with a
review gate between them.

---

## 1. Define the hull — the only file you write

`hulls/<hull-id>/hull.json`

```json
{
  "hull_id": "brigantine",
  "display_name": "Brigantine",
  "description": "a two-masted brigantine, square-rigged foremast and fore-and-aft mainsail, low sleek hull, plain stern",
  "frame_world_units": 13.0,
  "camera_elevation_deg": 30.0,
  "sprite_size": 512
}
```

`description` is spliced into the master prompt directly after
*"3D game asset render of"*, so write it as a noun phrase that reads naturally
there. Name the features that distinguish this hull's **silhouette** — mast
count and rig, hull profile, stern shape. Do not describe condition, camera,
palette or style; those are shared and will fight you if you restate them.

If the hull is much longer or shorter than a galleon, raise or lower
`frame_world_units` — it is the world-unit span the sprite frame covers, and
everything is normalised to a hull length of 10.0.

---

## 2. Generate the plates — PAID, 8 calls

```bash
python pipeline/build_ladder_workflow.py --hull brigantine --api --out wf.json
```

Save `wf.json` to Comfy Cloud and run it. It produces 8 plates: one text→image
master, and 7 edits each carrying the master (identity + style) and the previous
state (damage continuity).

Download the plates to `hulls/<hull-id>/plates-raw/`.

---

## 3. GATE — look at all 8 plates at full resolution

**Do not skip this.** Stage 2 turns each plate into a paid mesh, so a bad plate
costs twice. This gate exists because it was once removed: plates and meshes were
merged into one graph "so they cannot drift apart", which also deleted the only
checkpoint between them — and three wrong-rig plates became three wrong-rig
meshes.

Check each plate against the spec:

- **rig** — on `sails-closed` states, are the sails actually *stowed*? Bare masts
  and yards, canvas in thin bundles, sky visible through the gaps. "Gathered but
  still set" is the known failure and is not acceptable.
- **heading** — bow pointing LEFT in every plate, no mirrored states
- **palette** — consistent across all 8; the master must not be the odd one out
- **damage** — reads as a progression, and each state's damage carries forward
- **framing** — whole ship in frame, nothing cropped at the edges

Fix any failures before spending on meshes. To regenerate a subset, upload the
good plates and reference them (see
`portlight-ships — galleon sails-closed fix` on Comfy Cloud for the pattern) so
the corrected plates match the shipped ones instead of drifting off a re-rolled
master.

---

## 4. Generate the meshes — PAID, 21 calls + 8 Tripo

```bash
python pipeline/build_mesh_workflow.py --hull brigantine --state 01-pristine --rig sails-open --out mesh.json
```

⚠ The mesh stage topology and every Tripo parameter are **proven**. Do not
"improve" them. The only thing that should change is which plate feeds the front
view.

Download the GLBs to the mesh store, **not** the repo — one hull is ~460 MB and
`.gitignore` enforces the exclusion.

---

## 5. Normalise — free, and mandatory

```bash
python pipeline/normalize_meshes.py \
    --src  E:/AI-Models/mesh-store/portlight-ships/brigantine \
    --out  E:/AI-Models/mesh-store/portlight-ships/brigantine-normalised \
    --report hulls/brigantine/mesh_normalisation.json
```

Tripo returns meshes at arbitrary scale — **four** distinct scales were observed
across a single galleon ladder, needing corrections from ×0.68 to ×16.4. This
uniform-scales on fore-aft length, the right invariant because a degrading ship
loses masts and canvas but not hull length.

Sanity check the report: after normalisation, mast height should cluster tightly
(the galleon lands in 7.69–8.32, a 7.6% spread, wreck lowest). A wide spread
means the hull's states are not actually the same ship.

---

## 6. Build and verify the pack — free

```bash
python pipeline/build_pack.py   --hull brigantine
python pipeline/verify_pack.py  --hull brigantine
```

`build_pack.py` renders 8 headings per subject with **true alpha** — Blender
writes it directly, so there is no background to remove and none of the concept-
plate cutout problems apply here.

`verify_pack.py` gates on three things and exits non-zero on failure:

1. every subject has all 8 headings for every declared channel
2. alpha is in range — fully opaque means the alpha path broke, near-empty means
   the mesh failed to frame
3. **broadside sprite width is consistent across subjects** — that measures hull
   length, which cannot legitimately change, so a spread there means an
   un-normalised mesh got in

`front`/`back` width is reported but never gated: those measure beam plus spread
sails, and a furled ship really is ~42% narrower bow-on.

---

## Known gaps

- **`depth` and `normal` channels are not implemented.** Blender 5.2 rewrote the
  compositor (`Scene.node_tree` gone, no Math/MapRange/ValToRGB nodes,
  `OutputFile.file_slots` removed). A depth pass built on what survives would be
  normalised per-frame and silently useless. The durable route is a material-
  override render; that is its own increment.
- **Plate background is mid-grey, not chroma key.** Both concept-plate cutout
  problems (rigging sealing the sky into unreachable pockets, pale sails falling
  within tolerance of the background) exist only because of this. One clause in
  `FRAMING` fixes it for every future hull, but it changes the master, so it is a
  deliberate call.
- **Normalisation anchors the keel at Y=0**, a deterministic approximation of a
  waterline. If ships sit wrong in engine, look here first.
