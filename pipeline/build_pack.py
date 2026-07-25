#!/usr/bin/env python3
"""
Stage 3 driver — turn a hull's normalised meshes into a finished sprite pack.

    normalised GLBs  ->  8 headings each  ->  assets/<subject-id>/  ->  manifests

Emits the sprite-foundry-packs layout verbatim, with the hull/state/rig triple
occupying the `subject` slot, so existing tooling that globs
`assets/*/albedo/*.png` works on ship packs unchanged:

    assets/<subject-id>/albedo/{front,front_left,left,back_left,
                                back,back_right,right,front_right}.png
    assets/<subject-id>/manifest.json
    assets/<subject-id>/preview/contact_sheet.png
    hulls/<hull>/pack.json          <- pack-level index

PRECONDITION: meshes must already be normalised (normalize_meshes.py). Stage 3
frames the camera in fixed world units, so raw Tripo output — which arrives at
arbitrary scale — would render every damage state at a different sprite size.
stage3_render_pack.py hard-fails rather than let that through, and this driver
surfaces that failure per subject instead of silently skipping.

Usage:
    python pipeline/build_pack.py --hull galleon
    python pipeline/build_pack.py --hull galleon --only galleon__05-destroyed__sails-none
    python pipeline/build_pack.py --hull galleon --size 1024 --force
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HEADINGS = [
    "front", "front_left", "left", "back_left",
    "back", "back_right", "right", "front_right",
]

REPO = Path(__file__).resolve().parent.parent
DEFAULT_BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
DEFAULT_STORE = Path(r"E:\AI-Models\mesh-store\portlight-ships")


def parse_subject(subject_id: str) -> dict:
    """`<hull>__<state>__<rig>` -> parts. Fixed field count is why this is safe."""
    parts = subject_id.split("__")
    if len(parts) != 3:
        raise ValueError(
            f"subject id {subject_id!r} does not have exactly 3 '__'-separated fields"
        )
    hull, state, rig = parts
    return {"subject_id": subject_id, "hull": hull, "state": state, "rig": rig}


def render_subject(blender: str, glb: Path, dest: Path, subject_id: str,
                   size: int, frame: float, elev: float) -> None:
    cmd = [
        blender, "-b", "--python", str(REPO / "pipeline" / "stage3_render_pack.py"), "--",
        "--glb", str(glb), "--out", str(dest), "--subject", subject_id,
        "--size", str(size), "--frame", str(frame), "--elev", str(elev),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or "STAGE3 DONE" not in proc.stdout:
        tail = "\n".join(
            l for l in (proc.stdout + proc.stderr).splitlines()
            if "ERROR" in l or "Error" in l
        )[:900]
        raise RuntimeError(f"render failed for {subject_id}\n{tail}")


def contact_sheet(subject_dir: Path, subject_id: str) -> Path:
    """8-up sheet on a checkerboard, so alpha problems are visible not assumed."""
    tiles = [Image.open(subject_dir / "albedo" / f"{h}.png").convert("RGBA")
             for h in HEADINGS]
    w, h = tiles[0].size
    cols, rows, lh = 4, 2, 20
    sheet = Image.new("RGB", (w * cols, (h + lh) * rows), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)
    for i, (name, tile) in enumerate(zip(HEADINGS, tiles)):
        c, r = i % cols, i // cols
        x, y = c * w, r * (h + lh)
        for cy in range(0, h, 16):
            for cx in range(0, w, 16):
                shade = (70, 70, 78) if ((cx // 16 + cy // 16) % 2 == 0) else (52, 52, 60)
                draw.rectangle([x + cx, y + lh + cy, x + cx + 15, y + lh + cy + 15],
                               fill=shade)
        sheet.paste(tile, (x, y + lh), tile)
        draw.text((x + 6, y + 4), name, fill=(255, 255, 255))
    out_dir = subject_dir / "preview"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "contact_sheet.png"
    sheet.save(path)
    return path


def measure(subject_dir: Path) -> dict:
    """Per-heading alpha coverage + bbox. Cheap, and it is the receipt that the
    pack is actually cut out and consistently framed rather than assumed to be."""
    import numpy as np
    rows = {}
    for h in HEADINGS:
        a = np.asarray(Image.open(subject_dir / "albedo" / f"{h}.png").convert("RGBA"))
        alpha = a[:, :, 3]
        ys, xs = np.nonzero(alpha > 8)
        rows[h] = {
            "transparent_pct": round(float((alpha == 0).mean() * 100), 1),
            "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
            if len(xs) else None,
        }
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hull", required=True)
    ap.add_argument("--meshes", default=None,
                    help="normalised GLB dir (default: <store>/<hull>-normalised)")
    ap.add_argument("--assets", default=str(REPO / "assets"))
    ap.add_argument("--blender", default=DEFAULT_BLENDER)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--frame", type=float, default=13.0)
    ap.add_argument("--elev", type=float, default=30.0)
    ap.add_argument("--only", nargs="*", default=None, help="subject ids to (re)build")
    ap.add_argument("--force", action="store_true", help="rebuild even if present")
    args = ap.parse_args()

    meshes = Path(args.meshes) if args.meshes else DEFAULT_STORE / f"{args.hull}-normalised"
    if not meshes.is_dir():
        print(f"ERROR: mesh dir not found: {meshes}", file=sys.stderr)
        return 1

    assets = Path(args.assets)
    glbs = sorted(meshes.glob("*.glb"))
    if args.only:
        wanted = set(args.only)
        glbs = [g for g in glbs if g.stem in wanted]

    print(f"{args.hull}: {len(glbs)} subjects at {args.size}px, frame {args.frame}")

    built, skipped, failed = [], [], []
    for glb in glbs:
        subject_id = glb.stem
        dest = assets / subject_id
        if dest.exists() and not args.force:
            print(f"  SKIP   {subject_id} (exists; --force to rebuild)")
            skipped.append(subject_id)
            continue
        try:
            meta = parse_subject(subject_id)
            render_subject(args.blender, glb, dest, subject_id,
                           args.size, args.frame, args.elev)
            sheet = contact_sheet(dest, subject_id)
            meta.update({
                "headings": HEADINGS,
                "channels": ["albedo"],
                "size": args.size,
                "frame_world_units": args.frame,
                "camera_elevation_deg": args.elev,
                "source_mesh": glb.name,
                "preview": str(sheet.relative_to(dest)).replace("\\", "/"),
                "per_heading": measure(dest),
            })
            (dest / "manifest.json").write_text(
                json.dumps(meta, indent=2), encoding="utf-8")
            print(f"  BUILT  {subject_id}")
            built.append(subject_id)
        except Exception as exc:                       # noqa: BLE001 — report, continue
            print(f"  FAIL   {subject_id}: {exc}")
            failed.append(subject_id)

    pack = {
        "hull": args.hull,
        "headings": HEADINGS,
        "channels": ["albedo"],
        "channels_not_yet_implemented": ["depth", "normal"],
        "size": args.size,
        "subjects": sorted({p.name for p in assets.glob(f"{args.hull}__*")}),
    }
    pack_dir = REPO / "hulls" / args.hull
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "pack.json").write_text(json.dumps(pack, indent=2), encoding="utf-8")

    print(f"\nbuilt {len(built)}  skipped {len(skipped)}  failed {len(failed)}")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
