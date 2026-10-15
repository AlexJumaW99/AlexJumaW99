"""Build the static profile artwork in assets/.

    pip install fonttools brotli
    python scripts/build_assets.py

Writes the hero banner, tech-stack panel, contact buttons, heading glyph and
footer (dark and light variants where the colours differ), plus the font
subsets in scripts/fonts/ that the scheduled activity card embeds. Edit the
content constants below and re-run; the README picks the files up as-is.
"""

import io
import json
import math
import random
import re
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from brand import (
    BRAND, DARK, FONT_DIR, FONTS, LIGHT, MONO_ADVANCE, REDUCED_MOTION_CSS, ROOT,
    THEMES, card_background, esc, font_face_css, legible, svg_open,
)

ASSETS = ROOT / "assets"
ICON_DIR = ROOT / "scripts" / "icons"

SOURCE_FONTS = {
    "Space Grotesk": FONT_DIR / "SpaceGrotesk[wght].ttf",
    "JetBrains Mono": FONT_DIR / "JetBrainsMono[wght].ttf",
}

# ------------------------------------------------------------------ content

KICKER = "WINNIPEG, CANADA"
NAME = "Alex Juma"
ROLE = ("Agentic AI", " × ", "3D Vision Engineer")
TAGLINES = [
    "orchestrating multi-agent systems with LangGraph",
    "turning photos & video into 3D Gaussian splats",
    "running GPU-native 3D pipelines on Blackwell",
    "shipping AI products from idea to production",
]
COORDS = "49.90°N  97.14°W"

# (row label, [(simple-icons slug or custom key, tile label, brand hex)])
STACK = [
    ("AGENTIC AI", [
        ("langgraph", "LangGraph", "7FC8FF"),
        ("langchain", "LangChain", "7FC8FF"),
        ("googlegemini", "Gemini", "8E75B2"),
        ("fastapi", "FastAPI", "009688"),
        ("postgresql", "pgvector", "4169E1"),
        ("streamlit", "Streamlit", "FF4B4B"),
    ]),
    ("3D & GPU", [
        ("pytorch", "PyTorch", "EE4C2C"),
        ("nvidia", "CUDA", "76B900"),
        ("@splat", "Splatting", None),
        ("opencv", "OpenCV", "5C3EE8"),
        ("docker", "Docker", "2496ED"),
        ("linux", "Linux", "FCC624"),
    ]),
    ("DATA & ML", [
        ("scikitlearn", "scikit-learn", "F7931E"),
        ("pandas", "pandas", "150458"),
        ("numpy", "NumPy", "013243"),
        ("jupyter", "Jupyter", "F37626"),
        ("d3", "D3.js", "F9A03C"),
        ("@sql", "SQL", None),
    ]),
    ("LANGUAGES & WEB", [
        ("python", "Python", "3776AB"),
        ("javascript", "JavaScript", "F7DF1E"),
        ("c", "C", "A8B9CC"),
        ("html5", "HTML5", "E34F26"),
        ("css", "CSS", "663399"),
        ("django", "Django", "092E20"),
        ("git", "Git", "F03C2E"),
    ]),
]

MOTTO = "Audentes Fortuna Iuvat"
MOTTO_EN = "fortune favours the bold"

# ------------------------------------------------------------------ fonts

_instances = {}


def font_instance(key):
    """Static instance of the variable source font at the key's weight."""
    if key not in _instances:
        family, weight = FONTS[key]
        font = TTFont(SOURCE_FONTS[family])
        _instances[key] = instancer.instantiateVariableFont(font, {"wght": weight})
    return _instances[key]


def woff2_subset(key, text):
    font = font_instance(key)
    font.recalcTimestamp = False  # reproducible output: no build time in head.modified
    buf = io.BytesIO()
    font.save(buf)
    buf.seek(0)
    font = TTFont(buf, recalcTimestamp=False)
    options = subset.Options()
    options.flavor = "woff2"
    options.hinting = False
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]  # keep copyright + OFL notice
    options.layout_features = ["kern"]  # JetBrains Mono's code ligatures would bloat every subset
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    out = io.BytesIO()
    font.flavor = "woff2"
    font.save(out)
    return out.getvalue()


def measure(text, key, size):
    """Advance width of `text` in px (ignores kerning; close enough for layout)."""
    font = font_instance(key)
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    upm = font["head"].unitsPerEm
    return sum(hmtx[cmap.get(ord(ch), cmap[32])][0] for ch in text) * size / upm


