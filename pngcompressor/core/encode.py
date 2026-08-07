"""Output format encoders."""

import io
from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class EncodeOptions:
    quality: int = 85
    colors: int | None = None


class Encoder(ABC):
    extension: str
    mimetype: str

    @abstractmethod
    def encode(self, im, options):
        raise NotImplementedError

    @staticmethod
    def _icc(im):
        icc = im.info.get("icc_profile")
        return {"icc_profile": icc} if icc else {}


class PngEncoder(Encoder):
    extension = "png"
    mimetype = "image/png"

    def encode(self, im, options):
        icc = self._icc(im)
        if options.colors:
            im = im.quantize(colors=max(2, min(256, options.colors)),
                             method=Image.Quantize.FASTOCTREE)
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True, **icc)
        return buf.getvalue()


class JpegEncoder(Encoder):
    extension = "jpg"
    mimetype = "image/jpeg"

    def encode(self, im, options):
        icc = self._icc(im)
        quality = max(1, min(100, options.quality))
        im = self._flatten(im)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True,
                subsampling=0 if quality >= 90 else 2, **icc)
        return buf.getvalue()

    @staticmethod
    def _flatten(im, background=(255, 255, 255)):
        if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            base = Image.new("RGB", im.size, background)
            base.paste(rgba, mask=rgba.getchannel("A"))
            return base
        if im.mode in ("RGB", "L"):
            return im
        return im.convert("RGB")


ENCODERS = {"png": PngEncoder(), "jpeg": JpegEncoder()}
