#!/usr/bin/env python3
"""Local web UI server for the Lightroom-style image exporter."""

import io
import re
import secrets
import zipfile
from collections import OrderedDict
from pathlib import Path

from flask import Flask, abort, request, send_file, send_from_directory
from PIL import Image

from downscale import SHARPEN_PRESETS, process_image, save_bytes

APP_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024

RESULTS: OrderedDict[str, tuple[str, bytes]] = OrderedDict()
MAX_RESULTS = 200


def _remember(filename, data):
    token = secrets.token_urlsafe(12)
    RESULTS[token] = (filename, data)
    while len(RESULTS) > MAX_RESULTS:
        RESULTS.popitem(last=False)
    return token


def _safe_stem(name):
    stem = Path(name or "image").stem
    stem = re.sub(r"[^\w.\- ]", "_", stem).strip() or "image"
    return stem


@app.get("/")
def index():
    return send_from_directory(APP_DIR / "static", "index.html")


@app.post("/api/process")
def process():
    upload = request.files.get("file")
    if upload is None:
        abort(400, "no file uploaded")

    form = request.form
    mode = form.get("mode", "long_edge")
    sharpen = form.get("sharpen", "standard")
    if sharpen not in SHARPEN_PRESETS:
        abort(400, f"bad sharpen value: {sharpen}")
    fmt = form.get("format", "png")
    if fmt not in ("png", "jpeg"):
        abort(400, f"bad format: {fmt}")

    opts = {"sharpen": sharpen,
            "no_enlarge": form.get("no_enlarge", "1") != "0",
            "colors": None}
    try:
        quality = max(1, min(100, int(form.get("quality", 85))))
        if fmt == "png" and form.get("reduce_colors") == "1":
            opts["colors"] = max(2, min(256, int(form.get("colors", 256))))
        if mode == "long_edge":
            opts["long_edge"] = max(1, int(form["long_edge"]))
        elif mode == "percent":
            opts["percent"] = max(0.1, min(100.0, float(form["percent"])))
        elif mode == "fit":
            opts["box"] = (max(1, int(form["width"])), max(1, int(form["height"])))
        elif mode != "none":
            abort(400, f"bad resize mode: {mode}")
    except (KeyError, ValueError):
        abort(400, "missing or invalid resize parameters")

    raw = upload.read()
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            orig_size = im.size
            out, _ = process_image(im, mode, **opts)
    except Exception:
        abort(415, "could not decode image — is it a valid PNG/JPEG?")

    data = save_bytes(out, fmt, quality)
    ext = "jpg" if fmt == "jpeg" else "png"
    filename = f"{_safe_stem(upload.filename)}_{max(out.size)}px.{ext}"
    token = _remember(filename, data)

    resp = send_file(io.BytesIO(data), mimetype=f"image/{fmt}",
                     download_name=filename)
    resp.headers["X-Token"] = token
    resp.headers["X-Filename"] = filename
    resp.headers["X-Original-Bytes"] = str(len(raw))
    resp.headers["X-New-Bytes"] = str(len(data))
    resp.headers["X-Original-Dims"] = f"{orig_size[0]}x{orig_size[1]}"
    resp.headers["X-New-Dims"] = f"{out.size[0]}x{out.size[1]}"
    return resp


@app.get("/api/zip")
def download_zip():
    tokens = [t for t in request.args.get("tokens", "").split(",") if t]
    entries = [RESULTS[t] for t in tokens if t in RESULTS]
    if not entries:
        abort(404, "no processed files available for those tokens")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        used = set()
        for filename, data in entries:
            name, n = filename, 1
            while name in used:
                n += 1
                name = f"{Path(filename).stem}_{n}{Path(filename).suffix}"
            used.add(name)
            zf.writestr(name, data)
    buf.seek(0)
    return send_file(buf, mimetype="application/zip",
                     download_name="exported_images.zip")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False)
