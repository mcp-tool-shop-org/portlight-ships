#!/usr/bin/env python3
"""
SPIKE 2: segment the fused mesh by TEXTURE COLOUR rather than topology.

Spike 1 found 2,174 connected components that do not correspond to semantic
parts — they are surface patches. But it also found a 4096x4096 albedo texture
with full UVs, and on a ship the parts are strongly colour-separated:

    sails   bright, low-saturation cream
    hull    mid-tone brown timber
    masts   dark near-black spars
    trim    saturated warm gold

If face colour separates those cleanly, structural damage becomes deterministic:
select sail faces -> delete them for a furled/stripped variant; select one mast's
faces -> cut and hinge it. No prompting involved.

Reports the actual colour distribution and how much of the mesh each class wins.
Draws no conclusion it cannot support.
"""

import sys

import numpy as np
import trimesh

path = sys.argv[1]
scene = trimesh.load(path)
mesh = list(scene.geometry.values())[0]

vis = mesh.visual
img = vis.material.baseColorTexture
tex = np.asarray(img.convert("RGB"))
H, W, _ = tex.shape
print(f"texture {W}x{H}   faces {len(mesh.faces):,}   verts {len(mesh.vertices):,}")

# Face colour = texture sampled at the face's UV centroid.
uv = np.asarray(vis.uv)
face_uv = uv[mesh.faces].mean(axis=1)
px = np.clip((face_uv[:, 0] % 1.0) * (W - 1), 0, W - 1).astype(np.int32)
py = np.clip((1.0 - (face_uv[:, 1] % 1.0)) * (H - 1), 0, H - 1).astype(np.int32)
face_rgb = tex[py, px].astype(np.float32)

r, g, b = face_rgb[:, 0], face_rgb[:, 1], face_rgb[:, 2]
lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
mx, mn = face_rgb.max(axis=1), face_rgb.min(axis=1)
sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)

print("\n[luminance distribution over faces]")
for lo, hi in [(0, 40), (40, 80), (80, 120), (120, 160), (160, 200), (200, 256)]:
    m = (lum >= lo) & (lum < hi)
    print(f"    lum {lo:>3}-{hi:<3} {m.sum():>9,} faces  {100 * m.mean():5.1f}%")

# Face areas — a class that wins many faces but little area is noise.
area = mesh.area_faces
total = area.sum()

CLASSES = {
    "sail   (bright, low sat)": (lum > 150) & (sat < 0.28),
    "gold trim (bright, high sat)": (lum > 120) & (sat >= 0.35),
    "hull timber (mid, warm)": (lum >= 60) & (lum <= 150) & (sat >= 0.18) & (sat < 0.35),
    "dark spars / shadow": lum < 60,
}
print("\n[colour classes]")
covered = np.zeros(len(mesh.faces), dtype=bool)
for name, m in CLASSES.items():
    covered |= m
    print(f"    {name:<30} {m.sum():>9,} faces  {100 * m.mean():5.1f}%   "
          f"area {100 * area[m].sum() / total:5.1f}%")
print(f"    {'unclassified':<30} {(~covered).sum():>9,} faces  "
      f"{100 * (~covered).mean():5.1f}%")

# The decisive question: are the sail faces where sails actually are (high up),
# or scattered everywhere (meaning colour is not tracking semantics)?
sail = CLASSES["sail   (bright, low sat)"]
y = mesh.vertices[:, 1]
y_lo, y_hi = y.min(), y.max()
face_y = y[mesh.faces].mean(axis=1)
rel = (face_y - y_lo) / (y_hi - y_lo)
print("\n[where do 'sail' faces sit vertically?]  0.0 = keel, 1.0 = masthead")
for lo, hi in [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]:
    band = (rel >= lo) & (rel < hi)
    if band.sum() == 0:
        continue
    frac = sail[band].mean()
    print(f"    band {lo:.1f}-{hi:.1f}   {100 * frac:5.1f}% of faces classed sail "
          f"  ({band.sum():>8,} faces in band)")

print("\n[interpretation inputs]")
print(f"    sail-classed area fraction : {100 * area[sail].sum() / total:.1f}%")
print(f"    sail faces above mid-height: "
      f"{100 * (rel[sail] > 0.4).mean():.1f}%")
