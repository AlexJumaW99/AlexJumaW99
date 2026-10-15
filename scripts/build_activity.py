"""Render the 3D contribution skyline + streak card (dark and light).

    GITHUB_TOKEN=... python scripts/build_activity.py --user AlexJumaW99 --out dist

Standard library only; runs in the scheduled workflow. Reads the contribution
calendar from the GraphQL API (private contributions are included when the
profile setting "Include private contributions" is on) and exits non-zero on
any API or data problem, so a failed run never replaces the published images.
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from brand import (
    BRAND, DARK, FONTS, REDUCED_MOTION_CSS, THEMES, card_background, esc,
    font_face_css, hex_to_oklch, measure, oklch_to_hex, svg_open,
)

API = "https://api.github.com/graphql"
DAY_FIELDS = "weeks { contributionDays { date contributionCount contributionLevel } }"
LEVELS = ["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"]


# ------------------------------------------------------------------ data

def graphql(query, variables, token, attempts=4):
    body = json.dumps({"query": query, "variables": variables}).encode()
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            API,
            data=body,
            headers={
                "Authorization": f"bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "profile-activity-card",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            if payload.get("errors"):
                raise RuntimeError(f"GraphQL errors: {payload['errors']}")
            return payload["data"]
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            if attempt == attempts:
                raise
            wait = 5 * attempt
            print(f"attempt {attempt} failed ({exc}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)


def fetch(user, token, now):
    created = graphql(
        "query($u:String!){user(login:$u){createdAt}}", {"u": user}, token
    )["user"]
    if created is None:
        raise RuntimeError(f"user {user!r} not found")
    first_year = int(created["createdAt"][:4])
    years = []
    for year in range(first_year, now.year + 1):
        start = f"{year}-01-01T00:00:00Z"
        end = f"{year}-12-31T23:59:59Z" if year < now.year else now.strftime("%Y-%m-%dT%H:%M:%SZ")
        years.append(
            f'y{year}: contributionsCollection(from: "{start}", to: "{end}") '
            f"{{ contributionCalendar {{ totalContributions {DAY_FIELDS} }} }}"
        )
    query = (
        "query($u:String!){ user(login:$u){ "
        f"last: contributionsCollection {{ contributionCalendar {{ totalContributions {DAY_FIELDS} }} }} "
        + " ".join(years)
        + " } }"
    )
    data = graphql(query, {"u": user}, token)["user"]
    return created["createdAt"][:10], data


def flatten(calendar):
    return [day for week in calendar["weeks"] for day in week["contributionDays"]]


def summarise(created, data):
    last = data["last"]["contributionCalendar"]
    weeks = last["weeks"]
    if len(weeks) < 52:
        raise RuntimeError(f"calendar has only {len(weeks)} weeks")
    # "today" is the calendar's own latest date rather than the runner's
    # clock. GitHub buckets days in the token's timezone; the Actions token
    # gets UTC, which is also what anonymous visitors see on the profile
    # graph, so the card and the graph agree day for day.
    today = dt.date.fromisoformat(flatten(last)[-1]["date"])

    counts = {}
    total = 0
    for key, value in data.items():
        if key == "last":
            continue
        calendar = value["contributionCalendar"]
        total += calendar["totalContributions"]
        for day in flatten(calendar):
            counts[day["date"]] = day["contributionCount"]
    for day in flatten(last):
        counts.setdefault(day["date"], day["contributionCount"])

    def count(day):
        return counts.get(day.isoformat(), 0)

    # an empty "today" does not break the streak yet; the day is not over
    end = today if count(today) else today - dt.timedelta(days=1)
    cursor = end
    while count(cursor):
        cursor -= dt.timedelta(days=1)
    current = (end - cursor).days
    current_range = (cursor + dt.timedelta(days=1), end) if current else None

    longest, longest_range, run_start = 0, None, None
    day = dt.date.fromisoformat(min(counts))
    while day <= today:
        if count(day):
            run_start = run_start or day
            length = (day - run_start).days + 1
            if length > longest:
                longest, longest_range = length, (run_start, day)
        else:
            run_start = None
        day += dt.timedelta(days=1)

    busiest = max(flatten(last), key=lambda d: d["contributionCount"])
    return {
        "created": created,
        "first_year": created[:4],
        "total": total,
        "year_total": last["totalContributions"],
        "weeks": weeks,
        "current": current,
        "current_range": current_range,
        "longest": longest,
        "longest_range": longest_range,
        "busiest": busiest,
        "today": today,
    }


# ------------------------------------------------------------------ render

def shade(hex_color, delta):
    L, C, H = hex_to_oklch(hex_color)
    return oklch_to_hex(max(0.0, min(1.0, L + delta)), C, H)


def fmt_range(span):
    a, b = span
    if a.year == b.year:
        return f"{a:%b} {a.day} – {b:%b} {b.day}, {b.year}"
    return f"{a:%b} {a.day}, {a.year} – {b:%b} {b.day}, {b.year}"


def font_rule(key, size, extra=""):
    family, weight = FONTS[key]
    return f"font-family:'{family}',sans-serif;font-weight:{weight};font-size:{size}px;{extra}"


LAYOUTS = {
    "desktop": dict(W=1200, pad=44, max_h=118, sky_top=144, big=54, big_y=86, cap=18,
                    cap_y=(66, 88), sub=12.5, sub_y=118, val=30, key=11.5, key_ls=2,
                    stats_y=(78, 102), stats_right=True, month=12, month_gap=3,
                    label_dy=26, swatch=11, bottom=34),
    # phones: stats move under the headline, type is larger (shown at ~0.6x)
    "mobile": dict(W=600, pad=32, max_h=96, sky_top=246, big=62, big_y=96, cap=21,
                   cap_y=(73, 98), sub=15, sub_y=134, val=34, key=14, key_ls=0.8,
                   stats_y=(196, 222), stats_right=False, month=15, month_gap=4,
                   label_dy=30, swatch=13, bottom=36),
}


def render(stats, theme, layout="desktop"):
    L = LAYOUTS[layout]
    W, pad = L["W"], L["pad"]
    weeks = stats["weeks"]
    n_weeks = len(weeks)
    # cabinet-style oblique projection: weeks run left to right, the seven
    # weekday rows recede up and to the right, bar height is vertical
    depth_ratio_x, depth_ratio_y = 0.42, 0.30
    s = (W - 2 * pad) / (n_weeks + 7 * depth_ratio_x)
    dx, dy = s * depth_ratio_x, s * depth_ratio_y
    max_h = float(L["max_h"])
    y0 = L["sky_top"] + max_h  # ground line of the back row; tallest bar clears the header
    x0 = pad + 7 * dx
    margin = 0.1

    def ground(wx, dz):
        return x0 + wx * s - dz * dx, y0 + dz * dy

    peak = max(d["contributionCount"] for w in weeks for d in w["contributionDays"]) or 1
    ramp = theme["ramp"]
    faces = []
    for level, colour in enumerate(ramp):
        faces.append(
            f".t{level}{{fill:{colour}}}.f{level}{{fill:{shade(colour, -0.07)}}}"
            f".r{level}{{fill:{shade(colour, -0.15)}}}"
        )

    cells = []
    for w, week in enumerate(weeks):
        for day in week["contributionDays"]:
            d = dt.date.fromisoformat(day["date"]).isoweekday() % 7  # Sun=0
            cells.append((d, w, day))
    cells.sort(key=lambda c: (c[0], c[1]))  # back row first, then left to right

    bars = []
    today_top = None
    for d, w, day in cells:
        n = day["contributionCount"]
        level = LEVELS.index(day["contributionLevel"]) if n else 0
        h = 2.0 if n == 0 else 5 + (max_h - 5) * (n / peak) ** 0.55
        a = ground(w + margin, d + 1 - margin)
        b = ground(w + 1 - margin, d + 1 - margin)
        c = ground(w + 1 - margin, d + margin)
        e = ground(w + margin, d + margin)

        def up(p):
            return p[0], p[1] - h

        def poly(points, cls):
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
            return f'<polygon points="{pts}" class="{cls}"/>'

        shape = (
            poly([b, c, up(c), up(b)], f"r{level}")
            + poly([a, b, up(b), up(a)], f"f{level}")
            + poly([up(a), up(b), up(c), up(e)], f"t{level}")
        )
        if n:
            delay = w * 16 + d * 9
            bars.append(f'<g class="g" style="animation-delay:{delay}ms">{shape}</g>')
        else:
            bars.append(shape)
        if day["date"] == stats["today"].isoformat():
            top = up(a), up(c)
            today_top = ((top[0][0] + top[1][0]) / 2, (top[0][1] + top[1][1]) / 2)

    # month labels under the front row
    labels = []
    last_label_week = -9
    for w, week in enumerate(weeks):
        days = [dt.date.fromisoformat(d["date"]) for d in week["contributionDays"]]
        month_start = next((x for x in days if x.day == 1), None)
        if month_start and w - last_label_week >= L["month_gap"] and w < n_weeks - 1:
            x, y = ground(w, 7)
            labels.append(f'<text x="{x:.1f}" y="{y + L["label_dy"]:.1f}" class="m">{month_start:%b}</text>')
            last_label_week = w

    start = dt.date.fromisoformat(weeks[0]["contributionDays"][0]["date"])
    period = f"{start:%b} {start.day}, {start.year} – {stats['today']:%b} {stats['today'].day}, {stats['today'].year}"

    # legend sits on the date line, clear of the month labels
    sub, sub_y, sw = L["sub"], L["sub_y"], L["swatch"]
    lx = pad + measure(period, "mono", sub) + 2.2 * sub
    legend = [f'<text x="{lx:.1f}" y="{sub_y}" class="sub">Less</text>']
    lx += measure("Less", "mono", sub) + 8
    for i in range(len(ramp)):
        legend.append(
            f'<rect x="{lx + i * (sw + 4):.1f}" y="{sub_y - sw + 1}" width="{sw}" height="{sw}" rx="2.5" class="t{i}"/>'
        )
    lx += len(ramp) * (sw + 4) + 4
    legend.append(f'<text x="{lx:.1f}" y="{sub_y}" class="sub">More</text>')

    # headline + stat blocks
    year_total = f"{stats['year_total']:,}"
    blocks = [(f"{stats['total']:,}", f"TOTAL SINCE {stats['first_year']}")]
    blocks.append((f"{stats['longest']} days", "LONGEST STREAK"))
    if stats["current"] >= 2:
        blocks.append((f"{stats['current']} days", "CURRENT STREAK"))
    else:
        busiest = stats["busiest"]
        when = dt.date.fromisoformat(busiest["date"])
        blocks.append((f"{busiest['contributionCount']}", f"BEST DAY · {when:%b} {when.day}".upper()))

    stat_parts = []
    vy, ky = L["stats_y"]
    if L["stats_right"]:
        positions = [(W - pad - 210 * i, "end") for i in range(len(blocks))][::-1]
    else:
        column = (W - 2 * pad) / len(blocks)
        positions = [(pad + column * i, "start") for i in range(len(blocks))]
    for (value, label), (x, anchor) in zip(blocks, positions):
        stat_parts.append(
            f'<text x="{x:.0f}" y="{vy}" class="v" text-anchor="{anchor}">{esc(value)}</text>'
            f'<text x="{x:.0f}" y="{ky}" class="k" text-anchor="{anchor}">{esc(label)}</text>'
        )

    pulse = ""
    if today_top:
        tx, ty = today_top
        pulse = (
            f'<circle cx="{tx:.1f}" cy="{ty - 14:.1f}" r="4" class="pulse"/>'
            f'<circle cx="{tx:.1f}" cy="{ty - 14:.1f}" r="4" fill="{theme["cyan"]}"/>'
            f'<line x1="{tx:.1f}" y1="{ty - 10:.1f}" x2="{tx:.1f}" y2="{ty - 2:.1f}" stroke="{theme["cyan"]}" stroke-width="1.5" opacity=".6"/>'
        )

    css = (
        "".join(font_face_css(k) for k in ("display", "display-medium", "mono"))
        + "".join(faces)
        + f".big{{{font_rule('display', L['big'], 'letter-spacing:-1px')}}}"
        + f".cap{{{font_rule('display-medium', L['cap'], 'fill:' + theme['text'])}}}"
        + f".sub{{{font_rule('mono', sub, 'fill:' + theme['muted'] + ';letter-spacing:.5px')}}}"
        + f".v{{{font_rule('display', L['val'], 'fill:' + theme['text'])}}}"
        + f".k{{{font_rule('mono', L['key'], 'fill:' + theme['muted'] + ';letter-spacing:' + str(L['key_ls']) + 'px')}}}"
        + f".m{{{font_rule('mono', L['month'], 'fill:' + theme['muted'])}}}"
        + ".g{transform-box:fill-box;transform-origin:50% 100%;animation:grow .9s cubic-bezier(.2,.8,.2,1) both}"
        + "@keyframes grow{from{transform:scaleY(.02)}to{transform:scaleY(1)}}"
        + f".pulse{{fill:{theme['cyan']};transform-box:fill-box;transform-origin:center;animation:pulse 2.4s ease-out infinite}}"
        + "@keyframes pulse{from{transform:scale(1);opacity:.6}to{transform:scale(3.4);opacity:0}}"
        + REDUCED_MOTION_CSS
    )
    hi = "#B9BCFF" if theme is DARK else BRAND
    defs = (
        f"<defs><style>{css}</style>"
        f'<linearGradient id="hl" x1="0" x2="1"><stop offset="0" stop-color="{theme["text"]}"/>'
        f'<stop offset="1" stop-color="{hi}"/></linearGradient></defs>'
    )
    longest_note = fmt_range(stats["longest_range"]) if stats["longest_range"] else ""
    desc = (
        f"{stats['year_total']} contributions in the last year ({period}); "
        f"{stats['total']} total since {stats['first_year']}; longest streak {stats['longest']} days"
        + (f" ({longest_note})" if longest_note else "")
        + f"; current streak {stats['current']} days."
    )
    H = round(ground(0, 7)[1] + L["label_dy"] + L["bottom"])
    cap_x = pad + measure(year_total, "display", L["big"]) + 0.26 * L["big"]
    cap_top, cap_bottom = L["cap_y"]
    body = (
        card_background(W, H, theme)
        + f'<text x="{pad}" y="{L["big_y"]}" class="big" fill="url(#hl)">{year_total}</text>'
        + f'<text x="{cap_x:.1f}" y="{cap_top}" class="cap">contributions</text>'
        + f'<text x="{cap_x:.1f}" y="{cap_bottom}" class="cap">in the last year</text>'
        + f'<text x="{pad}" y="{sub_y}" class="sub">{esc(period)}</text>'
        + "".join(stat_parts)
        + "".join(bars)
        + pulse
        + "".join(labels)
        + "".join(legend)
    )
    return svg_open(W, H, "GitHub contribution activity", desc) + defs + body + "</svg>"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    now = dt.datetime.now(dt.timezone.utc)
    created, data = fetch(args.user, token, now)
    stats = summarise(created, data)
    args.out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        for layout in LAYOUTS:
            suffix = theme["name"] if layout == "desktop" else f"mobile-{theme['name']}"
            path = args.out / f"activity-{suffix}.svg"
            path.write_text(render(stats, theme, layout), encoding="utf-8")
            print(f"{path} {path.stat().st_size / 1024:.1f} KB")
    print(
        f"year={stats['year_total']} total={stats['total']} since={stats['created']} "
        f"current={stats['current']} {stats['current_range']} "
        f"longest={stats['longest']} {stats['longest_range']}"
    )


if __name__ == "__main__":
    main()
