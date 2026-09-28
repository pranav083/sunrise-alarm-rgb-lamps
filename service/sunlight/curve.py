"""Sunrise colour/brightness curve (lamp-independent) and floor-lamp conversion."""
import math

# (p, r, g, b, brightness) in standard RGB; verified on the floor lamp 2026-09-28.
KEYFRAMES = [
    (0.00,  80,   0,   0, 0.005),
    (0.10, 140,   5,   0, 0.015),
    (0.20, 200,  15,   0, 0.04),
    (0.35, 255,  45,   0, 0.09),
    (0.50, 255,  95,   5, 0.18),
    (0.62, 255, 135,  30, 0.30),
    (0.72, 255, 160,  60, 0.44),
    (0.82, 255, 185,  95, 0.60),
    (0.91, 255, 205, 125, 0.78),
    (1.00, 255, 220, 150, 1.00),
]

# Floor lamp LEDs: green ~3x and blue ~1.7x too strong.
G_SCALE = 0.3
B_SCALE = 0.6


def curve(p: float) -> tuple[float, float, float, float]:
    """Return (r, g, b, brightness) at progress p, smoothstep-interpolated between keyframes."""
    p = min(1.0, max(0.0, p))
    for a, b in zip(KEYFRAMES, KEYFRAMES[1:]):
        if p <= b[0]:
            t = (p - a[0]) / (b[0] - a[0])
            t = t * t * (3 - 2 * t)
            return tuple(a[i] + (b[i] - a[i]) * t for i in range(1, 5))
    return tuple(KEYFRAMES[-1][1:])


def floor_values(r: float, g: float, b: float, brightness: float) -> tuple[int, int, int, int]:
    """Convert curve output to floor-lamp (R, G, B, pct).

    The lamp only accepts whole-percent brightness, so use the next percent up and scale RGB
    down to land exactly on the target level (RGB has 255 steps -> much finer dimming).
    """
    pct = max(1, min(100, math.ceil(round(brightness * 100, 6))))
    k = min(1.0, brightness * 100 / pct)
    return round(r * k), round(g * G_SCALE * k), round(b * B_SCALE * k), pct
