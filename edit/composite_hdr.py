"""Composite the SDR text overlay onto the HDR (HLG / BT.2020) base and encode the final HEVC 10-bit file.

Graphics are mapped so overlay white sits at HLG reference white (75% signal, ITU-R BT.2408)
instead of peak brightness, keeping the text comfortable next to the original footage.
usage: composite_hdr.py base.mkv overlay_dir audio.wav out.mp4
"""
import glob, subprocess, sys
import cv2
import numpy as np

base, ov_dir, audio, out = sys.argv[1:5]
W, H, FPS = 1080, 1920, 24

# sRGB 8-bit -> linear light
c = np.arange(256) / 255
SRGB_LIN = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)
BT709_TO_2020 = np.array([[0.6274, 0.3293, 0.0433],
                          [0.0691, 0.9195, 0.0114],
                          [0.0164, 0.0880, 0.8956]], np.float32)
REF_WHITE = 0.2649  # scene light that HLG encodes at 0.75
A, B, C = 0.17883277, 0.28466892, 0.55991073


def hlg_oetf(e):
    e = np.clip(e, 0, 1)
    return np.where(e <= 1 / 12, np.sqrt(3 * e), A * np.log(np.maximum(12 * e - B, 1e-6)) + C)


frames = sorted(glob.glob(f"{ov_dir}/f*.png"))
dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", base, "-vf",
                        "scale=in_color_matrix=bt2020:in_range=tv,format=rgb48le", "-f", "rawvideo", "-"],
                       stdout=subprocess.PIPE)
x265 = "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc:range=limited:aq-mode=3"
enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb48le", "-s", f"{W}x{H}",
                        "-r", str(FPS), "-i", "-", "-i", audio,
                        "-vf", "scale=out_color_matrix=bt2020:out_range=tv,format=yuv420p10le",
                        "-c:v", "libx265", "-preset", "slow", "-crf", "15", "-profile:v", "main10",
                        "-x265-params", x265, "-tag:v", "hvc1",
                        "-colorspace", "bt2020nc", "-color_primaries", "bt2020", "-color_trc", "arib-std-b67",
                        "-color_range", "tv", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                        "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
fsz = W * H * 3 * 2
for k, path in enumerate(frames):
    buf = dec.stdout.read(fsz)
    if len(buf) < fsz:
        break
    img = np.frombuffer(buf, np.uint16).reshape(H, W, 3).astype(np.float32) / 65535
    ov = cv2.imread(path, cv2.IMREAD_UNCHANGED)          # BGRA
    alpha = ov[:, :, 3]
    ys, xs = np.nonzero(alpha)
    if len(ys):
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        rgb = SRGB_LIN[ov[y0:y1, x0:x1, 2::-1]]          # BGR -> RGB, linear
        sig = hlg_oetf((rgb @ BT709_TO_2020.T) * REF_WHITE)
        a = (alpha[y0:y1, x0:x1].astype(np.float32) / 255)[..., None]
        img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - a) + sig * a
    enc.stdin.write((img * 65535 + 0.5).astype(np.uint16).tobytes())
    print(f"\rcomposite {k + 1}/{len(frames)}", end="", flush=True)
enc.stdin.close(); enc.wait(); dec.wait()
print()
