"""Request parsing and validation."""

from ..core import (ENCODERS, EncodeOptions, ExportOptions, RESIZE_MODES,
                    SHARPEN_PRESETS, build_strategy)


class ValidationError(ValueError):
    pass


def parse_export_form(form):
    sharpen = form.get("sharpen", "standard")
    if sharpen not in SHARPEN_PRESETS:
        raise ValidationError(f"bad sharpen value: {sharpen}")
    fmt = form.get("format", "png")
    if fmt not in ENCODERS:
        raise ValidationError(f"bad format: {fmt}")
    mode = form.get("mode", "long_edge")
    if mode not in RESIZE_MODES:
        raise ValidationError(f"bad resize mode: {mode}")

    try:
        quality = max(1, min(100, int(form.get("quality", 85))))
        colors = None
        if fmt == "png" and form.get("reduce_colors") == "1":
            colors = max(2, min(256, int(form.get("colors", 256))))
        kwargs = {"no_enlarge": form.get("no_enlarge", "1") != "0"}
        if mode == "long_edge":
            kwargs["long_edge"] = max(1, int(form["long_edge"]))
        elif mode == "percent":
            kwargs["percent"] = max(0.1, min(100.0, float(form["percent"])))
        elif mode == "fit":
            kwargs["box"] = (max(1, int(form["width"])),
                             max(1, int(form["height"])))
        strategy = build_strategy(mode, **kwargs)
    except (KeyError, ValueError):
        raise ValidationError("missing or invalid resize parameters")

    return ExportOptions(resize=strategy, sharpen=sharpen, format=fmt,
                         encode=EncodeOptions(quality=quality, colors=colors))
