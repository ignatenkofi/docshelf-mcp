# Example memory-shelf INDEX

What `INDEX.md` — the only memshelf artifact that permanently occupies the
context window — looks like after a few weeks of use. Rendered by docshelf's
standard indexer; only the *content* of titles/descriptions differs from a
document shelf (they are digests, not manual blurbs). This whole file is
~1 KB; links are relative (`provider: none`, private shelf, MCP read path).

---

```markdown
# Homelab — working memory

> Agent memory shelf. Recall rule: check this index before answering
> questions about past work; fetch only the needed episode/section via
> memshelf_recall. Don't guess about past decisions.

## Topics

- [VLAN migration (2026-06-02)](docs/topics/2026-06-02-vlan-migration.md) —
  Flat LAN → VLANs 10/20/30/40 on hAP ac3. Bridge VLAN filtering (switch chip
  can't tag Wi-Fi); two SSIDs + access-list assignment; default-drop
  inter-VLAN firewall. Open: IoT hardcoded-DNS bypass.
- [NAS disk replacement (2026-06-14)](docs/topics/2026-06-14-nas-disk-replacement.md) —
  Replaced failing WD Red in the mirror; chose resilver-then-swap over
  degraded-swap (reason: no cold spare). Burn-in procedure saved to
  Artifacts. Open: none.
- [Pi-hole v6 upgrade (2026-06-28)](docs/topics/2026-06-28-pihole-v6-upgrade/SUBINDEX.md) —
  Upgrade broke custom dnsmasq confs (v6 moved to embedded FTL config).
  Rolled forward, not back; migration map in § Decisions. 14 sections.

## Research

- [UPS sizing notes (2026-06-20)](docs/research/2026-06-20-ups-sizing.md) —
  Measured draw: 180 W idle / 310 W peak. Line-interactive 1000 VA suffices;
  double-conversion rejected (noise, cost). Shortlist with prices in body.

## Sessions

- [2026-07-12 — weekly maintenance](docs/sessions/2026-07-12-weekly-maintenance.md) —
  Updates applied to router+NAS, one failed service (grafana, fixed, cause in
  § Timeline). Open: IoT DNS redirect still pending from VLAN episode.
```

---

Points to notice:

- Each entry's description **is** the episode digest (or its head) — dense
  enough that most questions die here without any fetch.
- The long episode (Pi-hole, 14 sections) links to its SUBINDEX instead of
  inlining sections — inherited docshelf behavior keeping INDEX flat.
- Open threads surface twice (episode + latest session digest), which is
  deliberate: the index is scanned top-to-bottom at session start, and open
  work should be impossible to miss.
