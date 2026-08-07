"""Export pipeline orchestration."""

from dataclasses import dataclass, field

from .encode import ENCODERS, EncodeOptions
from .resize import LinearLightResampler, ResizeStrategy
from .sharpen import EdgeMaskedSharpener


@dataclass(frozen=True)
class ExportOptions:
    resize: ResizeStrategy
    sharpen: str = "standard"
    format: str = "png"
    encode: EncodeOptions = field(default_factory=EncodeOptions)


@dataclass(frozen=True)
class ExportResult:
    data: bytes
    size: tuple[int, int]
    resized: bool
    extension: str
    mimetype: str


def _normalize_mode(im):
    if im.mode == "P":
        return im.convert("RGBA" if "transparency" in im.info else "RGB")
    if im.mode in ("1", "I", "I;16", "I;16B", "I;16L", "F"):
        return im.convert("L")
    if im.mode in ("L", "LA", "RGB", "RGBA"):
        return im
    return im.convert("RGBA" if "A" in im.getbands() else "RGB")


class ExportPipeline:
    def __init__(self, resampler=None, sharpener=None, encoders=None):
        self.resampler = resampler or LinearLightResampler()
        self.sharpener = sharpener or EdgeMaskedSharpener()
        self.encoders = encoders or ENCODERS

    def run(self, im, options):
        icc = im.info.get("icc_profile")
        im = _normalize_mode(im)
        target = options.resize.target_size(im.width, im.height)
        resized = target != im.size
        if resized:
            im = self.resampler.resample(im, target)
        im = self.sharpener.apply(im, options.sharpen)
        if icc:
            im.info["icc_profile"] = icc
        encoder = self.encoders[options.format]
        data = encoder.encode(im, options.encode)
        return ExportResult(data, im.size, resized,
                            encoder.extension, encoder.mimetype)