class FontBook:
    """Collects the text each SVG draws so its fonts are subset to exactly that."""

    def __init__(self):
        self.text = {}

    def use(self, key, text):
        self.text[key] = self.text.get(key, "") + text
        return text

    def css(self):
        return "".join(
            font_face_css(key, woff2_subset(key, chars))
            for key, chars in self.text.items()
        )


def font_rule(key, size, extra=""):
    family, weight = FONTS[key]
    return f"font-family:'{family}',sans-serif;font-weight:{weight};font-size:{size}px;{extra}"


# ------------------------------------------------------------------ hero

EASE_SINE = "cubic-bezier(.37,0,.63,1)"


def typing_animation(fonts, theme, x, y, size):
    """Typewriter cycling through TAGLINES, built from discrete SMIL steps."""
    cw = size * MONO_ADVANCE
    type_ms, hold_ms, delete_ms, gap_ms = 48, 2100, 18, 380
    slots = []
    t = 0
    for line in TAGLINES:
        n = len(line)
        start = t
        t += n * type_ms + hold_ms + n * delete_ms + gap_ms
        slots.append((start, n))
    total = t

    def width_timeline(index):
        start, n = slots[index]
        steps = [(0, 0)]
        for k in range(1, n + 1):
            steps.append((start + k * type_ms, k * cw))
        erase_at = start + n * type_ms + hold_ms
        for k in range(n - 1, -1, -1):
            steps.append((erase_at + (n - k) * delete_ms, k * cw))
        return steps

    parts = []
    caret_steps = [(0, 0)]
    for i, line in enumerate(TAGLINES):
        steps = width_timeline(i)
        caret_steps += steps[1:]
        key_times = ";".join(f"{ms / total:.5f}" for ms, _ in steps)
        values = ";".join(f"{w:.1f}" for _, w in steps)
        parts.append(
            f'<clipPath id="type{i}"><rect x="{x}" y="{y - size}" width="0" height="{size * 1.5}">'
            f'<animate attributeName="width" dur="{total}ms" repeatCount="indefinite" '
            f'calcMode="discrete" keyTimes="{key_times}" values="{values}"/></rect></clipPath>'
            f'<text x="{x}" y="{y}" clip-path="url(#type{i})" class="typed">'
            f"{esc(fonts.use('mono', line))}</text>"
        )
    caret_steps.sort()
    key_times = ";".join(f"{ms / total:.5f}" for ms, _ in caret_steps)
    values = ";".join(f"{x + w + 2:.1f}" for _, w in caret_steps)
    parts.append(
        f'<rect class="caret" x="{x + 2}" y="{y - size * 0.82}" width="2.5" height="{size * 1.05}" rx="1">'
        f'<animate attributeName="x" dur="{total}ms" repeatCount="indefinite" calcMode="discrete" '
        f'keyTimes="{key_times}" values="{values}"/></rect>'
    )
    return "".join(parts)


def splat_globe(theme, cx, cy, radius, count=120, half_period=9.0, seed=7):
    """Rotating sphere of Gaussian splats.

    Each splat slides on an ease-in-out-sine path (x) while a quarter-phase
    shifted scale/opacity animation fakes depth, which together read as a
    rotation about the vertical axis. Blend mode is commutative, so no
    per-frame depth sorting is needed.
    """
    rng = random.Random(seed)
    golden = math.pi * (3 - math.sqrt(5))
    D = half_period
    keyframes = {}
    splats = []
    for i in range(count):
        yy = 1 - 2 * (i + 0.5) / count
        ring = math.sqrt(max(0.0, 1 - yy * yy))
        theta = (i * golden) % (2 * math.pi)
        amp = round(ring * radius / 3) * 3
        keyframes.setdefault(amp, f"@keyframes x{amp}{{from{{transform:translateX(-{amp}px)}}to{{transform:translateX({amp}px)}}}}")
        tau = D * (theta / math.pi + 0.5)
        dx = -(tau % (2 * D))
        dz = dx + D / 2 - 2 * D
        rx = 6 + rng.random() * 7.5
        ry = rx * (0.42 + rng.random() * 0.5)
        rot = rng.randrange(0, 180)
        band = min(4, int((1 - yy) / 2 * 5))
        splats.append(
            f'<g transform="translate({cx},{cy - yy * radius:.1f})" class="s">'
            f'<g class="x{amp}" style="animation-delay:{dx:.2f}s">'
            f'<g class="z" style="animation-delay:{dz:.2f}s">'
            f'<ellipse rx="{rx:.1f}" ry="{ry:.1f}" transform="rotate({rot})" fill="url(#sp{band})"/>'
            f"</g></g></g>"
        )
    grads = "".join(
        f'<radialGradient id="sp{b}"><stop offset="0" stop-color="{c}" stop-opacity=".95"/>'
        f'<stop offset=".55" stop-color="{c}" stop-opacity=".45"/>'
        f'<stop offset="1" stop-color="{c}" stop-opacity="0"/></radialGradient>'
        for b, c in enumerate(theme["splat"])
    )
    css = (
        "".join(keyframes.values())
        + f".s{{mix-blend-mode:{theme['blend']}}}"
        + "".join(
            f".x{a}{{animation:x{a} {D}s {EASE_SINE} infinite alternate}}" for a in keyframes
        )
        + f".z{{transform-box:fill-box;transform-origin:center;"
        f"animation:z {D}s {EASE_SINE} infinite alternate}}"
        "@keyframes z{from{transform:scale(.4);opacity:.16}to{transform:scale(1.1);opacity:1}}"
    )
    return grads, css, "".join(splats)


