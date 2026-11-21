#!/usr/bin/env python3
"""Turn a still photo into a cinematic camera-move clip (2.5D, no AI model needed).

  python3 cinematic.py IMAGE OUT.mp4 --config scene.json [--move dolly-out] [--duration 5]
  python3 cinematic.py IMAGE masks.jpg --config scene.json --preview-masks

Camera moves: dolly-out, dolly-in, truck-left, truck-right, crane-up, crane-down, static.
All coordinates in the config are normalized (0..1 of width / height). See SKILL.md.
"""
import argparse
import json
import subprocess

import cv2
import numpy as np

# ------------------------------------------------------------------ helpers
_remap = cv2.remap


def remap(img, mx, my, interp=cv2.INTER_LINEAR, border=cv2.BORDER_REPLICATE):
    f = lambda v: np.ascontiguousarray(v, dtype=np.float32)
    return _remap(f(img), f(mx), f(my), interp, borderMode=border)


def blur(m, k):
    k = max(3, int(k) | 1)
    return cv2.GaussianBlur(m.astype(np.float32), (k, k), 0)


def sstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def tile_noise(size, sigma, seed):
    r = np.random.default_rng(seed).standard_normal((size, size))
    k = np.fft.fftfreq(size)[:, None] ** 2 + np.fft.fftfreq(size)[None, :] ** 2
    n = np.real(np.fft.ifft2(np.fft.fft2(r) * np.exp(-k * (2 * np.pi * sigma) ** 2 / 2)))
    return (n / (n.std() + 1e-6)).astype(np.float32)


EASES = {
    "linear": lambda t: t,
    "smooth": lambda t: t * t * (3 - 2 * t),
    "cinematic": lambda t: 0.55 * t * t * (3 - 2 * t) + 0.45 * t,  # soft start/stop, steady middle
}


