"""Motion-interpolate a video to a higher frame rate, in parallel chunks.

minterpolate is single-threaded, so the video is cut into overlapping chunks, interpolated
side by side and stitched back together frame-exactly.
usage: interp60.py in.mkv out.mkv [fps] [chunks]
"""
import json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

src, out = sys.argv[1:3]
FPS = int(sys.argv[3]) if len(sys.argv) > 3 else 60
CHUNKS = int(sys.argv[4]) if len(sys.argv) > 4 else 4
PAD = 0.5  # seconds of overlap so motion estimation has neighbours at the seams
probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                                            "stream=color_space,color_transfer,color_primaries:format=duration",
                                            "-of", "json", src]))
dur = float(probe["format"]["duration"])
st = probe["streams"][0]
tags = ["-colorspace", st.get("color_space", "bt709"), "-color_primaries", st.get("color_primaries", "bt709"),
        "-color_trc", st.get("color_transfer", "bt709"), "-color_range", "tv"]
total = round(dur * FPS)
per = -(-total // CHUNKS)
# tpad holds the last frame so interpolation still has a neighbour for the final output frames
mi = f"tpad=stop_mode=clone:stop_duration=0.5,minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"


def run(i):
    f0, f1 = i * per, min(total, (i + 1) * per)       # output frames this chunk owns
    t0 = max(0.0, f0 / FPS - PAD)
    skip = round((f0 / FPS - t0) * FPS)
    p = f"{out}.chunk{i}.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.4f}", "-t", f"{(f1 - f0) / FPS + 2 * PAD:.4f}",
                    "-i", src, "-an", "-vf", f"{mi},trim=start_frame={skip}:end_frame={skip + f1 - f0},setpts=N/{FPS}/TB",
                    "-c:v", "libx264", "-crf", "8", "-preset", "medium", "-pix_fmt", "yuv420p10le", *tags, p], check=True)
    return p


with ThreadPoolExecutor(CHUNKS) as ex:
    parts = list(ex.map(run, range(CHUNKS)))
lst = out + ".txt"
open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], check=True)
for p in parts + [lst]:
    os.remove(p)
n = subprocess.check_output(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v", "-show_entries",
                             "stream=nb_read_packets", "-of", "csv=p=0", out]).decode().strip()
print(f"{out}: {n} frames (expected {total})")
