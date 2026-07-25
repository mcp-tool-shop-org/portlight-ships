#!/usr/bin/env python3
"""
Build a reference-chained ship damage-ladder ComfyUI workflow (save/graph format).

WHY THIS EXISTS
---------------
The original per-state workflows on Comfy Cloud had three defects:

  1. Every state was an independent text->image call, so style, camera, heading
     and palette were re-rolled from scratch each time. Here each state is a
     Nano Banana EDIT carrying two references: the pristine master (identity +
     style anchor) and the previous state (damage continuity).
  2. SaveImage was wired to the pre-background-removal node, so every saved
     plate had a baked-in gray/white background. Here the cutout is saved.
  3. State 05 was generated free-standing and came back as a beached wreck on a
     ground plane. Here it inherits the master's framing and explicitly forbids
     water, ground and debris.

Both the raw plate AND the cutout are saved. The generation is the expensive
step; the cutout is cheap to redo. Never make a failed cutout cost a re-render.

NAMING CONTRACT (load-bearing — many hulls go through this)
-----------------------------------------------------------
Subject id      <hull>__<state>__<rig>      galleon__03-moderate__sails-open
  - kebab-case within a field, double underscore BETWEEN fields, so a hull id
    containing a hyphen still parses with a plain split("__")
  - state carries a numeric prefix so lexical sort == damage order
  - rig is always present (05 uses `sails-none`) so field count is fixed

Comfy output    <hull>/<stage>/<subject-id>
  galleon/plates-raw/galleon__03-moderate__sails-open   (with background)
  galleon/plates/galleon__03-moderate__sails-open       (RGBA cutout)
  ComfyUI appends its own _00001_ counter to every prefix.

Pack layout     packages/<pack>/assets/<subject-id>/<channel>/<heading>.png
  This is EXACTLY the existing sprite-foundry-packs shape, with the hull/state/
  rig triple occupying the `subject` slot. Tooling that globs
  `assets/*/albedo/*.png` keeps working unchanged.

Usage:
    python build_ladder_workflow.py --hull galleon --api --out wf.json
    python build_ladder_workflow.py --hull galleon --manifest manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

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

# Brand binding, from mcp-tool-shop-org/brand logos/portlight/readme.png.
# Set to False to let a hull keep its own colours.
BRAND_LOCK = True
BRAND_PALETTE = (
    " Palette: deep navy sea-world tones, dark seasoned timber, aged off-white canvas, "
    "warm gold lantern accents."
)

# CHROMA KEY, not grey. Measured on a one-call probe (see docs/adding-a-hull.md):
#
#   grey   background and pale canvas share a colour neighbourhood. Tolerance 8
#          worked; 26 punched holes straight through the sails. A knife edge.
#   green  shares nothing with timber, canvas or gold. Tolerance 26..90 returned a
#          byte-identical bbox — a 3.5x window instead of a knife edge — with the
#          sails fully intact at the top of it.
#
# The cost is green spill on rigging edges and through the ratlines, which
# cutout_plates.py removes automatically (it detects a green plate and despills).
# That is why the prompt forbids green ANYWHERE on the ship: despill would
# desaturate a genuinely green sail.
#
# NOTE: the galleon's shipped plates predate this and are on grey. They are not
# being regenerated — stage 3 takes alpha straight from Blender, so the sprite
# pack is unaffected either way. This is for hull #2 onward.
FRAMING = (
    "Rendered at a 3/4 FRONT angle with the BOW POINTING LEFT, ship centred and fully "
    "inside the frame with clear margin on all four sides, clean even lighting, no "
    "water, no ground plane, no cast shadow. THE BACKGROUND IS FLAT PURE CHROMA-KEY "
    "GREEN, pure saturated RGB(0,255,0), completely uniform with no gradient, no "
    "vignette and no shading. NOTHING else in the image is green: the hull, sails, "
    "rigging, flags and every other part of the ship must contain no green whatsoever."
)

STYLE = (
    "Stylised 2.5D game-asset look: crisp readable silhouette, clean line work, "
    "restrained painterly shading."
)

EDIT_CONTRACT = (
    "Reference image 1 is the PRISTINE MASTER for this ship. Reference image 2 is the "
    "immediately previous state.\n"
    "Produce the SAME SHIP in the SAME ART STYLE. Match the master exactly for hull "
    "design, mast count and placement, stern gallery, figurehead, palette, line quality, "
    "shading treatment, lighting, background colour, camera angle (3/4 front, BOW "
    "POINTING LEFT), ship scale and framing. Do NOT restyle. Do NOT render "
    "photorealistically. Do NOT convert to pixel art. Do NOT mirror the ship. Do NOT crop "
    "the ship. Do NOT add water, ground or debris.\n"
    "Keep the palette identical to the master: dark seasoned timber, aged off-white "
    "canvas, warm gold lantern accents. Do NOT recolour the sails.\n"
    "Change ONLY the condition, continuing from the previous state:\n"
)

BG_PROMPT = (
    "Remove the background completely, leaving only the ship on full transparency. "
    "Do not alter, restyle, recolour, crop, rotate or move the ship in any way."
)

# --- hull definitions ------------------------------------------------------
# Loaded from hulls/<hull>/hull.json so adding a ship is a CONFIG change, not a
# code change. Everything below this point — the damage ladder, framing, palette,
# style, the STOWED clause — is shared by every hull deliberately: that shared
# spine is what makes different ships look like they belong to the same game.
_HULL_DIR = Path(__file__).resolve().parent.parent / "hulls"


def _load_hulls() -> dict[str, str]:
    hulls: dict[str, str] = {}
    if _HULL_DIR.is_dir():
        for hull_json in sorted(_HULL_DIR.glob("*/hull.json")):
            spec = json.loads(hull_json.read_text(encoding="utf-8"))
            hulls[spec["hull_id"]] = spec["description"]
    return hulls


HULLS = _load_hulls()

ANCHOR_STATE = "01-pristine"
ANCHOR_RIG = "sails-open"

# The sails-closed clause. EARNED THE HARD WAY — do not "tidy" this back into
# nautical terminology. "Sails FURLED and stowed tight to the yards" is the
# correct term and it FAILED: the model read *furled* as *gathered* and returned
# full canvas on every yard across all three closed states, which then went on to
# waste three Tripo meshes. Describing the visual RESULT works. Note the explicit
# negative ("NOT a ship under sail") — the positive description alone was not
# enough on its own.
STOWED = (
    "ALL SAILS ARE STOWED AWAY. Every single sail is rolled up into a tight thin bundle "
    "lashed along the TOP of its yard-arm. NO canvas hangs below any yard. NO sail "
    "surface is visible anywhere on the ship. The sky and the rigging show clearly "
    "through the large empty gaps between the masts and yards where the sails used to "
    "hang. The ship's silhouette is reduced to bare masts, bare yards and rigging only. "
    "This is a ship at anchor with all canvas put away, NOT a ship under sail. "
)

# (state, rig, prev_or_None, damage delta). prev None => master is the previous state.
LADDER = [
    (
        "01-pristine", "sails-closed", None,
        STOWED
        + "The hull and everything else is identical to the master and completely "
        "undamaged.",
    ),
    (
        "02-light", "sails-open", None,
        "LIGHT damage. A few small tears and canvas patches in the sails, light scuffing "
        "and salt staining along the hull planking, one or two loose ropes. All masts "
        "intact and upright. Sails still open and drawing.",
    ),
    (
        "02-light", "sails-closed", ("02-light", "sails-open"),
        STOWED
        + "The hull keeps EXACTLY the light damage shown in reference image 2 — the same "
        "scuffing and salt staining along the planking, the same loose ropes.",
    ),
    (
        "03-moderate", "sails-open", ("02-light", "sails-open"),
        "MODERATE damage. Noticeably torn sails with several holes, scorch marks and "
        "splintered planking around the gun ports, one broken spar, rigging hanging "
        "slack. All masts still standing. Sails open.",
    ),
    (
        "03-moderate", "sails-closed", ("03-moderate", "sails-open"),
        STOWED.replace("ALL SAILS ARE", "ALL SURVIVING SAILS ARE")
        + "There is one broken spar and slack hanging rigging. The hull keeps EXACTLY the "
        "moderate damage shown in reference image 2 — the same scorch marks and "
        "splintered planking around the gun ports.",
    ),
    (
        "04-heavy", "sails-open", ("03-moderate", "sails-open"),
        "HEAVY damage. Sails shredded to ragged strips, one mast snapped and leaning, the "
        "hull breached in two places with visible splintering and blackened scorching, "
        "rigging torn and trailing, stern gallery partly shattered. Still afloat and "
        "clearly recognisable as the same vessel. Remaining sails open.",
    ),
    (
        "05-destroyed", "sails-none", ("04-heavy", "sails-open"),
        "DESTROYED. A burnt-out derelict hulk. Masts snapped and fallen, only stumps and "
        "one leaning spar remain, sails gone apart from a few blackened rags, hull holed "
        "through with ribs exposed, timbers charred and grey. Still recognisably the same "
        "vessel, at the same scale and camera angle. The wreck alone on the flat neutral "
        "gray background — no water, no ground plane, no debris scattered beneath it.",
    ),
]

COL_W = 380
ROW_H = 460


def subject_id(hull: str, state: str, rig: str) -> str:
    return f"{hull}__{state}__{rig}"


def anchor_prompt(hull: str) -> str:
    return (
        f"3D game asset render of {HULLS[hull]}. "
        "Condition: PRISTINE and immaculate — sails FULLY UNFURLED and OPEN, billowing on "
        "every mast, taut rigging, polished undamaged timber hull, no damage anywhere. "
        + FRAMING + " " + STYLE + (BRAND_PALETTE if BRAND_LOCK else "")
    )


class Graph:
    """Minimal ComfyUI save-format graph builder."""

    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.links: list[list] = []
        self._node_id = 0
        self._link_id = 0
        self._order = 0

    def _nid(self) -> int:
        self._node_id += 1
        return self._node_id

    def _order_next(self) -> int:
        o = self._order
        self._order += 1
        return o

    def connect(self, src: dict, src_slot: int, dst: dict, dst_slot: int, type_: str) -> None:
        self._link_id += 1
        lid = self._link_id
        self.links.append([lid, src["id"], src_slot, dst["id"], dst_slot, type_])
        src["outputs"][src_slot]["links"].append(lid)
        dst["inputs"][dst_slot]["link"] = lid

    def nano_banana(self, prompt: str, seed: int, title: str, pos: tuple[int, int]) -> dict:
        node = {
            "id": self._nid(),
            "type": "GeminiNanoBanana2",
            "pos": list(pos),
            "size": [300, 350],
            "flags": {},
            "order": self._order_next(),
            "mode": 0,
            "title": title,
            "inputs": [
                {"localized_name": "images", "name": "images", "shape": 7, "type": "IMAGE", "link": None},
                {"localized_name": "files", "name": "files", "shape": 7, "type": "GEMINI_INPUT_FILES", "link": None},
                {"localized_name": "prompt", "name": "prompt", "type": "STRING", "widget": {"name": "prompt"}, "link": None},
                {"localized_name": "model", "name": "model", "type": "COMBO", "widget": {"name": "model"}, "link": None},
                {"localized_name": "seed", "name": "seed", "type": "INT", "widget": {"name": "seed"}, "link": None},
                {"localized_name": "aspect_ratio", "name": "aspect_ratio", "type": "COMBO", "widget": {"name": "aspect_ratio"}, "link": None},
                {"localized_name": "resolution", "name": "resolution", "type": "COMBO", "widget": {"name": "resolution"}, "link": None},
                {"localized_name": "response_modalities", "name": "response_modalities", "type": "COMBO", "widget": {"name": "response_modalities"}, "link": None},
                {"localized_name": "thinking_level", "name": "thinking_level", "type": "COMBO", "widget": {"name": "thinking_level"}, "link": None},
                {"localized_name": "system_prompt", "name": "system_prompt", "shape": 7, "type": "STRING", "widget": {"name": "system_prompt"}, "link": None},
            ],
            "outputs": [
                {"localized_name": "IMAGE", "name": "IMAGE", "type": "IMAGE", "links": []},
                {"localized_name": "STRING", "name": "STRING", "type": "STRING", "links": []},
                {"localized_name": "thought_image", "name": "thought_image", "type": "IMAGE", "links": []},
            ],
            "properties": {"Node name for S&R": "GeminiNanoBanana2"},
            "widgets_values": [
                prompt, MODEL, seed, "fixed", "auto", "1K", "IMAGE", "MINIMAL", SYSTEM_PROMPT,
            ],
            "color": "#432",
            "bgcolor": "#653",
        }
        self.nodes.append(node)
        return node

    def batch_images(self, title: str, pos: tuple[int, int]) -> dict:
        node = {
            "id": self._nid(),
            "type": "BatchImagesNode",
            "pos": list(pos),
            "size": [280, 126],
            "flags": {},
            "order": self._order_next(),
            "mode": 0,
            "title": title,
            "inputs": [
                {"localized_name": "images.image0", "name": "images.image0", "type": "IMAGE", "link": None},
                {"label": "image1", "localized_name": "images.image1", "name": "images.image1", "shape": 7, "type": "IMAGE", "link": None},
                {"label": "image2", "localized_name": "images.image2", "name": "images.image2", "shape": 7, "type": "IMAGE", "link": None},
                {"label": "image3", "localized_name": "images.image3", "name": "images.image3", "shape": 7, "type": "IMAGE", "link": None},
                {"name": "images", "type": "COMFY_AUTOGROW_V3", "link": None},
            ],
            "outputs": [{"localized_name": "IMAGE", "name": "IMAGE", "type": "IMAGE", "links": []}],
            "properties": {"Node name for S&R": "BatchImagesNode"},
            "widgets_values": [],
        }
        self.nodes.append(node)
        return node

    def save_image(self, prefix: str, title: str, pos: tuple[int, int]) -> dict:
        node = {
            "id": self._nid(),
            "type": "SaveImage",
            "pos": list(pos),
            "size": [280, 300],
            "flags": {},
            "order": self._order_next(),
            "mode": 0,
            "title": title,
            "inputs": [
                {"localized_name": "images", "name": "images", "type": "IMAGE", "link": None},
                {"localized_name": "filename_prefix", "name": "filename_prefix", "type": "STRING", "widget": {"name": "filename_prefix"}, "link": None},
            ],
            "outputs": [{"localized_name": "images", "name": "images", "type": "IMAGE", "links": []}],
            "properties": {},
            "widgets_values": [prefix],
        }
        self.nodes.append(node)
        return node

    def to_json(self) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "revision": 0,
            "last_node_id": self._node_id,
            "last_link_id": self._link_id,
            "nodes": self.nodes,
            "links": self.links,
            "groups": [],
            "config": {},
            "extra": {"ds": {"scale": 0.45, "offset": [120, 120]}},
            "version": 0.4,
        }


def build(hull: str) -> tuple[dict, list[dict]]:
    """Return (save-format graph, manifest rows)."""
    g = Graph()
    plates: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    seed = 1001

    anchor_key = (ANCHOR_STATE, ANCHOR_RIG)
    anchor = g.nano_banana(
        anchor_prompt(hull), seed,
        f"MASTER · {subject_id(hull, *anchor_key)}", (0, 0),
    )
    plates[anchor_key] = anchor
    order.append(anchor_key)
    seed += 1

    for row, (state, rig, prev, delta) in enumerate(LADDER, start=1):
        y = row * ROW_H
        key = (state, rig)
        sid = subject_id(hull, state, rig)

        if prev is None:
            ref_src = anchor
        else:
            batch = g.batch_images(f"refs · {sid}", (COL_W, y))
            g.connect(anchor, 0, batch, 0, "IMAGE")
            g.connect(plates[prev], 0, batch, 1, "IMAGE")
            ref_src = batch

        node = g.nano_banana(EDIT_CONTRACT + delta, seed, sid, (COL_W * 2, y))
        g.connect(ref_src, 0, node, 0, "IMAGE")
        plates[key] = node
        order.append(key)
        seed += 1

    manifest: list[dict] = []
    bg_seed = 2001
    for row, key in enumerate(order):
        y = row * ROW_H
        state, rig = key
        sid = subject_id(hull, state, rig)

        # Raw plate (background intact) — the expensive artifact, always kept.
        raw_save = g.save_image(
            f"{hull}/plates-raw/{sid}", f"raw · {sid}", (COL_W * 3, y)
        )
        g.connect(plates[key], 0, raw_save, 0, "IMAGE")

        # Cutout -> RGBA plate, the deliverable.
        bg = g.nano_banana(BG_PROMPT, bg_seed, f"cutout · {sid}", (COL_W * 4, y))
        g.connect(plates[key], 0, bg, 0, "IMAGE")
        rgba_save = g.save_image(
            f"{hull}/plates/{sid}", f"plate · {sid}", (COL_W * 5, y)
        )
        g.connect(bg, 0, rgba_save, 0, "IMAGE")
        bg_seed += 1

        manifest.append({
            "subject_id": sid,
            "hull": hull,
            "state": state,
            "rig": rig,
            "is_master": key == anchor_key,
            "plate_raw": f"{hull}/plates-raw/{sid}",
            "plate_rgba": f"{hull}/plates/{sid}",
            "pack_path": f"assets/{sid}",
        })

    return g.to_json(), manifest


def to_api_format(wf: dict) -> dict:
    """Convert save-format graph to ComfyUI API format (far more compact)."""
    NB_WIDGETS = [
        "prompt", "model", "seed", None,  # index 3 is control_after_generate
        "aspect_ratio", "resolution", "response_modalities", "thinking_level",
        "system_prompt",
    ]
    link_src = {l[0]: (l[1], l[2]) for l in wf["links"]}
    api: dict[str, dict] = {}

    for n in wf["nodes"]:
        inputs: dict = {}
        if n["type"] == "GeminiNanoBanana2":
            for i, key in enumerate(NB_WIDGETS):
                if key is not None:
                    inputs[key] = n["widgets_values"][i]
        elif n["type"] == "SaveImage":
            inputs["filename_prefix"] = n["widgets_values"][0]

        for inp in n["inputs"]:
            lid = inp.get("link")
            if lid is None:
                continue
            src_id, src_slot = link_src[lid]
            inputs[inp["name"]] = [str(src_id), src_slot]

        api[str(n["id"])] = {
            "inputs": inputs,
            "class_type": n["type"],
            "_meta": {"title": n.get("title", n["type"])},
        }
    return api


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hull", default="galleon", choices=sorted(HULLS))
    ap.add_argument("--out", default=None, help="write workflow JSON here")
    ap.add_argument("--api", action="store_true", help="emit compact API format")
    ap.add_argument("--manifest", default=None, help="write the subject manifest here")
    args = ap.parse_args()

    wf, manifest = build(args.hull)
    out_obj = to_api_format(wf) if args.api else wf
    text = json.dumps(out_obj, indent=2, ensure_ascii=False)

    if args.manifest:
        with open(args.manifest, "w", encoding="utf-8") as fh:
            json.dump({"hull": args.hull, "subjects": manifest}, fh, indent=2, ensure_ascii=False)
        print(f"wrote {args.manifest}: {len(manifest)} subjects", file=sys.stderr)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        types = [n["class_type"] for n in out_obj.values()] if args.api else [n["type"] for n in wf["nodes"]]
        print(
            f"wrote {args.out}: {len(types)} nodes, "
            f"{types.count('GeminiNanoBanana2')} Nano Banana calls, "
            f"{types.count('SaveImage')} saves ({len(text):,} bytes)",
            file=sys.stderr,
        )
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