def orbit(theme, cx, cy, rx, ry, tilt, half_period=5.5, nodes=3):
    """Tilted ring with agent nodes circling the globe (same sine trick)."""
    D = half_period
    back = f'<path d="M{-rx} 0A{rx} {ry} 0 0 1 {rx} 0" class="ring back"/>'
    front = f'<path d="M{rx} 0A{rx} {ry} 0 0 1 {-rx} 0" class="ring"/>'
    dots = []
    for n in range(nodes):
        phase = 2 * D * n / nodes
        dx = -phase
        dy = dx + D / 2 - 2 * D
        dots.append(
            f'<g class="ox" style="animation-delay:{dx:.2f}s">'
            f'<g class="oy" style="animation-delay:{dy:.2f}s">'
            f'<circle r="11" class="halo"/><circle r="4.2" class="node"/></g></g>'
        )
    css = (
        f"@keyframes ox{{from{{transform:translateX(-{rx}px)}}to{{transform:translateX({rx}px)}}}}"
        f"@keyframes oy{{from{{transform:translateY(-{ry}px) scale(.6);opacity:.25}}"
        f"to{{transform:translateY({ry}px) scale(1.15);opacity:1}}}}"
        f".ox{{animation:ox {D}s {EASE_SINE} infinite alternate}}"
        f".oy{{animation:oy {D}s {EASE_SINE} infinite alternate}}"
        f".ring{{fill:none;stroke:{theme['accent']};stroke-width:1.2;stroke-dasharray:3 7;opacity:.55}}"
        f".ring.back{{opacity:.22}}"
        f".node{{fill:{theme['cyan']}}}.halo{{fill:{theme['cyan']};opacity:.22}}"
    )
    group = f'<g transform="translate({cx},{cy}) rotate({tilt})">'
    return css, group + back + "</g>", group + front + "".join(dots) + "</g>"


HERO_LAYOUTS = {
    # side by side: text left, globe right
    "desktop": dict(W=1200, H=400, left=72, kicker_y=104, name_y=196, name_size=96,
                    role_y=252, role_size=28, type_y=318, type_size=20,
                    gx=948, gy=198, gr=124, glow_r=250, coords=(1160, 370, "end")),
    # stacked for phones: globe on top, larger type (shown at ~0.6x)
    "mobile": dict(W=600, H=600, left=40, kicker_y=372, name_y=452, name_size=78,
                   role_y=500, role_size=25, type_y=558, type_size=17,
                   gx=300, gy=180, gr=106, glow_r=200, coords=(572, 44, "end")),
}


