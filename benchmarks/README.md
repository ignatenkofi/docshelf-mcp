# benchmarks

Reproducible measurement of the docshelf pattern's token savings.

## `token_savings.py`

Measures the token cost of answering a question from a shelf three ways —
dump the whole collection, load the whole containing document, or the docshelf
way (`INDEX.md` + one section) — so the savings are measured, not asserted.

```bash
python benchmarks/token_savings.py /path/to/shelf [/another/shelf ...]
python benchmarks/token_savings.py --json /path/to/shelf     # machine-readable
python benchmarks/token_savings.py --tiktoken /path/to/shelf # exact GPT tokens
```

A "shelf" is any directory with an `INDEX.md` and a `docs/` (or `DOCS/`) tree —
point it at your own to get your own numbers.

Token counting is **network-free by default** (OpenAI's ~4-chars-per-token rule
of thumb). Because every measure uses the same counter, the savings *ratios*
are tokenizer-independent; `--tiktoken` gives exact `cl100k_base` counts (needs
`pip install tiktoken` and network access to fetch its vocabulary).

## `make_chart.py`

Regenerates `docs/assets/token-savings.svg` from the measured numbers (kept in
the script). Run it after re-measuring to refresh the chart on the
[demo page](../docs/demo.md).

See the write-up with the published numbers: **[docs/demo.md](../docs/demo.md)**.
