"""Runs inside Blender: build stand-in mannequins from a plan, animate them, and render.

blender -b --factory-startup -P scene.py -- plan.json outdir preview|keys [scale%]
"""

import json
import math
import os
import random
import sys

import bpy

FPS = 24
COLORS = [(0.85, 0.35, 0.25, 1), (0.25, 0.5, 0.85, 1), (0.3, 0.75, 0.4, 1)]


def key(obj, path, frame, value, index=-1):
    setattr(obj, path, value) if index < 0 else getattr(obj, path).__setitem__(index, value)
    obj.keyframe_insert(path, index=index, frame=frame)


def empty(name, parent=None, loc=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    e.parent, e.location = parent, loc
    return e


def limb(name, parent, length, radius, color):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=length, location=(0, 0, -length / 2))
    o = bpy.context.object
    o.name, o.color, o.parent = name, color, parent
    return o


def mannequin(i, color, x):
    root = empty(f"actor{i}", loc=(x, 0, 0))
    hips = empty(f"actor{i}_hips", root, (0, 0, 0.95))
    bpy.ops.mesh.primitive_cylinder_add(radius=0.17, depth=0.6, location=(0, 0, 0.3))
    torso = bpy.context.object
    torso.name, torso.color, torso.parent = f"actor{i}_torso", color, hips
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.12, location=(0, 0, 0.78))
    head = bpy.context.object
    head.name, head.color, head.parent = f"actor{i}_head", (0.9, 0.8, 0.7, 1), hips
    j = {"root": root, "hips": hips, "torso": torso}
    for side, sx in (("l", 0.24), ("r", -0.24)):
        j[f"sh_{side}"] = empty(f"actor{i}_sh_{side}", hips, (sx, 0, 0.55))
        limb(f"actor{i}_arm_{side}", j[f"sh_{side}"], 0.6, 0.05, color)
        j[f"hip_{side}"] = empty(f"actor{i}_hip_{side}", hips, (sx / 2.4, 0, 0))
        limb(f"actor{i}_leg_{side}", j[f"hip_{side}"], 0.92, 0.07, (0.2, 0.2, 0.25, 1))
    return j


