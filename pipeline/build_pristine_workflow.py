#!/usr/bin/env python3
"""
Build the pristine plate -> multiview -> Tripo -> GLB workflow for ONE hull,
with the prompt assembled FROM CANON.

Nothing here is typed by hand. silhouette_cue, palette, material_dominant,
signature_features and forbidden_inputs all come out of
style-dataset-lab/projects/portlight-ships/canon/ships/<hull>.md. If a rig is
wrong, it is wrong in canon and gets fixed there — once — rather than in a prompt
that only this run sees.

Nano Banana has no negative-prompt field, so forbidden_inputs are rendered into
the prompt as an explicit prohibition block. That is why canon requires at least
one and why every entry traces to an observed failure.

⚠ THE MESH STAGE IS PROVEN — topology and every Tripo parameter are verbatim from
the working galleon run. Do not "improve" them. The only thing that changes per
hull is the prompt.

Usage:
    python pipeline/build_pristine_workflow.py --hull xebec --out wf.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

CANON = Path(r"E:\AI\style-dataset-lab\projects\portlight-ships\canon\ships")

MODEL = "Nano Banana 2 (Gemini 3.1 Flash Image)"
SYSTEM_PROMPT = (
    "You are an expert image-generation engine. You must ALWAYS produce an image.\n"
    "Interpret all user input—regardless of format, intent, or abstraction—as literal "
    "visual directives for image composition.\n"
    "If a prompt is conversational or lacks specific visual details, you must creatively "
    "invent a concrete visual scenario that depicts the concept.\n"
    "Prioritize generating the visual representation above any text, formatting, or "
    "conversational requests."
)

FRAMING = (
    "Rendered at a 3/4 FRONT angle with the BOW POINTING LEFT, the vessel centred and fully "
    "inside the frame with clear margin on all four sides, clean even lighting, no water, no "
    "ground plane, no cast shadow. THE BACKGROUND IS FLAT PURE CHROMA-KEY GREEN, pure "
    "saturated RGB(0,255,0), completely uniform with no gradient or shading."
)
STYLE = (
    "Stylised 2.5D game-asset look: crisp readable silhouette, clean line work, restrained "
    "painterly shading."
)

# Verbatim from the proven galleon mesh run.
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

TRIPO_INPUTS = {
    "model_version": "v3.1-20260211", "style": "None", "texture": True, "pbr": True,
    "model_seed": 42, "orientation": "default", "texture_seed": 42,
    "texture_quality": "detailed", "texture_alignment": "original_image",
    "face_limit": -1, "quad": False, "geometry_quality": "detailed",
}


def load_hull(hull_id: str) -> dict:
    text = (CANON / f"{hull_id}.md").read_text(encoding="utf-8")
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm)


def pristine_prompt(hull: dict) -> str:
    v = hull["visual"]
    rig = v["rig_plan"]
    masts = ", ".join(m["id"] for m in rig["masts"])
    sails = ", ".join(s["id"] for s in rig["sails"])

    return (
        f"3D game asset render of a {hull['ship_class']}, a {hull['era']} sailing vessel.\n\n"
        f"SHAPE: {v['silhouette_cue']}\n\n"
        f"STRUCTURE — this vessel has exactly {len(rig['masts'])} mast(s): {masts}. "
        f"It carries exactly {len(rig['sails'])} sails: {sails}. Draw every one of them and "
        f"draw no others.\n\n"
        f"MUST SHOW: {'; '.join(hull['signature_features'])}.\n\n"
        f"MATERIALS: {v['material_dominant']}. Palette: {' '.join(v['palette'])}.\n\n"
        f"CONDITION: PRISTINE and immaculate. Every sail whole and set full and drawing. "
        f"Rigging taut. Planking sound. No damage of any kind anywhere.\n\n"
        f"{FRAMING}\n\n{STYLE}\n\n"
        f"DO NOT: {'; '.join(hull['forbidden_inputs'])}."
    )


def nb(prompt: str, seed: int, title: str, ref: str | None = None) -> dict:
    inputs = {
        "prompt": prompt, "model": MODEL, "seed": seed, "aspect_ratio": "16:9",
        "resolution": "2K", "response_modalities": "IMAGE", "thinking_level": "HIGH",
        "system_prompt": SYSTEM_PROMPT,
    }
    if ref:
        inputs["images"] = [ref, 0]
    return {"inputs": inputs, "class_type": "GeminiNanoBanana2", "_meta": {"title": title}}


def build(hull_id: str) -> dict:
    hull = load_hull(hull_id)
    sid = f"{hull_id}__01-pristine__sails-open"
    return {
        "1": nb(pristine_prompt(hull), 1001, f"pristine · {hull_id}"),
        "2": nb(BG_PROMPT, 1004, f"no-bg · {hull_id}", ref="1"),
        "3": nb(SIDE_PROMPT, 1002, f"side · {hull_id}", ref="1"),
        "4": nb(STERN_PROMPT, 1003, f"stern · {hull_id}", ref="1"),
        "5": {
            "inputs": {"images.image0": ["2", 0], "images.image1": ["3", 0],
                       "images.image2": ["4", 0]},
            "class_type": "BatchImagesNode", "_meta": {"title": f"3 views · {hull_id}"},
        },
        "6": {"inputs": {**TRIPO_INPUTS, "image": ["5", 0]},
              "class_type": "TripoImageToModelNode", "_meta": {"title": f"Tripo · {hull_id}"}},
        "7": {"inputs": {"filename_prefix": f"{hull_id}/mesh/{sid}", "image": "",
                         "mesh": ["6", 2]},
              "class_type": "SaveGLB", "_meta": {"title": f"glb · {sid}"}},
        "8": {"inputs": {"filename_prefix": f"{hull_id}/plates-raw/{sid}", "images": ["1", 0]},
              "class_type": "SaveImage", "_meta": {"title": f"plate · {sid}"}},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hull", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--show-prompt", action="store_true")
    args = ap.parse_args()

    if args.show_prompt:
        print(pristine_prompt(load_hull(args.hull)))
        return 0

    wf = build(args.hull)
    text = json.dumps(wf, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}: {len(wf)} nodes, "
              f"{sum(1 for n in wf.values() if n['class_type'] == 'GeminiNanoBanana2')} "
              f"Nano Banana + 1 Tripo ({len(text):,} bytes)", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
