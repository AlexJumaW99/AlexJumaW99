"""Gate before publishing: every expected SVG must exist, be well formed and
look like what its generator normally writes. A failure here stops the
workflow, so the output branch keeps serving the last good images.

    python scripts/check_svgs.py dist
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "{http://www.w3.org/2000/svg}"

# file -> (minimum bytes, text that must appear)
EXPECTED = {
    "activity-dark.svg": (20_000, "contributions"),
    "activity-light.svg": (20_000, "contributions"),
    "activity-mobile-dark.svg": (20_000, "contributions"),
    "activity-mobile-light.svg": (20_000, "contributions"),
    "snake-dark.svg": (5_000, "<svg"),
    "snake-light.svg": (5_000, "<svg"),
}
MAX_BYTES = 5_000_000


def check(path, min_bytes, marker):
    if not path.is_file():
        return "missing"
    size = path.stat().st_size
    if not min_bytes <= size <= MAX_BYTES:
        return f"unexpected size {size} bytes"
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        return f"does not contain {marker!r}"
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return f"not well-formed XML ({exc})"
    if root.tag not in ("svg", SVG_NS + "svg"):
        return f"root element is {root.tag}, not svg"
    if not (root.get("viewBox") or (root.get("width") and root.get("height"))):
        return "no viewBox or width/height"
    return None


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    extra = sorted(p.name for p in out.glob("*") if p.name not in EXPECTED)
    failures = []
    for name, (min_bytes, marker) in EXPECTED.items():
        problem = check(out / name, min_bytes, marker)
        status = "ok" if problem is None else f"FAIL: {problem}"
        print(f"{name:22s} {status}")
        if problem:
            failures.append(name)
    for name in extra:
        print(f"{name:22s} (not checked)")
    if failures:
        sys.exit(f"{len(failures)} file(s) failed validation; not publishing")


if __name__ == "__main__":
    main()
