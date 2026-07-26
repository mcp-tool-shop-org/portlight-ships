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

    square, lateen, gaff, spanker, topsail_over_gaff, lug = [], [], [], [], [], []
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
        elif "lugsail" in kinds:
            # The junk's battened lugsail. Added when the far-trade tradition got its
            # first hull. Note this branch is not decoration: before it existed, a
            # mast carrying ONLY a lugsail matched no branch, landed in no list, and
            # was silently dropped from the caption — a three-masted junk would have
            # been captioned as a three-masted ship with no rig described at all.
            lug.append(mid)

    single = len(plan["masts"]) == 1
    parts = []
    if square:
        parts.append("single square-rigged mast" if single else f"square-rigged {names(square)}")
    if gaff:
        parts.append("single gaff-rigged mast" if single else f"gaff-rigged {names(gaff)}")
    if lateen:
        parts.append(f"lateen-rigged {names(lateen)}")
    if lug:
        parts.append(f"battened lugsails on the {names(lug)}")
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
        f"{n_sails} sail{'s' if n_sails != 1 else ''} set",
        *[s.split(" — ")[0].strip() for s in sig],
        "pristine undamaged condition",
        HEADINGS[heading],
        ELEV_PHRASE[elev],
        "game asset render on a plain background",
    ]
    return ", ".join(b for b in bits if b)


def check_no_clipping(out: Path, frame: float) -> int:
    """Fail the build if any render touches a frame edge.

    A clipped ship is a ship with a piece missing, and the caption still claims
    the piece is there — so a clipped set teaches the model that a barque
    sometimes has two masts. It is the single most corrupting defect this stage
    can produce and it is completely silent: the images look fine in a contact
    sheet, because a cropped bowsprit just reads as a shorter bowsprit.

    This exists because --frame is fleet-dependent and WILL go stale. When the
    junk was added she became the fleet's worst case and pushed the requirement
    from 12.04 to 12.78, so the value derived for ten hulls would have clipped
    her. Rather than rely on remembering to re-derive it, verify the output and
    print the value that would have worked.
    """
    import numpy as np
    from PIL import Image

    clipped, worst = [], 0.0
    for p in sorted(out.glob("*.png")):
        a = np.asarray(Image.open(p).convert("RGBA"))[:, :, 3] > 16
        if not a.any():
            clipped.append(f"{p.name} (EMPTY)")
            continue
        ys, xs = np.where(a)
        H, W = a.shape
        if xs.min() <= 1 or ys.min() <= 1 or xs.max() >= W - 2 or ys.max() >= H - 2:
            clipped.append(p.name)
        worst = max(worst, max(abs(xs.min() - W / 2), abs(xs.max() - W / 2),
                               abs(ys.min() - H / 2), abs(ys.max() - H / 2)) / (W / 2))

    if clipped:
        print(f"\nFAIL: {len(clipped)} of {len(list(out.glob('*.png')))} renders touch a "
              f"frame edge at --frame {frame}.")
        for n in clipped[:8]:
            print(f"  {n}")
        if len(clipped) > 8:
            print(f"  ... and {len(clipped) - 8} more")
        print(f"\nRe-run with --frame {frame * worst / 0.96:.1f} (or higher). "
              f"THIS SET IS NOT SAFE TO TRAIN ON.")
        return 1

    print(f"no clipping — worst subject reaches {worst:.3f} of the half-frame "
          f"at --frame {frame}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=r"E:\AI\_staging\ship-training")
    ap.add_argument("--size", type=int, default=768)
    # THIS VALUE IS FLEET-DEPENDENT. It is the smallest frame that fits the TALLEST
    # hull in the fleet at the highest elevation, so it moves whenever a hull is
    # added. Do not treat it as a constant.
    #
    # Derived by projecting every hull's vertices through the same orthographic
    # camera math this pipeline uses, across all 8 headings x 3 elevations, and
    # taking the worst case. History:
    #
    #   10 hulls  worst = galleon @50deg, half-reach 5.777  -> min frame 12.04
    #   14 hulls  worst = junk    @50deg, half-reach 6.134  -> min frame 12.78
    #
    # 12.9 is the 14-hull figure with margin. The junk is the binding constraint
    # because her masts are tall relative to her hull (height 7.88 against a
    # normalised length of 10) — she is the fleet's worst case, not the galleon.
    #
    # Two earlier attempts got this wrong and both are worth not repeating. 13.0
    # was safe but ~7% wasteful. 10.5 was measured from how much of the frame a
    # subject's bounding box SPANNED (0.770) while assuming the subject was
    # centred — it is not, since a hull's mass sits low and its masts are thin, so
    # the projected silhouette is not centred on the bounding-box pivot. That one
    # clipped 15 of 240 renders at the bottom edge. Span is the wrong measure;
    # reach from the frame centre is the right one.
    #
    # Vertically re-centring was also tested: the best constant z-offset (-0.3)
    # only lowers the 14-hull requirement to 12.38, so the existing
    # bounding-box-mid-height pivot is already close to optimal and not worth a
    # parameter.
    #
    # You do not have to remember any of this — check_no_clipping() below verifies
    # the result and tells you the correct value if it is wrong.
    #
    # Do NOT propagate this to stage3's own default — the sprite pack needs the
    # looser frame so damage states with debris keep consistent framing.
    ap.add_argument("--frame", type=float, default=12.9)
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
                    # Measured, not chosen by eye: the inherited rig was tuned to lift
                    # black armour and washed ships out — 46-78% of plate saturation and
                    # 60-80% of dark pixels lost. At 0.35/0.18 luminance lands at 126
                    # against a plate target of 130 and dark pixels at 37% against 32%.
                    "--light", "0.35", "--world", "0.18",
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
    if args.dry_run:
        print("\n(dry run — no files written)")
        return 0

    print(f"\n{made} image/caption pairs written to {out}")
    return check_no_clipping(out, args.frame)


if __name__ == "__main__":
    raise SystemExit(main())
