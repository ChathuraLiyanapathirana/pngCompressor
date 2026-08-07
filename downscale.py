#!/usr/bin/env python3
"""Lightroom-style image export pipeline: linear-light bicubic resize,
edge-masked output sharpening, optimized PNG/JPEG encoding."""

import argparse
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SHARPEN_PRESETS = {
    "none": None,
    "low": (0.5, 30, 0),
    "standard": (0.6, 50, 0),
    "high": (0.8, 80, 0),
}

_u = np.arange(256, dtype=np.float32) / 255.0
_SRGB_TO_LINEAR = np.where(_u <= 0.04045, _u / 12.92,
                           ((_u + 0.055) / 1.055) ** 2.4).astype(np.float32)
del _u

_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def compute_target_size(width, height, mode, *, long_edge=None, percent=None,
                        box=None, no_enlarge=True):
    if mode == "none":
        return width, height
    if mode == "long_edge":
        scale = long_edge / max(width, height)
    elif mode == "percent":
        scale = percent / 100.0
    elif mode == "fit":
        box_w, box_h = box
        scale = min(box_w / width, box_h / height)
    else:
        raise ValueError(f"unknown resize mode: {mode!r}")
    if no_enlarge:
        scale = min(scale, 1.0)
    return max(1, round(width * scale)), max(1, round(height * scale))


def _normalize_mode(im):
    if im.mode == "P":
        return im.convert("RGBA" if "transparency" in im.info else "RGB")
    if im.mode in ("1", "I", "I;16", "I;16B", "I;16L", "F"):
        return im.convert("L")
    if im.mode in ("L", "LA", "RGB", "RGBA"):
        return im
    return im.convert("RGBA" if "A" in im.getbands() else "RGB")


def _linear_to_srgb(f):
    f = np.clip(f, 0.0, 1.0)
    s = np.where(f <= 0.0031308, f * 12.92, 1.055 * f ** (1 / 2.4) - 0.055)
    return np.round(s * 255.0).astype(np.uint8)


def _resize_planes(planes, size):
    return [np.asarray(Image.fromarray(np.ascontiguousarray(p), mode="F")
                       .resize(size, Image.Resampling.BICUBIC)) for p in planes]


def _resize(im, size):
    arr = np.asarray(im)
    if im.mode in ("RGBA", "LA"):
        alpha = arr[..., -1].astype(np.float32) / 255.0
        prem = _SRGB_TO_LINEAR[arr[..., :-1]] * alpha[..., None]
        planes = _resize_planes(
            [prem[..., i] for i in range(prem.shape[-1])] + [alpha], size)
        alpha_r = np.clip(planes[-1], 0.0, 1.0)
        unprem = np.where(alpha_r > 1e-4, 1.0 / np.maximum(alpha_r, 1e-4), 0.0)
        color = np.stack(planes[:-1], axis=-1) * unprem[..., None].astype(np.float32)
        out = np.dstack([_linear_to_srgb(color),
                         np.round(alpha_r * 255.0).astype(np.uint8)])
        return Image.fromarray(out, im.mode)
    lin = _SRGB_TO_LINEAR[arr]
    if arr.ndim == 2:
        return Image.fromarray(_linear_to_srgb(_resize_planes([lin], size)[0]), "L")
    planes = _resize_planes([lin[..., i] for i in range(lin.shape[-1])], size)
    return Image.fromarray(_linear_to_srgb(np.stack(planes, axis=-1)), "RGB")


def _gauss(arr, sigma):
    r = max(1, int(sigma * 3 + 0.5))
    x = np.arange(-r, r + 1, dtype=np.float32)
    kernel = np.exp(-(x * x) / (2 * sigma * sigma))
    kernel /= kernel.sum()
    for axis in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[axis] = (r, r)
        padded = np.pad(arr, pad, mode="edge")
        out = np.zeros(arr.shape, dtype=np.float32)
        for i, w in enumerate(kernel):
            sl = [slice(None), slice(None)]
            sl[axis] = slice(i, i + arr.shape[axis])
            out += w * padded[tuple(sl)]
        arr = out
    return arr


def _sharpen(im, preset):
    params = SHARPEN_PRESETS[preset]
    if params is None or min(im.size) < 3:
        return im
    radius, percent, _ = params

    arr = np.asarray(im).astype(np.float32)
    if arr.ndim == 2:
        color, alpha = arr[..., None], None
    elif im.mode in ("RGBA", "LA"):
        color, alpha = arr[..., :-1], arr[..., -1]
    else:
        color, alpha = arr, None
    luma = color @ _LUMA if color.shape[-1] == 3 else color[..., 0]

    detail = luma - _gauss(luma, radius)
    gy, gx = np.gradient(_gauss(luma, 1.0))
    mask = np.clip((np.hypot(gx, gy) - 3.0) / 22.0, 0.0, 1.0)
    mask = np.clip(_gauss(mask, radius * 2 + 1) * 1.5, 0.0, 1.0)

    sharpened = color + (detail * (percent / 100.0) * mask)[..., None]
    sharpened = np.clip(np.round(sharpened), 0, 255).astype(np.uint8)
    if alpha is not None:
        sharpened = np.dstack([sharpened, alpha.astype(np.uint8)])
    if im.mode == "L":
        sharpened = sharpened[..., 0]
    return Image.fromarray(sharpened, im.mode)