def build_hero(theme, layout="desktop"):
    L = HERO_LAYOUTS[layout]
    W, H, left = L["W"], L["H"], L["left"]
    name_size, role_size, type_size = L["name_size"], L["role_size"], L["type_size"]
    gx, gy, gr = L["gx"], L["gy"], L["gr"]
    fonts = FontBook()

    globe_defs, globe_css, globe = splat_globe(theme, gx, gy, gr)
    orbit_css, orbit_back, orbit_front = orbit(theme, gx, gy, int(gr * 1.55), int(gr * 0.36), -16)

    name_w = measure(NAME, "display", name_size)
    name_hi = "#B9BCFF" if theme is DARK else BRAND
    role_x = left
    role_parts = []
    for i, chunk in enumerate(ROLE):
        cls = "role accent" if i == 1 else "role"
        role_parts.append(f'<text x="{role_x:.1f}" y="{L["role_y"]}" class="{cls}">{esc(fonts.use("display-medium", chunk))}</text>')
        role_x += measure(chunk, "display-medium", role_size)

    fonts.use("mono", KICKER + COORDS + "❯")
    body = (
        card_background(W, H, theme)
        + '<g clip-path="url(#card)">'
        + f'<rect width="{W}" height="{H}" fill="url(#dots)" mask="url(#gridmask)"/>'
        + f'<circle cx="{gx}" cy="{gy}" r="{L["glow_r"]}" fill="url(#glow)"/>'
        + orbit_back
        + f"<g>{globe}</g>"
        + orbit_front
        + "</g>"
        + f'<circle cx="{left + 4}" cy="{L["kicker_y"]}" r="4" class="pulse"/>'
        + f'<circle cx="{left + 4}" cy="{L["kicker_y"]}" r="4" fill="{theme["cyan"]}"/>'
        + f'<text x="{left + 20}" y="{L["kicker_y"] + 5}" class="kicker">{esc(KICKER)}</text>'
        + f'<text x="{left - name_size / 24:.0f}" y="{L["name_y"]}" class="name" fill="url(#name)">{esc(fonts.use("display", NAME))}</text>'
        + "".join(role_parts)
        + f'<text x="{left}" y="{L["type_y"]}" class="prompt">❯</text>'
        + typing_animation(fonts, theme, left + type_size * 1.5, L["type_y"], type_size)
        + f'<text x="{L["coords"][0]}" y="{L["coords"][1]}" text-anchor="{L["coords"][2]}" class="coords">{esc(COORDS)}</text>'
    )

    # every fonts.use() has run by now, so the subsets cover all drawn text
    css = (
        fonts.css()
        + f".kicker{{{font_rule('mono', 15, 'letter-spacing:3.5px;fill:' + theme['accent'])}}}"
        + f".name{{{font_rule('display', name_size, 'letter-spacing:-2px')}}}"
        + f".role{{{font_rule('display-medium', role_size, 'white-space:pre;fill:' + theme['text'])}}}"
        + f".accent{{fill:{theme['accent']}}}"
        + f".typed,.prompt{{{font_rule('mono', type_size, 'white-space:pre;fill:' + theme['muted'])}}}"
        + f".prompt{{fill:{theme['cyan']}}}"
        + f".coords{{{font_rule('mono', 12, 'letter-spacing:1.5px;fill:' + theme['muted'] + ';opacity:.8')}}}"
        + f".caret{{fill:{theme['cyan']};animation:blink 1.05s steps(1) infinite}}"
        + "@keyframes blink{50%{opacity:0}}"
        + f".pulse{{fill:{theme['cyan']};transform-box:fill-box;transform-origin:center;animation:pulse 2.4s ease-out infinite}}"
        + "@keyframes pulse{from{transform:scale(1);opacity:.55}to{transform:scale(3.2);opacity:0}}"
        + globe_css
        + orbit_css
        + REDUCED_MOTION_CSS
    )

    defs = (
        f'<defs><style>{css}</style>{globe_defs}'
        f'<linearGradient id="name" gradientUnits="userSpaceOnUse" x1="{left}" y1="0" x2="{left + name_w:.0f}" y2="0">'
        f'<stop offset="0" stop-color="{theme["text"]}"/><stop offset=".38" stop-color="{theme["text"]}"/>'
        f'<stop offset=".72" stop-color="{name_hi}"/><stop offset="1" stop-color="{theme["cyan"]}"/>'
        f'<animateTransform attributeName="gradientTransform" type="translate" values="0 0;-90 0;0 0" '
        f'dur="9s" repeatCount="indefinite"/></linearGradient>'
        f'<radialGradient id="glow"><stop offset="0" stop-color="{BRAND}" stop-opacity="{theme["glow"]}"/>'
        f'<stop offset="1" stop-color="{BRAND}" stop-opacity="0"/></radialGradient>'
        f'<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
        f'<circle cx="11" cy="11" r="1.1" fill="{theme["grid"]}"/></pattern>'
        f'<radialGradient id="fade" cx="{gx / W:.3f}" cy="{gy / H:.3f}" r=".55"><stop offset="0" stop-color="#fff"/>'
        f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        f'<mask id="gridmask"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask>'
        f'<clipPath id="card"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="19"/></clipPath></defs>'
    )

    desc = (
        f"{NAME}: {''.join(ROLE)}, {KICKER.title()}. Rotating taglines: "
        + "; ".join(TAGLINES)
        + "."
    )
    return svg_open(W, H, f"{NAME} | {''.join(ROLE)}", desc) + defs + body + "</svg>"


