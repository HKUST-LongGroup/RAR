"""Build the visual assets of README.md.

GitHub strips CSS from READMEs, so the tricolour "RAR" wordmark, the buttons and the demos are images.
Outputs (static/readme/):
  title_{light,dark}.svg            gradient "RAR" (glow + slow sheen) and the full title, text as paths
  btn_{page,arxiv}_{light,dark}.svg        link buttons in the style of the project page
  teaser.webp                       rate-switching clips (Doom / CS2 / FPV) with their live target-FPS curves
  multirate.webp                    three rollout rates per environment on one physical clock

Usage:
    pip install fonttools uharfbuzz pillow numpy imageio-ffmpeg
    python scripts/make_readme_assets.py            # everything
    python scripts/make_readme_assets.py svg        # only the SVGs
"""
from __future__ import annotations

import io
import json
import math
import re
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image, ImageDraw, ImageFont

PAGE = Path(__file__).resolve().parents[1]
OUT = PAGE / "static" / "readme"
FONTS = Path(__file__).resolve().parent / "fonts"
INTER_TIGHT = FONTS / "InterTight-VF.ttf"      # SIL OFL, same face as the page title
INTER = FONTS / "Inter-VF.ttf"                 # SIL OFL
ARXIV_SVG = Path(__file__).resolve().parent / "icons" / "arxiv.svg"   # Academicons (SIL OFL)

THEME = {
    "light": {
        "ink": "#1d2230", "top": "#C01F6E", "mid": "#3B4DB7", "bottom": "#23893B", "btn": "#1d2230",
        "grad": [(0, "#d2387f"), (.16, "#C01F6E"), (.36, "#6a3aa2"), (.52, "#3B4DB7"), (.68, "#2e7f8a"), (.86, "#2FA34A"), (1, "#45b35f")],
        "glow": .34, "shade_dark": .10,
    },
    "dark": {
        "ink": "#e6e8ee", "top": "#ec5c9f", "mid": "#8c99f2", "bottom": "#57c771", "btn": "#3a3e49",
        "grad": [(0, "#e4579a"), (.16, "#d0337f"), (.36, "#8455c4"), (.52, "#5f70dc"), (.68, "#3d9aa6"), (.86, "#3cbb5b"), (1, "#5fcf79")],
        "glow": .5, "shade_dark": 0,
    },
}
BRIGHT = {"doom": (236, 92, 159), "cs2": (140, 153, 242), "fpv": (87, 199, 113)}   # dark-theme inks
ENV_NAME = {"doom": "Doom", "cs2": "CS2", "fpv": "FPV"}