def swing(j, s, e, amp=0.5, step=12):
    for f in range(s, e + 1, step):
        a = amp if ((f - s) // step) % 2 == 0 else -amp
        key(j["hip_l"], "rotation_euler", f, a, 0)
        key(j["hip_r"], "rotation_euler", f, -a, 0)
        key(j["sh_l"], "rotation_euler", f, -a, 0)
        key(j["sh_r"], "rotation_euler", f, a, 0)


def rest(j, f):
    for n in ("hip_l", "hip_r", "sh_l", "sh_r"):
        key(j[n], "rotation_euler", f, (0, 0, 0))
    key(j["hips"], "location", f, 0.95, 2)


def act(action, j, s, e, home, other=None):
    """Keyframe one beat (frames s..e) for one actor."""
    root = j["root"]
    rest(j, s)
    if action == "walk_in":
        key(root, "location", s, (home[0] - 3.0, home[1], 0))
        key(root, "location", e, (home[0], home[1], 0))
        swing(j, s, e)
        rest(j, e)
    elif action == "wave":
        key(j["sh_r"], "rotation_euler", s + 6, (0, -2.6, 0))
        for k, f in enumerate(range(s + 12, e - 6, 6)):
            key(j["sh_r"], "rotation_euler", f, (0, -2.6 + (0.4 if k % 2 else -0.4), 0))
        key(j["sh_r"], "rotation_euler", e, (0, -2.6, 0))
    elif action == "point":
        key(j["sh_r"], "rotation_euler", s + 10, (-1.5, 0, 0.4))
        key(j["sh_r"], "rotation_euler", e, (-1.5, 0, 0.4))
    elif action == "hand_off":
        face = 0.0 if other is None else math.atan2(other[0] - home[0], 1) * 0.8
        key(root, "rotation_euler", s, (0, 0, 0))
        key(root, "rotation_euler", s + 12, (0, 0, -face))
        key(j["sh_r"], "rotation_euler", s + 18, (-1.3, 0, 0))
        key(j["sh_r"], "rotation_euler", e, (-1.3, 0, 0))
    elif action == "turn_to_camera":
        key(root, "rotation_euler", s, (0, 0, math.pi / 2))
        key(root, "rotation_euler", min(e, s + 36), (0, 0, 0))
    elif action == "sit":
        key(j["hips"], "location", s + 18, 0.5, 2)
        key(j["hips"], "location", e, 0.5, 2)
        for n in ("hip_l", "hip_r"):
            key(j[n], "rotation_euler", s + 18, (-1.57, 0, 0))
            key(j[n], "rotation_euler", e, (-1.57, 0, 0))
    else:  # idle: breathe
        for k, f in enumerate(range(s, e + 1, 24)):
            key(j["torso"], "scale", f, (1, 1, 1.0 + 0.02 * (k % 2)))


def camera(beat, s, e, target, rng):
    cam_obj = bpy.context.scene.camera
    rig = cam_obj.parent
    kind = beat["camera"]
    key(rig, "rotation_euler", s, (0, 0, 0))
    key(cam_obj, "location", s, (0, -4.6, 1.3))
    if kind == "dolly":
        key(cam_obj, "location", e, (0, -3.2, 1.3))
    elif kind == "orbit":
        key(rig, "rotation_euler", e, (0, 0, math.radians(30)))
    elif kind == "handheld":
        for f in range(s + 6, e, 6):
            key(cam_obj, "location", f, (rng.uniform(-0.05, 0.05), -4.6 + rng.uniform(-0.05, 0.05),
                                         1.3 + rng.uniform(-0.04, 0.04)))
    key(cam_obj, "location", e, tuple(cam_obj.location))
    key(rig, "rotation_euler", e, tuple(rig.rotation_euler))


def build(plan, scale):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "OBJECT"
    sc.render.fps = FPS
    w, h = (720, 1280) if plan.get("aspect", "9:16") == "9:16" else (1280, 720)
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = scale
    sc.render.image_settings.file_format = "PNG"
    sc.world = bpy.data.worlds.new("world")
    sc.world.color = (0.62, 0.66, 0.72)
    sc.display.shading.background_type = "WORLD"

    bpy.ops.mesh.primitive_plane_add(size=30)
    bpy.context.object.color = (0.55, 0.55, 0.52, 1)
    target = empty("target", loc=(0, 0, 1.0))
    rig = empty("cam_rig")
    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    sc.collection.objects.link(cam)
    cam.parent = rig
    cam.data.lens = 35
    tr = cam.constraints.new("TRACK_TO")
    tr.target, tr.track_axis, tr.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
    sc.camera = cam

    cast = plan["cast"]
    xs = [(-0.9 + 1.8 * k / (len(cast) - 1)) if len(cast) > 1 else 0.0 for k in range(len(cast))]
    actors = [mannequin(k, COLORS[k % 3], xs[k]) for k in range(len(cast))]
    sits = [i for i, b in enumerate(plan["beats"]) if b["action"] == "sit"]
    if sits:
        bpy.ops.mesh.primitive_cube_add(size=0.45, location=(xs[sits[0] % len(actors)], 0.25, 0.22))
        bpy.context.object.color = (0.45, 0.3, 0.2, 1)

    rng = random.Random(7)
    s = 1
    for i, b in enumerate(plan["beats"]):
        e = s + b["duration"] * FPS
        lead = i % len(actors)
        for k, j in enumerate(actors):
            home = (xs[k], 0)
            other = (xs[1 - k], 0) if len(actors) > 1 and k < 2 else None
            if b["action"] == "walk_in" and i > 0 and k != lead:
                act("idle", j, s, e, home)
            elif k == lead or b["action"] in ("hand_off", "walk_in"):
                act(b["action"], j, s, e, home, other)
            else:
                act("idle", j, s, e, home)
        camera(b, s, e, target, rng)
        s = e
    sc.frame_start, sc.frame_end = 1, s
    return s


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    plan_path, out, mode = argv[0], argv[1], argv[2]
    scale = int(argv[3]) if len(argv) > 3 else (25 if mode == "preview" else 100)
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    build(plan, scale)
    sc = bpy.context.scene
    if mode == "preview":
        sc.render.filepath = os.path.join(out, "preview", "f_")
        bpy.ops.render.render(animation=True)
    else:
        frames, t = [1], 0
        for b in plan["beats"]:
            t += b["duration"]
            frames.append(1 + t * FPS)
        for i, fr in enumerate(frames):
            sc.frame_set(fr)
            sc.render.filepath = os.path.join(out, "keys", f"k_{i:02d}.png")
            bpy.ops.render.render(write_still=True)
    print("STANDIN_DONE", mode)


if __name__ == "__main__":
    main()
