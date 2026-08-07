"""Resize strategies and the linear-light bicubic resampler."""

from abc import ABC, abstractmethod

import numpy as np
from PIL import Image

from .color import linear_to_srgb, srgb_to_linear

MODES = ("none", "long_edge", "percent", "fit")


class ResizeStrategy(ABC):
    def __init__(self, no_enlarge=True):
        self.no_enlarge = no_enlarge

    @abstractmethod
    def _scale(self, width, height):
        raise NotImplementedError

    def target_size(self, width, height):
        scale = self._scale(width, height)
        if self.no_enlarge:
            scale = min(scale, 1.0)
        return max(1, round(width * scale)), max(1, round(height * scale))


class NoResize(ResizeStrategy):
    def _scale(self, width, height):
        return 1.0


class LongEdge(ResizeStrategy):
    def __init__(self, pixels, no_enlarge=True):
        super().__init__(no_enlarge)
        self.pixels = pixels

    def _scale(self, width, height):
        return self.pixels / max(width, height)


class Percent(ResizeStrategy):
    def __init__(self, percent, no_enlarge=True):
        super().__init__(no_enlarge)
        self.percent = percent

    def _scale(self, width, height):
        return self.percent / 100.0


class FitWithin(ResizeStrategy):
    def __init__(self, width, height, no_enlarge=True):
        super().__init__(no_enlarge)
        self.box = (width, height)

    def _scale(self, width, height):
        return min(self.box[0] / width, self.box[1] / height)


def build_strategy(mode, *, long_edge=None, percent=None, box=None, no_enlarge=True):
    if mode == "none":
        return NoResize(no_enlarge)
    if mode == "long_edge":
        return LongEdge(long_edge, no_enlarge)
    if mode == "percent":
        return Percent(percent, no_enlarge)
    if mode == "fit":
        return FitWithin(*box, no_enlarge=no_enlarge)
    raise ValueError(f"unknown resize mode: {mode!r}")


class LinearLightResampler:
    """Bicubic resampling in linear light with premultiplied alpha."""

    filter = Image.Resampling.BICUBIC

    def resample(self, im, size):
        arr = np.asarray(im)
        if im.mode in ("RGBA", "LA"):
            return self._resample_with_alpha(im, arr, size)
        lin = srgb_to_linear(arr)
        if arr.ndim == 2:
            return Image.fromarray(linear_to_srgb(self._planes([lin], size)[0]), "L")
        planes = self._planes([lin[..., i] for i in range(lin.shape[-1])], size)
        return Image.fromarray(linear_to_srgb(np.stack(planes, axis=-1)), "RGB")

    def _resample_with_alpha(self, im, arr, size):
        alpha = arr[..., -1].astype(np.float32) / 255.0
        prem = srgb_to_linear(arr[..., :-1]) * alpha[..., None]
        planes = self._planes(
            [prem[..., i] for i in range(prem.shape[-1])] + [alpha], size)
        alpha_r = np.clip(planes[-1], 0.0, 1.0)
        unprem = np.where(alpha_r > 1e-4, 1.0 / np.maximum(alpha_r, 1e-4), 0.0)
        color = np.stack(planes[:-1], axis=-1) * unprem[..., None].astype(np.float32)
        out = np.dstack([linear_to_srgb(color),
                         np.round(alpha_r * 255.0).astype(np.uint8)])
        return Image.fromarray(out, im.mode)

    def _planes(self, planes, size):
        return [np.asarray(Image.fromarray(np.ascontiguousarray(p), mode="F")
                           .resize(size, self.filter)) for p in planes]
