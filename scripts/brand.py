"""Shared design tokens and SVG helpers for the profile assets.

Standard library only, so the scheduled workflow can import it without
installing anything. Palette ramps are derived in OKLCH from the brand
violet (#6C63FF) with monotonic lightness; text colours clear WCAG AA (4.5:1)
on their surfaces.
"""

import base64
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "scripts" / "fonts"

BRAND = "#6C63FF"

DARK = {
    "name": "dark",
    "card_a": "#111528",
    "card_b": "#0B0E17",
    "border": "#262B40",
    "tile": "#151A2C",
    "tile_border": "#252B42",
    "grid": "#2A3050",
    "text": "#E6EDF3",
    "muted": "#8B949E",
    "accent": "#8B85FF",  # violet for text, 6.2:1 on the card
    "cyan": "#22D3EE",
    "pink": "#F472B6",
    "glow": 0.42,
    "blend": "screen",
    # contribution ramp: empty, then four OKLCH steps (L .40/.52/.64/.78)
    "ramp": ["#1B2032", "#3C349A", "#5952D2", "#7978FB", "#A9AFFE"],
    "splat": ["#22D3EE", "#60A5FA", "#7978FB", "#A78BFA", "#F472B6"],
}

LIGHT = {
    "name": "light",
    "card_a": "#FFFFFF",
    "card_b": "#F5F4FF",
    "border": "#D8DBE8",
    "tile": "#FFFFFF",
    "tile_border": "#E1E3EE",
    "grid": "#D9DAF0",
    "text": "#1F2328",
    "muted": "#59636E",
    "accent": "#5B52F0",  # 5.4:1 on white
    "cyan": "#0E7490",
    "pink": "#DB2777",
    "glow": 0.20,
    "blend": "multiply",
    # contribution ramp: empty, then four OKLCH steps (L .88/.75/.60/.45)
    "ramp": ["#EBEDF0", "#CFD4FE", "#9EA4FF", "#6E6CED", "#4843AA"],
    "splat": ["#06B6D4", "#3B82F6", "#6C63FF", "#8B5CF6", "#EC4899"],
}

THEMES = (DARK, LIGHT)

# font key -> (family name used in CSS, weight)
FONTS = {
    "display": ("Space Grotesk", 700),
    "display-medium": ("Space Grotesk", 500),
    "mono": ("JetBrains Mono", 400),
    "mono-bold": ("JetBrains Mono", 700),
}

MONO_ADVANCE = 0.6  # JetBrains Mono advance width, in em

REDUCED_MOTION_CSS = (
    "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"
)


def esc(text):
    return escape(str(text), {'"': "&quot;"})


_metrics = None


def measure(text, key, size):
    """Advance width in px from scripts/fonts/metrics.json (written by
    build_assets.py), so the workflow can lay out text without fontTools."""
    global _metrics
    if _metrics is None:
        _metrics = json.loads((FONT_DIR / "metrics.json").read_text())
    table = _metrics[key]
    fallback = table["advances"][" "]
    return sum(table["advances"].get(ch, fallback) for ch in text) * size / table["upm"]


def font_face_css(key, woff2_bytes=None):
    """@font-face rule embedding a woff2 subset as a data URI.

    Images rendered through <img> cannot fetch web fonts, but data URIs load
    fine (verified under raw.githubusercontent.com's CSP).
    """
    family, weight = FONTS[key]
    if woff2_bytes is None:
        woff2_bytes = (FONT_DIR / f"{key}.woff2").read_bytes()
    data = base64.b64encode(woff2_bytes).decode("ascii")
    return (
        f"@font-face{{font-family:'{family}';font-weight:{weight};"
        f"src:url(data:font/woff2;base64,{data}) format('woff2')}}"
    )


def svg_open(width, height, title, desc):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d">'
        f'<title id="t">{esc(title)}</title><desc id="d">{esc(desc)}</desc>'
    )


def card_background(width, height, theme, radius=20, gid="cardbg"):
    """Rounded card with a diagonal gradient and hairline border."""
    return (
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{theme["card_a"]}"/>'
        f'<stop offset="1" stop-color="{theme["card_b"]}"/></linearGradient></defs>'
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="{radius}" '
        f'fill="url(#{gid})" stroke="{theme["border"]}"/>'
    )


# ---------------------------------------------------------------- colour maths


def _to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_to_oklch(hex_color):
    r, g, b = (_to_linear(int(hex_color[i:i + 2], 16) / 255) for i in (1, 3, 5))
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(A, B), math.degrees(math.atan2(B, A)) % 360


def oklch_to_hex(L, C, H):
    """OKLCH to sRGB hex, reducing chroma until the colour is in gamut."""

    def rgb(chroma):
        a = chroma * math.cos(math.radians(H))
        b = chroma * math.sin(math.radians(H))
        l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
        m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
        s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
        return (
            4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
        )

    while C > 0 and not all(-1e-6 <= v <= 1 + 1e-6 for v in rgb(C)):
        C -= 0.002
    channels = rgb(max(C, 0))
    return "#" + "".join(
        "%02X" % round(min(1, max(0, _to_srgb(min(1, max(0, v))))) * 255)
        for v in channels
    )


def luminance(hex_color):
    r, g, b = (_to_linear(int(hex_color[i:i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def legible(hex_color, surface, minimum=3.0):
    """Keep a brand hue but move its lightness until it reaches `minimum`
    contrast against `surface` (3:1 is the WCAG floor for graphics)."""
    if contrast(hex_color, surface) >= minimum:
        return hex_color
    L, C, H = hex_to_oklch(hex_color)
    step = 0.02 if luminance(surface) < 0.5 else -0.02
    while 0 < L < 1:
        L += step
        candidate = oklch_to_hex(L, C, H)
        if contrast(candidate, surface) >= minimum:
            return candidate
    return "#FFFFFF" if step > 0 else "#000000"
