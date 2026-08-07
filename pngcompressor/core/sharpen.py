"""Edge-masked luminance output sharpening."""

import numpy as np
from PIL import Image

from .color import LUMA_WEIGHTS

PRESETS = {
    "none": None,
    "low": (0.5, 30),
    "standard": (0.6, 50),
    "high": (0.8, 80),
}


class EdgeMaskedSharpener:
    noise_floor = 3.0
    edge_range = 22.0

    def apply(self, im, preset):
        params = PRESETS[preset]
        if params is None or min(im.size) < 3:
            return im
        radius, percent = params

        arr = np.asarray(im).astype(np.float32)
        if arr.ndim == 2:
            color, alpha = arr[..., None], None
        elif im.mode in ("RGBA", "LA"):
            color, alpha = arr[..., :-1], arr[..., -1]
        else:
            color, alpha = arr, None
        luma = color @ LUMA_WEIGHTS if color.shape[-1] == 3 else color[..., 0]

        detail = luma - self._gauss(luma, radius)
        mask = self._edge_mask(luma, radius)

        sharpened = color + (detail * (percent / 100.0) * mask)[..., None]
        sharpened = np.clip(np.round(sharpened), 0, 255).astype(np.uint8)
        if alpha is not None:
            sharpened = np.dstack([sharpened, alpha.astype(np.uint8)])
        if im.mode == "L":
            sharpened = sharpened[..., 0]
        return Image.fromarray(sharpened, im.mode)

    def _edge_mask(self, luma, radius):
        gy, gx = np.gradient(self._gauss(luma, 1.0))
        mask = np.clip((np.hypot(gx, gy) - self.noise_floor) / self.edge_range,
                       0.0, 1.0)
        return np.clip(self._gauss(mask, radius * 2 + 1) * 1.5, 0.0, 1.0)

    @staticmethod
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
