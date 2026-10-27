"""Synthesize an original lo-fi music bed and UI sound effects timed to timeline_hd.json.

Writes music.wav and sfx.wav (48 kHz stereo) into the output dir. Everything is generated here,
so the track is royalty-free.
"""
import json, sys, wave
import numpy as np

SR = 48000
rng = np.random.default_rng(7)
tl = json.load(open(sys.argv[1]))
out_dir = sys.argv[2]
FPS, T = tl["fps"], tl.get("xfade_frames", 8)

# clip start times on the joined timeline (same maths as cut_hd.py)
starts, s = [], 0
for c in tl["clips"]:
    starts.append(s / FPS)
    s += round((c["out"] - c["in"]) * FPS)
total = s / FPS + 0.05
N = int(total * SR)


def t_(dur):
    return np.arange(int(dur * SR)) / SR


def place(buf, sig, at, gain=1.0, pan=0.0):
    i = int(at * SR)
    j = min(len(buf), i + len(sig))
    if j <= i:
        return
    l, r = np.sqrt(0.5 * (1 - pan)), np.sqrt(0.5 * (1 + pan))
    buf[i:j, 0] += sig[: j - i] * gain * l
    buf[i:j, 1] += sig[: j - i] * gain * r


def fft_filter(x, lo=None, hi=None):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    m = np.ones_like(f)
    if lo:
        m *= 1 / (1 + (lo / np.maximum(f, 1)) ** 4)
    if hi:
        m *= 1 / (1 + (f / hi) ** 4)
    return np.fft.irfft(X * m, len(x))


def midi(n):
    return 440 * 2 ** ((n - 69) / 12)


# ---------------- music ----------------
BPM = 88
beat = 60 / BPM
bar = 4 * beat
music = np.zeros((N, 2))

# Fmaj9 - Em7 - Dm9 - Cmaj7 (warm, cafe-ish), one chord per bar
chords = [[53, 57, 60, 64, 67], [52, 55, 59, 62, 67], [50, 53, 57, 60, 64], [48, 55, 59, 62, 64]]
roots = [41, 40, 38, 36]


def epiano(freq, dur):
    t = t_(dur)
    env = np.exp(-t * 1.1) * (1 - np.exp(-t * 400))
    tine = np.exp(-t * 9) * 0.35 * np.sin(2 * np.pi * freq * 7.0 * t)  # bell-ish attack
    body = np.sin(2 * np.pi * freq * t + 0.6 * np.sin(2 * np.pi * freq * t) * np.exp(-t * 3))
    trem = 1 + 0.12 * np.sin(2 * np.pi * 4.5 * t)
    return (body + tine) * env * trem


def pad(notes, dur):
    # soft detuned pad that sustains through the bar so the bed never drops out
    t = t_(dur)
    x = sum(np.sin(2 * np.pi * midi(n) * d * t + p) for n in notes for d, p in ((0.997, 0), (1.003, 1.3)))
    env = np.minimum(1, t / 0.35) * np.minimum(1, (dur - t) / 0.35)
    return fft_filter(x, hi=1800) * env / (2 * len(notes))


def kick():
    t = t_(0.45)
    f = 45 + 75 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) * 0.9


def snare():
    t = t_(0.3)
    n = fft_filter(rng.standard_normal(len(t)), lo=1500, hi=7000) * np.exp(-t * 18)
    tone = np.sin(2 * np.pi * 185 * t) * np.exp(-t * 25)
    return (0.55 * n / np.abs(n).max() + 0.35 * tone)


def hat(open_=False):
    t = t_(0.18 if open_ else 0.06)
    n = fft_filter(rng.standard_normal(len(t)), lo=7000)
    return n / np.abs(n).max() * np.exp(-t * (14 if open_ else 70)) * 0.32


def bass(freq, dur):
    t = t_(dur)
    env = np.minimum(1, t * 80) * np.exp(-t * 1.2)
    x = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(4 * np.pi * freq * t)
    return np.tanh(1.4 * x) * env * 0.55


