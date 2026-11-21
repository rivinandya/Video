# Prompting AI image-to-video tools

Image-to-video models already see the photo. The prompt should describe **motion and camera**, not repeat what's visible. Use 1–3 sentences in this order:

1. **Camera move, speed and path:** "Slow cinematic dolly pull-out following the red cord…"
2. **Subject motion:** what moves, how, and in which direction. "Water flows toward camera around mossy rocks; plastic bottles and wrappers drift and bob with the current."
3. **Atmosphere:** "Misty god rays shift through the canopy, dust floats in the light, leaves sway gently."
4. **Style and constraints:** "Photorealistic, natural physics, steady camera, consistent lighting, no cuts, 5 seconds."

## Camera vocabulary
| want | say |
|---|---|
| move back | slow dolly pull-out / dolly back / pull back revealing |
| move forward | slow push-in / dolly in |
| sideways | lateral tracking shot / trucking left |
| up | crane up / pedestal up / rising shot |
| follow a line | camera follows along the [cord/path/river] |
| orbit | slow arc / orbit around [subject] |
| handheld feel | subtle handheld drift (otherwise say "locked-off, steady") |
| lens feel | shallow depth of field, 35mm, anamorphic, low angle near the ground |

Speed words matter: "slow", "gentle", "gradual" give smoother output. Use one camera move per clip. Combining moves tends to cause warping.

## Negative / avoid list
(Use where the tool supports a negative prompt, or append "avoid …")
morphing objects, warping, flickering, jitter, sudden cuts, text, watermark, extra limbs, melting, cartoon, oversaturated, fast motion, objects appearing or disappearing.

## Per-tool notes
- **Grok Imagine (xAI):** in the Grok app, go to Imagine, upload the image and type the prompt. Keep the prompt short and motion-focused. The API needs a key from console.x.ai and network access to `api.x.ai`. Check the current docs at docs.x.ai for the endpoint and model name, and don't guess them.
- **Runway (Gen-3/Gen-4):** supports camera-control presets. Pick one or describe it. 5 s or 10 s.
- **Kling:** strong physics for water and cloth. Has a negative prompt field. Use "professional mode" for realism.
- **Google Veo:** follows cinematic language well. Can add audio ("sound of running water, birds").
- **Luma Dream Machine / Sora:** similar prompting. Describe end-frame framing for big reveals.

## Template
> [Speed] cinematic [move] [following/towards SUBJECT]. [Element 1 motion], [element 2 motion]. [Light/atmosphere motion]. Photorealistic, natural motion, [steady/subtle handheld] camera, consistent lighting, [N] seconds.

## Example (forest stream with trash and a red cord)
> Slow cinematic dolly pull-out following the red corrugated cord as it snakes back through a shallow forest stream. Realistic flowing water rippling around mossy rocks, plastic bottles, wrappers and a foam box floating and drifting gently with the current. Misty god rays through the canopy with drifting dust, leaves swaying slightly. Photorealistic, natural motion, steady camera, 5 seconds.

## Finishing an AI clip locally
- Trim: `ffmpeg -i in.mp4 -t 5 -c:v libx264 -crf 16 out.mp4`
- Slow down 1.5×: `ffmpeg -i in.mp4 -vf "minterpolate=fps=60,setpts=1.5*PTS" -r 30 out.mp4`
- Upscale: `ffmpeg -i in.mp4 -vf scale=1920:-2:flags=lanczos out.mp4`
- Match the look of the original photo: compare frame 0 to the photo and adjust with `eq=contrast=..:saturation=..` or `colorbalance`.
