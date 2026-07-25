#!/usr/bin/env python3
"""
SPIKE: can the fused Tripo mesh be separated into parts?

The whole question for mesh-first damage generation. If sails / masts / hull come
apart cleanly, then structural damage (furl the sails, snap a mast, hole the hull)
becomes a deterministic modelling operation instead of something we ask an image
model for and get ~60% of the time.

Three separation strategies, cheapest first:
  1. connected components  — are parts topologically disjoint?
  2. material / UV islands — did Tripo assign distinct materials?
  3. spatial + geometric   — sails are large, thin, high; hull is dense and low.

Reports what it finds. Draws no conclusion it cannot support.
"""

import sys
from collections import Counter

import numpy as np
import trimesh

path = sys.argv[1]
print(f"loading {path}")
scene = trimesh.load(path)

geoms = scene.geometry if hasattr(scene, "geometry") else {"mesh": scene}
print(f"\n[1] SCENE STRUCTURE")
print(f"    geometries: {len(geoms)}")
for name, g in geoms.items():
    print(f"    {name[:44]:<46} {len(g.vertices):>9,} verts  {len(g.faces):>9,} faces")

mesh = list(geoms.values())[0]

print(f"\n[2] MATERIALS / UV")
vis = mesh.visual
print(f"    visual kind: {type(vis).__name__}")
mat = getattr(vis, "material", None)
print(f"    material:    {type(mat).__name__ if mat is not None else 'none'}")
if mat is not None:
    img = getattr(mat, "baseColorTexture", None) or getattr(mat, "image", None)
    print(f"    texture:     {img.size if img is not None else 'none'}")
uv = getattr(vis, "uv", None)
print(f"    uv coords:   {'yes ' + str(uv.shape) if uv is not None else 'NO'}")
print("    -> single material means material-based separation is NOT available")

print(f"\n[3] CONNECTED COMPONENTS  (this is the decisive test)")
# mesh.split() builds a submesh per component and blows out RAM on a 2M-face
# mesh. Work on the adjacency graph directly — index arrays only, no geometry.
from trimesh.graph import connected_components

comp_idx = connected_components(mesh.face_adjacency, nodes=np.arange(len(mesh.faces)))
print(f"    components: {len(comp_idx)}")
if len(comp_idx) == 1:
    print("    -> ONE component. The mesh is topologically fused:")
    print("       sails, masts, rigging and hull are welded into a single surface.")
    print("       Component-based separation is NOT available.")
else:
    sizes = sorted((len(c) for c in comp_idx), reverse=True)
    print(f"    face counts (top 15): {sizes[:15]}")
    print(f"    components >0.1% of mesh: "
          f"{sum(1 for c in comp_idx if len(c) > len(mesh.faces) * 0.001)}")
    print("\n    largest components — bbox, relative height, thinness:")
    ranked = sorted(comp_idx, key=len, reverse=True)[:14]
    y_lo, y_hi = mesh.bounds[0][1], mesh.bounds[1][1]
    span = y_hi - y_lo
    for i, idx in enumerate(ranked):
        vid = np.unique(mesh.faces[idx])
        pts = mesh.vertices[vid]
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        e = hi - lo
        rel_h = ((lo[1] + hi[1]) / 2 - y_lo) / span
        thin = float(min(e) / max(e)) if max(e) > 0 else 0.0
        print(f"      {i:>2}  faces {len(idx):>8,}  extents "
              f"{e[0]:5.2f} {e[1]:5.2f} {e[2]:5.2f}  "
              f"height {rel_h:4.2f}  thinness {thin:5.3f}")

print(f"\n[4] SPATIAL SEPARABILITY  (fallback if topology is fused)")
v = mesh.vertices
y = v[:, 1]
lo, hi = y.min(), y.max()
h = hi - lo
bands = [(0.0, 0.25, "hull / below deck"), (0.25, 0.45, "deck & lower rig"),
         (0.45, 1.0, "upper rig & sails")]
for a, b, label in bands:
    m = (y >= lo + a * h) & (y < lo + b * h)
    print(f"    {label:<20} {m.sum():>9,} verts  ({100 * m.mean():5.1f}%)")
print("    -> a height band can isolate the RIG from the HULL, but cannot tell")
print("       a sail from the mast it hangs on; both live in the same band.")

print("\n[5] VERDICT INPUTS")
print(f"    components:        {len(comps)}")
print(f"    single material:   {mat is not None}")
print(f"    watertight:        {mesh.is_watertight}")
