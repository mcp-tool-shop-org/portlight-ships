#!/usr/bin/env python3
"""
Build Hugging Face ImageFolder viewer metadata (`metadata.jsonl`) from the
`<hull>__<elevation>__<heading>.png` and `.txt` pairs in the training set.

Each JSONL row emits:
  {"file_name": "<hull>__<elevation>__<heading>.png",
   "text": "<caption text>",
   "hull": "<hull>",
   "elevation": "<elevation>",
   "heading": "<heading>"}

Usage:
    python tools/build_hf_metadata.py --src E:/AI/_staging/ship-training --out hf/portlight-ships-anatomy/metadata.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SRC = Path(r"E:\AI\_staging\ship-training")
DEFAULT_OUT = REPO / "hf" / "portlight-ships-anatomy" / "metadata.jsonl"

VALID_ELEVATIONS = {"low", "mid", "high"}
VALID_HEADINGS = {
    "front",
    "front_left",
    "left",
    "back_left",
    "back",
    "back_right",
    "right",
    "front_right",
}


def parse_stem(stem: str) -> tuple[str, str, str]:
    parts = stem.split("__")
    if len(parts) != 3:
        raise ValueError(
            f"expected '<hull>__<elevation>__<heading>', got {stem!r}"
        )
    hull, elevation, heading = parts
    if not hull:
        raise ValueError(f"empty hull in {stem!r}")
    if elevation not in VALID_ELEVATIONS:
        raise ValueError(
            f"unknown elevation {elevation!r} in {stem!r} "
            f"(expected one of {sorted(VALID_ELEVATIONS)})"
        )
    if heading not in VALID_HEADINGS:
        raise ValueError(
            f"unknown heading {heading!r} in {stem!r} "
            f"(expected one of {sorted(VALID_HEADINGS)})"
        )
    return hull, elevation, heading


def build_rows(src: Path) -> list[dict[str, str]]:
    if not src.is_dir():
        raise FileNotFoundError(f"source directory not found: {src}")

    rows: list[dict[str, str]] = []
    for png in sorted(src.glob("*.png")):
        if "__" not in png.stem:
            continue
        hull, elevation, heading = parse_stem(png.stem)
        txt = png.with_suffix(".txt")
        if not txt.is_file():
            raise FileNotFoundError(f"missing caption file for {png.name}: {txt}")
        caption = txt.read_text(encoding="utf-8").strip()
        if not caption:
            raise ValueError(f"empty caption in {txt}")
        rows.append(
            {
                "file_name": png.name,
                "text": caption,
                "hull": hull,
                "elevation": elevation,
                "heading": heading,
            }
        )
    return rows


def write_metadata(src: Path, out: Path) -> int:
    rows = build_rows(src)
    if not rows:
        print(f"ERROR: no <hull>__<elevation>__<heading>.png pairs found in {src}", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    hulls = sorted({r["hull"] for r in rows})
    print(
        f"wrote {out}: {len(rows)} pairs across {len(hulls)} hulls ({', '.join(hulls)})",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--src",
        type=Path,
        default=DEFAULT_SRC,
        help="Directory containing <hull>__<elevation>__<heading>.png/.txt pairs",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output path for metadata.jsonl",
    )
    args = ap.parse_args(argv)
    return write_metadata(args.src, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