# ------------------------------------------------------------------ scene setup
class Scene:
    def __init__(self, img_path, cfg):
        self.cfg = cfg
        src = cv2.imread(img_path)
        if src is None:
            raise SystemExit(f"cannot read {img_path}")
        self.src = src.astype(np.float32) / 255.0
        H, W = self.src.shape[:2]
        self.H, self.W = H, W
        self.yy, self.xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.feather = cfg.get("feather", 0.025) * W
        self.lum = cv2.cvtColor(self.src, cv2.COLOR_BGR2GRAY)
        self._masks()
        self._depth()

    def px(self, pt):
        return (pt[0] * self.W, pt[1] * self.H)

    def poly_mask(self, polys, feather=None):
        m = np.zeros((self.H, self.W), np.float32)
        for p in polys or []:
            pts = np.array([self.px(q) for q in p], np.int32)
            cv2.fillPoly(m, [pts], 1.0)
        return blur(m, feather or self.feather) if m.any() else m

    def _masks(self):
        c = self.cfg
        static = self.poly_mask(c.get("static"), self.feather * 0.3)
        hue = c.get("static_hue")
        if hue:
            hsv = cv2.cvtColor((self.src * 255).astype(np.uint8), cv2.COLOR_BGR2HSV)
            sel = np.zeros((self.H, self.W), bool)
            for lo, hi in hue.get("ranges", [[0, 10], [165, 180]]):
                sel |= (hsv[..., 0] >= lo) & (hsv[..., 0] <= hi)
            sel &= (hsv[..., 1] >= hue.get("min_sat", 110)) & (hsv[..., 2] >= hue.get("min_val", 40))
            m = sel.astype(np.uint8) * 255
            for p in hue.get("ignore", []):  # areas where this hue is NOT the static object
                cv2.fillPoly(m, [np.array([self.px(q) for q in p], np.int32)], 0)
            m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
            n, lab, st, _ = cv2.connectedComponentsWithStats(m)
            keep = np.zeros((self.H, self.W), np.float32)
            min_area = hue.get("min_area", 0.0016) * self.W * self.H
            for i in range(1, n):
                if st[i, cv2.CC_STAT_AREA] > min_area:
                    keep[lab == i] = 1
            keep = blur(cv2.dilate(keep, np.ones((7, 7), np.uint8)), 9)
            static = np.maximum(static, keep)
        self.static = static
        self.water = self.poly_mask(c.get("water")) * (1 - static)
        self.sway = self.poly_mask(c.get("sway"), self.feather * 2) * (1 - static)
        self.hilite = sstep(0.45, 0.85, self.lum)

    def _depth(self):
        c, H = self.cfg, self.H
        hz = c.get("horizon", 0.3) * H
        d = np.clip((self.yy - hz) / (H - hz), 0, 1) ** c.get("depth_gamma", 0.85)
        near = self.poly_mask(c.get("near"), self.feather * 2)
        far = self.poly_mask(c.get("far"), self.feather * 2)
        d = np.maximum(d, 0.8 * near) * (1 - 0.8 * far)
        self.depth = blur(d, self.W * 0.05)
        self.Z = 1.0 / (0.2 + 0.8 * self.depth)  # near = 1 .. far = 5

    def preview(self, out):
        ov = self.src.copy()
        ov = ov * (1 - 0.5 * self.water[..., None]) + 0.5 * self.water[..., None] * np.array([0.9, 0.6, 0.0])
        ov = ov * (1 - 0.6 * self.static[..., None]) + 0.6 * self.static[..., None] * np.array([1.0, 0.0, 1.0])
        ov = ov * (1 - 0.4 * self.sway[..., None]) + 0.4 * self.sway[..., None] * np.array([0.0, 1.0, 0.0])
        dep = cv2.applyColorMap((self.depth * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
        fx, fy = self.px(self.cfg.get("focus", [0.5, 0.5]))
        ov = (np.clip(ov, 0, 1) * 255).astype(np.uint8)
        cv2.drawMarker(ov, (int(fx), int(fy)), (0, 255, 255), cv2.MARKER_CROSS, 40, 3)
        sheet = np.vstack([ov, dep])
        cv2.imwrite(out, sheet)
        print(f"wrote {out}  (top: blue=water, magenta=static, green=sway, cross=focus; bottom: depth, bright=near)")


# ------------------------------------------------------------------ renderer
def render(sc, args):
    c = sc.cfg
    W, H, xx, yy = sc.W, sc.H, sc.xx, sc.yy
    OW, OH = map(int, args.size.split("x"))
    N = int(round(args.fps * args.duration))
    rng = np.random.default_rng(c.get("seed", 7))
    fx0, fy0 = sc.px(c.get("focus", [0.5, 0.5]))
    ease = EASES[args.ease]

    # ---- water flow field
    T = 512
    NZ = [tile_noise(T, s, i) for i, s in enumerate([22, 9, 4, 2.2, 40])]
    VX, VY = sc.px(c.get("vanish", [0.5, c.get("horizon", 0.3)]))
    fx, fy = xx - VX, yy - VY
    fl = np.sqrt(fx * fx + fy * fy) + 1e-3
    fx, fy = fx / fl, fy / fl
    flow_dir = c.get("flow", "toward")  # toward camera, away, or [dx, dy]
    if flow_dir == "away":
        fx, fy = -fx, -fy
    elif isinstance(flow_dir, list):
        fx = np.full_like(xx, flow_dir[0]); fy = np.full_like(xx, flow_dir[1])
    ws = c.get("water_strength", 1.0)
    speed = (0.6 + 4.5 * sc.depth) * c.get("water_speed", 1.0) * (W / 1672)
    persp = 0.35 + 0.65 * sc.depth
    ux, uy = -fy, fx
    bu = (xx * ux + yy * uy) / persp / 1.6
    bv = (xx * fx + yy * fy) / persp

    def advect(nz, tp):
        return remap(nz, bu % T, (bv - tp * speed / persp) % T, border=cv2.BORDER_WRAP)

    # ---- light rays + dust
    rays_cfg = c.get("rays")
    warm = np.array(c.get("light_bgr", [0.62, 0.86, 1.0]), np.float32)
    if rays_cfg:
        RX, RY = sc.px(rays_cfg.get("source", [0.9, -0.15]))
        ang = np.arctan2(yy - RY, xx - RX)
        rdist = np.sqrt((xx - RX) ** 2 + (yy - RY) ** 2) / W
        zone = sc.poly_mask(rays_cfg.get("zone"), sc.feather * 4) if rays_cfg.get("zone") \
            else sstep(0.66 * H, 0.15 * H, yy)
        existing = sstep(0.30, 0.6, blur(sc.lum, 31)) * zone
        rstr = rays_cfg.get("strength", 0.06)
    nd = int(c.get("dust", 60 if rays_cfg else 0))
    if nd:
        dz = c.get("dust_box", [0.35, 0.04, 0.95, 0.6])
        dust = np.stack([rng.uniform(dz[0], dz[2], nd) * W, rng.uniform(dz[1], dz[3], nd) * H,
                         rng.uniform(0.6, 2.2, nd) * W / 1672, rng.uniform(0, 2 * np.pi, nd),
                         rng.uniform(0.2, 1.0, nd)], 1)

    # ---- camera
    mv, amt = args.move, args.amount
    defaults = {"dolly-out": 0.3, "dolly-in": 0.3, "truck-left": 0.035, "truck-right": 0.035,
                "crane-up": 0.03, "crane-down": 0.03, "static": 0}
    amt = defaults[mv] if amt is None else amt
    tmax = amt if mv.startswith(("truck", "crane")) else 0
    margin = 1.0 + 2.2 * tmax + 0.035
    ogx, ogy = np.meshgrid(np.linspace(0, W - 1, OW, dtype=np.float32),
                           np.linspace(0, H - 1, OH, dtype=np.float32))
    shake = c.get("handheld", 1.0) * W / 1672

    def cam(t):
        e = ease(t)
        D = {"dolly-out": amt * (1 - e), "dolly-in": amt * e}.get(mv, 0.0)
        s = e - 0.5
        Tx = {"truck-left": amt * s, "truck-right": -amt * s}.get(mv, 0.0) * W
        Ty = {"crane-up": amt * s, "crane-down": -amt * s}.get(mv, 0.0) * H
        jx = shake * (0.6 * np.sin(t * 7.1) + 0.4 * np.sin(t * 13.3 + 1))
        jy = shake * (0.5 * np.sin(t * 5.3 + 2) + 0.3 * np.sin(t * 11.7))
        qx = fx0 + (ogx - fx0) / margin + jx
        qy = fy0 + (ogy - fy0) / margin + jy
        px, py = qx.copy(), qy.copy()
        for _ in range(3):  # fixed-point inverse of depth-dependent warp
            z = remap(sc.Z, np.clip(px, 0, W - 1), np.clip(py, 0, H - 1))
            m = z / np.maximum(z - D, 0.05)
            par = 1.0 / z  # parallax: near objects move most
            px = fx0 + (qx - fx0) / m - Tx * par
            py = fy0 + (qy - fy0) / m + Ty * par
        return np.clip(px, 0, W - 1.001), np.clip(py, 0, H - 1.001)

    # ---- encoder
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{OW}x{OH}", "-r", str(args.fps), "-i", "-", "-c:v", "libx264",
           "-preset", "slow", "-crf", str(args.crf), "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", args.out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    sw_amp = c.get("sway_strength", 1.0) * W / 1672
    grain = c.get("grain", 0.008)

    for f in range(N):
        t = f / max(N - 1, 1)
        sec = f / args.fps
        dx = np.zeros_like(xx); dy = np.zeros_like(xx)
        frame = sc.src
        if sc.water.any():
            n1, n2, n3 = advect(NZ[0], f), advect(NZ[1], f * 1.15), advect(NZ[2], f * 1.3)
            bob = advect(NZ[4], f * 0.5)
            a = sc.water * (0.5 + 2.6 * sc.depth) * ws * W / 1672
            lat = 0.55 * n2 + 0.35 * n3 + 0.6 * bob
            dx += a * (lat * ux + 0.5 * n1 * fx)
            dy += a * (lat * uy + 0.5 * n1 * fy)
        if sc.sway.any():
            s = sc.sway * sw_amp * (1.6 * np.sin(2 * np.pi * sec / 3.1 + yy / (0.15 * H)) +
                                    0.6 * np.sin(2 * np.pi * sec / 1.3 + xx / (0.054 * W)))
            dx += s; dy += 0.4 * s
        if sc.water.any() or sc.sway.any():
            frame = remap(sc.src, xx + dx, yy + dy, cv2.INTER_CUBIC, cv2.BORDER_REFLECT)
        if sc.water.any():
            g = advect(NZ[3], f * 1.6)
            glint = np.clip(g - 1.2, 0, None) ** 2 * (0.25 + sc.hilite) * sc.water * (0.3 + 0.7 * sc.depth)
            frame = frame * (1 + 0.22 * ws * n3 * sc.hilite * sc.water)[..., None] \
                + (0.30 * glint)[..., None] * warm
        if rays_cfg:
            r = 0.5 + 0.5 * np.sin(ang * 46 + 0.35 * sec + np.sin(ang * 13 - 0.25 * sec) * 1.4)
            r *= 0.5 + 0.5 * np.sin(ang * 19 - 0.2 * sec + 1.7)
            r = blur(r, 9) * zone * np.exp(-rdist * 0.9)
            br = 0.85 + 0.15 * np.sin(2 * np.pi * sec / 4.3)
            light = rstr * br * r + rstr * 0.8 * existing * (br - 0.85) / 0.15
            frame = 1 - (1 - frame) * (1 - light[..., None] * warm)
        if nd:
            dl = np.zeros((H, W), np.float32)
            for x0, y0, rr, ph, a in dust:
                x = x0 + 9 * sec * a + 6 * np.sin(sec * 0.9 + ph)
                y = y0 - 4 * sec * a + 5 * np.sin(sec * 1.3 + ph * 2)
                cv2.circle(dl, (int(x), int(y)), int(np.ceil(rr)),
                           float(a * (0.5 + 0.5 * np.sin(sec * 2.5 + ph * 3))), -1, cv2.LINE_AA)
            boost = (0.3 + existing + 0.5 * zone) if rays_cfg else 1.0
            frame = frame + (0.35 * blur(dl, 5) * boost)[..., None] * warm
        mx, my = cam(t)
        out = remap(np.clip(frame, 0, 1), mx, my, cv2.INTER_LANCZOS4)
        out = out + 0.35 * (out - cv2.GaussianBlur(out, (0, 0), 1.2))
        if grain:
            out += rng.normal(0, grain, out.shape[:2]).astype(np.float32)[..., None]
        ff.stdin.write((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
        if f % 30 == 0:
            print(f"frame {f}/{N}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("wrote", args.out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--config", help="scene JSON (masks, depth hints, effects)")
    ap.add_argument("--move", default="dolly-out",
                    choices=["dolly-out", "dolly-in", "truck-left", "truck-right",
                             "crane-up", "crane-down", "static"])
    ap.add_argument("--amount", type=float, help="move strength (dolly ~0.15-0.4, truck/crane ~0.02-0.05)")
    ap.add_argument("--duration", type=float, default=5.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--ease", default="cinematic", choices=list(EASES))
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--preview-masks", action="store_true", help="write a mask/depth check image instead")
    args = ap.parse_args()
    cfg = json.load(open(args.config)) if args.config else {}
    sc = Scene(args.image, cfg)
    if args.preview_masks:
        sc.preview(args.out)
    else:
        render(sc, args)


if __name__ == "__main__":
    main()
