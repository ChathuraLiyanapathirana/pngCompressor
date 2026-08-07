"""Command-line interface."""

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

from .core import (ENCODERS, EncodeOptions, ExportOptions, ExportPipeline,
                   SHARPEN_PRESETS, build_strategy)


def _parse_fit(value):
    try:
        w, h = value.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT, e.g. 1920x1080")


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="pngcompressor",
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
    parser.add_argument("--format", choices=tuple(ENCODERS), default="png",
                        dest="fmt", help="output format (default: png)")
    parser.add_argument("--quality", type=int, default=85, metavar="1-100",
                        help="JPEG quality (default: 85)")
    parser.add_argument("--sharpen", choices=tuple(SHARPEN_PRESETS),
                        default="standard",
                        help="screen output sharpening amount (default: standard)")
    parser.add_argument("--colors", type=int, metavar="N",
                        help="quantize PNG to N colors (lossy)")
    parser.add_argument("--allow-enlarge", action="store_true",
                        help="allow upscaling smaller images")
    parser.add_argument("-j", "--jobs", type=int,
                        default=min(4, os.cpu_count() or 1), metavar="N",
                        help="images to process in parallel (default: up to 4)")
    parser.add_argument("-o", "--output", type=Path,
                        help="output file (single input only)")
    parser.add_argument("--out-dir", type=Path, help="output directory")
    parser.add_argument("--suffix", default="_small",
                        help="filename suffix when no explicit output is given")
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.output and len(args.inputs) > 1:
        parser.error("-o/--output only works with a single input; use --out-dir")
    if args.colors and args.fmt == "jpeg":
        parser.error("--colors only applies to --format png")

    mode = ("long_edge" if args.long_edge else "percent" if args.percent
            else "fit" if args.fit else "none")
    strategy = build_strategy(mode, long_edge=args.long_edge,
                              percent=args.percent, box=args.fit,
                              no_enlarge=not args.allow_enlarge)
    options = ExportOptions(resize=strategy, sharpen=args.sharpen,
                            format=args.fmt,
                            encode=EncodeOptions(quality=args.quality,
                                                 colors=args.colors))
    pipeline = ExportPipeline()
    ext = f".{ENCODERS[args.fmt].extension}"

    def run_one(src):
        if args.output:
            dst = args.output
        else:
            out_dir = args.out_dir or src.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            dst = out_dir / f"{src.stem}{args.suffix}{ext}"
        with Image.open(src) as im:
            im.load()
            result = pipeline.run(im, options)
        dst.write_bytes(result.data)
        return dst, result

    failures = 0
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(run_one, src): src for src in args.inputs}
        for future in as_completed(futures):
            src = futures[future]
            try:
                dst, result = future.result()
            except Exception as exc:
                print(f"ERROR {src}: {exc}", file=sys.stderr)
                failures += 1
                continue
            orig, new = src.stat().st_size, len(result.data)
            saved = (1 - new / orig) * 100 if orig else 0
            change = f"{abs(saved):.1f}% {'smaller' if saved >= 0 else 'larger'}"
            w, h = result.size
            print(f"{src} -> {dst}  {w}x{h}  "
                  f"{orig / 1024:.0f} KB -> {new / 1024:.0f} KB  ({change})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
