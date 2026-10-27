---
name: ugc-video
description: Edit raw phone footage into a polished UGC-style business video (café/restaurant/product review) for TikTok, Reels or Shorts — reaction hook, long tasting takes, clean native captions, product cards, rating, CTA end card, original colour (HDR kept), AI upscaling, generated royalty-free music, 1080p60 MP4. Use when the user uploads a video and asks for a UGC, food/drink review, "what I ate", or business promo edit, or references the Cong Caphe video.
---

# UGC business video from phone footage

Reference project: the Cong Caphe edit (`examples/cong_caphe_timeline.json`, final render
`edit/cong_caphe_ugc_1080p60.mp4` on branch `what-i-ate-this-week-edit`). Follow the same
recipe; only the timeline JSON and the captions change per video.

## The user's preferences (learned the hard way — follow them)

- **Colour must look like the original.** No colour grade, no LUT, no "pop". iPhone footage is
  usually HDR (HLG/BT.2020, Dolby Vision 8.4): keep it HDR end to end (`"hdr": true`). Never read
  HDR as SDR (looks flat/yellow-green) and don't tone-map unless an SDR copy is asked for.
- **Long, uncut takes of the tasting.** Don't chop the "me trying the drink/food" moments into
  short clips; put several captions on one take with `beats` instead.
- **Smooth transitions:** soft crossfades (`fade`), `fadeblack` into the end card. No flashes.
- **Sound:** no whooshes. Soft pops when text appears are OK, but drop them (`--no-pops`) when the
  user will add a voiceover. Remove all background/ambient noise — music (and SFX) only.
  A sparkle on the rating and a chime on the end card were fine.
- **Exact names.** Ask for / use the venue and product names exactly as the user writes them
  (e.g. "Cong Caphe", "Coconut Green Rice", "Avocado Smoothie"). Never guess a product name and
  never claim things not seen (no "coffee run" when it wasn't coffee; don't mention merch unless asked).
- Short, plain captions in English ("Vintage vibes"); Taglish only if requested.
- Output: **1080×1920, 60 fps, MP4**, sent with SendUserFile (`display: attach` is fine). Always
  send the MP4 itself when a version is done, and resend on request.

## Video structure (≈35–40 s)

1. **Hook** (0–3 s): storefront or reaction shot, 3-line hook at the top, e.g.
   "Okay… this <product> is *actually* worth the hype" + 📍 location pin.
2. **Ambience** (≈5 s): interior pan, one short caption.
3. **The order** (≈3 s): products on the table, "Got the *A* + an *B*".
4. **Tasting take 1** (≈14 s, one take): "MUST TRY · <product>" card → clear → taste caption.
5. **Tasting take 2** (≈8 s, one take): "ALSO GOOD · <product>" card → taste caption.
6. **Verdict** (≈2.5 s): face to camera, "Would I come back? *100%*" + 10/10 badge.
7. **CTA end card** (≈2.5 s): products shot, "📍 <Venue> · Save this for your next café visit 📌"
   + product recap line.

Captions sit in the TikTok safe zone (clear of the right action rail and bottom UI);
`*word*` renders as a yellow highlight pill. Taste wording is the user's call — flag any
adjectives you invented.

## Pipeline (scripts in `scripts/`)

| Step | Script | What it does |
|---|---|---|
| 1 | `cut_hd.py timeline.json BUILD` | per clip: trim, (optional vidstab), Real-ESRGAN 4× upscale (`sr.py`), slow push-in sampled from the 4× frame, then `xfade`/`acrossfade` join → `BUILD/base.mkv`, `BUILD/clips.json`. Resumable after container restarts. |
| 2 | `make_audio.py timeline.json OUT [--no-pops]` | synthesizes an original lo-fi bed (royalty-free) + pops/sparkle/chime timed to the captions → `music.wav`, `sfx.wav`. Mix: music 0.75 + sfx 0.6, `loudnorm=I=-14:TP=-1.5`. No ambience. |
| 3 | `interp60.py BUILD/base.mkv BUILD/base60.mkv 60 4` | parallel motion interpolation 24→60 fps. |
| 4 | `node render.mjs tl60.json BUILD /abs/path/overlay_ugc.html` | renders the caption layer frame by frame (headless Chromium, transparent PNGs) at the output fps; uses `BUILD/clips.json` for timing. Make `tl60.json` = timeline with `"fps": 60`. |
| 5 | `composite_hdr.py base60.mkv BUILD/ov mix.wav out.mp4 60` | composites captions into HLG (graphics at HLG reference white, BT.2408) and encodes HEVC Main10 `hvc1`, BT.2020/HLG tags. |

Timeline JSON: `source`, `upscale` (model path), `hdr`, `stabilize` (false for HDR — vidstab is
8-bit only), `fps` (source fps), `w/h` 1080×1920, `src_w/src_h`, `xfade_frames` (8), and `clips`
with `in/out` (source seconds), `zoom`, `transition`, and either single fields (`hook`, `pin`,
`text`, `card`, `rating`, `cta`) or `beats: [{at, ...}]` (an empty beat clears the screen).

## Before starting

1. `ffprobe` the upload: resolution, fps, `color_transfer` (`arib-std-b67` = HLG → `"hdr": true`).
   If it is small (e.g. 480×854) it was compressed in transit — ask for the camera-roll original,
   and upscale meanwhile.
2. Make a 1–2 fps contact sheet with timestamps and pick takes from it; confirm product names.
3. Setup (cloud container): `pip install torch opencv-python-headless` (PyPI works;
   download.pytorch.org and Hugging Face are blocked), model from GitHub releases:
   `realesr-general-x4v3.pth` (v0.2.5.0) → `/home/user/models/`. Playwright + Chromium are
   preinstalled; for ESM use `createRequire` and `NODE_PATH=$(npm root -g)`.
4. Budget: upscaling ≈4 s/frame on 4 CPU cores (≈1 h for a 37 s video at 24 fps) — run
   `cut_hd.py` in the background; interpolation to 60 fps ≈13 min; composite ≈5–8 min.

## Gotchas

- CapCut / TikTok reference links can't be fetched from the sandbox — say so and work from
  conventions or ask for a screen recording.
- Voice cloning isn't possible here (model hosts and ElevenLabs are blocked); offer a voiceover
  script timed to the scenes and mix the user's own recording instead.
- Verify colour against the source by tone-mapping both the same way and comparing means/std
  (`mobius`, `npl=203`) — previews in the chat are SDR.
- You can't listen: check audio with `ebur128`, `astats` and `showwavespic` (no gaps, no
  clipping, pops audible), and ask the user to play it once.
- Large MP4s (>50 MB) push with a GitHub warning; that's fine.
