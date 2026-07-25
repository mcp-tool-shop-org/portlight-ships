"""
Stage 3 — render one NORMALISED ship GLB to 8 pack-ready headings.

Run:
  blender -b --python stage3_render_pack.py -- --glb <glb> --out <dir>
          --subject <subject-id> [--views 8] [--size 512] [--frame 13.0]
          [--passes albedo,depth,normal]

TWO THINGS THIS DOES DIFFERENTLY FROM pipeline/turntable.py
-----------------------------------------------------------
turntable.py is a REVIEW tool: opaque grey background, camera auto-framed to
each mesh so you can eyeball it. Both are wrong for a sprite pack.

1. TRANSPARENT FILM. Blender writes real alpha. There is no background to
   remove, so none of the cutout problems apply here — no flood fill, no
   tolerance tuning, no pale-sails-punched-through. (Those only ever affected
   the concept PLATES, which are generated on a grey studio background.)

2. FIXED CAMERA IN WORLD UNITS. The camera distance is derived from --frame,
   NOT from each mesh's bounding box. Inputs must be normalised first by
   normalize_meshes.py (length 10.0, keel at Y=0). Auto-framing would silently
   rescale every damage state to fill its own frame, so a ship losing masts
   would appear to GROW as it took damage. Fixed framing keeps a pixel the
   same size in every state — which is the whole point of a sprite pack.

HEADING NAMES match the existing sprite-foundry-packs vocabulary exactly, so
tooling that globs assets/*/albedo/*.png keeps working:

    front  front_left  left  back_left  back  back_right  right  front_right

`front` means BOW TOWARD THE VIEWER. View 0 is bow-on and the orbit runs
counter-clockwise, matching turntable.py's convention.
"""

import math
import os
import sys

import bpy
import mathutils

# ---------------------------------------------------------------- args
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


GLB = arg("--glb")
OUT = arg("--out")
SUBJECT = arg("--subject", "subject")
VIEWS = int(arg("--views", "8"))
SIZE = int(arg("--size", "512"))
FRAME = float(arg("--frame", "13.0"))   # world units the frame must span
ELEV = float(arg("--elev", "30.0"))     # camera elevation, degrees — 2.5D three-quarter
PASSES = [p.strip() for p in arg("--passes", "albedo").split(",") if p.strip()]

HEADINGS = [
    "front", "front_left", "left", "back_left",
    "back", "back_right", "right", "front_right",
]

if not GLB or not os.path.exists(GLB):
    print(f"ERROR: --glb missing or not found: {GLB!r}", flush=True)
    sys.exit(1)
if VIEWS != 8:
    print(f"ERROR: heading names are defined for 8 views, got {VIEWS}", flush=True)
    sys.exit(1)

for p in PASSES:
    os.makedirs(os.path.join(OUT, p), exist_ok=True)

# ---------------------------------------------------------------- scene
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not meshes:
    print("ERROR: no mesh in GLB", flush=True)
    sys.exit(1)

verts = []
for m in meshes:
    verts += [m.matrix_world @ v.co for v in m.data.vertices]
xs = [v.x for v in verts]
ys = [v.y for v in verts]
zs = [v.z for v in verts]
cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
lo_z, hi_z = min(zs), max(zs)
length = max(max(xs) - min(xs), max(ys) - min(ys))
print(f"[bbox] length={length:.2f} height={hi_z - lo_z:.2f}", flush=True)

# Guard: normalisation is a precondition, not a suggestion. If someone feeds raw
# Tripo output the whole pack silently comes out at inconsistent scale.
if not (FRAME * 0.45 < length < FRAME * 1.05):
    print(
        f"ERROR: mesh length {length:.2f} is not consistent with --frame {FRAME}. "
        "Run normalize_meshes.py first — fixed framing requires normalised input.",
        flush=True,
    )
    sys.exit(2)

# Pivot at the hull centre, vertically mid-height, so the ship sits centred.
centre = mathutils.Vector((cx, cy, (lo_z + hi_z) / 2))

cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"                 # orthographic: no perspective drift between headings
cam_data.ortho_scale = FRAME
cam = bpy.data.objects.new("cam", cam_data)
bpy.context.scene.collection.objects.link(cam)
bpy.context.scene.camera = cam

target = bpy.data.objects.new("target", None)
target.location = centre
bpy.context.scene.collection.objects.link(target)
track = cam.constraints.new("TRACK_TO")
track.target = target
track.track_axis = "TRACK_NEGATIVE_Z"
track.up_axis = "UP_Y"

