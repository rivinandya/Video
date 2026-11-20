#!/usr/bin/env python3
"""Render a 5s 'slow dolly pull-out following the cord' clip from a still photo.

2.5D approach:
  * hand-tuned depth map -> parallax dolly (near ground shrinks faster than far forest)
  * water mask -> advected noise displacement (ripples flowing toward camera),
    flickering specular glints, slight bobbing of floating trash
  * animated god-rays, drifting dust motes, gentle leaf sway, film grain
Usage: python3 render.py [src.png] [out.mp4]
"""
import subprocess
import sys

import cv2
import numpy as np

SRC = sys.argv[1] if len(sys.argv) > 1 else "src/source.png"
OUT = sys.argv[2] if len(sys.argv) > 2 else "stream_dolly_out.mp4"
FPS, DUR = 30, 5.0
OW, OH = 1920, 1080
N = int(FPS * DUR)
rng = np.random.default_rng(7)

src = cv2.imread(SRC).astype(np.float32) / 255.0
H, W = src.shape[:2]
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)


_remap = cv2.remap
def _r(img, mx, my, *a, **k):
    f32 = lambda v: np.ascontiguousarray(v, dtype=np.float32)
    return _remap(f32(img), f32(mx), f32(my), *a, **k)
cv2.remap = _r


def smooth(m, k):
    k = int(k) | 1
    return cv2.GaussianBlur(m, (k, k), 0)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- masks
sx, sy = W / 1672.0, H / 941.0
def P(pts):
    return np.array([(x * sx, y * sy) for x, y in pts], np.int32)

water = np.zeros((H, W), np.uint8)
cv2.fillPoly(water, [P([(600, 941), (640, 760), (760, 620), (830, 500), (900, 420),
                        (960, 330), (1050, 295), (1200, 290), (1300, 330), (1260, 380),
                        (1380, 425), (1672, 440), (1672, 941)])], 255)
# far stream + channel between the left rocks
cv2.fillPoly(water, [P([(760, 330), (900, 300), (1060, 285), (1220, 285), (1250, 310),
                        (1000, 340), (880, 400), (820, 440), (760, 400)])], 255)
cv2.fillPoly(water, [P([(470, 470), (560, 440), (700, 425), (830, 470), (800, 540),
                        (700, 500), (600, 490), (520, 500)])], 160)
water = smooth(water.astype(np.float32) / 255.0, 41)

hsv = cv2.cvtColor((src * 255).astype(np.uint8), cv2.COLOR_BGR2HSV)
red = (((hsv[..., 0] < 10) | (hsv[..., 0] > 165)) & (hsv[..., 1] > 110) & (hsv[..., 2] > 40))
red = red.astype(np.uint8) * 255
red[:, int(1050 * sx):] = 0                      # the red wrapper is trash, not cord
red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
n, lab, stats, _ = cv2.connectedComponentsWithStats(red)
cord = np.zeros((H, W), np.float32)
for i in range(1, n):
    if stats[i, cv2.CC_STAT_AREA] > 2500:
        cord[lab == i] = 1
cord = smooth(cv2.dilate(cord, np.ones((7, 7), np.uint8)), 9)
water = water * (1 - cord)

lum = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
hilite = smoothstep(0.45, 0.85, lum)             # pixels that already glint

leaves = np.zeros((H, W), np.float32)
cv2.fillPoly(leaves, [P([(0, 0), (330, 0), (330, 120), (280, 330), (190, 430), (0, 470)])], 1)
leaves = smooth(leaves, 61)

# ---------------------------------------------------------------- depth (0 far .. 1 near)
VX, VY = 1100 * sx, 270 * sy                     # vanishing area of the stream
depth = np.clip((yy - VY) / (H - VY), 0, 1) ** 0.85
depth = np.maximum(depth, 0.75 * leaves)
depth = smooth(depth, 81)
Z = 1.0 / (0.2 + 0.8 * depth)                    # near=1 .. far=5

