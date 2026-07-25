#!/usr/bin/env python3
"""
portlight-ships — the full per-hull pipeline in ONE workflow.

    reference-chained damage ladder  ->  multiview  ->  Tripo  ->  GLB

Running both stages in a single graph is deliberate: the plates that feed Tripo
ARE the chained plates, so the 2D ladder and the 3D meshes cannot drift out of
sync. Two separate runs would need the plates re-uploaded and kept in step by
hand, which is exactly the class of mistake this pipeline exists to remove.

STAGE 1 (ladder) — see build_ladder_workflow.py. One text->image master; every
other state is an edit carrying the master (identity + style) and the previous
state (damage continuity).

STAGE 2 (mesh) — see build_mesh_workflow.py. ⚠ Topology and Tripo parameters are
verbatim from the proven ship->3D workflows. Do not "improve" them.

Note the cutout nodes from the first ladder revision are GONE. They produced no
alpha (verified 0.0% transparent) — the cutout is done locally by
cutout_plates.py for free. The `Remove the background` node inside the MESH
stage is a different thing and stays: it is Tripo's input prep, part of the
proven path.

Usage:
    python build_full_workflow.py --hull galleon --out wf.json \
        --skip-mesh galleon__01-pristine__sails-open
"""

from __future__ import annotations

import argparse
import json
import sys

from build_ladder_workflow import (
    ANCHOR_RIG,
    ANCHOR_STATE,
    EDIT_CONTRACT,
    LADDER,
    MODEL,
    SYSTEM_PROMPT,
    anchor_prompt,
    subject_id,
)
from build_mesh_workflow import BG_PROMPT, SIDE_PROMPT, STERN_PROMPT, TRIPO_INPUTS


def nb(prompt: str, seed: int, title: str, ref: str | None = None) -> dict:
    inputs = {
        "prompt": prompt,
        "model": MODEL,
        "seed": seed,
        "aspect_ratio": "auto",
        "resolution": "1K",
        "response_modalities": "IMAGE",
        "thinking_level": "MINIMAL",
        "system_prompt": SYSTEM_PROMPT,
    }
    if ref is not None:
        inputs["images"] = [ref, 0]
    return {"inputs": inputs, "class_type": "GeminiNanoBanana2", "_meta": {"title": title}}


def build(hull: str, skip_mesh: set[str]) -> tuple[dict, list[dict]]:
    wf: dict[str, dict] = {}
    plates: dict[tuple[str, str], str] = {}
    order: list[tuple[str, str]] = []
    nid = 0

    def add(node: dict) -> str:
        nonlocal nid
        nid += 1
        wf[str(nid)] = node
        return str(nid)

    # ---- stage 1: the chained ladder ------------------------------------
    anchor_key = (ANCHOR_STATE, ANCHOR_RIG)
    anchor = add(nb(anchor_prompt(hull), 1001, f"MASTER · {subject_id(hull, *anchor_key)}"))
    plates[anchor_key] = anchor
    order.append(anchor_key)

    for i, (state, rig, prev, delta) in enumerate(LADDER, start=1):
        key = (state, rig)
        sid = subject_id(hull, state, rig)
        if prev is None:
            ref = anchor
        else:
            ref = add({
                "inputs": {"images.image0": [anchor, 0], "images.image1": [plates[prev], 0]},
                "class_type": "BatchImagesNode",
                "_meta": {"title": f"refs · {sid}"},
            })
        plates[key] = add(nb(EDIT_CONTRACT + delta, 1001 + i, sid, ref=ref))
        order.append(key)

    # ---- stage 2: multiview -> Tripo -> GLB, per subject -----------------
    manifest: list[dict] = []
    for i, key in enumerate(order):
        state, rig = key
        sid = subject_id(hull, state, rig)
        plate = plates[key]

        add({
            "inputs": {"filename_prefix": f"{hull}/plates-raw/{sid}", "images": [plate, 0]},
            "class_type": "SaveImage",
            "_meta": {"title": f"plate · {sid}"},
        })

        meshed = sid not in skip_mesh
        if meshed:
            bg = add(nb(BG_PROMPT, 3000 + i, f"no-bg · {sid}", ref=plate))
            side = add(nb(SIDE_PROMPT, 4000 + i, f"side · {sid}", ref=plate))
            stern = add(nb(STERN_PROMPT, 5000 + i, f"stern · {sid}", ref=plate))
            views = add({
                "inputs": {
                    "images.image0": [bg, 0],
                    "images.image1": [side, 0],
                    "images.image2": [stern, 0],
                },
                "class_type": "BatchImagesNode",
                "_meta": {"title": f"3 views · {sid}"},
            })
            tripo = add({
                "inputs": {**TRIPO_INPUTS, "image": [views, 0]},
                "class_type": "TripoImageToModelNode",
                "_meta": {"title": f"Tripo · {sid}"},
            })
            add({
                "inputs": {
                    "filename_prefix": f"{hull}/mesh/{sid}",
                    "image": "",
                    "mesh": [tripo, 2],
                },
                "class_type": "SaveGLB",
                "_meta": {"title": f"glb · {sid}"},
            })

        manifest.append({
            "subject_id": sid,
            "hull": hull,
            "state": state,
            "rig": rig,
            "is_master": key == anchor_key,
            "plate_raw": f"{hull}/plates-raw/{sid}",
            "mesh": f"{hull}/mesh/{sid}" if meshed else None,
            "pack_path": f"assets/{sid}",
        })

    return wf, manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hull", default="galleon")
    ap.add_argument("--out", default=None)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--skip-mesh", nargs="*", default=[],
                    help="subject ids whose mesh already exists")
    args = ap.parse_args()

    wf, manifest = build(args.hull, set(args.skip_mesh))
    text = json.dumps(wf, indent=2, ensure_ascii=False)

    if args.manifest:
        with open(args.manifest, "w", encoding="utf-8") as fh:
            json.dump({"hull": args.hull, "subjects": manifest}, fh, indent=2, ensure_ascii=False)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)

    types = [n["class_type"] for n in wf.values()]
    print(
        f"{len(types)} nodes | {types.count('GeminiNanoBanana2')} Nano Banana | "
        f"{types.count('TripoImageToModelNode')} Tripo | {types.count('SaveGLB')} GLB | "
        f"{types.count('SaveImage')} plates | {len(text):,} bytes",
        file=sys.stderr,
    )
    if not args.out:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
