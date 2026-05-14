# Security Policy

## Supported versions

`docshelf-mcp` is still in `0.x`. Only the latest minor release receives
security fixes.

| Version | Supported |
|---------|-----------|
| `0.2.x` | ✅        |
| `< 0.2` | ❌        |

## Reporting a vulnerability

**Please do NOT open a public GitHub issue for security reports.**

Instead, report it privately via GitHub's **"Report a vulnerability"**
button under the
[Security tab](https://github.com/ignatenkofi/docshelf-mcp/security/advisories/new)
of this repository. That creates a private advisory only the maintainer and
you can see.

If for some reason that doesn't work, send an email to the address on the
maintainer's GitHub profile ([ignatenkofi](https://github.com/ignatenkofi))
with `docshelf-mcp security` in the subject line.

### What to include

- A clear description of the vulnerability and its impact.
- Steps to reproduce, ideally with a minimal example.
- The version of `docshelf-mcp` and your environment (Python version, OS).
- (Optional) A suggested fix.

### What to expect

- Acknowledgement within 72 hours.
- A first-pass assessment within 7 days.
- For confirmed issues: a coordinated disclosure timeline, a fixed release,
  and credit in the release notes (unless you ask to remain anonymous).

## Scope

In-scope concerns:

- Arbitrary code execution triggered by malicious input (PDF, MD, config).
- Path traversal via crafted document paths or category names.
- Leakage of files outside the configured shelf root.
- Dependency vulnerabilities with a direct exploitation path through
  `docshelf-mcp`.

Out of scope:

- Issues that require the attacker to already control the shelf's source
  files or the user's Python environment.
- Security of services the shelf is hosted on (GitHub, PyPI, Glama).
- Bugs in `pymupdf4llm` or other dependencies that don't have a
  `docshelf-mcp`-specific exploitation path — please report those upstream.

Thank you for helping keep the project safe.