# ---------------------------------------------------------------- tileable noise
def tile_noise(size, sigma, seed):
    r = np.random.default_rng(seed).standard_normal((size, size)).astype(np.float32)
    f = np.fft.fft2(r)
    k = np.fft.fftfreq(size)[:, None] ** 2 + np.fft.fftfreq(size)[None, :] ** 2
    n_ = np.real(np.fft.ifft2(f * np.exp(-k * (2 * np.pi * sigma) ** 2 / 2))).astype(np.float32)
    return n_ / (n_.std() + 1e-6)

T = 512
NZ = [tile_noise(T, s, i) for i, s in enumerate([22, 9, 4, 2.2, 40])]

# flow: radiates from the vanishing area toward the camera, faster when near
fx, fy = xx - VX, yy - VY
fl = np.sqrt(fx * fx + fy * fy) + 1e-3
fx, fy = fx / fl, fy / fl
speed = (0.6 + 4.5 * depth)                       # px per frame at source res
persp = 0.35 + 0.65 * depth                       # ripples shrink into the distance
# noise coords: stretch across flow so ripples are wider than long
ux, uy = -fy, fx
base_u = (xx * ux + yy * uy) / persp / 1.6
base_v = (xx * fx + yy * fy) / persp


def advect(nz, t_px, scale):
    mu = (base_u / scale) % T
    mv = ((base_v - t_px * speed / persp) / scale) % T
    return cv2.remap(nz, mu.astype(np.float32), mv.astype(np.float32),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)

# ---------------------------------------------------------------- light rays
RX, RY = 1500 * sx, -150 * sy                     # sun behind upper-right canopy
ang = np.arctan2(yy - RY, xx - RX)
rdist = np.sqrt((xx - RX) ** 2 + (yy - RY) ** 2) / W
ray_zone = smoothstep(620 * sy, 150 * sy, yy) * smoothstep(250 * sx, 900 * sx, xx)
existing_rays = smoothstep(0.30, 0.6, smooth(lum, 31)) * ray_zone

# dust motes
ND = 70
dust = np.stack([rng.uniform(600, 1600, ND) * sx, rng.uniform(40, 560, ND) * sy,
                 rng.uniform(0.6, 2.2, ND), rng.uniform(0, 2 * np.pi, ND),
                 rng.uniform(0.2, 1.0, ND)], 1)

# ---------------------------------------------------------------- camera
CX, CY = 830 * sx, 470 * sy                       # dolly focus: bend of the cord
D0 = 0.30                                         # how far forward the camera starts


def ease(t):
    s = t * t * (3 - 2 * t)
    return 0.55 * s + 0.45 * t


ogx, ogy = np.meshgrid(np.linspace(0, W - 1, OW, dtype=np.float32),
                       np.linspace(0, H - 1, OH, dtype=np.float32))


def camera_maps(t):
    e = ease(t)
    D = D0 * (1 - e)
    margin = 1.035
    # slight drift: start a touch right/up along the cord, settle centred
    shx = (1 - e) * 18 * sx + 0.6 * np.sin(t * 7.1) + 0.4 * np.sin(t * 13.3 + 1)
    shy = (1 - e) * -10 * sy + 0.5 * np.sin(t * 5.3 + 2) + 0.3 * np.sin(t * 11.7)
    qx = CX + (ogx - CX) / margin + shx
    qy = CY + (ogy - CY) / margin + shy
    px, py = qx.copy(), qy.copy()
    for _ in range(3):  # fixed-point inverse of depth-dependent magnification
        z = cv2.remap(Z, px, py, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        m = z / np.maximum(z - D, 0.05)
        px = CX + (qx - CX) / m
        py = CY + (qy - CY) / m
    return np.clip(px, 0, W - 1.001), np.clip(py, 0, H - 1.001)


# ---------------------------------------------------------------- render
ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo",
                       "-pix_fmt", "bgr24", "-s", f"{OW}x{OH}", "-r", str(FPS), "-i", "-",
                       "-c:v", "libx264", "-preset", "slow", "-crf", "15",
                       "-pix_fmt", "yuv420p", "-movflags", "+faststart", OUT],
                      stdin=subprocess.PIPE)

