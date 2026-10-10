"""Extract the artwork of the paper's motivation figure (figs/RAR_problem.pptx) for the
animated Motivation section of the project page.

Outputs (static/images/motivation/):
    road.jpg        side-view road strip (lane background, panel a)
    car_pink.png    car sprites, side view (panel a)
    car_blue.png
    car_green.png
    car_ghost.png   white car, used as the "expected position" ghost
    gpu.png         GPU icon
    map.jpg         top-down road with a left-to-right bend (panel b)
    car_top.png     top-down car (panel b)

Usage:
    pip install pillow
    python scripts/extract_motivation_assets.py
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from PIL import Image

PAGE = Path(__file__).resolve().parents[1]
PPTX = PAGE.parent / "figs" / "RAR_problem.pptx"
OUT = PAGE / "static" / "images" / "motivation"

# media name inside the pptx -> crop boxes, measured on the original images
ROAD = ("image3.png", (0, 860, 3840, 1330))                 # sky trimmed, kerb kept
CARS = ("image4.png", {                                      # 2 x 2 sheet of side-view cars
    "blue": (336, 125, 1689, 750),
    "green": (2105, 131, 3444, 757),
    "pink": (339, 882, 1692, 1507),
    "ghost": (2098, 889, 3444, 1513),
})
GPU = "image2.png"
MAP = ("image25.png", (200, 420, 1330, 1300))               # bend: up the left, then right
CAR_TOP = ("image26.png", (136, 60, 1220, 1965))


def load(z: zipfile.ZipFile, name: str) -> Image.Image:
    return Image.open(io.BytesIO(z.read(f"ppt/media/{name}")))


def fit_w(im: Image.Image, w: int) -> Image.Image:
    return im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PPTX) as z:
        road = load(z, ROAD[0]).convert("RGB").crop(ROAD[1])
        fit_w(road, 2000).save(OUT / "road.jpg", quality=86, optimize=True, progressive=True)

        sheet = load(z, CARS[0]).convert("RGBA")
        for name, box in CARS[1].items():
            fit_w(sheet.crop(box), 360).save(OUT / f"car_{name}.png", optimize=True)

        load(z, GPU).convert("RGBA").save(OUT / "gpu.png", optimize=True)

        m = load(z, MAP[0]).convert("RGB").crop(MAP[1])
        fit_w(m, 960).save(OUT / "map.jpg", quality=86, optimize=True, progressive=True)

        car = load(z, CAR_TOP[0]).convert("RGBA").crop(CAR_TOP[1])
        fit_w(car, 120).save(OUT / "car_top.png", optimize=True)

    for p in sorted(OUT.iterdir()):
        im = Image.open(p)
        print(f"{p.name:14s} {im.size[0]}x{im.size[1]}  {p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
