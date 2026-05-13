# Example: HomeLab shelf

The original use case. You're running a home lab — router, switch, NAS, two motherboards, a UPS — and you'd like Claude to be able to answer questions across all the manuals.

## Setup

```python
from docshelf_mcp import Shelf

shelf = Shelf("~/Documents/homelab-docs").init(
    name="HomeLab Documentation",
    remote="https://github.com/me/homelab-docs",
    default_categories=[
        "router",
        "switch",
        "motherboard",
        "psu",
        "ups",
        "nas",
        "cpu",
        "ram",
        "ssd",
    ],
)
```

## Adding manuals

```python
shelf.add_document(
    "~/Downloads/MIKROTIK_RouterOS.pdf",
    category="router",
    title="Mikrotik RouterOS — full manual",
    description="Official RouterOS reference (split by chapter).",
)

shelf.add_document(
    "~/Downloads/INTEL_X550_DS.pdf",
    category="nic",
    title="Intel X550 — datasheet",
    description="10 GbE controller datasheet, split by chapter.",
)

shelf.add_document(
    "~/Downloads/CUDY_GS1010PE_QIG.pdf",
    category="switch",
    title="Cudy GS1010PE — quick install",
)
```

## Resulting INDEX (excerpt)

```markdown
# HomeLab Documentation

Repo: <https://github.com/me/homelab-docs>

## Router

### Mikrotik RouterOS — full manual — Official RouterOS reference (split by chapter).

Full document: [`mikrotik-routeros-full-manual.md`](https://raw.githubusercontent.com/.../docs/router/mikrotik-routeros-full-manual.md) (~4200 KB — prefer pulling individual sections below).

- [Overview](https://raw.githubusercontent.com/.../001-overview.md)
- [Bridging](https://raw.githubusercontent.com/.../002-bridging.md)
- [Firewall](https://raw.githubusercontent.com/.../003-firewall.md)
- …

  *(sections: 47)*

## Switch

- **Cudy GS1010PE — quick install** — [`cudy-gs1010pe-quick-install.md`](https://raw.githubusercontent.com/.../switch/cudy-gs1010pe-quick-install.md)
```

## Then

Drop `INDEX.md` into your Claude project. Ask Claude things like:

- "How do I configure a bridge VLAN filter on Mikrotik for a PoE switch on port 5?"
- "What's the maximum cable length for the Cudy switch?"
- "Does my motherboard support PCIe bifurcation?"

Claude will reach for the relevant raw URL on its own.