def process_image(im, mode, *, long_edge=None, percent=None, box=None,
                  sharpen="standard", no_enlarge=True, colors=None):
    icc = im.info.get("icc_profile")
    im = _normalize_mode(im)
    target = compute_target_size(im.width, im.height, mode, long_edge=long_edge,
                                 percent=percent, box=box, no_enlarge=no_enlarge)
    resized = target != im.size
    if resized:
        im = _resize(im, target)
    im = _sharpen(im, sharpen)
    if colors:
        im = im.quantize(colors=colors, method=Image.Quantize.FASTOCTREE)
    if icc:
        im.info["icc_profile"] = icc
    return im, resized


def _flatten(im, background=(255, 255, 255)):
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        base = Image.new("RGB", im.size, background)
        base.paste(rgba, mask=rgba.getchannel("A"))
        return base
    if im.mode in ("RGB", "L"):
        return im
    return im.convert("RGB")


def save_bytes(im, fmt="png", quality=85):
    buf = io.BytesIO()
    kwargs = {"optimize": True}
    if im.info.get("icc_profile"):
        kwargs["icc_profile"] = im.info["icc_profile"]
    if fmt == "jpeg":
        quality = max(1, min(100, quality))
        im = _flatten(im)
        im.save(buf, "JPEG", quality=quality, progressive=True,
                subsampling=0 if quality >= 90 else 2, **kwargs)
    else:
        im.save(buf, "PNG", **kwargs)
    return buf.getvalue()


def process_file(src, dst, mode, *, fmt="png", quality=85, **kwargs):
    with Image.open(src) as im:
        im.load()
        out, _ = process_image(im, mode, **kwargs)
    data = save_bytes(out, fmt, quality)
    Path(dst).write_bytes(data)
    return Path(src).stat().st_size, len(data), out.size


def _parse_fit(value):
    try:
        w, h = value.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT, e.g. 1920x1080")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compress and optionally downscale images with a "
                    "Lightroom-style export pipeline.")
    parser.add_argument("inputs", nargs="+", type=Path, help="input image file(s)")
    size = parser.add_mutually_exclusive_group(required=True)
    size.add_argument("--long-edge", type=int, metavar="PX",
                      help="resize so the long edge is PX pixels")
    size.add_argument("--percent", type=float, metavar="PCT",
                      help="resize to PCT%% of original dimensions")
    size.add_argument("--fit", type=_parse_fit, metavar="WxH",
                      help="fit within WxH pixels (aspect preserved)")
    size.add_argument("--no-resize", action="store_true",
                      help="keep original dimensions, compress only")
    parser.add_argument("--format", choices=("png", "jpeg"), default="png",
                        dest="fmt", help="output format (default: png)")
    parser.add_argument("--quality", type=int, default=85, metavar="1-100",
                        help="JPEG quality (default: 85)")
    parser.add_argument("--sharpen", choices=SHARPEN_PRESETS, default="standard",
                        help="screen output sharpening amount (default: standard)")
    parser.add_argument("--colors", type=int, metavar="N",
                        help="quantize PNG to N colors (lossy)")
    parser.add_argument("--allow-enlarge", action="store_true",
                        help="allow upscaling smaller images")
    parser.add_argument("-o", "--output", type=Path,
                        help="output file (single input only)")
    parser.add_argument("--out-dir", type=Path, help="output directory")
    parser.add_argument("--suffix", default="_small",
                        help="filename suffix when no explicit output is given")
    args = parser.parse_args(argv)

    if args.output and len(args.inputs) > 1:
        parser.error("-o/--output only works with a single input; use --out-dir")
    if args.colors and args.fmt == "jpeg":
        parser.error("--colors only applies to --format png")

    mode = ("long_edge" if args.long_edge else "percent" if args.percent
            else "fit" if args.fit else "none")
    opts = dict(long_edge=args.long_edge, percent=args.percent, box=args.fit,
                sharpen=args.sharpen, no_enlarge=not args.allow_enlarge,
                colors=args.colors, fmt=args.fmt, quality=args.quality)

    ext = ".jpg" if args.fmt == "jpeg" else ".png"
    failures = 0
    for src in args.inputs:
        if args.output:
            dst = args.output
        else:
            out_dir = args.out_dir or src.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            dst = out_dir / f"{src.stem}{args.suffix}{ext}"
        try:
            orig, new, (w, h) = process_file(src, dst, mode, **opts)
        except Exception as exc:
            print(f"ERROR {src}: {exc}", file=sys.stderr)
            failures += 1
            continue
        saved = (1 - new / orig) * 100 if orig else 0
        change = f"{abs(saved):.1f}% {'smaller' if saved >= 0 else 'larger'}"
        print(f"{src} -> {dst}  {w}x{h}  "
              f"{orig / 1024:.0f} KB -> {new / 1024:.0f} KB  ({change})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
