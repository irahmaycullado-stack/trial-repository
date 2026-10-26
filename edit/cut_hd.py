"""HD build: stabilize, AI-upscale and zoom each clip, then join with soft transitions.

Writes base.mp4 and clips.json (start/dur of each clip on the joined timeline) into the build dir.
"""
import json, os, subprocess, sys
import numpy as np

tl = json.load(open(sys.argv[1]))
out_dir = sys.argv[2]
W, H, FPS = tl["w"], tl["h"], tl["fps"]
SW, SH = tl["src_w"], tl["src_h"]
T = tl.get("xfade_frames", 8)            # transition length in frames
sr = None
if tl.get("upscale"):
    from sr import Upscaler
    sr = Upscaler(tl["upscale"])
UP = 4 if sr else 1
clips, parts, start = [], [], 0
n = len(tl["clips"])
for i, c in enumerate(tl["clips"]):
    nd = round((c["out"] - c["in"]) * FPS)
    nl = nd + (T if i < n - 1 else 0)    # each clip runs T frames longer so the next one can dissolve over it
    d = nl / FPS
    tmp = os.path.join(out_dir, f"stab{i:02d}.trf")
    trim = ["-ss", str(c["in"]), "-i", tl["source"], "-frames:v", str(nl)]
    # light stabilization on the source clip (two passes)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *trim, "-vf",
                    f"vidstabdetect=shakiness=5:accuracy=15:result={tmp}", "-f", "null", "-"], check=True)
    pre = (f"fps={FPS},vidstabtransform=input={tmp}:smoothing=12:optzoom=1:interpol=bicubic,"
           f"hqdn3d=1.2:1.2:2:2,scale={SW}:{SH},format=rgb24")
    z = f"1.0+{c.get('zoom', 0.04)}*t/{d}"  # slow push-in, sampled down from the 4x frame so it never pixelates
    post = (f"scale=w='trunc({W}*({z})/2)*2':h='trunc({H}*({z})/2)*2':eval=frame:flags=lanczos,"
            f"crop={W}:{H}:(iw-{W})/2:(ih-{H})/2,{tl['grade']},unsharp=5:5:0.35,format=yuv420p")
    p = os.path.join(out_dir, f"part{i:02d}.mkv")
    dec = subprocess.Popen(["ffmpeg", "-v", "error", *trim, "-vf", pre, "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{SW * UP}x{SH * UP}", "-r", str(FPS), "-i", "-", "-vf", post,
                            "-c:v", "libx264", "-crf", "8", "-preset", "medium", p], stdin=subprocess.PIPE)
    fsz = SW * SH * 3
    k = 0
    while (buf := dec.stdout.read(fsz)) and len(buf) == fsz:
        f = np.frombuffer(buf, np.uint8).reshape(SH, SW, 3)
        enc.stdin.write((sr(f) if sr else f).tobytes())
        k += 1
        print(f"\rclip {i + 1}/{n} frame {k}/{nl}", end="", flush=True)
    enc.stdin.close(); enc.wait(); dec.wait()
    a = os.path.join(out_dir, f"part{i:02d}.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(c["in"]), "-t", str(d), "-i", tl["source"],
                    "-vn", "-ar", "48000", "-ac", "2", a], check=True)
    parts.append((p, a))
    clips.append({**c, "start": start / FPS, "dur": nd / FPS})
    start += nd
print()

# join: chained xfade for video, acrossfade for audio
args, fv, fa = [], [], []
for p, a in parts:
    args += ["-i", p]
for p, a in parts:
    args += ["-i", a]
v, au, off = "[0:v]", f"[{n}:a]", 0
for i in range(1, n):
    off += round((clips[i - 1]["dur"]) * FPS)
    tr = tl["clips"][i].get("transition", "fade")
    fv.append(f"{v}[{i}:v]xfade=transition={tr}:duration={T / FPS}:offset={off / FPS}[v{i}]")
    fa.append(f"{au}[{n + i}:a]acrossfade=d={T / FPS}:c1=tri:c2=tri[a{i}]")
    v, au = f"[v{i}]", f"[a{i}]"
subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex", ";".join(fv + fa),
                "-map", v, "-map", au, "-c:v", "libx264", "-crf", "8", "-preset", "medium",
                "-c:a", "pcm_s16le", os.path.join(out_dir, "base.mkv")], check=True)
json.dump(clips, open(os.path.join(out_dir, "clips.json"), "w"), ensure_ascii=False, indent=1)
