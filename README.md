# RAR Project Page

Static project page for **RAR: Rate-Adaptive Rollout for Time-Consistent Interactive World Models**.
Plain HTML/CSS/JS, no build step, ready for GitHub Pages. Supports light / dark mode (toggle in the top bar); dark by default, the visitor's choice is remembered.

## Structure

```
project_page/
├── index.html
├── .nojekyll                 # tell GitHub Pages to serve files as-is
├── static/
│   ├── css/style.css         # light/dark theme variables, layout
│   ├── js/main.js            # rate players (video + live FPS chart), galleries, KaTeX, theme
│   ├── js/schedules.js       # auto-generated target-FPS curves of rate-switching videos (from the 2 XML schedules)
│   ├── js/multirate.js       # auto-generated layout of the multi-rate comparison videos
│   ├── js/motivation.js      # interactive Motivation figures (rate-throughput / rate-horizon)
│   ├── images/               # figures from paper PDFs; switch/ = tracking panels; favicon.*
│   │   └── motivation/       # artwork extracted from figs/RAR_problem.pptx
│   ├── videos/               # supplementary videos (H.264, +faststart); multirate/ = 3-rate composites
│   └── posters/              # first-frame posters for videos
└── scripts/
    ├── prepare_assets.py     # build all images / videos / schedules from the paper sources
    ├── extract_motivation_assets.py  # road / cars / GPU / map sprites from figs/RAR_problem.pptx
    ├── make_favicon.py       # belt-wrapped "RAR" icon -> favicon.svg / .ico / apple-touch-icon
    ├── fonts/                # Montserrat ExtraBold (SIL OFL), glyphs used by the icon
    └── serve.py              # local preview server with HTTP Range support
```

The "RAR" title is plain text styled in CSS (`.rar-word`: blended tricolour gradient, soft glow, subtle sheen).

## Local preview

```bash
cd project_page
python scripts/serve.py 8000
# open http://localhost:8000
```

Use `serve.py` rather than `python -m http.server`: the built-in server ignores HTTP Range
requests, so browsers cannot seek videos (dragging the progress bar does nothing).
GitHub Pages supports Range, so no change is needed after deployment.

Fonts, KaTeX and Academicons load from CDNs, so formulas and icons render only when online.

## Regenerate assets

```bash
pip install pymupdf pillow imageio-ffmpeg numpy fonttools
python scripts/prepare_assets.py
python scripts/extract_motivation_assets.py
python scripts/make_favicon.py      # needs Microsoft Edge to rasterize the SVG
```

The Motivation figures are drawn live in the browser (`static/js/motivation.js`) from the
sprites above, so all numbers in them are exact: (a) a machine with throughput *r* finishes
`floor(t·r)` frames by wall-clock *t*, each advancing the world by `1/f_rollout`
(fixed model: 30 FPS; RAR: *r*); (b) a sample at rate *f* holds *N* = 7 frames at `k/f`.

Sources: `../Rate_Adaptive_Rollout_preprint/figs/*.pdf`,
`../supp/ICLR5809_RAR_Supplementary_Material/`, and
`../figs/main_figure_sequences_9x6_frames/source_videos/` (multi-rate comparison).

The multi-rate composites put the generated rollouts at three rates side by side on one
physical clock: output frame *k* (time *k / f_max*) shows, in each panel, the frame of that
rate nearest to the same physical time. The page overlays rate, frame index and a timeline
with the matched physical times used in the paper figure.

For the rate-switching videos, the script crops away the burned-in FPS chart (top 240 px) and
re-encodes the clip. All clips use the same two fixed schedules, defined over latent frames in
`../case000_RWB_FLAT3_s3532.xml` (smooth: raised cosine between 20 and 60 FPS) and
`../case001_RSV_WAVE2_s2609.xml` (abrupt: 60 / 25 / 45 / 20 / 50 / 30 FPS segments). The script
maps them onto each clip's frames (4 video frames per latent; Doom clips have 54 latents instead
of 61) and writes the target-FPS curves to `static/js/schedules.js`; the page draws them as
interactive charts synced with playback. Rebuild only the curves with
`python scripts/prepare_assets.py --schedules`.

## Before publishing

- In `index.html`, replace the `href="#"` of the **arXiv / Code** buttons (marked `data-pending`).
- Update the arXiv ID in the BibTeX block.

## Deploy to GitHub Pages

1. Push the **contents** of this folder to the root of a repo (e.g. `rar-project`), or into `docs/` of the code repo.
2. Repo **Settings → Pages → Build and deployment**: Source = *Deploy from a branch*, choose `main` and `/ (root)` (or `/docs`).
3. The site appears at `https://<user>.github.io/<repo>/`.

All paths are relative, so no changes are needed when moving the folder.
Total size is about 90 MB (largest single file < 10 MB), which is within GitHub limits.