# ---------------------------------------------------------------- lighting
world = bpy.data.worlds.new("W")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.22, 0.22, 0.24, 1.0)
bg.inputs[1].default_value = 0.85


def sun(name, energy, rot):
    light = bpy.data.lights.new(name, "SUN")
    light.energy = energy
    light.angle = math.radians(7)
    obj = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(obj)
    obj.rotation_euler = rot
    return obj


# The lights ORBIT WITH THE CAMERA (see the render loop). If they stay fixed in
# world space the ship is lit from a different side in every heading — `back`
# comes out markedly darker than `front_left` — and in game that reads as the
# sprite flickering brighter and darker as the ship turns. Rotating the rig with
# the camera keeps relative lighting identical across all 8 headings, which is
# what makes them usable as a turn cycle.
SUNS = [
    sun("key", 5.2, (math.radians(58), 0, math.radians(38))),
    sun("fill", 3.0, (math.radians(62), 0, math.radians(-48))),
    sun("rim", 5.5, (math.radians(-48), 0, math.radians(170))),
    sun("top", 1.8, (math.radians(8), 0, 0)),
]
SUN_BASE_Z = [s.rotation_euler.z for s in SUNS]

# ---------------------------------------------------------------- render cfg
scene = bpy.context.scene
try:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
except TypeError:
    scene.render.engine = "BLENDER_EEVEE"
scene.view_settings.view_transform = "Standard"
scene.render.resolution_x = SIZE
scene.render.resolution_y = SIZE
scene.render.film_transparent = True                 # <- real alpha
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
try:
    scene.eevee.taa_render_samples = 64
except AttributeError:
    pass

# --- depth / normal channels: NOT IMPLEMENTED, deliberately ----------------
# The sprite-foundry-packs layout has albedo/ depth/ normal/, so these are
# wanted eventually. They are NOT implemented here yet, and this fails loudly
# rather than writing something plausible-but-wrong.
#
# Reason: Blender 5.2 rewrote the compositor. `Scene.node_tree` is gone
# (replaced by `Scene.compositing_node_group`), the node set is cut to 92 types
# with no Math / MapRange / ValToRGB, and CompositorNodeOutputFile lost
# `file_slots` in favour of a single unnamed input. A depth pass built on what
# survives would be normalised PER FRAME, so the same hull point would map to a
# different grey in each heading — comparable-looking, silently useless.
#
# The durable route is a material-override render (ShaderNodeNewGeometry +
# ShaderNodeVectorTransform -> Emission) which is camera-space, explicit, and
# immune to compositor API churn. That is its own increment with its own
# verification, not a bolt-on to this one.
unsupported = [p for p in PASSES if p != "albedo"]
if unsupported:
    print(
        f"ERROR: pass(es) {unsupported} are not implemented. Only 'albedo' is "
        "supported today — see the comment in this file for why, and do not "
        "work around it by enabling the compositor passes.",
        flush=True,
    )
    sys.exit(3)

file_outputs = {}

# ---------------------------------------------------------------- orbit
CAM_DIST = FRAME * 1.6
elev = math.radians(ELEV)

written = []
for i, heading in enumerate(HEADINGS):
    ang = -math.pi / 2 + (2 * math.pi) * i / VIEWS
    horiz = CAM_DIST * math.cos(elev)
    cam.location = (
        centre.x + horiz * math.cos(ang),
        centre.y + horiz * math.sin(ang),
        centre.z + CAM_DIST * math.sin(elev),
    )

    # Orbit the light rig by the same delta as the camera, so every heading is
    # lit identically relative to the hull.
    delta = ang - (-math.pi / 2)
    for s, base_z in zip(SUNS, SUN_BASE_Z):
        s.rotation_euler.z = base_z + delta

    scene.render.filepath = os.path.join(OUT, "albedo", f"{heading}.png")
    bpy.ops.render.render(write_still=True)
    written.append(heading)
    print(f"[view {i}] {heading}", flush=True)

# The compositor File Output node always appends the frame number; rename to the
# bare heading so every channel matches assets/<subject>/<channel>/<heading>.png
frame = scene.frame_current
for key in file_outputs:
    d = os.path.join(OUT, key)
    for heading in written:
        src = os.path.join(d, f"{heading}_{frame:04d}.png")
        dst = os.path.join(d, f"{heading}.png")
        if os.path.exists(src):
            if os.path.exists(dst):
                os.remove(dst)
            os.rename(src, dst)

print(f"STAGE3 DONE {SUBJECT} views={len(written)} passes={','.join(PASSES)}", flush=True)