# ------------------------------------------------------------------ stack

def simple_icon_path(slug):
    svg = (ICON_DIR / f"{slug}.svg").read_text()
    return re.search(r'<path d="([^"]+)"', svg).group(1)


def custom_icon(key, theme):
    if key == "@splat":
        c = theme["splat"]
        return (
            f'<ellipse cx="9" cy="13" rx="7.5" ry="4.2" transform="rotate(-28 9 13)" fill="{c[0]}" opacity=".85"/>'
            f'<ellipse cx="15" cy="10" rx="7" ry="4" transform="rotate(35 15 10)" fill="{c[2]}" opacity=".85"/>'
            f'<ellipse cx="13.5" cy="16.5" rx="5.5" ry="3.2" transform="rotate(8 13.5 16.5)" fill="{c[4]}" opacity=".85"/>'
        )
    if key == "@sql":
        col = theme["accent"]
        return (
            f'<g fill="none" stroke="{col}" stroke-width="1.8">'
            f'<ellipse cx="12" cy="5" rx="8" ry="3"/>'
            f'<path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/>'
            f'<path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/></g>'
        )
    raise KeyError(key)


STACK_LAYOUTS = {
    "desktop": dict(W=1200, cols=4, pad_x=44, col_gap=28, box=38, icon=22, step=50,
                    cat_size=13, label_size=16.5, header=46),
    # 2 x 2 blocks with bigger type for phones (shown at ~0.6x)
    "mobile": dict(W=600, cols=2, pad_x=32, col_gap=24, box=46, icon=26, step=60,
                   cat_size=15.5, label_size=21, header=54),
}


def build_stack(theme, layout="desktop"):
    """Category columns ("spec sheet"), each a list of icon + name rows."""
    L = STACK_LAYOUTS[layout]
    W, cols, pad_x, col_gap = L["W"], L["cols"], L["pad_x"], L["col_gap"]
    box, step, icon_size = L["box"], L["step"], L["icon"]
    pad_top, pad_bottom, block_gap = 50, 40, 48
    col_w = (W - 2 * pad_x - (cols - 1) * col_gap) / cols
    fonts = FontBook()
    parts = [
        f'<linearGradient id="rule" x1="0" x2="1"><stop offset="0" stop-color="{theme["accent"]}"/>'
        f'<stop offset="1" stop-color="{theme["accent"]}" stop-opacity="0"/></linearGradient>'
    ]
    block_top = pad_top
    for start in range(0, len(STACK), cols):
        row = STACK[start:start + cols]
        list_top = block_top + L["header"]
        for c, (label, items) in enumerate(row):
            x = pad_x + c * (col_w + col_gap)
            parts.append(
                f'<text x="{x}" y="{block_top + 6}" class="cat">{esc(fonts.use("mono-bold", label))}</text>'
                f'<rect x="{x}" y="{block_top + 18}" width="{col_w:.0f}" height="1.5" fill="url(#rule)" opacity=".7"/>'
            )
            for r, (slug, name, hexcode) in enumerate(items):
                y = list_top + r * step
                if slug.startswith("@"):
                    icon = custom_icon(slug, theme)
                else:
                    colour = legible("#" + hexcode, theme["tile"], 3.5)
                    icon = f'<path d="{simple_icon_path(slug)}" fill="{colour}"/>'
                offset = (box - icon_size) / 2
                parts.append(
                    f'<g class="it" style="animation-delay:{((start + c) * 2 + r) * 45}ms">'
                    f'<rect x="{x}" y="{y}" width="{box}" height="{box}" rx="{box / 3.8:.0f}" class="t"/>'
                    f'<g transform="translate({x + offset},{y + offset}) scale({icon_size / 24:.4f})">{icon}</g>'
                    f'<text x="{x + box + box * 0.37:.0f}" y="{y + box / 2 + L["label_size"] * 0.34:.1f}" class="lbl">'
                    f'{esc(fonts.use("display-medium", name))}</text></g>'
                )
        tallest = max(len(items) for _, items in row)
        block_top = list_top + (tallest - 1) * step + box + block_gap
    H = round(block_top - block_gap + pad_bottom)
    css = (
        fonts.css()
        + f".cat{{{font_rule('mono-bold', L['cat_size'], 'letter-spacing:2.5px;fill:' + theme['accent'])}}}"
        + f".lbl{{{font_rule('display-medium', L['label_size'], 'fill:' + theme['text'])}}}"
        + f".t{{fill:{theme['tile']};stroke:{theme['tile_border']}}}"
        + ".it{animation:rise .6s cubic-bezier(.2,.7,.2,1) both}"
        + "@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}"
        + REDUCED_MOTION_CSS
    )
    names = ", ".join(f"{label.title()}: " + ", ".join(n for _, n, _ in items) for label, items in STACK)
    return (
        svg_open(W, H, "Tech stack", names)
        + f"<defs><style>{css}</style></defs>"
        + card_background(W, H, theme)
        + "".join(parts)
        + "</svg>"
    )


