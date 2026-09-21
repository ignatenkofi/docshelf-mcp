"""Generate the token-savings chart SVG from the measured numbers.

Linear scale (not log): the whole point is a 300x-plus gap, so the bars must
*look* that different. Each shelf is normalized to its own "load everything"
cost, so the green docshelf sliver reads as "this is all it actually needs".

The render is a pure function of the numbers below, so two runs produce the
same bytes and ``--check`` can judge whether the committed chart is current::

    python benchmarks/make_chart.py            rewrite docs/assets/token-savings.svg
    python benchmarks/make_chart.py --check    write nothing; exit 1 if that file
                                               is missing or not what this renders
    python benchmarks/make_chart.py --out X    write X instead
"""
import argparse
import sys
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "docs" / "assets" / "token-savings.svg"

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


def render() -> str:
    """Return the SVG document as text."""
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
    return "\n".join(svg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the token-savings chart from the numbers kept in this script."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="file to write, or with --check the file to compare against (default: %(default)s)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if --out is missing or differs from the render",
    )
    args = parser.parse_args(argv)
    text = render()

    if args.check:
        on_disk = args.out.read_text(encoding="utf-8") if args.out.is_file() else None
        if on_disk == text:
            print("up to date:", args.out)
            return 0
        print("missing:" if on_disk is None else "stale:", args.out, "(rerun without --check)")
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print("wrote", args.out, args.out.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
