#!/usr/bin/env python3
"""
SPIKE 3 — the decisive one. Delete the sails from the mesh by deterministic
selection and export the result, so we can LOOK at whether it worked.

If this produces a recognisable galleon under bare poles, then structural damage
is a modelling operation and the whole damage ladder stops being a generation
problem. If it produces swiss cheese, mesh-first is harder than colour+height and
we need to say so.

Selection rule: bright + low-saturation (canvas) AND above a height threshold
(rules out bright deck planking, which spike 2 showed is the main false positive).
"""

import sys

import numpy as np
import trimesh

src, dst = sys.argv[1], sys.argv[2]
h_min = float(sys.argv[3]) if len(sys.argv) > 3 else 0.35

# force='mesh' BAKES the scene-graph transform. Taking scene.geometry directly
# returns untransformed local coords and silently drops normalisation.
mesh = trimesh.load(src, force="mesh")
vis = mesh.visual
tex = np.asarray(vis.material.baseColorTexture.convert("RGB"))
H, W, _ = tex.shape

uv = np.asarray(vis.uv)
face_uv = uv[mesh.faces].mean(axis=1)
px = np.clip((face_uv[:, 0] % 1.0) * (W - 1), 0, W - 1).astype(np.int32)
py = np.clip((1.0 - (face_uv[:, 1] % 1.0)) * (H - 1), 0, H - 1).astype(np.int32)
rgb = tex[py, px].astype(np.float32)

lum = 0.2126 * rgb[:, 0] + 0.7152 * rgb[:, 1] + 0.0722 * rgb[:, 2]
mx, mn = rgb.max(axis=1), rgb.min(axis=1)
sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)

y = mesh.vertices[:, 1]
rel = (y[mesh.faces].mean(axis=1) - y.min()) / (y.max() - y.min())

is_sail = (lum > 150) & (sat < 0.28) & (rel > h_min)
print(f"height cut {h_min}: {is_sail.sum():,} of {len(mesh.faces):,} faces "
      f"({100 * is_sail.mean():.1f}%) selected as sail")
print(f"area removed: {100 * mesh.area_faces[is_sail].sum() / mesh.area_faces.sum():.1f}%")

keep = ~is_sail
kept_faces = mesh.faces[keep]
used = np.unique(kept_faces)
remap = np.full(len(mesh.vertices), -1, dtype=np.int64)
remap[used] = np.arange(len(used))

stripped = trimesh.Trimesh(
    vertices=mesh.vertices[used],
    faces=remap[kept_faces],
    visual=trimesh.visual.TextureVisuals(
        uv=uv[used], material=vis.material),
    process=False,
)
stripped.export(dst)
print(f"wrote {dst}: {len(stripped.faces):,} faces, {len(stripped.vertices):,} verts")