# ------------------------------------------------------------------ small pieces

def build_button(label, icon):
    fonts = FontBook()
    size, h = 15, 40
    text_w = measure(label, "display", size)
    w = round(18 + 20 + 10 + text_w + 20)
    fonts.use("display", label)
    css = (
        fonts.css()
        + f".l{{{font_rule('display', size, 'fill:#fff;letter-spacing:.2px')}}}"
        + ".shine{animation:shine 7s ease-in-out infinite}"
        + f"@keyframes shine{{0%,70%{{transform:translateX(-80px)}}100%{{transform:translateX({w + 80}px)}}}}"
        + REDUCED_MOTION_CSS
    )
    return (
        svg_open(w, h, label, f"{label} button")
        + f"<defs><style>{css}</style>"
        + '<linearGradient id="b" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#5B52F0"/>'
        + '<stop offset="1" stop-color="#4338CA"/></linearGradient>'
        + '<linearGradient id="s" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        + '<stop offset=".5" stop-color="#fff" stop-opacity=".28"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        + f'<clipPath id="c"><rect width="{w}" height="{h}" rx="{h / 2}"/></clipPath></defs>'
        + f'<rect width="{w}" height="{h}" rx="{h / 2}" fill="url(#b)"/>'
        + f'<g clip-path="url(#c)"><rect class="shine" x="0" y="0" width="60" height="{h}" fill="url(#s)" transform="skewX(-20)"/></g>'
        + f'<g transform="translate(18,{(h - 20) / 2})">{icon}</g>'
        + f'<text x="48" y="{h / 2 + 5.5}" class="l">{esc(label)}</text></svg>'
    )


LINKEDIN_ICON = (
    '<rect width="20" height="20" rx="4" fill="#fff"/>'
    '<rect x="4" y="8" width="2.8" height="8" fill="#4338CA"/>'
    '<circle cx="5.4" cy="5.2" r="1.7" fill="#4338CA"/>'
    '<path d="M9 8h2.7v1.2c.5-.8 1.5-1.4 2.8-1.4 2.2 0 3 1.4 3 3.6V16h-2.8v-4.1c0-1.1-.3-1.8-1.3-1.8s-1.6.7-1.6 1.8V16H9z" fill="#4338CA"/>'
)
EMAIL_ICON = (
    '<rect x="1" y="3.5" width="18" height="13" rx="2.5" fill="none" stroke="#fff" stroke-width="1.8"/>'
    '<path d="M2.5 5.5l7.5 5.6 7.5-5.6" fill="none" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/>'
)


def build_orb():
    return (
        svg_open(28, 28, "", "")
        .replace('role="img" aria-labelledby="t d"', 'aria-hidden="true"')
        + "<defs><style>.p{transform-box:fill-box;transform-origin:center;animation:p 3s ease-out infinite}"
        "@keyframes p{from{transform:scale(1);opacity:.5}to{transform:scale(1.9);opacity:0}}"
        + REDUCED_MOTION_CSS
        + "</style>"
        '<radialGradient id="o" cx=".35" cy=".3" r=".75"><stop offset="0" stop-color="#E0E7FF"/>'
        f'<stop offset=".45" stop-color="{BRAND}"/><stop offset="1" stop-color="#0E7490"/></radialGradient></defs>'
        f'<circle cx="14" cy="14" r="7" fill="{BRAND}" class="p"/>'
        '<circle cx="14" cy="14" r="7" fill="url(#o)"/></svg>'
    )


