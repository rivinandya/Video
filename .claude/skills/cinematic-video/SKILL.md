---
name: cinematic-video
description: Turn a still photo into a short cinematic video clip with realistic camera moves (dolly in/out, truck, crane, static cinemagraph) and natural motion (flowing water, floating debris, shimmering glints, god rays, drifting dust, swaying foliage, film grain). Use when the user shares an image and asks to animate it, make a video/clip/cinemagraph from it, add a camera move ("slow dolly pull out", "push in", "pan"), or bring water/light/leaves to life. Also use to write prompts for AI image-to-video tools (Grok Imagine, Runway, Kling, Veo, Sora, Luma) when the user wants to generate there instead.
---

# Cinematic video from a still image

Two routes. Pick based on what the user has:

1. **Local 2.5D render (always available):** `scripts/cinematic.py` warps the photo using a hand-tuned depth map, water and foliage masks and procedural effects. Its output is deterministic, high-res and faithful to the photo. It can't create new content: no reveal past the frame edges, no splashes, and objects bob rather than travel.
2. **AI image-to-video (when the user has a tool or API key):** Write a prompt with `references/prompting.md` and either hand it to the user or call the API if a key is configured. This gives real physics and new detail, but it may drift from the photo.

Tell the user which route you used and what its limits are. Don't claim local output is "AI generated".

## Local render workflow

Requirements: `python3`, `numpy`, `opencv-python-headless` (`pip install opencv-python-headless`) and `ffmpeg`.

1. **Look at the image** and choose:
   - `focus`: the point the camera move centres on, usually the subject the user named (e.g. "following the cord" → a point on the cord).
   - `horizon`: the y value where the ground fades into the distance. Depth goes from far there to near at the bottom.
   - `vanish`: where water flows from (the far end of the stream or river).
   - Polygons: `water` (moving liquid, including floating trash), `static` (things that must not wobble: cords, poles, people, rocks inside water), `sway` (foliage), `near` (foreground objects above the horizon, such as overhanging leaves) and `far`.
   - `rays`: if there are visible sunbeams, set the light `source` (it can be off-frame, e.g. y < 0).
2. **Write a scene JSON.** All coordinates are normalized from 0 to 1. Copy `examples/forest-stream.json` as a template. The keys are listed below.
3. **Preview the masks** and iterate until they fit:
   ```bash
   python3 scripts/cinematic.py photo.png masks.jpg --config scene.json --preview-masks
   ```
   Read `masks.jpg`. The top half shows water in blue, static in magenta, sway in green and the focus as a cross. The bottom half is depth, where brighter means nearer. Fix any polygon that spills onto land or misses water.
4. **Do a quick low-res test**, then the final render:
   ```bash
   python3 scripts/cinematic.py photo.png test.mp4 --config scene.json --move dolly-out --size 960x540 --duration 2
   python3 scripts/cinematic.py photo.png out.mp4  --config scene.json --move dolly-out --duration 5
   ```
   A 1080p 5 s render takes about 1.5 min on 4 cores.
5. **Verify** with a contact sheet of the first, middle and last frames, plus a close crop of the water from two frames a few apart:
   ```bash
   ffmpeg -i out.mp4 -vf "select='eq(n\,0)+eq(n\,75)+eq(n\,149)',scale=960:-1,tile=1x3" -frames:v 1 sheet.jpg
   ```
   Check for edge smearing (if you see it, lower `--amount`), static objects wobbling (add them to `static`) and water that looks like jelly (lower `water_strength`).
6. Deliver the mp4, and say which motion is synthetic and what it can't do.

### CLI options
| flag | default | notes |
|---|---|---|
| `--move` | `dolly-out` | `dolly-in`, `truck-left/right` (lateral with parallax), `crane-up/down`, `static` (cinemagraph) |
| `--amount` | per move | dolly 0.15–0.4 (0.3 is a strong, slow pull). Truck/crane 0.02–0.05. Higher values stretch near objects. |
| `--duration` / `--fps` | 5 / 30 | |
| `--size` | 1920x1080 | Keep the source aspect ratio. For a vertical clip, crop the source first. |
| `--ease` | `cinematic` | `smooth` or `linear` |
| `--crf` | 16 | x264 quality |

### Scene JSON keys
| key | meaning |
|---|---|
| `focus` [x,y] | centre of the dolly (the subject the camera "follows") |
| `horizon` y | depth reaches its farthest at this y |
| `depth_gamma` | depth falloff (0.85) |
| `vanish` [x,y] | flow origin for water |
| `flow` | `"toward"` (default, toward the camera), `"away"`, or `[dx,dy]` for sideways flow |
| `water`, `static`, `sway`, `near`, `far` | lists of polygons `[[x,y],...]` |
| `static_hue` | auto-mask a coloured static object: `{"ranges":[[0,10],[165,180]], "min_sat":110, "min_val":40, "min_area":0.0016, "ignore":[polygons]}` (OpenCV hue 0–180) |
| `rays` | `{"source":[x,y], "strength":0.06, "zone":[polygon] (optional)}` |
| `dust`, `dust_box` | number of motes, and their box `[x0,y0,x1,y1]` |
| `water_strength`, `water_speed`, `sway_strength`, `handheld`, `grain` | multipliers (1.0) / grain sigma (0.008) |
| `floaters` | floating objects that bob, rock and drift rigidly: `{"ellipse":[cx,cy,rx,ry,deg]}` or `{"poly":[...]}` |
| `standing_wave`, `surface_speed`, `flow_period`, `motion_blur`, `detail_sigma`, `glints`, `floater_bob`, `floater_drift` | water realism controls. **See the `realistic-water` skill** for what each does and how to tune it. |
| `light_bgr` | colour of the glints and rays (warm by default) |
| `feather` | mask edge softness as a fraction of the width (0.025) |

### Matching user wording to moves
- "pull out", "pull back", "reveal" → `dolly-out`. "push in", "move closer" → `dolly-in`.
- "pan" / "slide" / "track sideways" → `truck-left/right`. Use small amounts: a true pan has no parallax, but a truck looks more cinematic.
- "rise", "boom up", "pedestal" → `crane-up`.
- "only the water moving", "cinemagraph", "loop" → `static`. For a seamless loop, render 2× the length and crossfade the halves with ffmpeg `xfade`.
- "following X" → put `focus` on X. With dolly-out, the camera backs away along it.

## AI image-to-video route
See `references/prompting.md` for prompt structure, camera vocabulary, a negative-prompt list and per-tool notes. Never ask for an API key in chat. Use the environment's credential and network-settings flow. If the network blocks the provider, say so and give the user the prompt to run themselves.
