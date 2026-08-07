# pngconvert — Lightroom-style image exporter

Compresses (and optionally downscales) PNG/JPEG images using the same pipeline
Adobe Lightroom uses on export. Like Lightroom, the default is **compress only,
no resize**: full resolution is kept and the file is saved as a quality-
controlled JPEG — small files that stay sharp when you zoom in. When resizing
is enabled it uses an adaptive **bicubic resample in linear light** (sRGB is
decoded to linear float32 first — resampling gamma-encoded bytes darkens and
crunches fine detail — with premultiplied alpha so transparent edges don't
fringe). Either way, **"Sharpen For Screen" output sharpening** is applied:
a luminance-only, edge-masked unsharp mask (Low / Standard / High) that
sharpens edges without crunching noise, sky, or other flat areas.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Web UI

```sh
.venv/bin/python server.py
```

Open <http://127.0.0.1:8765>, then pick or drag PNG/JPEG files — they are
processed immediately with the current settings. Each row shows the
before/after dimensions, file size, and % saved, with a per-file download
and a Download-all ZIP. Everything runs locally.

Settings mirror Lightroom's export panel:

- **Format:** JPEG with a quality slider (best for photos) or lossless PNG
- **Resize to fit:** Don't resize (default, like Lightroom) / Long edge /
  Percentage / Width & height
- **Output sharpening:** None / Low / Standard / High (screen)
- **Don't enlarge** — never upscale smaller images
- **Reduce colors** — optional lossy palette quantization (PNG only)

> If exports look pixelated when you zoom in, don't resize — a 1080px image
> has no data to show past 100% zoom, from any tool. Full resolution + JPEG
> quality ~80–85 is how Lightroom makes small files that stay zoomable.

## CLI

```sh
.venv/bin/python -m pngcompressor photo.png --no-resize --format jpeg --quality 85
.venv/bin/python -m pngcompressor photo.png --long-edge 2048
.venv/bin/python -m pngcompressor *.png --percent 50 --sharpen high --out-dir out/
.venv/bin/python -m pngcompressor icon.png --fit 512x512 --colors 256 -o icon_small.png
```

## Structure

```
pngcompressor/
├── core/               processing pipeline
│   ├── color.py        sRGB <-> linear-light conversion
│   ├── resize.py       resize strategies + linear-light bicubic resampler
│   ├── sharpen.py      edge-masked luminance output sharpening
│   ├── encode.py       PNG/JPEG encoders (registry, open for extension)
│   └── pipeline.py     ExportPipeline orchestration
├── web/                Flask layer
│   ├── __init__.py     application factory (dependency injection)
│   ├── routes.py       HTTP endpoints
│   ├── forms.py        request validation -> ExportOptions
│   └── storage.py      ResultStore abstraction + in-memory implementation
├── cli.py              command-line interface
└── __main__.py         `python -m pngcompressor`
static/                 web UI (index.html, css/, js/)
server.py               development server entry point
```