def fmt(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ---------------------------------------------------------------- text -> SVG paths
class Face:
    def __init__(self, path: Path, wght: float, opsz: float | None = None):
        tt = TTFont(path)
        axes = {a.axisTag for a in tt["fvar"].axes}
        loc = {"wght": wght}
        if opsz is not None and "opsz" in axes:
            loc["opsz"] = opsz
        inst = instantiateVariableFont(tt, loc)
        buf = io.BytesIO()
        inst.save(buf)
        data = buf.getvalue()
        self.tt = TTFont(io.BytesIO(data))
        self.gs = self.tt.getGlyphSet()
        self.order = self.tt.getGlyphOrder()
        self.upem = self.tt["head"].unitsPerEm
        self.cap = self.tt["OS/2"].sCapHeight / self.upem
        self.hb = hb.Font(hb.Face(hb.Blob(data)))

    def shape(self, text: str, size: float, tracking: float = 0.0):
        """-> ([(glyph name, char index, x, y)], advance width) for a run starting at x = 0."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf, {"kern": True, "liga": True})
        s = size / self.upem
        x, out = 0.0, []
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            out.append((self.order[info.codepoint], info.cluster, x + pos.x_offset * s, pos.y_offset * s))
            x += pos.x_advance * s + tracking * size
        return out, x - tracking * size

    def path(self, glyph: str, x: float, baseline: float, size: float) -> str:
        pen = SVGPathPen(self.gs, ntos=fmt)
        s = size / self.upem
        self.gs[glyph].draw(TransformPen(pen, (s, 0, 0, -s, x, baseline)))
        return pen.getCommands()


def text_paths(face: Face, text: str, size: float, x0: float, baseline: float, tracking: float = 0.0,
               color_of=lambda i: "ink") -> dict[str, str]:
    glyphs, _ = face.shape(text, size, tracking)
    groups: dict[str, list[str]] = {}
    for g, ci, x, y in glyphs:
        groups.setdefault(color_of(ci), []).append(face.path(g, x0 + x, baseline - y, size))
    return {k: "".join(v) for k, v in groups.items()}


def css_gradient_line(deg: float, x: float, y: float, w: float, h: float):
    """Endpoints of a CSS linear-gradient(deg) over the box (x, y, w, h)."""
    a = math.radians(deg)
    dx, dy = math.sin(a), -math.cos(a)
    half = (abs(w * dx) + abs(h * dy)) / 2
    cx, cy = x + w / 2, y + h / 2
    return cx - dx * half, cy - dy * half, cx + dx * half, cy + dy * half


def title_svg(theme: str) -> str:
    T = THEME[theme]
    W = 1000
    word = Face(INTER_TIGHT, 700)
    sub = Face(INTER, 700, opsz=32)
    size, track = 176, -0.03
    _, ww = word.shape("RAR", size, track)
    x0, top = (W - ww) / 2, 40
    cap = word.cap * size
    base = top + cap
    rar = text_paths(word, "RAR", size, x0, base, track)["ink"]

    lines = ["Rate-Adaptive Rollout for", "Time-Consistent Interactive World Models"]
    initials = {0: "top", 5: "mid", 14: "bottom"}          # R, A, R of the first line
    sub_size, b1 = 36, base + 78
    b2 = b1 + 50
    groups: dict[str, str] = {}
    for li, (text, b) in enumerate(zip(lines, (b1, b2))):
        _, lw = sub.shape(text, sub_size)
        color = (lambda i: initials.get(i, "ink")) if li == 0 else (lambda i: "ink")
        for k, d in text_paths(sub, text, sub_size, (W - lw) / 2, b, color_of=color).items():
            groups[k] = groups.get(k, "") + d
    H = round(b2 + 22)

    gx1, gy1, gx2, gy2 = css_gradient_line(115, x0, top, ww, cap)
    stops = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in T["grad"])
    shade = (f'<stop offset="0" stop-color="#fff" stop-opacity=".20"/><stop offset=".48" stop-color="#fff" stop-opacity="0"/>'
             + (f'<stop offset="1" stop-color="#000" stop-opacity="{T["shade_dark"]}"/>' if T["shade_dark"] else ""))
    mv = 0.75 * ww
    sheen = (f'<linearGradient id="sheen" gradientUnits="userSpaceOnUse" x1="{fmt(x0)}" y1="{fmt(top)}" '
             f'x2="{fmt(x0 + ww)}" y2="{fmt(top + 0.27 * ww)}">'
             '<stop offset=".42" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".42"/>'
             '<stop offset=".58" stop-color="#fff" stop-opacity="0"/>'
             f'<animateTransform attributeName="gradientTransform" type="translate" dur="9s" repeatCount="indefinite" '
             f'values="{fmt(-mv)} 0;{fmt(-mv)} 0;{fmt(mv)} 0;{fmt(mv)} 0" keyTimes="0;.62;.92;1" calcMode="spline" '
             'keySplines="0 0 1 1;.45 0 .25 1;0 0 1 1"/></linearGradient>')
    body = "".join(f'<path fill="{T[k]}" d="{d}"/>' for k, d in groups.items())
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
        f'<title>RAR: Rate-Adaptive Rollout for Time-Consistent Interactive World Models</title><defs>'
        f'<linearGradient id="g" gradientUnits="userSpaceOnUse" x1="{fmt(gx1)}" y1="{fmt(gy1)}" x2="{fmt(gx2)}" y2="{fmt(gy2)}">{stops}</linearGradient>'
        f'<linearGradient id="shade" gradientUnits="userSpaceOnUse" x1="0" y1="{fmt(top)}" x2="0" y2="{fmt(base)}">{shade}</linearGradient>'
        f'{sheen}<filter id="glow" x="-25%" y="-45%" width="150%" height="190%"><feGaussianBlur stdDeviation="26"/></filter></defs>'
        f'<g filter="url(#glow)" opacity="{T["glow"]}"><path transform="translate(0 14)" fill="url(#g)" d="{rar}"/></g>'
        f'<path fill="url(#g)" d="{rar}"/><path fill="url(#shade)" d="{rar}"/><path fill="url(#sheen)" d="{rar}"/>'
        f'{body}</svg>'
    )


# ---------------------------------------------------------------- buttons
GITHUB = ("M12 .5a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.37-3.88-1.37-.53-1.33-1.28-1.69-1.28-1.69"
          "-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.56-.29-5.25-1.28"
          "-5.25-5.68 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17"
          "-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.83 1.19 3.09 0 4.41-2.7 5.38-5.26 5.67.41.36.78 1.06.78 2.14v3.17"
          "c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .5z")


def icon_svg(kind: str, x: float, y: float, s: float, color: str) -> str:
    if kind == "page":
        sw = 1.9
        return (f'<g transform="translate({fmt(x)} {fmt(y)}) scale({fmt(s / 24)})" fill="none" stroke="{color}" '
                f'stroke-width="{sw}" stroke-linecap="round"><circle cx="12" cy="12" r="9.5"/>'
                '<ellipse cx="12" cy="12" rx="4.2" ry="9.5"/><path d="M2.8 9h18.4M2.8 15h18.4"/></g>')
    if kind == "code":
        return f'<g transform="translate({fmt(x)} {fmt(y)}) scale({fmt(s / 24)})"><path fill="{color}" d="{GITHUB}"/></g>'
    src = ARXIV_SVG.read_text(encoding="utf-8")
    d = re.search(r'\sd="([^"]+)"', src).group(1)
    tr = re.search(r'transform="([^"]+)"', src).group(1)
    return (f'<svg x="{fmt(x)}" y="{fmt(y)}" width="{fmt(s)}" height="{fmt(s)}" viewBox="0 0 448 512">'
            f'<g transform="{tr}"><path fill="{color}" d="{d}"/></g></svg>')


def button_svg(kind: str, label: str, theme: str, tag: str | None = None) -> str:
    T = THEME["dark"]                                   # icons use the bright inks on both themes
    face, tag_face = Face(INTER, 600, opsz=15), Face(INTER, 600, opsz=11)
    H, pad, isz, gap, fs = 38, 17, 18, 9, 15.5
    _, lw = face.shape(label, fs)
    tw = 0.0
    if tag:
        _, tlw = tag_face.shape(tag, 11)
        tw = 8 + tlw + 14
    W = round(pad + isz + gap + lw + tw + pad)
    base = H / 2 + face.cap * fs / 2
    color = {"page": T["top"], "arxiv": T["mid"], "code": T["bottom"]}[kind]
    txt = text_paths(face, label, fs, pad + isz + gap, base)["ink"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
           f'<rect width="{W}" height="{H}" rx="{H / 2}" fill="{THEME[theme]["btn"]}"/>',
           icon_svg(kind, pad, (H - isz) / 2, isz, color),
           f'<path fill="#fff" d="{txt}"/>']
    if tag:
        tx = pad + isz + gap + lw + 8
        out.append(f'<rect x="{fmt(tx)}" y="{fmt(H / 2 - 9)}" width="{fmt(tw - 8)}" height="18" rx="9" fill="#fff" fill-opacity=".14"/>')
        tb = H / 2 + tag_face.cap * 11 / 2
        out.append(f'<path fill="#fff" fill-opacity=".78" d="{text_paths(tag_face, tag, 11, tx + 7, tb)["ink"]}"/>')
    out.append("</svg>")
    return "".join(out)


def build_svgs() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for theme in ("light", "dark"):
        (OUT / f"title_{theme}.svg").write_text(title_svg(theme), encoding="utf-8")
        for kind, label, tag in (("page", "Project Page", None), ("arxiv", "arXiv", None)):
            (OUT / f"btn_{kind}_{theme}.svg").write_text(button_svg(kind, label, theme, tag), encoding="utf-8")
    for p in sorted(OUT.glob("*.svg")):
        print(f"[svg] {p.relative_to(PAGE)} ({p.stat().st_size // 1024} KB)")


# ---------------------------------------------------------------- raster helpers
R = 2                                                    # render scale; frames are downsampled at the end
CARD, CARD_LINE = (21, 23, 28, 255), (44, 47, 55, 255)


def pil_font(path: Path, size: float, wght: float) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(path), round(size * R))
    vals = []
    for a in f.get_variation_axes():
        name = a["name"] if isinstance(a["name"], str) else a["name"].decode()
        if name.lower().startswith("weight"):
            vals.append(wght)
        elif "optical" in name.lower():
            vals.append(min(max(size, a["minimum"]), a["maximum"]))
        else:
            vals.append(a["default"])
    f.set_variation_by_axes(vals)
    return f


def rounded_mask(w: int, h: int, r: int) -> Image.Image:
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    return m


def pill(draw: ImageDraw.ImageDraw, xy, text_parts, anchor="lt", bg=(10, 12, 18, 170)):
    """Draw a pill with [(text, font, fill)] parts; xy is its top-left (anchor lt) or top-right (rt) or bottom-right (rb)."""
    padx, pady, gap = 8 * R, 4 * R, 5 * R
    widths = [draw.textlength(t, font=f) for t, f, _ in text_parts]
    asc = max(f.getmetrics()[0] for _, f, _ in text_parts)
    w = sum(widths) + gap * (len(text_parts) - 1) + 2 * padx
    h = asc + 2 * pady
    x, y = xy
    if anchor[0] == "r":
        x -= w
    if anchor[1] == "b":
        y -= h
    draw.rounded_rectangle((x, y, x + w, y + h), h / 2, fill=bg)
    cx = x + padx
    for (t, f, c), tw in zip(text_parts, widths):
        draw.text((cx, y + pady + asc - f.getmetrics()[0]), t, font=f, fill=c)
        cx += tw + gap
    return x, y, w, h


def read_frames(path: Path, step: int = 1) -> list[np.ndarray]:
    reader = imageio_ffmpeg.read_frames(str(path))
    meta = next(reader)
    w, h = meta["size"]
    out = [np.frombuffer(b, np.uint8).reshape(h, w, 3) for i, b in enumerate(reader) if i % step == 0]
    return out


def cover(fr: np.ndarray, w: int, h: int) -> Image.Image:
    im = Image.fromarray(fr)
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def save_webp(frames: list[Image.Image], path: Path, fps: float, out_w: int, hold: float, quality: int) -> None:
    out_h = round(frames[0].height * out_w / frames[0].width)
    small = [f.resize((out_w, out_h), Image.LANCZOS) for f in frames]
    ms = 1000 / fps
    durs = [round((i + 1) * ms) - round(i * ms) for i in range(len(small))]
    durs[-1] += round(hold * 1000)
    small[0].save(path, save_all=True, append_images=small[1:], duration=durs, loop=0,
                  quality=quality, alpha_quality=90, method=5)
    print(f"[webp] {path.relative_to(PAGE)} {out_w}x{out_h}, {len(small)} frames, {path.stat().st_size / 1e6:.2f} MB")


def value_at(curve, x):
    if x <= curve[0][0]:
        return curve[0][1]
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x0 <= x <= x1:
            return y1 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return curve[-1][1]


# ---------------------------------------------------------------- teaser: rate switching
def build_teaser() -> None:
    js = (PAGE / "static" / "js" / "schedules.js").read_text(encoding="utf-8")
    clips = json.loads(js[js.index("{"):js.rindex("}") + 1])["clips"]
    PW, PH, CH, PAD, GAP, LM = 320 * R, 176 * R, 66 * R, 16 * R, 14 * R, 22 * R
    W = 2 * PAD + 3 * PW + 2 * GAP
    H = PAD + PH + 8 * R + CH + PAD
    Y0, Y1 = 12, 68
    f_chip, f_num, f_small = pil_font(INTER, 13, 650), pil_font(INTER, 15, 750), pil_font(INTER, 11.5, 550)
    f_tick = pil_font(INTER, 10.5, 500)
    vmask = rounded_mask(PW, PH, 10 * R)

    panels = []
    for i, env in enumerate(("doom", "cs2", "fpv")):
        clip = clips[f"{env}/smooth/1"]
        frames = read_frames(PAGE / "static" / "videos" / env / "switch" / f"{env}_smooth_switch_video1.mp4", step=2)
        frames = [cover(f, PW, PH) for f in frames]
        col = BRIGHT[env]
        x0 = PAD + i * (PW + GAP)
        cw, ch = PW, CH
        top, bot = 6 * R, 6 * R
        yv = lambda v: top + (Y1 - v) / (Y1 - Y0) * (ch - top - bot)
        pts = [(LM + x * (cw - LM), yv(v)) for x, v in clip["pts"]]
        base = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        d = ImageDraw.Draw(base)
        for v in (20, 40, 60):
            d.line((LM, yv(v), cw, yv(v)), fill=(255, 255, 255, 20), width=R)
            d.text((LM - 6 * R, yv(v)), str(v), font=f_tick, fill=(140, 146, 160, 255), anchor="rm")
        d.line(pts, fill=col + (80,), width=2 * R, joint="curve")
        area = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        grad = np.zeros((ch, cw, 4), np.uint8)
        grad[..., :3] = col
        grad[..., 3] = (np.linspace(90, 0, ch)[:, None]).astype(np.uint8)
        poly = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(poly).polygon(pts + [(cw, ch), (LM, ch)], fill=255)
        area = Image.composite(Image.fromarray(grad, "RGBA"), area, poly)
        line = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(line).line(pts, fill=col + (255,), width=round(2.6 * R), joint="curve")
        panels.append(dict(env=env, clip=clip, frames=frames, col=col, x0=x0, base=base, area=area, line=line,
                           yv=yv, LM=LM, n=clip["frames"]))

    n_out = max(len(p["frames"]) for p in panels)
    card_mask = rounded_mask(W, H, 18 * R)
    out = []
    for k in range(n_out):
        canvas = Image.new("RGBA", (W, H), CARD)
        dc = ImageDraw.Draw(canvas)
        dc.rounded_rectangle((0, 0, W - 1, H - 1), 18 * R, outline=CARD_LINE, width=R)
        for p in panels:
            idx = min(k, len(p["frames"]) - 1)
            src = min(2 * k, p["n"] - 1)
            frac = src / p["n"]
            fps = value_at(p["clip"]["pts"], frac)
            canvas.paste(p["frames"][idx], (p["x0"], PAD), vmask)
            pill(dc, (p["x0"] + 8 * R, PAD + 8 * R), [("\u25cf", f_small, p["col"] + (255,)), (ENV_NAME[p["env"]], f_chip, (255, 255, 255, 255))])
            pill(dc, (p["x0"] + PW - 8 * R, PAD + 8 * R), [(f"{round(fps)}", f_num, (255, 255, 255, 255)), ("FPS target", f_small, (200, 204, 214, 255))], anchor="rt")
            sp = 30 / fps
            word = "faster" if sp >= 1.05 else "slower" if sp <= 0.95 else "speed"
            arrow = "\u25b2" if sp >= 1.05 else "\u25bc" if sp <= 0.95 else "\u2022"
            pill(dc, (p["x0"] + PW - 8 * R, PAD + PH - 8 * R),
                 [(arrow, f_small, p["col"] + (255,)), (f"{word} \u00d7{sp:.2f}", f_small, (235, 237, 242, 255))], anchor="rb")
            chart = p["base"].copy()
            xc = round(p["LM"] + frac * (PW - p["LM"]))
            if xc > 0:
                chart.alpha_composite(p["area"].crop((0, 0, xc, CH)), (0, 0))
                chart.alpha_composite(p["line"].crop((0, 0, xc, CH)), (0, 0))
            dch = ImageDraw.Draw(chart)
            dch.line((xc, 2 * R, xc, CH - 2 * R), fill=(255, 255, 255, 60), width=R)
            y = p["yv"](fps)
            r = 5 * R
            dch.ellipse((xc - r, y - r, xc + r, y + r), fill=p["col"] + (255,), outline=(255, 255, 255, 255), width=2 * R)
            canvas.alpha_composite(chart, (p["x0"], PAD + PH + 8 * R))
        canvas.putalpha(Image.composite(canvas.getchannel("A"), Image.new("L", (W, H), 0), card_mask))
        out.append(canvas)
    save_webp(out, OUT / "teaser.webp", fps=15, out_w=1280, hold=0.6, quality=72)


# ---------------------------------------------------------------- multi-rate: shared physical clock
def build_multirate(t_end: float = 3.0, fps_out: float = 15) -> None:
    js = (PAGE / "static" / "js" / "multirate.js").read_text(encoding="utf-8")
    meta = json.loads(js[js.index("{"):js.rindex("}") + 1])
    PW, PH, PAD, GAP, ROWGAP, LAB, HEAD = 300 * R, 165 * R, 16 * R, 8 * R, 10 * R, 64 * R, 40 * R
    W = PAD + LAB + 3 * PW + 2 * GAP + PAD
    H = PAD + HEAD + 3 * PH + 2 * ROWGAP + PAD
    f_chip, f_tag, f_small = pil_font(INTER, 12.5, 700), pil_font(INTER, 10.5, 700), pil_font(INTER, 11, 550)
    f_env, f_head = pil_font(INTER, 15, 750), pil_font(INTER, 12, 600)
    vmask = rounded_mask(PW, PH, 8 * R)
    TAG = {"train": ("Train", (87, 199, 113)), "interp": ("Interp.", (140, 153, 242))}

    rows = []
    for env in ("doom", "cs2", "fpv"):
        m = meta[env]
        frames = read_frames(PAGE / "static" / "videos" / "multirate" / f"{env}.mp4")
        rows.append((env, m, frames))

    n_out = int(round(t_end * fps_out)) + 1
    card_mask = rounded_mask(W, H, 18 * R)
    bar_x0, bar_x1 = PAD + LAB + 150 * R, W - PAD - 92 * R
    bar_y = PAD + 14 * R
    grad = np.zeros((6 * R, bar_x1 - bar_x0, 4), np.uint8)
    stops = [(0, (236, 92, 159)), (.5, (127, 140, 240)), (1, (87, 199, 113))]
    xs = np.linspace(0, 1, bar_x1 - bar_x0)
    for c in range(3):
        grad[..., c] = np.interp(xs, [s for s, _ in stops], [col[c] for _, col in stops])[None, :]
    grad[..., 3] = 255
    grad_im = Image.fromarray(grad, "RGBA")
    out = []
    for k in range(n_out):
        t = k / fps_out
        canvas = Image.new("RGBA", (W, H), CARD)
        dc = ImageDraw.Draw(canvas)
        dc.rounded_rectangle((0, 0, W - 1, H - 1), 18 * R, outline=CARD_LINE, width=R)
        dc.text((PAD + LAB, bar_y + 3 * R), "Shared physical clock", font=f_head, fill=(200, 204, 214, 255), anchor="lm")
        dc.rounded_rectangle((bar_x0, bar_y, bar_x1, bar_y + 6 * R), 3 * R, fill=(255, 255, 255, 30))
        fw = round((bar_x1 - bar_x0) * t / t_end)
        if fw > 0:
            canvas.alpha_composite(grad_im.crop((0, 0, fw, 6 * R)), (bar_x0, bar_y))
        for s in range(int(t_end) + 1):
            x = bar_x0 + (bar_x1 - bar_x0) * s / t_end
            dc.text((x, bar_y + 18 * R), f"{s} s", font=f_small, fill=(140, 146, 160, 255), anchor="mm")
        dc.text((W - PAD, bar_y + 3 * R), f"t = {t:.2f} s", font=f_head, fill=(255, 255, 255, 255), anchor="rm")

        for ri, (env, m, frames) in enumerate(rows):
            y0 = PAD + HEAD + ri * (PH + ROWGAP)
            dc.text((PAD + LAB / 2 - 4 * R, y0 + PH / 2), ENV_NAME[env], font=f_env, fill=BRIGHT[env] + (255,), anchor="mm")
            ci = min(int(math.floor(t * m["fps"] + 1e-9)), m["frames"] - 1)
            fr = frames[ci]
            for pi, rate in enumerate(m["rates"]):
                sx = pi * (m["panelW"] + m["gap"])
                panel = cover(fr[:, sx:sx + m["panelW"]], PW, PH)
                x0 = PAD + LAB + pi * (PW + GAP)
                canvas.paste(panel, (x0, y0), vmask)
                tag, tcol = TAG[rate["type"]]
                pill(dc, (x0 + 7 * R, y0 + 7 * R), [(f"{rate['f']} FPS", f_chip, (255, 255, 255, 255)), (tag, f_tag, tcol + (255,))])
                n = int(math.floor(ci * rate["f"] / m["fps"] + 1e-9))
                pill(dc, (x0 + PW - 7 * R, y0 + PH - 7 * R), [(f"frame {n:03d}", f_small, (235, 237, 242, 255))], anchor="rb")
        canvas.putalpha(Image.composite(canvas.getchannel("A"), Image.new("L", (W, H), 0), card_mask))
        out.append(canvas)
    save_webp(out, OUT / "multirate.webp", fps=fps_out, out_w=1280, hold=1.2, quality=72)


if __name__ == "__main__":
    build_svgs()
    if "svg" not in sys.argv[1:]:
        build_teaser()
        build_multirate()
