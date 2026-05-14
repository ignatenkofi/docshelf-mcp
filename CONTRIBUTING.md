# Contributing to docshelf-mcp

Thanks for considering a contribution. This project is small and friendly —
bug reports, doc improvements, and small PRs are all welcome.

## Reporting a bug

Open an issue on
[GitHub Issues](https://github.com/ignatenkofi/docshelf-mcp/issues).
Please include:

- What you tried (the exact command or MCP tool call).
- What you expected to happen.
- What actually happened (paste the traceback or the wrong output).
- Your Python version (`python --version`) and OS.

If the bug involves PDF conversion, attaching the offending PDF (or a
sanitised excerpt) makes life much easier.

## Suggesting a feature

Open an issue with `feature:` in the title. Describe the use case first,
then the proposed solution. The most useful feature suggestions explain a
real workflow that's currently painful.

## Submitting a pull request

1. Fork the repo and create a topic branch off `main`.
2. Install the dev environment:

   ```bash
   uv pip install -e ".[dev]"
   ```

3. Make your change. Keep PRs focused — one concern per PR.
4. Run the local checks:

   ```bash
   ruff check src tests
   pytest -v
   ```

   CI runs the same on Python 3.10 / 3.11 / 3.12.

5. Add a short note to `CHANGELOG.md` under the `[Unreleased]` section.
6. Open the PR. Reference the issue it addresses, if any.

PRs that touch core logic (splitter, indexer) should add or update tests
under `tests/`. The bar is "this regression would have been caught."

## Coding style

- `ruff` is the source of truth — if it's happy, the style is fine.
- Type hints are encouraged but not strictly enforced; add them where they
  help the reader.
- Public functions get a short docstring. Internal helpers don't need one.
- No new dependencies without discussion in an issue first.

## Releases

Maintainer-only:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

The `release.yml` workflow builds the wheel and publishes to PyPI via
trusted publishing.

## Code of Conduct

By participating you agree to abide by the
[Contributor Covenant](CODE_OF_CONDUCT.md). In short: be kind, assume good
faith, no harassment.

## License

By contributing, you agree your contribution is licensed under the
project's MIT license.
