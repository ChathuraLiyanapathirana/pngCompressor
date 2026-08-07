"""sRGB <-> linear-light conversion."""

import numpy as np

_u = np.arange(256, dtype=np.float32) / 255.0
_SRGB_TO_LINEAR = np.where(_u <= 0.04045, _u / 12.92,
                           ((_u + 0.055) / 1.055) ** 2.4).astype(np.float32)
del _u

LUMA_WEIGHTS = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def srgb_to_linear(arr):
    return _SRGB_TO_LINEAR[arr]


def linear_to_srgb(f):
    f = np.clip(f, 0.0, 1.0)
    s = np.where(f <= 0.0031308, f * 12.92, 1.055 * f ** (1 / 2.4) - 0.055)
    return np.round(s * 255.0).astype(np.uint8)
