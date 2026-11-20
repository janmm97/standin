"""Runs inside Blender (see test_blender_run.py): print the arm and camera at a beat's last frame."""
import os
import runpy

ns = runpy.run_path(os.environ["STANDIN_SCENE"], run_name="probe")
beat = {"camera": "static", "duration": 4, "scene": "", "vo": ""}
plan = {"aspect": "9:16", "cast": [{"name": "a", "look": "x"}],
        "beats": [{**beat, "action": "point", "camera": "dolly"}, {**beat, "action": "idle"}]}
ns["build"](plan, 10)
bpy = ns["bpy"]
for f in (97, 193):
    bpy.context.scene.frame_set(f)
    arm = bpy.data.objects["actor0_sh_r"].rotation_euler[0]
    cam = bpy.data.objects["camera"].location[1]
    print(f"PROBE {f} {arm:.2f} {cam:.2f}")
