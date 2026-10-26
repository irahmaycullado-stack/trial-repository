"""Cut, zoom, grade and join the clips from timeline.json into base.mp4 (no text)."""
import json, subprocess, sys, os

tl = json.load(open(sys.argv[1]))
out_dir = sys.argv[2]
W, H, FPS = tl["w"], tl["h"], tl["fps"]
parts = []
for i, c in enumerate(tl["clips"]):
    d = round(c["out"] - c["in"], 3)
    if c["zoom"] == "snap":
        # CapCut-style punch-in: starts zoomed at 1.18, eases out to 1.04 in 0.35s, then drifts
        z = f"if(lt(t,0.35),1.04+0.14*pow(1-t/0.35,3),1.04+0.02*(t-0.35)/{d})"
    else:
        z = f"1.0+0.07*t/{d}"  # slow push-in
    vf = (f"scale=w='trunc({W}*({z})/2)*2':h='trunc({H}*({z})/2)*2':eval=frame:flags=lanczos,"
          f"crop={W}:{H}:(iw-{W})/2:(ih-{H})/2,"
          f"eq=contrast=1.06:saturation=1.18:brightness=0.01,"
          f"colorbalance=rm=0.03:bm=-0.03,fps={FPS},format=yuv420p")
    af = f"afade=t=in:d=0.04,afade=t=out:st={d-0.05}:d=0.05"
    p = os.path.join(out_dir, f"part{i:02d}.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(c["in"]), "-t", str(d), "-i", tl["source"],
                    "-vf", vf, "-af", af, "-c:v", "libx264", "-crf", "16", "-preset", "fast",
                    "-c:a", "aac", "-ar", "48000", "-b:a", "192k", p], check=True)
    parts.append(p)
lst = os.path.join(out_dir, "parts.txt")
open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                "-c", "copy", os.path.join(out_dir, "base.mp4")], check=True)
