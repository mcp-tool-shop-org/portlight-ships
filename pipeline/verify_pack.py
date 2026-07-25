#!/usr/bin/env python3
"""
Verify a built pack — the receipt, not a vibe check.

Checks the three things that silently go wrong in a sprite pack and are hard to
spot by eye once there are dozens of subjects:

  1. COMPLETENESS — every subject has all 8 headings for every declared channel.
  2. ALPHA — sprites are actually cut out. A fully-opaque sprite means the alpha
     path broke; a nearly-empty one means the mesh failed to load or frame.
  3. SCALE CONSISTENCY — the same heading is the same size across every subject.
     This is the one that fixed framing exists to guarantee, so it is the one
     worth asserting. A widening spread means an un-normalised mesh slipped in.

Exits non-zero on failure so it can gate a build.

Usage:
    python pipeline/verify_pack.py --hull galleon
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HEADINGS = [
    "front", "front_left", "left", "back_left",
    "back", "back_right", "right", "front_right",
]

# Only the BROADSIDE headings are a scale invariant. There, sprite width measures
# hull LENGTH, which does not change as a ship degrades — so it must match tightly
# across every subject, and a real spread there means an un-normalised mesh got in.
#
# Do NOT extend this check to front/back. Those are bow-on and stern-on, where
# width measures BEAM PLUS SPREAD SAILS: sails-open spans ~167px and sails-furled
# collapses to the bare hull at ~97px, a legitimate ~42% difference that is the rig
# working correctly. An earlier revision failed the build on exactly that and the
# "fix" would have been to loosen the real check until it stopped catching anything.
SCALE_INVARIANT_HEADINGS = ("left", "right")
MAX_WIDTH_SPREAD_PCT = 5.0

MIN_TRANSPARENT_PCT = 40.0
MAX_TRANSPARENT_PCT = 99.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hull", required=True)
    ap.add_argument("--assets", default=str(REPO / "assets"))
    args = ap.parse_args()

    assets = Path(args.assets)
    subjects = sorted(assets.glob(f"{args.hull}__*"))
    if not subjects:
        print(f"FAIL: no subjects found for hull {args.hull!r} in {assets}")
        return 1

    errors: list[str] = []
    widths: dict[str, list[tuple[str, int]]] = {h: [] for h in HEADINGS}

    for sub in subjects:
        mf = sub / "manifest.json"
        if not mf.exists():
            errors.append(f"{sub.name}: missing manifest.json")
            continue
        meta = json.loads(mf.read_text(encoding="utf-8"))

        for channel in meta["channels"]:
            for h in HEADINGS:
                p = sub / channel / f"{h}.png"
                if not p.exists():
                    errors.append(f"{sub.name}: missing {channel}/{h}.png")

        for h, row in meta["per_heading"].items():
            t = row["transparent_pct"]
            if not (MIN_TRANSPARENT_PCT <= t <= MAX_TRANSPARENT_PCT):
                errors.append(
                    f"{sub.name}/{h}: transparency {t}% outside "
                    f"{MIN_TRANSPARENT_PCT}..{MAX_TRANSPARENT_PCT}% "
                    "(opaque = alpha path broke; near-empty = mesh failed to frame)"
                )
            if row["bbox"] is None:
                errors.append(f"{sub.name}/{h}: empty sprite")
            else:
                bb = row["bbox"]
                widths[h].append((sub.name, bb[2] - bb[0]))

    print(f"{args.hull}: {len(subjects)} subjects")
    print(f"\n{'heading':<14} {'min':>6} {'max':>6} {'spread':>8}   check")
    for h in HEADINGS:
        vals = [w for _, w in widths[h]]
        if not vals:
            continue
        spread = 100.0 * (max(vals) - min(vals)) / max(vals)
        invariant = h in SCALE_INVARIANT_HEADINGS
        if invariant:
            failed = spread > MAX_WIDTH_SPREAD_PCT
            note = "FAIL" if failed else "ok"
            if failed:
                worst = max(widths[h], key=lambda kv: kv[1])[0]
                errors.append(
                    f"heading {h}: hull-length spread {spread:.1f}% exceeds "
                    f"{MAX_WIDTH_SPREAD_PCT}% (widest: {worst}) — an un-normalised "
                    "mesh got into the pack"
                )
        else:
            note = "informational (beam varies with rig)"
        print(f"{h:<14} {min(vals):>6} {max(vals):>6} {spread:>7.1f}%   {note}")

    if errors:
        print(f"\nFAIL — {len(errors)} problem(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    total = len(subjects) * len(HEADINGS)
    print(f"\nPASS — {total} sprites, all headings present, "
          "alpha in range, scale consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