FOOTER_LAYOUTS = {
    "desktop": dict(W=1200, H=190, motto=30, en=13, motto_y=52, en_y=80,
                    waves=((14, 600, 140), (10, 400, 152))),
    "mobile": dict(W=600, H=180, motto=36, en=15, motto_y=56, en_y=88,
                   waves=((11, 300, 136), (8, 200, 146))),
}


def build_footer(theme, layout="desktop"):
    L = FOOTER_LAYOUTS[layout]
    W, H = L["W"], L["H"]
    fonts = FontBook()
    fonts.use("display-medium", MOTTO)
    fonts.use("mono", MOTTO_EN)

    def wave(amplitude, length, base):
        # two periods across 2W so a -W translate loops seamlessly
        segs = [f"M0 {base}"]
        x = 0
        while x < 2 * W:
            segs.append(f"q{length / 4} {-amplitude} {length / 2} 0t{length / 2} 0")
            x += length
        segs.append(f"V{H}H0z")
        return "".join(segs)

    css = (
        fonts.css()
        + f".m{{{font_rule('display-medium', L['motto'], 'fill:' + theme['text'] + ';letter-spacing:.5px')}}}"
        + f".e{{{font_rule('mono', L['en'], 'fill:' + theme['muted'] + ';letter-spacing:2px')}}}"
        + ".w1{animation:w 18s linear infinite}.w2{animation:w 11s linear infinite reverse}"
        + f"@keyframes w{{from{{transform:translateX(0)}}to{{transform:translateX(-{W}px)}}}}"
        + REDUCED_MOTION_CSS
    )
    return (
        svg_open(W, H, MOTTO, f"{MOTTO}: {MOTTO_EN}.")
        + f"<defs><style>{css}</style>"
        + f'<linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="{BRAND}"/>'
        + f'<stop offset=".5" stop-color="#8B5CF6"/><stop offset="1" stop-color="#22D3EE"/></linearGradient></defs>'
        + f'<text x="{W / 2}" y="{L["motto_y"]}" text-anchor="middle" class="m">{esc(MOTTO)}</text>'
        + f'<text x="{W / 2}" y="{L["en_y"]}" text-anchor="middle" class="e">{esc(MOTTO_EN.upper())}</text>'
        + f'<path class="w1" d="{wave(*L["waves"][0])}" fill="url(#g)" opacity=".35"/>'
        + f'<path class="w2" d="{wave(*L["waves"][1])}" fill="url(#g)" opacity=".55"/>'
        + "</svg>"
    )


# ------------------------------------------------------------------ main

CI_FONT_TEXT = "".join(chr(c) for c in range(32, 127)) + "×·–—→°❯"


def main():
    ASSETS.mkdir(exist_ok=True)
    written = {}
    for theme in THEMES:
        for layout in ("desktop", "mobile"):
            suffix = theme["name"] if layout == "desktop" else f"mobile-{theme['name']}"
            written[f"hero-{suffix}.svg"] = build_hero(theme, layout)
            written[f"stack-{suffix}.svg"] = build_stack(theme, layout)
            written[f"footer-{suffix}.svg"] = build_footer(theme, layout)
    written["btn-linkedin.svg"] = build_button("LinkedIn", LINKEDIN_ICON)
    written["btn-email.svg"] = build_button("Email me", EMAIL_ICON)
    written["orb.svg"] = build_orb()
    for name, svg in written.items():
        (ASSETS / name).write_text(svg, encoding="utf-8")
        print(f"assets/{name:22s} {len(svg.encode()) / 1024:6.1f} KB")
    metrics = {}
    for key in FONTS:
        data = woff2_subset(key, CI_FONT_TEXT)
        (FONT_DIR / f"{key}.woff2").write_bytes(data)
        print(f"scripts/fonts/{key}.woff2 {len(data) / 1024:6.1f} KB")
        font = font_instance(key)
        cmap, hmtx = font.getBestCmap(), font["hmtx"]
        metrics[key] = {
            "upm": font["head"].unitsPerEm,
            "advances": {ch: hmtx[cmap[ord(ch)]][0] for ch in CI_FONT_TEXT if ord(ch) in cmap},
        }
    (FONT_DIR / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
