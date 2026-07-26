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

# CAMERA IS ITS OWN EMPHATIC BLOCK, and it is placed LAST so it is the final word
# on composition.
#
# The first version said "Rendered at a 3/4 FRONT angle with the BOW POINTING
# LEFT" and the xebec came back as a near-pure broadside. Two causes:
#   1. "3/4 front angle" is jargon the model does not reliably ground.
#   2. More importantly, the hull's own silhouette_cue is written in PROFILE
#      language — "low, long and sharp", "slung between two points", "reads as a
#      low dark sliver". Canon was describing the broadside, and a one-line
#      camera note lost the argument to a paragraph of profile description.
#
# A profile plate is not merely off-spec: the mesh stage feeds Tripo
# [front, side, stern], so a profile "front" makes two of three views
# near-duplicates and costs real depth information. The xebec mesh came out with
# a beam of 1.95 against a length of 10.
#
# So: describe the camera POSITION concretely rather than naming the angle, state
# what must be simultaneously visible, and add the explicit negative. Same shape
# as the STOWED and mast-break fixes — describe the result, then forbid the
# failure.
# Takes has_bowsprit because three hulls in the fleet do not have one. The junk,
# galley and cog all declare `bowsprit: false`, and until this was parameterised the
# camera block asserted "the bowsprit projects toward the LOWER LEFT" at every hull —
# a false instruction sitting in the single most emphatic, last-placed section of the
# prompt, on hulls whose canon explicitly forbids a bowsprit. Left alone it would have
# fought the DO NOT block and probably grown one.
def framing(has_bowsprit: bool) -> str:
    bow_clause = (
        "The bowsprit projects toward the LOWER LEFT of the frame and the stern is the "
        "furthest part of the ship from the camera.\n"
        if has_bowsprit else
        "NOTHING PROJECTS FORWARD OF THE BOW — this vessel has no bowsprit and no spar of any "
        "kind out front. The stern is the furthest part of the ship from the camera.\n"
    )
    return (
    "CAMERA — this is the most important compositional instruction and it overrides any "
    "impression of a side view given by the shape description above.\n"
    "Place the camera OFF THE VESSEL'S PORT BOW: forward of amidships, out to the left, and "
    "raised to about twenty degrees above deck level looking slightly down.\n"
    "You must see the PORT SIDE OF THE HULL and the FRONT OF THE BOW AT THE SAME TIME. The "
    "deck must be visible, receding away from the viewer toward the stern. "
    + bow_clause +
    "THIS IS A THREE-QUARTER VIEW. It is NOT a flat side-on profile, NOT a broadside "
    "elevation, and NOT an orthographic side view. If the masts appear as a flat row on a "
    "single plane and no deck is visible, the camera is wrong.\n"
    "The bow points LEFT. The vessel is centred and fully inside the frame with clear margin "
    "on all four sides. Clean even lighting, no water, no ground plane, no cast shadow.\n"
    "THE BACKGROUND IS FLAT PURE CHROMA-KEY GREEN, pure saturated RGB(0,255,0), completely "
    "uniform with no gradient or shading."
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
        # reference_period, NOT the hull's tradition. Canon dropped `era` for
        # `tradition` on 2026-07-25 because the fleet spanned two real centuries and
        # the world is not tied to a date — but the image model knows what "a 1600s
        # sailing vessel" looks like and has never heard of a cold-coast one. So the
        # prompt speaks the model's language and canon speaks the world's. Feeding
        # the tradition slug here would be strictly worse than feeding nothing.
        f"3D game asset render of a {hull['ship_class']}, "
        f"a {v['reference_period']} sailing vessel.\n\n"
        f"SHAPE: {v['silhouette_cue']}\n\n"
        f"STRUCTURE — this vessel has exactly {len(rig['masts'])} mast(s): {masts}. "
        f"It carries exactly {len(rig['sails'])} sails: {sails}. Draw every one of them and "
        f"draw no others.\n\n"
        f"MUST SHOW: {'; '.join(hull['signature_features'])}.\n\n"
        f"CONDITION: PRISTINE and immaculate. Every sail whole and set full and drawing. "
        f"Rigging taut. Planking sound. No damage of any kind anywhere.\n\n"
        f"{STYLE}\n\n"
        f"DO NOT: {'; '.join(hull['forbidden_inputs'])}; a flat side-on profile or broadside "
        f"elevation view.\n\n"
        # COLOUR sits immediately before CAMERA, not five paragraphs above it.
        # In the xebec V2 run the palette line was high in the prompt, above a much
        # longer camera block, and the vessel came back with its canon-pinned red
        # sheer stripe (#b03028) largely gone to plain timber. Same positional
        # effect that made the camera clause lose to the shape description: what
        # sits last carries. Colour is now the last thing before the camera, and
        # hull_markings — which were not in the prompt at all — are named here.
        f"COLOUR AND MARKINGS — use this exact palette and no other: "
        f"{' '.join(v['palette'])}. The vessel is {v['material_dominant']}. "
        f"These markings must be present and clearly visible: "
        f"{'; '.join(v.get('hull_markings', []))}.\n\n"
        f"{framing(rig.get('bowsprit', True))}"
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


def build(hull_id: str, plate_only: bool = False, from_plate: str | None = None) -> dict:
    """Assemble the workflow for one hull.

    THREE MODES, and the third is the one that matters in practice:

      plate_only        generate the plate and stop. The plate is the gate.
      (default)         generate the plate AND mesh it, in one job.
      from_plate=<file> mesh an ALREADY-APPROVED plate that is on the cloud.

    `from_plate` exists because the default mode quietly wastes money and loses
    work once a plate has been reviewed. Re-running it regenerates node 1 from
    scratch — a fresh paid call producing a DIFFERENT plate from the one that was
    approved. For the junk that would have silently discarded a bow-fix edit pass
    that had already been paid for and signed off. Since every hull goes
    plate -> review -> mesh, `from_plate` is the normal path to the mesh stage and
    the default is really only for a first run where nobody has looked yet.

    Register the plate as an input with the comfy-cloud `use_previous_output` tool,
    which returns the filename to pass here.
    """
    hull = load_hull(hull_id)
    sid = f"{hull_id}__01-pristine__sails-open"

    if plate_only:
        # The plate is the gate. Prove the camera before paying for a mesh.
        return {
            "1": nb(pristine_prompt(hull), 1001, f"pristine · {hull_id}"),
            "8": {"inputs": {"filename_prefix": f"{hull_id}/plates-raw/{sid}",
                             "images": ["1", 0]},
                  "class_type": "SaveImage", "_meta": {"title": f"plate · {sid}"}},
        }

    if from_plate:
        head = {"0": {"inputs": {"image": from_plate}, "class_type": "LoadImage",
                      "_meta": {"title": f"approved plate · {hull_id}"}}}
        src, tail = "0", {}          # no SaveImage — the plate is already saved
    else:
        head = {"1": nb(pristine_prompt(hull), 1001, f"pristine · {hull_id}")}
        src = "1"
        tail = {"8": {"inputs": {"filename_prefix": f"{hull_id}/plates-raw/{sid}",
                                 "images": ["1", 0]},
                      "class_type": "SaveImage", "_meta": {"title": f"plate · {sid}"}}}

    return {
        **head,
        "2": nb(BG_PROMPT, 1004, f"no-bg · {hull_id}", ref=src),
        "3": nb(SIDE_PROMPT, 1002, f"side · {hull_id}", ref=src),
        "4": nb(STERN_PROMPT, 1003, f"stern · {hull_id}", ref=src),
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
        **tail,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hull", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--show-prompt", action="store_true")
    ap.add_argument("--plate-only", action="store_true")
    ap.add_argument("--from-plate", default=None,
                    help="Cloud filename of an already-approved plate (from the "
                         "use_previous_output tool). Meshes that exact plate instead "
                         "of paying to regenerate a different one.")
    args = ap.parse_args()

    if args.show_prompt:
        print(pristine_prompt(load_hull(args.hull)))
        return 0

    wf = build(args.hull, plate_only=args.plate_only, from_plate=args.from_plate)
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
