#!/usr/bin/env python3
"""
Build the pristine anatomy training set: 8 headings x N elevations per hull,
each with a caption generated FROM CANON.

WHY CAPTIONS COME FROM CANON
----------------------------
The whole point of this training run is to teach the model ship ANATOMY — that a
xebec has three lateen sails on angled yards, that a schooner's foremast is the
shorter one, that a brig carries a gaff spanker in addition to a square mainsail.
That only works if the caption vocabulary is exactly right and exactly consistent
across all 240 images. Hand-written captions drift, and caption drift is how a
LoRA learns fuzzy concepts.

So the rig phrase is DERIVED from rig_plan rather than written. If canon says the
mizzen carries a lateen, the caption says lateen — in every image, every time.

sdlab emits its own caption per entity, but it is the entire silhouette_cue
verbatim (~90 words of prose). Too long and too diffuse to train on; these are
~35 words and structured.

PRISTINE ONLY. No damage anywhere in the training set. Damage is what the trained
model is supposed to be able to infer.

Usage:
    python pipeline/build_training_set.py --out E:/AI/_staging/ship-training
    python pipeline/build_training_set.py --only xebec galleon --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CANON = Path(r"E:\AI\style-dataset-lab\projects\portlight-ships\canon\ships")
STORE = Path(r"E:\AI-Models\mesh-store\portlight-ships")
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"

TRIGGER = "plsvessel"

HEADINGS = {
    "front":       "bow-on view from directly ahead",
    "front_left":  "three-quarter bow view from the port side",
    "left":        "port broadside view",
    "back_left":   "three-quarter quarter view from the port side",
    "back":        "stern-on view from directly astern",
    "back_right":  "three-quarter quarter view from the starboard side",
    "right":       "starboard broadside view",
    "front_right": "three-quarter bow view from the starboard side",
}

# Three elevations. Low reads almost like a sea-level silhouette; high is close to
# the 2.5D game camera. Teaching all three is what stops the model from only
# knowing the ship from one height.
ELEVATIONS = {"low": 15.0, "mid": 30.0, "high": 50.0}
ELEV_PHRASE = {
    "low": "seen from near water level",
    "mid": "seen from a slightly elevated angle",
    "high": "seen from an elevated three-quarter angle",
}

SQUARE = {"course", "topsail", "topgallant", "spritsail"}


def load_hull(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm)


def rig_phrase(hull: dict) -> str:
    """Describe the rig from rig_plan — derived, never written.

    A mast is SQUARE-RIGGED when it carries a square COURSE, the lowest driving
    sail. It is NOT square-rigged merely for carrying a square topsail above a
    gaff mainsail — that is a gaff-rigged mast with a square topsail.

    An earlier version of this function got that wrong and classed any mast with
    any square sail as square-rigged. The result: the brigantine's caption came
    out byte-identical to the brig's, teaching the model that the two vessels are
    the same thing — the precise confusion the brig was added to the fleet to
    prevent. Verified against all ten hulls before any image was captioned.
    """
    plan = hull["visual"]["rig_plan"]
    by_mast: dict[str, set[str]] = {}
    for sail in plan["sails"]:
        by_mast.setdefault(sail["mast"], set()).add(sail["sail_type"])

    def names(ids: list[str]) -> str:
        if len(ids) == 1:
            return ids[0]
        return ", ".join(ids[:-1]) + " and " + ids[-1]

    square, lateen, gaff, spanker, topsail_over_gaff = [], [], [], [], []
    for m in plan["masts"]:
        mid = m["id"]
        kinds = by_mast.get(mid, set())
        has_course = "course" in kinds
        has_gaff = "gaff" in kinds
        has_upper = bool(kinds & {"topsail", "topgallant"})

        if has_course:
            square.append(mid)
            if has_gaff:
                spanker.append(mid)          # square course AND a gaff aft of it
        elif has_gaff:
            gaff.append(mid)                 # gaff is the principal sail here
            if has_upper:
                topsail_over_gaff.append(mid)
        elif "lateen" in kinds:
            lateen.append(mid)

    single = len(plan["masts"]) == 1
    parts = []
    if square:
        parts.append(f"square-rigged {names(square)}")
    if gaff:
        parts.append("single gaff-rigged mast" if single else f"gaff-rigged {names(gaff)}")
    if lateen:
        parts.append(f"lateen-rigged {names(lateen)}")
    if spanker:
        parts.append(f"with a gaff spanker on the {names(spanker)}")
    if topsail_over_gaff:
        parts.append(f"square topsail above the gaff on the {names(topsail_over_gaff)}")
    return ", ".join(parts)


def caption(hull: dict, heading: str, elev: str) -> str:
    plan = hull["visual"]["rig_plan"]
    n_masts = len(plan["masts"])
    n_sails = len(plan["sails"])
    sig = hull.get("signature_features", [])[:2]
    bits = [
        TRIGGER,
        f"a {hull['ship_class']}",
        f"{n_masts}-masted sailing ship" if n_masts > 1 else "single-masted sailing ship",
        rig_phrase(hull),
        f"{n_sails} sails set",
        *[s.split(" — ")[0].strip() for s in sig],
        "pristine undamaged condition",
        HEADINGS[heading],
        ELEV_PHRASE[elev],
        "game asset render on a plain background",
    ]
    return ", ".join(b for b in bits if b)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=r"E:\AI\_staging\ship-training")
    ap.add_argument("--size", type=int, default=768)
    ap.add_argument("--frame", type=float, default=13.0)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    hulls = sorted(CANON.glob("*.md"))
    if args.only:
        hulls = [h for h in hulls if h.stem in set(args.only)]

    made, missing = 0, []
    for hp in hulls:
        hull = load_hull(hp)
        hid = hull["id"]
        glb = STORE / f"{hid}-normalised" / f"{hid}__01-pristine__sails-open.glb"
        if not glb.exists():
            legacy = STORE / "galleon-normalised" / "galleon__01-pristine__sails-open.glb"
            if hid == "galleon" and legacy.exists():
                glb = legacy
            else:
                missing.append(hid)
                continue

        for elev_name, elev_deg in ELEVATIONS.items():
            dest = out / f"_render_{hid}_{elev_name}"
            if not args.dry_run:
                dest.mkdir(parents=True, exist_ok=True)
                cmd = [
                    BLENDER, "-b", "--python",
                    str(REPO / "pipeline" / "stage3_render_pack.py"), "--",
                    "--glb", str(glb), "--out", str(dest), "--subject", hid,
                    "--size", str(args.size), "--frame", str(args.frame),
                    "--elev", str(elev_deg), "--passes", "albedo",
                ]
                p = subprocess.run(cmd, capture_output=True, text=True)
                if "STAGE3 DONE" not in p.stdout:
                    print(f"  FAIL {hid} @{elev_name}: "
                          + "; ".join(l for l in (p.stdout + p.stderr).splitlines()
                                      if "ERROR" in l)[:200])
                    continue

            out.mkdir(parents=True, exist_ok=True)
            for heading in HEADINGS:
                stem = f"{hid}__{elev_name}__{heading}"
                cap = caption(hull, heading, elev_name)
                if args.dry_run:
                    if heading == "left" and elev_name == "mid":
                        print(f"\n{stem}\n  {cap}")
                else:
                    src = dest / "albedo" / f"{heading}.png"
                    if src.exists():
                        (out / f"{stem}.png").write_bytes(src.read_bytes())
                        (out / f"{stem}.txt").write_text(cap, encoding="utf-8")
                        made += 1

    if missing:
        print(f"\nno pristine mesh yet: {', '.join(missing)}")
    print(f"\n{made} image/caption pairs written to {out}"
          if not args.dry_run else "\n(dry run — no files written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
