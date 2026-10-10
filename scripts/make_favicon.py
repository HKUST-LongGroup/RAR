"""Build the site icon: tricolor "RAR" wrapped by a belt (vector), plus raster favicons.

Letters are Montserrat ExtraBold outlines (SIL OFL, see scripts/fonts/OFL-Montserrat.txt) converted
to paths, so the SVG has no font dependency. PNG/ICO rasters are rendered with headless
Microsoft Edge (transparent background).

Outputs (static/images/):
    rar_belt_logo.svg     wide logo
    favicon.svg           same logo on a square canvas (used by modern browsers)
    favicon.ico           16/32/48/64 px fallback
    apple-touch-icon.png  180 px, white background

Usage:
    pip install fonttools pillow
    python scripts/make_favicon.py
"""
from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image

PAGE = Path(__file__).resolve().parents[1]
OUT = PAGE / "static" / "images"
FONT = Path(__file__).resolve().parent / "fonts" / "Montserrat-ExtraBold.ttf"
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

COLORS = ("#C01F6E", "#3B4DB7", "#2FA34A")

# ---- geometry (SVG user units) ----
H = 200.0            # cap height of letters
SX = 0.6             # horizontal squeeze of the glyphs (1 = original width; smaller = narrower / taller look)
GAP = 6.0            # gap between letter bounding boxes
PAD = 14.0           # outer padding
BELT_T = 0.215 * H   # belt width (vertical)
BELT_RY = 0.10 * H   # perspective radius of the belt ring
BELT_MARGIN = 18.0   # how far the belt sticks out left/right of the letters
BELT_CENTER = 0.53   # vertical position of the front belt centre (fraction of H from top)


def f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def letter_paths() -> tuple[list[str], float]:
    font = TTFont(FONT)
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    s = H / font["OS/2"].sCapHeight
    x0 = PAD + BELT_MARGIN
    x = x0
    paths = []
    for ch in "RAR":
        g = gs[cmap[ord(ch)]]
        bp = BoundsPen(gs)
        g.draw(bp)
        xmin, _, xmax, _ = bp.bounds
        pen = SVGPathPen(gs, ntos=f)
        sx = s * SX
        g.draw(TransformPen(pen, (sx, 0, 0, -s, x - xmin * sx, PAD + H)))
        paths.append(pen.getCommands())
        x += (xmax - xmin) * sx + GAP
    return paths, x - GAP - x0


