#!/usr/bin/env python3
"""
Deterministic background removal for ship plates.

The Nano Banana "remove the background" pass does NOT produce alpha — it returns
an opaque image with a re-shaded flat background. This does the cutout locally:
free, exact, reproducible, and no API spend.

Method: flood-fill from the frame edges over pixels within a colour tolerance of
the sampled border colour. Edge flood-fill (NOT corner-colour estimation) is the
documented approach — corner estimation fails when hull colours overlap the
background. Enclosed regions (gaps between rigging and hull) stay opaque unless
they connect to the border, which is the correct behaviour for a ship.

Also emits a scale-normalised variant: every plate is alpha-bbox fitted to a
common canvas so the hull occupies the same footprint across the whole ladder,
rather than relying on the model to hold framing (it does not).

Usage:
    python cutout_plates.py --src <plates-raw dir> --out <plates dir> [--tol 26]
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def edge_flood_alpha(rgb: np.ndarray, tol: int, bridge: int = 3) -> np.ndarray:
    """Return a boolean mask of background pixels, flood-filled from the edges.

    Rigging lines partition the sky into pockets that never touch the frame, so a
    naive edge flood leaves them opaque. Fix: flood over a DILATED copy of the
    background mask, which bridges thin rigging (<= 2*bridge px) and lets the fill
    reach every pocket — then intersect the reachable set back with the strict
    mask, so the rigging itself stays fully opaque.
    """
    h, w, _ = rgb.shape

    # Border colour = median of the 1px frame, robust to a stray dark pixel.
    border = np.concatenate([rgb[0, :], rgb[-1, :], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)

    within = (np.abs(rgb.astype(np.int16) - bg.astype(np.int16)).max(axis=2) <= tol)

    if bridge > 0:
        m = Image.fromarray((within * 255).astype(np.uint8))
        m = m.filter(ImageFilter.MaxFilter(2 * bridge + 1))
        flood_mask = np.asarray(m) > 127
    else:
        flood_mask = within

    visited = np.zeros((h, w), dtype=bool)
    q: deque[tuple[int, int]] = deque()

    for x in range(w):
        for y in (0, h - 1):
            if flood_mask[y, x] and not visited[y, x]:
                visited[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if flood_mask[y, x] and not visited[y, x]:
                visited[y, x] = True
                q.append((y, x))

    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and flood_mask[ny, nx] and not visited[ny, nx]:
                visited[ny, nx] = True
                q.append((ny, nx))

    return visited & within


def cutout(path: Path, tol: int, bridge: int) -> Image.Image:
    im = Image.open(path).convert("RGB")
    rgb = np.asarray(im)
    bg_mask = edge_flood_alpha(rgb, tol, bridge)

    alpha = np.where(bg_mask, 0, 255).astype(np.uint8)
    rgba = np.dstack([rgb, alpha])
    return Image.fromarray(rgba, mode="RGBA")


def alpha_bbox(im: Image.Image) -> tuple[int, int, int, int] | None:
    a = np.asarray(im)[:, :, 3]
    ys, xs = np.nonzero(a)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--norm", default=None, help="also write scale-normalised plates here")
    ap.add_argument("--tol", type=int, default=8)
    ap.add_argument("--bridge", type=int, default=3, help="px of rigging to bridge")
    ap.add_argument("--canvas", default="1408x768")
    ap.add_argument("--margin", type=float, default=0.04, help="fraction of canvas kept clear")
    args = ap.parse_args()

    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cw, ch = (int(v) for v in args.canvas.split("x"))

    cut: dict[Path, Image.Image] = {}
    for p in sorted(src.glob("*.png")):
        im = cutout(p, args.tol, args.bridge)
        im.save(out / p.name)
        cut[p] = im
        a = np.asarray(im)[:, :, 3]
        pct = 100.0 * (a == 0).sum() / a.size
        bb = alpha_bbox(im)
        print(f"{p.name:52s} transparent {pct:5.1f}%  bbox {bb}")

    if not args.norm:
        return 0

    norm = Path(args.norm)
    norm.mkdir(parents=True, exist_ok=True)

    # Common scale: fit the LARGEST hull footprint into the margin box, then apply
    # that same scale to every plate so relative ship size is preserved.
    boxes = {p: alpha_bbox(im) for p, im in cut.items()}
    max_w = max(b[2] - b[0] for b in boxes.values() if b)
    max_h = max(b[3] - b[1] for b in boxes.values() if b)
    avail_w, avail_h = cw * (1 - 2 * args.margin), ch * (1 - 2 * args.margin)
    scale = min(avail_w / max_w, avail_h / max_h)

    for p, im in cut.items():
        b = boxes[p]
        if not b:
            continue
        crop = im.crop(b)
        nw, nh = max(1, round(crop.width * scale)), max(1, round(crop.height * scale))
        crop = crop.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        canvas.paste(crop, ((cw - nw) // 2, (ch - nh) // 2), crop)
        canvas.save(norm / p.name)

    print(f"\nnormalised {len(cut)} plates at common scale {scale:.4f} onto {cw}x{ch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
