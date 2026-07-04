"""Generate the token-savings chart SVG from the measured numbers."""
import math
from pathlib import Path

# Measured (chars/4 estimate) — see benchmarks/token_savings.py
DATA = [
    ("HomeLab — 24 hardware manuals (3,055 sections)", [
        ("Dump all 24 manuals", 1_217_460, "naive"),
        ("Load the RouterOS manual", 1_053_738, "naive"),
        ("docshelf: INDEX + 1 section", 3_682, "docshelf"),
    ], "99.7%"),
    ("Une Vie — one full novel · 16 chapters", [
        ("Load the whole book", 111_134, "naive"),
        ("docshelf: INDEX + 1 section", 7_781, "docshelf"),
    ], "93%"),
]

W, H = 780, 470
X0, X1 = 300, 730          # plot area x
LOGMIN, LOGMAX = 3, 7      # 1K .. 10M tokens
CTX = 200_000              # Claude 200K context budget

CARD = "#ffffff"
INK = "#1f2933"
MUTED = "#6b7280"
NAIVE = "#c0c7d0"
NAIVE_EDGE = "#98a2b3"
GOOD = "#2f9e44"
CTXLINE = "#e8590c"
RED = "#c92a2a"


def fx(v):
    return X0 + (math.log10(v) - LOGMIN) / (LOGMAX - LOGMIN) * (X1 - X0)


def fmt(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


svg = []
svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}" font-family="-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">')
svg.append(f'<rect x="0" y="0" width="{W}" height="{H}" rx="14" fill="{CARD}" stroke="#e5e7eb"/>')
svg.append(f'<text x="28" y="42" font-size="21" font-weight="700" fill="{INK}">'
           f'Tokens to answer one question</text>')
svg.append(f'<text x="28" y="66" font-size="13.5" fill="{MUTED}">'
           f'Measured on two real docshelf repos · lower is better · log scale</text>')

# 200K context reference line
cx = fx(CTX)
top, bot = 92, H - 58
svg.append(f'<line x1="{cx:.1f}" y1="{top}" x2="{cx:.1f}" y2="{bot}" '
           f'stroke="{CTXLINE}" stroke-width="1.5" stroke-dasharray="5 4"/>')
svg.append(f'<text x="{cx-8:.1f}" y="{bot-8}" font-size="11.5" fill="{CTXLINE}" '
           f'font-weight="600" text-anchor="end">200K context →</text>')

y = 108
BH = 26          # bar height
row_gap = 40
for group, bars, savings in DATA:
    svg.append(f'<text x="28" y="{y}" font-size="14" font-weight="700" fill="{INK}">{group}</text>')
    svg.append(f'<text x="{X1}" y="{y}" font-size="14" font-weight="700" fill="{GOOD}" '
               f'text-anchor="end">↓ {savings} fewer tokens</text>')
    y += 16
    for label, val, kind in bars:
        cy = y
        fill = GOOD if kind == "docshelf" else NAIVE
        edge = GOOD if kind == "docshelf" else NAIVE_EDGE
        xend = fx(val)
        svg.append(f'<text x="{X0-12}" y="{cy+BH*0.68:.0f}" font-size="12.5" '
                   f'fill="{INK}" text-anchor="end">{label}</text>')
        svg.append(f'<rect x="{X0}" y="{cy}" width="{max(xend-X0,2):.1f}" height="{BH}" '
                   f'rx="4" fill="{fill}" stroke="{edge}"/>')
        # value label
        lab = f'{fmt(val)} tokens'
        svg.append(f'<text x="{xend+8:.1f}" y="{cy+BH*0.68:.0f}" font-size="12" '
                   f'font-weight="600" fill="{INK}">{lab}</text>')
        # overflow marker
        if val > CTX:
            svg.append(f'<text x="{xend+8:.1f}" y="{cy+BH*0.68+15:.0f}" font-size="10.5" '
                       f'fill="{RED}" font-weight="600">✗ exceeds 200K — won’t fit</text>')
            y += 12
        y += BH + 10
    y += row_gap - 10

# x-axis ticks
axis_y = bot + 4
for p in range(LOGMIN, LOGMAX + 1):
    tx = fx(10 ** p)
    lab = {3: "1K", 4: "10K", 5: "100K", 6: "1M", 7: "10M"}[p]
    svg.append(f'<line x1="{tx:.1f}" y1="{axis_y}" x2="{tx:.1f}" y2="{axis_y+4}" stroke="{MUTED}"/>')
    svg.append(f'<text x="{tx:.1f}" y="{axis_y+18}" font-size="10.5" fill="{MUTED}" '
               f'text-anchor="middle">{lab}</text>')

svg.append('</svg>')

out = Path("/home/user/docshelf-mcp/docs/assets/token-savings.svg")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(svg), encoding="utf-8")
print("wrote", out, out.stat().st_size, "bytes")
