"""Build web assets for the RAR project page.

- Renders paper figures (PDF) to PNG/JPG under static/images/.
- Crops the rate-switching tracking plots into one panel per (environment, schedule).
- Copies fixed-rate / SANA-WM videos to static/videos/ (remuxed with +faststart).
- For rate-switching videos: removes the burned-in FPS chart and re-encodes the clip.
  The target-FPS curve of each clip is built from the two canonical schedules
  (case000_RWB_FLAT3_s3532.xml = smooth, case001_RSV_WAVE2_s2609.xml = abrupt) and written to
  static/js/schedules.js (drawn as an interactive chart on the page).
- Builds one side-by-side "multi-rate" video per environment from
  figs/main_figure_sequences_9x6_frames/source_videos: the generated rollouts at three
  rates are placed next to each other on a shared physical-time clock (each panel shows
  its frame nearest to physical time t), plus layout metadata in static/js/multirate.js.
- Extracts a poster frame (JPG) for every video.

Usage:
    pip install pymupdf pillow imageio-ffmpeg numpy
    python scripts/prepare_assets.py               # everything
    python scripts/prepare_assets.py --schedules   # only rebuild static/js/schedules.js
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import pymupdf
from PIL import Image

PAGE = Path(__file__).resolve().parents[1]
ROOT = PAGE.parent
FIG_SRC = ROOT / "Rate_Adaptive_Rollout_preprint" / "figs"
VID_SRC = ROOT / "supp" / "ICLR5809_RAR_Supplementary_Material"

IMG_DST = PAGE / "static" / "images"
VID_DST = PAGE / "static" / "videos"
POSTER_DST = PAGE / "static" / "posters"
SCHEDULE_JS = PAGE / "static" / "js" / "schedules.js"
SCHEDULE_XML = {                                # the two fixed rate-switching schedules
    "smooth": ROOT / "case000_RWB_FLAT3_s3532.xml",
    "abrupt": ROOT / "case001_RSV_WAVE2_s2609.xml",
}
MULTIRATE_JS = PAGE / "static" / "js" / "multirate.js"

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# multi-rate comparison (source of the paper's qualitative figure)
MR_SRC = ROOT / "figs" / "main_figure_sequences_9x6_frames" / "source_videos"
MR_ENVS = {
    # env: (source sub-folder, [(fps, type)], side-by-side GT|Pred source?)
    "doom": ("doom", [(35, "train"), (49, "interp"), (70, "train")], True),
    "cs2": ("csgo", [(32, "train"), (48, "interp"), (64, "train")], True),
    "fpv": ("fpv", [(20, "train"), (40, "interp"), (60, "train")], False),
}
MR_PANEL_H = 352
MR_GAP = 6
MR_GAP_COLOR = (15, 17, 23)
MR_CHECKPOINTS = 6

# (pdf name, output name, target width in px, format)
FIGURES = [
    ("RAR_method.pdf", "stride_rope", 2000, "png"),
    ("RAR_pipeline_3.pdf", "pipeline", 1600, "png"),
    ("RAR_result.pdf", "qualitative", 2400, "jpg"),
    ("RAR_efficiency_fixed_steps_rates.pdf", "eff_steps_rates", 2000, "png"),
    ("RAR_efficiency_fixed_steps_length.pdf", "eff_steps_length", 1400, "png"),
    ("RAR_efficiency_fixed_time.pdf", "eff_fixed_time", 1400, "png"),
]

# rate-switching tracking plots: pdf -> environments of each panel row
SWITCH_PLOTS = [
    ("RAR_rate_switch_appd.pdf", ["doom", "cs2"]),
    ("RAR_rate_switch_main.pdf", ["fpv"]),
]
SWITCH_KINDS = ["smooth", "abrupt"]          # panel columns
PANEL_FRAME_W = 760                           # output width of the axes frame (px)

VIDEO_DIRS = {
    "cs2": VID_SRC / "CS2",
    "doom": VID_SRC / "Doom",
    "fpv": VID_SRC / "FPV",
}

# burned-in chart of the rate-switching videos
CHART_H = 240                                 # header height (px) to crop away
CURVE_SAMPLES = 240                           # polyline points of the smooth schedule chart


# ---------------------------------------------------------------- figures
def render_page(src: Path, width: int) -> Image.Image:
    doc = pymupdf.open(src)
    page = doc[0]
    zoom = width / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return img


def flatten_rim(img: Image.Image, thresh: int = 12) -> Image.Image:
    """Paint the white rim / rounded corners around a coloured background panel with the panel colour,
    so the figure can sit on a box of the same colour without a visible inner rectangle."""
    from PIL import ImageDraw
    w, h = img.size
    panel = img.getpixel((w // 2, min(h - 1, 12)))
    img = img.copy()
    for xy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if img.getpixel(xy) != panel:
            ImageDraw.floodfill(img, xy, panel, thresh=thresh)
    return img


# figures drawn on a coloured panel (their rim is flattened, see flatten_rim)
PANEL_FIGURES = {"pipeline"}


def render_pdf(src: Path, dst: Path, width: int, fmt: str) -> None:
    img = render_page(src, width)
    if dst.stem in PANEL_FIGURES:
        img = flatten_rim(img)
    if fmt == "jpg":
        img.save(dst, "JPEG", quality=88, optimize=True, progressive=True)
    else:
        img.save(dst, "PNG", optimize=True)


def find_frames(gray: np.ndarray, min_run: int = 500) -> list[tuple[int, int, int, int]]:
    """Locate matplotlib axes frames (x0, y0, x1, y1) from long dark horizontal lines."""
    dark = gray < 110
    columns: dict[int, list[tuple[int, int, int]]] = {}
    for y in range(dark.shape[0]):
        row = np.concatenate(([0], dark[y].astype(np.int8), [0]))
        d = np.diff(row)
        for s, e in zip(np.where(d == 1)[0], np.where(d == -1)[0]):
            if e - s > min_run:
                columns.setdefault(int(s) // 20, []).append((y, int(s), int(e) - 1))
    frames = []
    for key in sorted(columns):
        col = columns[key]
        groups: list[list[tuple[int, int, int]]] = []
        for sg in col:
            if groups and sg[0] - groups[-1][-1][0] <= 3:
                groups[-1].append(sg)
            else:
                groups.append([sg])
        ys = [(g[0][0], g[-1][0], g[0][1], g[0][2]) for g in groups]
        for top, bot in zip(ys[0::2], ys[1::2]):
            frames.append((top[2], top[0], top[3], bot[1]))
    return sorted(frames, key=lambda f: (f[1], f[0]))


def crop_switch_panels() -> None:
    out_dir = IMG_DST / "switch"
    out_dir.mkdir(parents=True, exist_ok=True)
    panels: list[tuple[Path, Image.Image, int, int]] = []   # (dst, image, frame-x offset, frame-y offset)
    for pdf, envs in SWITCH_PLOTS:
        img = render_page(FIG_SRC / pdf, 2400)
        gray = np.asarray(img.convert("L"))
        H, W = gray.shape
        frames = find_frames(gray)
        assert len(frames) == 2 * len(envs), (pdf, frames)

        # left margin (y-label + tick labels) measured on the first panel
        x0, y0, x1, y1 = frames[0]
        band = gray[y0:y1, : x0 - 4] < 200
        left = x0 - int(np.where(band.any(axis=0))[0].min()) + 10

        for i, (x0, y0, x1, y1) in enumerate(frames):
            env, kind = envs[i // 2], SWITCH_KINDS[i % 2]
            # tick labels below the frame: first block of dark rows taller than the tick marks
            below = (gray[y1 + 3:, x0:x1] < 200).any(axis=1)
            end, i_row = None, 0
            while i_row < len(below):
                if below[i_row]:
                    start = i_row
                    while i_row + 1 < len(below) and below[i_row + 1]:
                        i_row += 1
                    if i_row - start >= 12:
                        end = i_row
                        break
                i_row += 1
            bottom = y1 + 3 + (end if end is not None else 40) + 3
            # the rotated y-label may extend above the frame: follow it upwards
            lab = (gray[:, max(0, x0 - left):x0 - 6] < 200).any(axis=1)
            top = y0 - 4
            while top > 0 and lab[top - 1]:
                top -= 1
            top = max(0, top - 4)
            box = (max(0, x0 - left), top, min(W, x1 + 34), min(H, bottom))
            panel = img.crop(box).copy()
            # blank anything above the frame except the y-label (e.g. column titles)
            if y0 - 4 > top:
                panel.paste((255, 255, 255), (x0 - 6 - box[0], 0, panel.width, y0 - 4 - top))
            s = PANEL_FRAME_W / (x1 - x0)
            panel = panel.resize((round(panel.width * s), round(panel.height * s)), Image.LANCZOS)
            off = (round((x0 - box[0]) * s), round((y0 - box[1]) * s))
            panels.append((out_dir / f"{env}_{kind}.png", panel, *off))

    # pad every panel onto one common canvas so all axes frames line up in the page grid
    ml = max(ox for _, _, ox, _ in panels)
    mr = max(p.width - ox for _, p, ox, _ in panels)
    mt = max(oy for _, _, _, oy in panels)
    mb = max(p.height - oy for _, p, _, oy in panels)
    for dst, p, ox, oy in panels:
        canvas = Image.new("RGB", (ml + mr, mt + mb), "white")
        canvas.paste(p, (ml - ox, mt - oy))
        canvas.save(dst, "PNG", optimize=True)
        print(f"[panel] {dst.relative_to(PAGE)} {canvas.size}")


# ---------------------------------------------------------------- videos
def run(cmd: list[str]) -> None:
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *cmd], check=True)


def remux(src: Path, dst: Path) -> None:
    run(["-i", str(src), "-c", "copy", "-an", "-movflags", "+faststart", str(dst)])


def crop_chart(src: Path, dst: Path) -> None:
    run(["-i", str(src), "-vf", f"crop=iw:ih-{CHART_H}:0:{CHART_H}",
         "-c:v", "libx264", "-crf", "20", "-preset", "slow", "-pix_fmt", "yuv420p",
         "-an", "-movflags", "+faststart", str(dst)])


def poster(src: Path, dst: Path) -> None:
    run(["-ss", "0.5", "-i", str(src), "-frames:v", "1",
         "-vf", "scale='min(960,iw)':-2", "-q:v", "4", str(dst)])


# ---------------------------------------------------------------- rate-switching schedules
def load_schedules() -> dict:
    """Read the two canonical schedules (defined over latent frames) from their XML files.

    smooth: a raised cosine fps(u) = mid + amp * cos(2 pi u), u = latent index / (L - 1) in [0, 1]
            (checked against every latent value in the XML).
    abrupt: piecewise-constant levels, one per segment; segments have L // n_segments latents and
            the last one takes the remainder (the XML: 10, 10, 10, 10, 10, 11 of L = 61).
    """
    out: dict[str, dict] = {}
    for kind, path in SCHEDULE_XML.items():
        root = ET.parse(path).getroot()
        lat = np.array([float(e.get("fps")) for e in root.find("latent_frames")])
        n_lat, n_pix = int(root.get("num_latent_frames")), int(root.get("num_pixel_frames"))
        f_min, f_max = float(root.get("fps_min")), float(root.get("fps_max"))
        info = {"source": path.name, "schedule": root.get("schedule"),
                "fpsMin": f_min, "fpsMax": f_max, "framesPerLatent": (n_pix - 1) // (n_lat - 1)}
        if kind == "smooth":
            u = np.arange(n_lat) / (n_lat - 1)
            fit = (f_min + f_max) / 2 + (f_max - f_min) / 2 * np.cos(2 * np.pi * u)
            assert np.abs(fit - lat).max() < 1e-3, f"{path.name} is not a raised cosine"
        else:
            segs = [(int(s.get("latent_start")), float(s.get("fps"))) for s in root.find("segments")]
            seg_len = n_lat // len(segs)
            assert [s for s, _ in segs] == [k * seg_len for k in range(len(segs))], segs
            info["levels"] = [f for _, f in segs]
        out[kind] = info
    return out


def schedule_curve(sched: dict, kind: str, n_frames: int) -> list[list[float]]:
    """Target-FPS polyline [[x, fps], ...] of one clip; x = playback time / clip duration in [0, 1].

    Video frame k belongs to latent ceil(k / fpl). The clip has L = ceil((n - 1) / fpl) + 1 latents
    (Doom clips are shorter: L = 54; one FPV abrupt clip lacks its last frame).
    """
    fpl = sched["framesPerLatent"]
    n_lat = math.ceil((n_frames - 1) / fpl) + 1
    if kind == "smooth":
        # continuous curve through the per-latent targets. Frames 4j-3 ... 4j share latent j, so the
        # curve passes through latent j's value at the middle of those frames (playback time 4j-1 frames).
        mid, amp = (sched["fpsMin"] + sched["fpsMax"]) / 2, (sched["fpsMax"] - sched["fpsMin"]) / 2
        pts = []
        for i in range(CURVE_SAMPLES + 1):
            x = i / CURVE_SAMPLES
            u = min(1.0, (x * n_frames + 1) / (fpl * (n_lat - 1)))
            pts.append([round(x, 5), round(mid + amp * math.cos(2 * math.pi * u), 3)])
        return pts
    # abrupt: exact steps, switching at the first video frame of each new segment
    levels = sched["levels"]
    seg_len = n_lat // len(levels)
    pts = [[0.0, levels[0]]]
    for s in range(1, len(levels)):
        x = round((fpl * s * seg_len - (fpl - 1)) / n_frames, 5)
        pts += [[x, levels[s - 1]], [x, levels[s]]]
    pts.append([1.0, levels[-1]])
    return pts


def build_schedules() -> None:
    sched = load_schedules()
    clips: dict[str, dict] = {}
    for vid in sorted((VID_DST).glob("*/switch/*_switch_video*.mp4")):
        env, kind, _, sample = vid.stem.split("_")             # e.g. doom_smooth_switch_video1
        reader = imageio_ffmpeg.read_frames(str(vid))
        meta = next(reader)
        reader.close()
        n = imageio_ffmpeg.count_frames_and_secs(str(vid))[0]
        key = f"{env}/{kind}/{sample.replace('video', '')}"
        clips[key] = {"kind": kind, "frames": n, "dt": round(1.0 / meta["fps"], 6),
                      "pts": schedule_curve(sched[kind], kind, n)}
        print(f"[sched] {key}: {n} frames @ {meta['fps']:g} fps, {len(clips[key]['pts'])} curve points")
    SCHEDULE_JS.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_JS.write_text(
        "/* Auto-generated by scripts/prepare_assets.py from the two fixed rate-switching schedules\n"
        f"   ({', '.join(p.name for p in SCHEDULE_XML.values())}).\n"
        "   clips[key].pts: target-FPS polyline, x = playback time / clip duration. */\n"
        "window.RAR_SCHEDULES = " + json.dumps({"schedules": sched, "clips": clips}, separators=(",", ":")) + ";\n",
        encoding="utf-8")


# ---------------------------------------------------------------- multi-rate comparison
def _mr_source(folder: Path, fps: int) -> Path:
    pat = re.compile(rf"(self{fps}fps|fps{fps}_)")
    hits = [p for p in folder.glob("*.mp4") if pat.search(p.name)]
    assert len(hits) == 1, (folder, fps, hits)
    return hits[0]


def _frames(path: Path, sxs: bool, panel_w: int):
    """Yield generated-rollout frames (H x W x 3 uint8), cropped / resized to the panel size."""
    reader = imageio_ffmpeg.read_frames(str(path))
    meta = next(reader)
    w, h = meta["size"]
    for buf in reader:
        fr = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        if sxs:
            fr = fr[:, w // 2:]
        if fr.shape[0] != MR_PANEL_H or fr.shape[1] != panel_w:
            fr = np.asarray(Image.fromarray(fr).resize((panel_w, MR_PANEL_H), Image.LANCZOS))
        yield np.ascontiguousarray(fr)


def build_multirate() -> dict:
    out_meta: dict[str, dict] = {}
    dst_dir = VID_DST / "multirate"
    dst_dir.mkdir(parents=True, exist_ok=True)
    for env, (sub, rates, sxs) in MR_ENVS.items():
        folder = MR_SRC / sub
        srcs = [_mr_source(folder, f) for f, _ in rates]
        info = []
        for p in srcs:
            r = imageio_ffmpeg.read_frames(str(p))
            m = next(r)
            r.close()
            n = imageio_ffmpeg.count_frames_and_secs(str(p))[0]
            info.append((m["size"], n))
        (w0, h0), _ = info[0]
        src_w = w0 // 2 if sxs else w0
        panel_w = int(round(src_w * MR_PANEL_H / h0 / 2)) * 2
        f_max = max(f for f, _ in rates)
        counts = [n for _, n in info]
        n_max = counts[[f for f, _ in rates].index(f_max)]
        width = 3 * panel_w + 2 * MR_GAP

        dst = dst_dir / f"{env}.mp4"
        writer = imageio_ffmpeg.write_frames(
            str(dst), (width, MR_PANEL_H), fps=f_max, codec="libx264",
            pix_fmt_in="rgb24", pix_fmt_out="yuv420p", quality=None, macro_block_size=2,
            ffmpeg_log_level="error",
            output_params=["-crf", "20", "-preset", "slow", "-movflags", "+faststart"])
        writer.send(None)

        gens = [_frames(p, sxs, panel_w) for p in srcs]
        cur = [next(g) for g in gens]
        idx = [0] * len(rates)
        canvas = np.empty((MR_PANEL_H, width, 3), np.uint8)
        canvas[:] = MR_GAP_COLOR
        for k in range(n_max):
            for i, (f, _) in enumerate(rates):
                want = min(counts[i] - 1, math.floor(k * f / f_max + 0.5))   # nearest frame (as in the paper figure)
                while idx[i] < want:
                    cur[i] = next(gens[i])
                    idx[i] += 1
                x = i * (panel_w + MR_GAP)
                canvas[:, x:x + panel_w] = cur[i]
            writer.send(canvas.tobytes())
        writer.close()
        for g in gens:
            g.close()

        t_last = (n_max - 1) / f_max
        out_meta[env] = {
            "fps": f_max,
            "frames": n_max,
            "duration": round(n_max / f_max, 6),
            "width": width, "height": MR_PANEL_H, "panelW": panel_w, "gap": MR_GAP,
            "rates": [{"f": f, "type": t} for f, t in rates],
            "checkpoints": [round(t_last * c / (MR_CHECKPOINTS - 1), 4) for c in range(MR_CHECKPOINTS)],
        }
        p = POSTER_DST / "multirate" / f"{env}.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        poster(dst, p)
        print(f"[multirate] {dst.relative_to(PAGE)} {width}x{MR_PANEL_H} @ {f_max} fps, "
              f"{n_max} frames ({dst.stat().st_size // 1024} KB)")

    MULTIRATE_JS.write_text(
        "/* Auto-generated by scripts/prepare_assets.py: layout of the multi-rate comparison videos. */\n"
        "window.RAR_MULTIRATE = " + json.dumps(out_meta, separators=(",", ":")) + ";\n",
        encoding="utf-8")
    return out_meta


def collect_videos() -> list[tuple[Path, Path, str]]:
    items: list[tuple[Path, Path, str]] = []
    for env, folder in VIDEO_DIRS.items():
        for sub, tag in (("fix_rate_result", "fixed"), ("rate_switch_result", "switch")):
            for f in sorted((folder / sub).glob("*.mp4")):
                items.append((f, VID_DST / env / tag / f.name.lower(), tag))
    for f in sorted((VID_SRC / "SANA-WM").glob("*.mp4")):
        items.append((f, VID_DST / "sanawm" / f.name.lower(), "sana"))
    return items


def main() -> None:
    IMG_DST.mkdir(parents=True, exist_ok=True)
    for name, out, width, fmt in FIGURES:
        dst = IMG_DST / f"{out}.{fmt}"
        render_pdf(FIG_SRC / name, dst, width, fmt)
        print(f"[fig] {name} -> {dst.relative_to(PAGE)} ({dst.stat().st_size // 1024} KB)")
    crop_switch_panels()
    build_multirate()

    for src, dst, tag in collect_videos():
        dst.parent.mkdir(parents=True, exist_ok=True)
        if tag == "switch":
            crop_chart(src, dst)
        else:
            remux(src, dst)
        p = POSTER_DST / dst.relative_to(VID_DST).with_suffix(".jpg")
        p.parent.mkdir(parents=True, exist_ok=True)
        poster(dst, p)
        print(f"[vid] {dst.relative_to(PAGE)}")

    build_schedules()
    print("done")


if __name__ == "__main__":
    if "--schedules" in sys.argv:
        build_schedules()
        raise SystemExit(0)
    if not FIG_SRC.exists() or not VID_SRC.exists():
        raise SystemExit("source folders not found")
    main()
