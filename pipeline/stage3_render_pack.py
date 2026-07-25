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

# --- depth / normal channels, via MATERIAL OVERRIDE ------------------------
# NOT via the compositor. Blender 5.2 rewrote it: `Scene.node_tree` is gone,
# the node set is cut to 92 types with no Math / MapRange / ValToRGB, and
# CompositorNodeOutputFile lost `file_slots`. A depth pass built on what
# survives would be normalised PER FRAME — the same hull point mapping to a
# different grey in each heading, which looks comparable and is silently
# useless.
#
# A material override sidesteps all of it. Both maps are computed in the SHADER
# in camera space, which is explicit, absolute, and immune to compositor churn.
# Emission needs no lighting, so the light rig is irrelevant to these passes.
KNOWN_PASSES = ("albedo", "depth", "normal")
unsupported = [p for p in PASSES if p not in KNOWN_PASSES]
if unsupported:
    print(f"ERROR: unknown pass(es) {unsupported}; known: {KNOWN_PASSES}", flush=True)
    sys.exit(3)


def make_depth_material(frame_units: float):
    """Camera-space depth -> greyscale. Near = white, far = black.

    The range is ABSOLUTE (derived from --frame), not auto-fitted per render, so
    the same point on the hull maps to the same grey in every heading and in
    every subject. That comparability is the entire point of a depth channel.
    """
    mat = bpy.data.materials.new("_depth")
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()

    cam = tree.nodes.new("ShaderNodeCameraData")
    rng = tree.nodes.new("ShaderNodeMapRange")
    rng.inputs["From Min"].default_value = CAM_DIST - frame_units * 0.5
    rng.inputs["From Max"].default_value = CAM_DIST + frame_units * 0.5
    rng.inputs["To Min"].default_value = 1.0
    rng.inputs["To Max"].default_value = 0.0
    rng.clamp = True
    emit = tree.nodes.new("ShaderNodeEmission")
    out = tree.nodes.new("ShaderNodeOutputMaterial")

    tree.links.new(cam.outputs["View Z Depth"], rng.inputs["Value"])
    tree.links.new(rng.outputs["Result"], emit.inputs["Color"])
    tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


def make_normal_material():
    """World normal -> CAMERA space -> encoded 0..1 as RGB.

    Camera space, not world space: a world-space normal map would rotate with
    the ship between headings, so the same surface would encode a different
    colour per view and be unusable for relighting a sprite.
    """
    mat = bpy.data.materials.new("_normal")
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()

    geo = tree.nodes.new("ShaderNodeNewGeometry")
    xf = tree.nodes.new("ShaderNodeVectorTransform")
    xf.vector_type = "NORMAL"
    xf.convert_from = "WORLD"
    xf.convert_to = "CAMERA"
    # Encode -1..1 into 0..1, NEGATING Z.
    #
    # Blender's WORLD->CAMERA transform returns camera-facing normals with
    # z ~= -1, the opposite of the OpenGL normal-map convention where +Z points
    # out of the surface toward the viewer (camera-facing = blue). Measured, not
    # assumed: before the flip, mean B over the opaque pixels of a bow-on view
    # was 24/255, decoding to z = -0.81 on a convex hull viewed head-on, which is
    # physically backwards. Green is left as-is: this is the OpenGL/+Y-up
    # convention, so flip G downstream if a consumer wants DirectX.
    half = tree.nodes.new("ShaderNodeVectorMath")
    half.operation = "MULTIPLY_ADD"
    half.inputs[1].default_value = (0.5, 0.5, -0.5)
    half.inputs[2].default_value = (0.5, 0.5, 0.5)
    emit = tree.nodes.new("ShaderNodeEmission")
    out = tree.nodes.new("ShaderNodeOutputMaterial")

    tree.links.new(geo.outputs["Normal"], xf.inputs["Vector"])
    tree.links.new(xf.outputs["Vector"], half.inputs[0])
    tree.links.new(half.outputs["Vector"], emit.inputs["Color"])
    tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat

# ---------------------------------------------------------------- orbit
CAM_DIST = FRAME * 1.6
elev = math.radians(ELEV)

# Built AFTER CAM_DIST — the depth range is anchored to the camera distance.
PASS_MATERIAL = {"albedo": None}
if "depth" in PASSES:
    PASS_MATERIAL["depth"] = make_depth_material(FRAME)
if "normal" in PASSES:
    PASS_MATERIAL["normal"] = make_normal_material()

view_layer = scene.view_layers[0]

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
    # lit identically relative to the hull. (Irrelevant to the emission-based
    # data passes, which are unlit by construction — kept here because albedo
    # needs it and the cost is nil.)
    delta = ang - (-math.pi / 2)
    for s, base_z in zip(SUNS, SUN_BASE_Z):
        s.rotation_euler.z = base_z + delta

    for pass_name in PASSES:
        view_layer.material_override = PASS_MATERIAL[pass_name]
        # Data maps must NOT be tone-mapped — 'Raw' writes the shader value
        # through unchanged. 'Standard' would apply an sRGB curve and silently
        # corrupt every depth reading and normal vector.
        scene.view_settings.view_transform = (
            "Standard" if pass_name == "albedo" else "Raw"
        )
        scene.render.filepath = os.path.join(OUT, pass_name, f"{heading}.png")
        bpy.ops.render.render(write_still=True)

    view_layer.material_override = None
    written.append(heading)
    print(f"[view {i}] {heading}", flush=True)

print(f"STAGE3 DONE {SUBJECT} views={len(written)} passes={','.join(PASSES)}", flush=True)