K, Sn = kick(), snare()
nbars = int(np.ceil(total / bar))
for b in range(nbars):
    t0 = b * bar
    ch = chords[b % 4]
    # keys: chord on 1 and a lighter re-hit on the "and" of 2, small strum offsets
    for k, n in enumerate(ch):
        place(music, epiano(midi(n), bar * 0.95), t0 + k * 0.012, 0.11, pan=-0.3 + 0.15 * k)
        place(music, epiano(midi(n), bar * 0.5), t0 + 1.5 * beat + k * 0.01, 0.06, pan=0.3 - 0.15 * k)
    # bass
    place(music, pad(ch[:4], bar + 0.3), max(0, t0 - 0.15), 0.22)
    place(music, bass(midi(roots[b % 4]), beat * 2.5), t0, 0.6)
    place(music, bass(midi(roots[b % 4] + 7), beat * 1.5), t0 + 2.5 * beat, 0.45)
    # drums come in after the hook bar and drop out on the last bar
    if 0 < b < nbars - 1:
        place(music, K, t0, 1.0)
        place(music, K, t0 + 2.5 * beat, 0.6)
        place(music, Sn, t0 + beat, 0.55, 0.1)
        place(music, Sn, t0 + 3 * beat, 0.55, 0.1)
        for e in range(8):
            swing = 0.06 * beat if e % 2 else 0
            place(music, hat(e == 7), t0 + e * beat / 2 + swing, 0.8 if e % 2 == 0 else 0.55, pan=0.25)

# warmth
for ch_ in range(2):
    music[:, ch_] = fft_filter(music[:, ch_], lo=30, hi=9000)
# fade in quickly, fade out over the end card
env = np.ones(N)
env[: int(0.08 * SR)] = np.linspace(0, 1, int(0.08 * SR))
fo = int(1.4 * SR)
env[-fo:] = np.linspace(1, 0, fo) ** 1.5
music *= env[:, None]

# ---------------- sound effects ----------------
sfx = np.zeros((N, 2))


def pop():
    t = t_(0.09)
    f = 520 + 900 * np.exp(-t * 60)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 45)


def sparkle():
    out = np.zeros(int(0.9 * SR))
    for k, n in enumerate([88, 91, 95, 100]):  # E6 G6 B6 E7 arpeggio
        t = t_(0.9 - k * 0.06)
        tone = (np.sin(2 * np.pi * midi(n) * t) + 0.3 * np.sin(2 * np.pi * midi(n) * 2.01 * t)) * np.exp(-t * 6)
        i = int(k * 0.06 * SR)
        out[i:i + len(tone)] += tone * 0.22
    return out


def chime():
    out = np.zeros(int(1.6 * SR))
    for k, n in enumerate([72, 76, 79, 84]):  # C major bell, gently rolled
        t = t_(1.6 - k * 0.08)
        tone = (np.sin(2 * np.pi * midi(n) * t) + 0.4 * np.sin(2 * np.pi * midi(n) * 3.0 * t) * np.exp(-t * 4)) * np.exp(-t * 2.5)
        i = int(k * 0.08 * SR)
        out[i:i + len(tone)] += tone * 0.18
    return out


for i, c in enumerate(tl["clips"]):
    lt0 = starts[i] + (0.15 if i else 0)  # overlay_ugc.html delays everything after clip 0 by 0.15s
    for b in c.get("beats", [{"at": 0, **c}]):
        at = lt0 + b["at"]
        if b.get("hook"):
            place(sfx, pop(), at + 0.05, 0.55)
        if b.get("pin"):
            place(sfx, pop(), at + 0.6, 0.6)
        if b.get("card"):
            place(sfx, pop(), at + 0.08, 0.65)
        if b.get("text"):
            place(sfx, pop(), at + 0.05, 0.45)
        if b.get("rating"):
            place(sfx, sparkle(), at + 0.9, 1.0)
        if b.get("cta"):
            place(sfx, chime(), at + 0.1, 1.0)


def write(path, x, peak):
    x = x / (np.abs(x).max() + 1e-9) * peak
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


write(f"{out_dir}/music.wav", music, 0.89)
write(f"{out_dir}/sfx.wav", sfx, 0.89)
print(f"music + sfx: {total:.2f}s, {nbars} bars at {BPM} bpm")
