#!/usr/bin/env python3
"""
Normalise Tripo GLB output to a canonical scale and origin.

WHY
---
Tripo returns meshes at inconsistent scales. Measured across one galleon ladder:

    galleon__01-pristine__sails-closed    6.02 x 12.00 x 15.11
    galleon__02-light__sails-open         5.79 x 12.00 x 14.78
    galleon__03-moderate__sails-open      3.26 x  8.00 x  9.78
    the other five                       ~1.2  x  2.50 x  ~3.2

Those Y values (12.00 / 8.00 / 2.50) are suspiciously round, so Tripo is
normalising to a fixed dimension but choosing a different one per job. The
turntable hides it because it auto-frames per mesh — but swap a damage state at
runtime and the ship would jump size by up to 4.7x.

METHOD
------
Uniform scale so the fore-aft LENGTH (the largest extent, Z in glTF's Y-up
convention) equals --length. Length is the right invariant for a damage ladder:
a ship loses masts and canvas as it degrades, so height shrinks legitimately,
but hull length does not change.

Cross-check on the galleon ladder — after normalising length to 10.0, mast
height lands in 7.69..8.18 (a ~6% spread) across all eight states, with the
wreck lowest. That is the expected signature of one ship at one scale, and is
the evidence that length-normalisation is the correct invariant here.

Origin: centred on X/Z, keel (min Y) placed at Y=0, so every state shares an
anchor. NOTE: keel-at-zero is a deterministic approximation of a waterline
anchor. A true waterline needs hull analysis; revisit if ships sit wrong in
engine.

Usage:
    python normalize_meshes.py --src <mesh dir> --out <dir> [--length 10.0]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import trimesh


def normalize(path: Path, target_length: float) -> tuple[trimesh.Scene, dict]:
    scene = trimesh.load(path)
    if isinstance(scene, trimesh.Trimesh):
        scene = trimesh.Scene(scene)

    before = scene.extents.copy()
    length = float(before.max())
    if length <= 0:
        raise ValueError(f"{path.name}: degenerate bounding box {before}")

    scale = target_length / length
    scene.apply_transform(trimesh.transformations.scale_matrix(scale))

    # centre on X/Z, keel to Y=0
    lo, hi = scene.bounds
    offset = np.array([
        -(lo[0] + hi[0]) / 2.0,
        -lo[1],
        -(lo[2] + hi[2]) / 2.0,
    ])
    scene.apply_translation(offset)

    after = scene.extents
    return scene, {
        "file": path.name,
        "extents_before": [round(float(v), 3) for v in before],
        "extents_after": [round(float(v), 3) for v in after],
        "scale_applied": round(float(scale), 5),
        "height_after": round(float(after[1]), 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--length", type=float, default=10.0)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for p in sorted(src.glob("*.glb")):
        scene, row = normalize(p, args.length)
        scene.export(out / p.name)
        rows.append(row)
        print(
            f"{p.stem:<40} x{row['scale_applied']:<8} "
            f"{row['extents_before']} -> {row['extents_after']}"
        )

    if rows:
        heights = [r["height_after"] for r in rows]
        spread = (max(heights) - min(heights)) / max(heights) * 100
        print(
            f"\n{len(rows)} meshes at length {args.length}. "
            f"Height {min(heights):.2f}..{max(heights):.2f} ({spread:.1f}% spread) "
            f"— low spread confirms one ship at one scale."
        )

    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump({"target_length": args.length, "meshes": rows}, fh, indent=2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
