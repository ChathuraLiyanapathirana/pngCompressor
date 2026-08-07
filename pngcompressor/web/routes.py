"""HTTP routes."""

import io
import re
import zipfile
from pathlib import Path

from flask import Blueprint, abort, current_app, request, send_file
from PIL import Image

from .forms import ValidationError, parse_export_form

bp = Blueprint("api", __name__)


def _safe_stem(name):
    stem = Path(name or "image").stem
    stem = re.sub(r"[^\w.\- ]", "_", stem).strip() or "image"
    return stem


@bp.get("/")
def index():
    return current_app.send_static_file("index.html")


@bp.post("/api/process")
def process():
    upload = request.files.get("file")
    if upload is None:
        abort(400, "no file uploaded")
    try:
        options = parse_export_form(request.form)
    except ValidationError as exc:
        abort(400, str(exc))

    raw = upload.read()
    pipeline = current_app.extensions["pipeline"]
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            orig_size = im.size
            result = pipeline.run(im, options)
    except Exception:
        abort(415, "could not decode image — is it a valid PNG/JPEG?")

    filename = (f"{_safe_stem(upload.filename)}_{max(result.size)}px"
                f".{result.extension}")
    token = current_app.extensions["results"].put(filename, result.data)

    resp = send_file(io.BytesIO(result.data), mimetype=result.mimetype,
                     download_name=filename)
    resp.headers["X-Token"] = token
    resp.headers["X-Filename"] = filename
    resp.headers["X-Original-Bytes"] = str(len(raw))
    resp.headers["X-New-Bytes"] = str(len(result.data))
    resp.headers["X-Original-Dims"] = f"{orig_size[0]}x{orig_size[1]}"
    resp.headers["X-New-Dims"] = f"{result.size[0]}x{result.size[1]}"
    return resp


@bp.get("/api/zip")
def download_zip():
    tokens = [t for t in request.args.get("tokens", "").split(",") if t]
    entries = current_app.extensions["results"].get_many(tokens)
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
