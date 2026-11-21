---
name: realistic-water
description: Make water in an animated still image move realistically — streams, rivers, creeks, puddles, waterfalls, shorelines, ponds, water with floating trash or leaves. Use when the user asks for "realistic water movement", says the water looks fake / like jelly / too wobbly / too static, wants floating objects to bob or drift, or when animating any photo that contains water (together with the cinematic-video skill). Covers how real water moves, how to mask it, and how to tune the renderer.
---

# Realistic water motion

The renderer is `.claude/skills/cinematic-video/scripts/cinematic.py`. That skill covers its CLI and camera moves. This skill covers the water: how to set it up, tune it and check it.

## How real water moves (and how the engine copies it)

| Real-world behaviour | Engine feature | Config key |
|---|---|---|
| Shallow streams: the big wave shapes over rocks (**standing waves**) stay in place and only shimmer | low and mid frequencies get a gentle advected wobble | `standing_wave` (0.7) |
| Small ripples, sparkle and foam **travel downstream** | fine detail (image minus blur) is carried along the flow with a two-phase flow map, a per-pixel phase offset (so it doesn't pulse) and a contrast-preserving crossfade | `detail_sigma` (2.5 px), `surface_speed` (0.5), `flow_period` (20 frames) |
| Fast water blurs at a normal shutter speed | 5-tap blur along the flow direction | `motion_blur` (1.0) |
| Perspective: near water moves faster and has bigger ripples, far water is finer and slower | speed and ripple scale come from the depth map | `horizon`, `vanish` |
| Flow follows the channel | direction radiates from `vanish` (toward the camera), or `"away"`, or a fixed `[dx,dy]` | `flow` |
| Floating objects **move as solid things**: they bob, rock a little and drift slowly downstream | each `floaters` entry gets its own rigid translate and rotate, with its own random phase and frequency | `floaters`, `floater_bob`, `floater_drift` |
| Sun glints twinkle | sparse advected highlights on pixels that are already bright | `glints` (0.12) |
| Ropes, poles, rocks and banks don't move | `static` polygons and `static_hue` are excluded from all water motion | `static`, `static_hue` |

## Workflow

1. **Mask the water** tightly with `water` polygons. Leave out dry rocks and banks. Rocks that stick out of the water go in `static`.
2. **Mark every floating object** (bottles, wrappers, leaves, boats, ducks) in `floaters`. Ellipses are easiest:
   `{"ellipse": [cx, cy, rx, ry, angle_deg]}`, all normalized (rx is a fraction of the width, ry of the height). Use `{"poly": [[x,y],...]}` for odd shapes. Make each ellipse slightly bigger than the object.
3. **Set the flow**: `vanish` at the upstream end and `horizon` where the water reaches the distance. Use `"flow": [1,0]` for a river crossing the frame, or `"away"` if the water runs away from the camera.
4. **Preview the masks**: `--preview-masks`. Water shows blue, floaters yellow, static magenta.
5. **Test with a 1 s static render** (`--move static --duration 1`), then crop the water from two frames about 10 apart and compare them side by side:
   ```bash
   ffmpeg -i t.mp4 -vf "select='eq(n\,10)+eq(n\,20)',crop=860:480:X:Y,tile=1x2" -frames:v 1 crop.jpg
   ```
6. **Fix what you see:**

| Symptom | Fix |
|---|---|
| Streaks / brushed-metal lines along the flow | lower `surface_speed` (0.3–0.5) or `motion_blur`. Raise `flow_period` only if pulsing isn't visible. |
| Visible pulsing (detail fades every cycle) | lower `flow_period` (12–16), raise `detail_sigma` slightly |
| Water looks like wobbling jelly | lower `standing_wave` (0.3–0.5) and `water_strength` |
| Water looks frozen | raise `surface_speed` (0.7–1.0), `standing_wave` 0.9 |
| Trash smears or stretches | add or enlarge its `floaters` ellipse |
| Trash looks glued in place | raise `floater_bob` (1.5) and `floater_drift` (1.5–2.5) |
| Sparkle looks like rain or grain | lower `glints` (0.05–0.1) |
| Calm pond or puddle | `surface_speed` 0.15, `standing_wave` 0.4, `flow` [1,0], `floater_drift` 0.3 |
| Rapids or waterfall | `surface_speed` 0.8–1.2, `motion_blur` 1.5, `flow` [0,1] for a falling sheet |

7. **Render the full clip** and check a contact sheet as described in the cinematic-video skill.

## Limits (tell the user)
The water is built from the photo's own texture. It can't add splashes, foam bursts, spray or objects passing out of frame, and floaters only drift a few pixels. For real fluid simulation, use an AI image-to-video tool. See `../cinematic-video/references/prompting.md`. For water in those prompts, describe the direction, speed and surface: "fast shallow water rippling around rocks, small foam lines travelling toward camera, bottles bobbing and drifting slowly".
