#!/usr/bin/env python3
"""
Render the turn cycle as an animated GIF — the shareable form of the spin test.

The interactive harness (tools/spin-test.html) is the real instrument; this is
what you can put in a commit, an issue, or a message. Every state spins in
lockstep against a FIXED crosshair, because the failures worth catching only
show up as motion relative to something that does not move:

  scale jump      one state larger/smaller than its neighbours
  anchor drift    hull wandering off the crosshair as it turns
  flicker         one heading darker than the rest
  silhouette pop  shape discontinuity between adjacent headings

Usage:
    python pipeline/make_spin_gif.py --hull galleon --out hulls/galleon/spin.gif
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
HEADINGS = [
    "front", "front_left", "left", "back_left",
    "back", "back_right", "right", "front_right",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hull", default="galleon")
    ap.add_argument("--channel", default="albedo")
    ap.add_argument("--cell", type=int, default=210)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--ms", type=int, default=220, help="frame duration")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    pack = json.loads((REPO / "hulls" / args.hull / "pack.json").read_text(encoding="utf-8"))
    subjects = pack["subjects"]
    cell, cols = args.cell, args.cols
    rows = (len(subjects) + cols - 1) // cols
    lh = 16
    W, H = cell * cols, (cell + lh) * rows

    frames = []
    for h in HEADINGS:
        canvas = Image.new("RGB", (W, H), (21, 22, 26))
        draw = ImageDraw.Draw(canvas)
        for i, s in enumerate(subjects):
            c, r = i % cols, i // cols
            x, y = c * cell, r * (cell + lh)
            sprite = (Image.open(REPO / "assets" / s / args.channel / f"{h}.png")
                      .convert("RGBA").resize((cell, cell), Image.LANCZOS))
            tile = Image.new("RGBA", (cell, cell), (34, 36, 43, 255))
            tile.alpha_composite(sprite)
            canvas.paste(tile.convert("RGB"), (x, y + lh))
            # fixed graticule — the thing the ship must NOT move relative to
            d2 = ImageDraw.Draw(canvas)
            d2.line([(x + cell // 2, y + lh), (x + cell // 2, y + lh + cell)],
                    fill=(217, 164, 65), width=1)
            d2.line([(x, y + lh + cell // 2), (x + cell, y + lh + cell // 2)],
                    fill=(217, 164, 65), width=1)
            draw.text((x + 4, y + 3), s.split("__", 1)[1], fill=(200, 205, 215))
        draw.text((W - 90, 3), h, fill=(217, 164, 65))
        frames.append(canvas.convert("P", palette=Image.ADAPTIVE, colors=128))

    out = Path(args.out) if args.out else REPO / "hulls" / args.hull / "spin.gif"
    out.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=args.ms, loop=0, optimize=True)
    print(f"wrote {out} — {len(frames)} frames, {W}x{H}, "
          f"{out.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
