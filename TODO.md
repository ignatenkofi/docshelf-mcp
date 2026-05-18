# TODO

Post-MVP improvements and ideas. GitHub Issues for triaged work; this file for
"future / nice-to-have" that doesn't warrant an issue yet.

## Ideas

- [ ] **Live demo with real numbers.** Publish a one-pager from a real shelf
  (e.g. the homelab shelf) showing concrete savings after a month of use:
  tokens saved per question, latency reduction, hit-rate of section-level
  fetches vs. naive full-file loads. Currently the README explains the
  *mechanism*; what's missing is proof that the mechanism pays off in
  practice. Format: short post (Hexo/Medium/Habr cross-post) + a chart.

- [ ] **Pipeline: auto-warn on suspicious sections during regeneration.**
  When `Shelf.add_document()` / `rebuild_index()` runs the splitter, emit
  warnings for sections whose heading matches "junk-heading" heuristics —
  unit-prefixed body fragments (`2.5 Gb/s. ...`), dotted-line TOC leaks
  (`5.6 LTR ........ 42`), table-row residue, near-duplicate titles within
  a chapter. The homelab encyclopedia rewrite (2026-05-14) had to bake
  these heuristics into a custom generator; they belong in the core splitter
  so any shelf benefits. Output: structured warning per offending section
  + a summary report at end of regen.
