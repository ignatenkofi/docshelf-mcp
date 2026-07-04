"""Generate the token-savings chart SVG from the measured numbers.

Linear scale (not log): the whole point is a 300x-plus gap, so the bars must
*look* that different. Each shelf is normalized to its own "load everything"
cost, so the green docshelf sliver reads as "this is all it actually needs".
"""
from pathlib import Path

# Measured with benchmarks/token_savings.py (chars/4 estimate).
SHELVES = [
    {
        "name": "HomeLab — 24 hardware manuals (3,055 sections)",
        "naive_label": "Attach all 24 manuals to the chat",
        "naive": 1_217_460,
        "docshelf": 3_682,
        "multiple": "330×",
        "pct": "99.7%",
        "wont_fit": "✗ won’t fit in a 200K context",
    },
    {
        "name": "Une Vie — one full novel (16 chapters)",
        "naive_label": "Load the whole book",
        "naive": 111_134,
        "docshelf": 7_781,
        "multiple": "14×",
        "pct": "93%",
        "wont_fit": "",
    },
]

W = 970
X0 = 300           # bars start here (left column = labels)
BARW = 420         # full bar width == the naive cost
BH = 30            # bar height
INK = "#1f2933"
MUTED = "#6b7280"
NAIVE = "#cbd5e1"
NAIVE_EDGE = "#94a3b8"
GOOD = "#2f9e44"
RED = "#c92a2a"


def fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


rows_h = 150
H = 96 + rows_h * len(SHELVES)
svg: list[str] = []
svg.append(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
    f'viewBox="0 0 {W} {H}" '
    f'font-family="-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">'
)
svg.append(f'<rect width="{W}" height="{H}" rx="14" fill="#ffffff" stroke="#e5e7eb"/>')
svg.append(
    f'<text x="30" y="44" font-size="22" font-weight="700" fill="{INK}">'
    f"Tokens to answer one question</text>"
)
svg.append(
    f'<text x="30" y="70" font-size="14" fill="{MUTED}">'
    f"Bars to scale · measured on two real shelves · "
    f"green = what docshelf actually loads</text>"
)

y = 112
for s in SHELVES:
    # Shelf name + big savings callout on the right.
    svg.append(
        f'<text x="30" y="{y}" font-size="15" font-weight="700" fill="{INK}">'
        f'{s["name"]}</text>'
    )
    svg.append(
        f'<text x="{X0 + BARW}" y="{y}" font-size="20" font-weight="800" '
        f'fill="{GOOD}" text-anchor="end">{s["multiple"]} fewer — {s["pct"]} less</text>'
    )

    # Naive bar (full width == its own cost).
    by = y + 16
    svg.append(
        f'<text x="{X0 - 12}" y="{by + BH * 0.68:.0f}" font-size="13" '
        f'fill="{INK}" text-anchor="end">{s["naive_label"]}</text>'
    )
    svg.append(
        f'<rect x="{X0}" y="{by}" width="{BARW}" height="{BH}" rx="4" '
        f'fill="{NAIVE}" stroke="{NAIVE_EDGE}"/>'
    )
    svg.append(
        f'<text x="{X0 + BARW + 10}" y="{by + BH * 0.68:.0f}" font-size="13" '
        f'font-weight="700" fill="{INK}">{fmt(s["naive"])} tokens</text>'
    )
    if s["wont_fit"]:
        svg.append(
            f'<text x="{X0 + BARW + 10}" y="{by + BH * 0.68 + 16:.0f}" '
            f'font-size="11" font-weight="600" fill="{RED}">{s["wont_fit"]}</text>'
        )

    # docshelf bar (to scale — a sliver of the naive bar).
    dy = by + BH + 12
    dw = max(BARW * s["docshelf"] / s["naive"], 4.0)
    svg.append(
        f'<text x="{X0 - 12}" y="{dy + BH * 0.68:.0f}" font-size="13" '
        f'font-weight="600" fill="{GOOD}" text-anchor="end">docshelf: INDEX + 1 section</text>'
    )
    svg.append(
        f'<rect x="{X0}" y="{dy}" width="{dw:.1f}" height="{BH}" rx="3" fill="{GOOD}"/>'
    )
    svg.append(
        f'<text x="{X0 + dw + 10:.1f}" y="{dy + BH * 0.68:.0f}" font-size="13" '
        f'font-weight="700" fill="{GOOD}">{fmt(s["docshelf"])} tokens</text>'
    )
    y += rows_h

svg.append("</svg>")

out = Path(__file__).resolve().parent.parent / "docs" / "assets" / "token-savings.svg"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(svg), encoding="utf-8")
print("wrote", out, out.stat().st_size, "bytes")
