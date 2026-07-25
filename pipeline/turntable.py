"""Lit turnaround of a GLB (mesh or rigged): orbit the camera N views around the figure on a
neutral mid-grey background with bright 3-point + ambient fill, so DARK materials (black armor)
read with form instead of crushing to silhouette. Saves full-res per-view PNGs + a montage strip.

The old validate/posetest scripts used 2 dim suns (4.0/2.5), NO ambient, and the default
view-transform -> black armor underlit. Fixes: grey ambient world, key/fill/rim/top suns,
Standard view transform.

Run: blender -b --python _turntable.py -- --glb <glb> --out <dir> --views 8 --size 768 --tag dec
"""
import bpy, sys, os, math, mathutils
argv = sys.argv[sys.argv.index("--")+1:]
def arg(n, d=None): return argv[argv.index(n)+1] if n in argv else d
GLB = arg("--glb"); OUT = arg("--out"); VIEWS = int(arg("--views","8")); SIZE = int(arg("--size","768")); TAG = arg("--tag","view")
CLAY = arg("--clay","0")=="1"   # override all materials with uniform grey = geometry-only compare
if not GLB or not os.path.exists(GLB):
    print(f"ERROR: --glb not supplied or not found: {GLB!r}", flush=True); sys.exit(1)
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
assert meshes, "no mesh in GLB"
# drop stray bounding-sphere meshes (UniRig merge / TRELLIS env bake) so they don't wreck framing
for o in list(meshes):
    if len(o.data.vertices) < 300:
        bb=[o.matrix_world@v.co for v in o.data.vertices]
        ext=max(max(p[i] for p in bb)-min(p[i] for p in bb) for i in range(3)) if bb else 0
        if ext > 1.4: bpy.data.objects.remove(o, do_unlink=True)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]

if CLAY:   # uniform grey material on every mesh -> pure geometry, no texture
    mc=bpy.data.materials.new("clay"); mc.use_nodes=True
    b=mc.node_tree.nodes.get("Principled BSDF")
    if b: b.inputs["Base Color"].default_value=(0.78,0.78,0.80,1.0); b.inputs["Roughness"].default_value=0.62
    for o in meshes:
        o.data.materials.clear(); o.data.materials.append(mc)

# world-space bbox over all meshes
allv = []
for m in meshes:
    allv += [m.matrix_world @ v.co for v in m.data.vertices]
xs=[v.x for v in allv]; ys=[v.y for v in allv]; zs=[v.z for v in allv]
minx,maxx=min(xs),max(xs); miny,maxy=min(ys),max(ys); minz,maxz=min(zs),max(zs)
cx=(minx+maxx)/2; cy=(miny+maxy)/2; cz=(minz+maxz)/2
W=maxx-minx; D=maxy-miny; H=maxz-minz
rad=max(W,D,H); ctr=mathutils.Vector((cx,cy,cz))
print(f"[bbox] W={W:.2f} D={D:.2f} H={H:.2f}", flush=True)

# camera, tracks centre
camd=bpy.data.cameras.new("C"); cam=bpy.data.objects.new("C",camd)
bpy.context.scene.collection.objects.link(cam); bpy.context.scene.camera=cam; camd.lens=80
tgt=bpy.data.objects.new("T",None); tgt.location=ctr; bpy.context.scene.collection.objects.link(tgt)
con=cam.constraints.new("TRACK_TO"); con.target=tgt; con.track_axis="TRACK_NEGATIVE_Z"; con.up_axis="UP_Y"
CAMDIST=rad*2.7; CAMZ=cz+H*0.04

# neutral mid-grey world = ambient fill + the background the Director sees
world=bpy.data.worlds.new("W"); bpy.context.scene.world=world; world.use_nodes=True
bg=world.node_tree.nodes["Background"]; bg.inputs[0].default_value=(0.215,0.215,0.235,1.0); bg.inputs[1].default_value=0.85

def sun(name,energy,rot):
    L=bpy.data.lights.new(name,"SUN"); L.energy=energy; L.angle=math.radians(7)
    o=bpy.data.objects.new(name,L); bpy.context.scene.collection.objects.link(o); o.rotation_euler=rot
    return o
# 3-point + soft top; energies tuned so black armour shows edges/specular, not a void
sun("key", 5.2, (math.radians(58), 0, math.radians(38)))
sun("fill", 3.0, (math.radians(62), 0, math.radians(-48)))
sun("rim", 5.5, (math.radians(-48), 0, math.radians(170)))
sun("top", 1.8, (math.radians(8), 0, 0))

sc=bpy.context.scene
try: sc.render.engine="BLENDER_EEVEE_NEXT"
except: sc.render.engine="BLENDER_EEVEE"
sc.view_settings.view_transform='Standard'
sc.render.resolution_x=int(SIZE*0.74); sc.render.resolution_y=SIZE
sc.render.film_transparent=False
try: sc.eevee.taa_render_samples=64
except: pass

def render(p): sc.render.filepath=p; bpy.ops.render.render(write_still=True)

# orbit: view 0 = front (camera on -Y per the rig scripts' convention), CCW
paths=[]
for i in range(VIEWS):
    ang = -math.pi/2 + (2*math.pi)*i/VIEWS
    cam.location=(cx+CAMDIST*math.cos(ang), cy+CAMDIST*math.sin(ang), CAMZ)
    p=os.path.join(OUT,f"{TAG}_{i}.png"); render(p); paths.append(p)
    print(f"[view {i}] deg={math.degrees(ang)%360:.0f} -> {os.path.basename(p)}", flush=True)

from PIL import Image
imgs=[Image.open(p).convert("RGB") for p in paths]
g=10; w=sum(im.width for im in imgs)+g*(len(imgs)+1); h=max(im.height for im in imgs)+2*g
M=Image.new("RGB",(w,h),(38,38,42)); x=g
for im in imgs: M.paste(im,(x,g)); x+=im.width+g
strip=os.path.join(OUT,f"_{TAG}_strip.png"); M.save(strip)
print(f"MONTAGE {strip}", flush=True)
print("TURNTABLE DONE", flush=True)