warm = np.array([0.62, 0.86, 1.0], np.float32)    # BGR warm sunlight
for f in range(N):
    t = f / (N - 1)
    sec = f / FPS
    # --- water displacement
    n1 = advect(NZ[0], f, 1.0)
    n2 = advect(NZ[1], f * 1.15, 1.0)
    n3 = advect(NZ[2], f * 1.3, 1.0)
    bob = advect(NZ[4], f * 0.5, 1.0)
    amp = water * (0.5 + 2.6 * depth)
    dx = amp * (0.55 * n2 + 0.35 * n3 + 0.6 * bob) * ux + amp * 0.5 * n1 * fx
    dy = amp * (0.55 * n2 + 0.35 * n3 + 0.6 * bob) * uy + amp * 0.5 * n1 * fy
    # --- leaf sway
    sway = leaves * (1.6 * np.sin(2 * np.pi * sec / 3.1 + yy / 140) +
                     0.6 * np.sin(2 * np.pi * sec / 1.3 + xx / 90))
    dx += sway
    dy += 0.4 * sway
    frame = cv2.remap(src, xx + dx, yy + dy, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)

    # --- shimmering glints on the moving water
    g = advect(NZ[3], f * 1.6, 1.0)
    glint = np.clip(g - 1.2, 0, None) ** 2 * (0.25 + hilite) * water * (0.3 + 0.7 * depth)
    flick = 1 + 0.22 * n3 * hilite * water
    frame = frame * flick[..., None] + (0.30 * glint)[..., None] * warm

    # --- god rays breathing / slowly sweeping
    rays = (0.5 + 0.5 * np.sin(ang * 46 + 0.35 * sec + np.sin(ang * 13 - 0.25 * sec) * 1.4))
    rays *= (0.5 + 0.5 * np.sin(ang * 19 - 0.2 * sec + 1.7))
    rays = smooth(rays.astype(np.float32), 9) * ray_zone * np.exp(-rdist * 0.9)
    breathe = 0.85 + 0.15 * np.sin(2 * np.pi * sec / 4.3)
    light = 0.06 * breathe * rays + 0.05 * existing_rays * (breathe - 0.85) / 0.15
    frame = 1 - (1 - frame) * (1 - light[..., None] * warm)

    # --- dust in the beams
    dl = np.zeros((H, W), np.float32)
    for x0, y0, r, ph, a in dust:
        x = x0 + 9 * sec * a + 6 * np.sin(sec * 0.9 + ph)
        y = y0 - 4 * sec * a + 5 * np.sin(sec * 1.3 + ph * 2)
        tw = 0.5 + 0.5 * np.sin(sec * 2.5 + ph * 3)
        cv2.circle(dl, (int(x), int(y)), int(np.ceil(r)), float(a * tw), -1, cv2.LINE_AA)
    dl = smooth(dl, 5) * (0.3 + existing_rays + 0.5 * ray_zone)
    frame = frame + (0.35 * dl)[..., None] * warm

    # --- camera
    mx, my = camera_maps(t)
    out = cv2.remap(np.clip(frame, 0, 1), mx, my, cv2.INTER_LANCZOS4)
    blur = cv2.GaussianBlur(out, (0, 0), 1.2)
    out = out + 0.35 * (out - blur)                       # gentle re-sharpen after upscale
    out += rng.normal(0, 0.008, out.shape[:2]).astype(np.float32)[..., None]  # grain
    ff.stdin.write((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
    if f % 15 == 0:
        print(f"frame {f}/{N}", flush=True)

ff.stdin.close()
ff.wait()
print("wrote", OUT)
