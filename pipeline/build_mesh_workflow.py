#!/usr/bin/env python3
"""
Build the multiview -> Tripo -> GLB workflow for ONE ship subject.

⚠ DO NOT "IMPROVE" THIS GRAPH.
The node topology and every Tripo parameter below are copied verbatim from the
workflows that already produce working GLBs on Comfy Cloud ("Pristine ship —
sails open -> 3D" etc.). Getting a usable ship mesh took six months; this stage
is the part that works. The ONLY intentional change versus those workflows is
where the front view comes from — the reference-chained master instead of an
independent text->image roll, so hull identity is shared across damage states.

In particular, keep these as-is:
  - BatchImages receives [background-removed FRONT, side/port, stern] in that order
  - the side/stern prompts are the proven wording, ending "No background"
  - Tripo: v3.1-20260211, texture=True, pbr=True, model_seed=42, texture_seed=42,
    texture_alignment=original_image, geometry_quality=detailed, face_limit=-1
  - SaveGLB takes Tripo output slot 2 (the GLB), not slot 0/1

Usage:
    python build_mesh_workflow.py --hull galleon --state 01-pristine --rig sails-open \
        --out mesh_wf.json
"""

from __future__ import annotations

import argparse
import json
import sys

from build_ladder_workflow import (
    MODEL,
    SYSTEM_PROMPT,
    anchor_prompt,
    subject_id,
)

# --- proven prompts, verbatim from the working cloud workflows ---------------
SIDE_PROMPT = (
    "Create a direct side (port) profile view of this exact same ship, keep the identical "
    "hull, masts, sails, colors and details, do not change the design or lighting.\n\n"
    "No background"
)
STERN_PROMPT = (
    "Create a rear (stern) view of this exact same ship, keep the identical hull, masts, "
    "sails, colors and details, do not change the design or lighting.\n\nNo background"
)
BG_PROMPT = "Remove the background"

# --- proven Tripo settings, verbatim ----------------------------------------
TRIPO_INPUTS = {
    "model_version": "v3.1-20260211",
    "style": "None",
    "texture": True,
    "pbr": True,
    "model_seed": 42,
    "orientation": "default",
    "texture_seed": 42,
    "texture_quality": "detailed",
    "texture_alignment": "original_image",
    "face_limit": -1,
    "quad": False,
    "geometry_quality": "detailed",
}


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


def build(hull: str, state: str, rig: str) -> dict:
    sid = subject_id(hull, state, rig)

    return {
        # 1 — front view. The reference-chained master prompt.
        "1": nb(anchor_prompt(hull), 1001, f"front · {sid}"),
        # 2 — background-removed front. Feeds Tripo, exactly as in the proven graph.
        "2": nb(BG_PROMPT, 1004, f"front no-bg · {sid}", ref="1"),
        # 3 — side/port profile off the front.
        "3": nb(SIDE_PROMPT, 1002, f"side · {sid}", ref="1"),
        # 4 — stern view off the front.
        "4": nb(STERN_PROMPT, 1003, f"stern · {sid}", ref="1"),
        # 5 — the 3-view batch, in the proven order.
        "5": {
            "inputs": {
                "images.image0": ["2", 0],
                "images.image1": ["3", 0],
                "images.image2": ["4", 0],
            },
            "class_type": "BatchImagesNode",
            "_meta": {"title": f"3 views · {sid}"},
        },
        # 6 — Tripo. Parameters verbatim.
        "6": {
            "inputs": {**TRIPO_INPUTS, "image": ["5", 0]},
            "class_type": "TripoImageToModelNode",
            "_meta": {"title": f"Tripo · {sid}"},
        },
        # 7 — GLB out. Tripo output slot 2.
        "7": {
            "inputs": {
                "filename_prefix": f"{hull}/mesh/{sid}",
                "image": "",
                "mesh": ["6", 2],
            },
            "class_type": "SaveGLB",
            "_meta": {"title": f"glb · {sid}"},
        },
        # 8 — keep the front plate alongside the mesh for provenance.
        "8": {
            "inputs": {
                "filename_prefix": f"{hull}/mesh-front/{sid}",
                "images": ["1", 0],
            },
            "class_type": "SaveImage",
            "_meta": {"title": f"front plate · {sid}"},
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hull", default="galleon")
    ap.add_argument("--state", default="01-pristine")
    ap.add_argument("--rig", default="sails-open")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    wf = build(args.hull, args.state, args.rig)
    text = json.dumps(wf, indent=2, ensure_ascii=False)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        types = [n["class_type"] for n in wf.values()]
        print(
            f"wrote {args.out}: {len(types)} nodes, "
            f"{types.count('GeminiNanoBanana2')} Nano Banana calls, "
            f"{types.count('TripoImageToModelNode')} Tripo call ({len(text):,} bytes)",
            file=sys.stderr,
        )
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