def build_body() -> tuple[str, str, float, float]:
    """Return (defs, body, width, height) of the logo."""
    paths, text_w = letter_paths()
    width = text_w + 2 * (PAD + BELT_MARGIN)
    height = H + 2 * PAD

    cx = width / 2
    rx = text_w / 2 + BELT_MARGIN
    ry, t = BELT_RY, BELT_T
    cy = PAD + BELT_CENTER * H - ry - t / 2

    def front_y(x: float, off: float = 0.0) -> float:
        u = max(0.0, 1 - ((x - cx) / rx) ** 2)
        return cy + ry * math.sqrt(u) + off

    L, R = cx - rx, cx + rx
    back = (f"M{f(L)} {f(cy)} A{f(rx)} {f(ry)} 0 0 1 {f(R)} {f(cy)} "
            f"L{f(R)} {f(cy + t)} A{f(rx)} {f(ry)} 0 0 0 {f(L)} {f(cy + t)} Z")
    front = (f"M{f(L)} {f(cy)} A{f(rx)} {f(ry)} 0 0 0 {f(R)} {f(cy)} "
             f"L{f(R)} {f(cy + t)} A{f(rx)} {f(ry)} 0 0 1 {f(L)} {f(cy + t)} Z")

    def front_arc(off: float) -> str:
        n = 60
        return "M" + " L".join(f"{f(L + (R - L) * i / n)} {f(front_y(L + (R - L) * i / n, off))}" for i in range(n + 1))

    yc = front_y(cx, t / 2)
    bh = t + 12
    bw = bh * 0.78
    bx = cx - bw / 2 + 6
    tongue_r = bx + 6
    tongue_l = cx - 0.30 * text_w
    tip, inset, n = 16.0, 4.0, 40
    xs = [tongue_l + tip + (tongue_r - tongue_l - tip) * i / n for i in range(n + 1)]
    tongue = ("M" + " L".join(f"{f(x)} {f(front_y(x, inset))}" for x in xs)
              + " " + " L".join(f"{f(x)} {f(front_y(x, t - inset))}" for x in reversed(xs))
              + f" L{f(tongue_l)} {f(front_y(tongue_l, t / 2))} Z")
    body_len = tongue_r - tongue_l - tip
    holes = [tongue_l + tip + body_len * fr for fr in (0.19, 0.42, 0.65)]
    keeper_x = tongue_l + tip + body_len * 0.84

    letters_svg = "\n    ".join(f'<path d="{p}" fill="{c}"/>' for p, c in zip(paths, COLORS))
    clip_svg = "".join(f'<path d="{p}"/>' for p in paths)

    defs = f'''
    <linearGradient id="beltFront" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#8E5226"/><stop offset=".22" stop-color="#B8733A"/>
      <stop offset=".5" stop-color="#C98848"/><stop offset=".78" stop-color="#B8733A"/>
      <stop offset="1" stop-color="#8E5226"/>
    </linearGradient>
    <linearGradient id="beltBack" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#7A4421"/><stop offset=".5" stop-color="#4F2A12"/>
      <stop offset="1" stop-color="#7A4421"/>
    </linearGradient>
    <linearGradient id="tongue" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#B06C35"/><stop offset="1" stop-color="#C98A4C"/>
    </linearGradient>
    <linearGradient id="metal" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#F4F6FA"/><stop offset=".55" stop-color="#C7CDD8"/>
      <stop offset="1" stop-color="#9CA4B4"/>
    </linearGradient>
    <clipPath id="letters">{clip_svg}</clipPath>
    <clipPath id="frontClip"><path d="{front}"/></clipPath>'''

    body = f'''
  <path d="{back}" fill="url(#beltBack)"/>
  <g>
    {letters_svg}
  </g>
  <g clip-path="url(#letters)">
    <path d="{front}" transform="translate(0 6)" fill="#000" opacity=".22"/>
  </g>
  <path d="{front}" fill="url(#beltFront)"/>
  <g clip-path="url(#frontClip)" fill="none" stroke-linecap="round">
    <path d="{front_arc(1.2)}" stroke="#E7AE74" stroke-width="2.4" opacity=".9"/>
    <path d="{front_arc(t - 1.2)}" stroke="#6E3A17" stroke-width="2.4" opacity=".6"/>
    <path d="{front_arc(6.5)}" stroke="#F6D9B4" stroke-width="1.8" stroke-dasharray="7 6" opacity=".75"/>
    <path d="{front_arc(t - 6.5)}" stroke="#F6D9B4" stroke-width="1.8" stroke-dasharray="7 6" opacity=".75"/>
  </g>
  <path d="{tongue}" transform="translate(0 2.5)" fill="#000" opacity=".18"/>
  <path d="{tongue}" fill="url(#tongue)"/>
  {''.join(f'<ellipse cx="{f(hx)}" cy="{f(front_y(hx, t / 2))}" rx="3.6" ry="3.2" fill="#4A2611"/>' for hx in holes)}
  <rect x="{f(keeper_x)}" y="{f(front_y(keeper_x, -2.5))}" width="11" height="{f(t + 5)}" rx="2.5" fill="#9C5C2B" stroke="#6E3A17" stroke-width="1.2"/>
  <rect x="{f(bx + 1.5)}" y="{f(yc - bh / 2 + 3)}" width="{f(bw)}" height="{f(bh)}" rx="7" fill="none" stroke="#000" stroke-opacity=".2" stroke-width="7"/>
  <rect x="{f(bx)}" y="{f(yc - bh / 2)}" width="{f(bw)}" height="{f(bh)}" rx="7" fill="none" stroke="#7D8698" stroke-width="8.5"/>
  <rect x="{f(bx)}" y="{f(yc - bh / 2)}" width="{f(bw)}" height="{f(bh)}" rx="7" fill="none" stroke="url(#metal)" stroke-width="5.5"/>
  <line x1="{f(bx + 3)}" y1="{f(yc)}" x2="{f(bx + bw * 0.62)}" y2="{f(yc)}" stroke="#7D8698" stroke-width="6" stroke-linecap="round"/>
  <line x1="{f(bx + 3)}" y1="{f(yc)}" x2="{f(bx + bw * 0.62)}" y2="{f(yc)}" stroke="#E9ECF2" stroke-width="3" stroke-linecap="round"/>
'''
    return defs, body, width, height


def svg_doc(defs: str, body: str, vb: tuple[float, float, float, float], size: tuple[float, float]) -> str:
    x, y, w, h = vb
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{f(x)} {f(y)} {f(w)} {f(h)}" '
            f'width="{f(size[0])}" height="{f(size[1])}">\n  <title>RAR</title>\n  <defs>{defs}\n  </defs>{body}</svg>\n')


def find_edge() -> str:
    for p in EDGE_CANDIDATES:
        if Path(p).exists():
            return p
    raise SystemExit("Microsoft Edge not found; cannot rasterize the SVG.")


def render_png(svg_path: Path, w: int, h: int, dst: Path) -> None:
    html = (f'<html><body style="margin:0;background:transparent">'
            f'<img src="{svg_path.as_uri()}" style="display:block;width:{w}px;height:{h}px"></body></html>')
    with tempfile.TemporaryDirectory() as td:
        page = Path(td) / "logo.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run([find_edge(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        f"--user-data-dir={Path(td) / 'profile'}",
                        "--default-background-color=00000000", "--force-device-scale-factor=1",
                        f"--window-size={w},{h}", f"--screenshot={dst}", page.as_uri()],
                       check=True, capture_output=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    defs, body, w, h = build_body()

    (OUT / "rar_belt_logo.svg").write_text(svg_doc(defs, body, (0, 0, w, h), (w, h)), encoding="utf-8")

    side = max(w, h) * 1.02                           # square canvas, logo centred
    sq = svg_doc(defs, body, ((w - side) / 2, (h - side) / 2, side, side), (side, side))
    fav_svg = OUT / "favicon.svg"
    fav_svg.write_text(sq, encoding="utf-8")

    big = OUT / "_favicon_512.png"
    render_png(fav_svg, 512, 512, big)
    img = Image.open(big).convert("RGBA")
    img.save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

    touch = Image.new("RGBA", (180, 180), (255, 255, 255, 255))
    logo = img.resize((164, 164), Image.LANCZOS)
    touch.alpha_composite(logo, (8, 8))
    touch.convert("RGB").save(OUT / "apple-touch-icon.png", optimize=True)
    big.unlink()
    print("wrote rar_belt_logo.svg, favicon.svg, favicon.ico, apple-touch-icon.png")


if __name__ == "__main__":
    main()
