# Example episode

What a real offloaded episode looks like on the shelf
(`docs/topics/2026-06-02-vlan-migration.md`). This one is small enough that
docshelf's splitter would keep it whole; a longer one (with big
`## Raw excerpts`) would be auto-split into `2026-06-02-vlan-migration/001-…`
section files with a SUBINDEX.

---

```markdown
---
id: 2026-06-02-vlan-migration
kind: topic
span: 2026-06-01..2026-06-02
tags: [homelab, mikrotik, vlan, networking]
approx_tokens: 38000
---

## Digest
Migrated the homelab from a flat LAN to VLANs 10 (mgmt), 20 (trusted),
30 (lab), 40 (iot) on the Mikrotik hAP ac3. Chose bridge VLAN filtering over
switch-chip rules because the switch chip on this model can't tag on the
Wi-Fi interfaces. Rejected one-SSID-per-VLAN (AP limit: 4 virtual SSIDs kill
2.4 GHz throughput); went with two SSIDs + per-client VLAN assignment via
access list. Firewall inter-VLAN policy: default drop, allowlist per service.
Open: IoT devices with hardcoded DNS bypass the Pi-hole — needs dst-nat rule.

## Decisions
- **Bridge VLAN filtering, not switch-chip VLANs** — switch chip can't tag
  wlan1/wlan2 on hAP ac3; bridge filtering handles both wired and wireless
  uniformly. Cost: ~5% CPU on routing between VLANs, acceptable at 1 Gbps.
- **Two SSIDs + access-list VLAN assignment, not SSID-per-VLAN** — rejected
  because >2 virtual SSIDs measurably degraded 2.4 GHz (beacon overhead).
- **Default-drop inter-VLAN firewall** — allowlist entries only for
  Pi-hole DNS (all→30:53) and printer (20→40:631/9100).

## Timeline
Day 1: read RouterOS bridge VLAN chapter (shelf: routers/mikrotik-routeros,
§ bridging), drafted plan, moved mgmt to VLAN 10 last to avoid lockout —
still locked myself out once via wrong PVID on the uplink port; recovered
with MAC-telnet. Day 2: Wi-Fi access lists, firewall policy, verified with
per-VLAN DHCP leases and inter-VLAN nmap scans.

## Artifacts
- `/export` backup: homelab-shelf repo, `configs/hap-ac3-2026-06-02.rsc`
- Firewall ruleset table: § Raw excerpts below
- Verification checklist reused from RouterOS manual § firewall

## Open threads
- IoT devices with hardcoded 8.8.8.8 bypass Pi-hole → add dst-nat 53
  redirect on VLAN 40.
- Guest VLAN (50) postponed until the second AP arrives.

## Raw excerpts
    /interface bridge port
    set [find interface=ether2] pvid=20
    set [find interface=ether5] pvid=30   # ← the port that locked me out
                                          #    (was: uplink, pvid must stay 10)
    /interface bridge vlan
    add bridge=bridge1 tagged=bridge1,ether1 vlan-ids=10,20,30,40
```

---

Points to notice:

- The **digest alone** answers the likely future questions ("why bridge
  filtering?", "why only two SSIDs?") without fetching the body.
- `## Decisions` keeps rejected alternatives *with reasons* — the thing
  auto-compaction always destroys first.
- `## Raw excerpts` holds the two verbatim fragments that would be painful to
  reconstruct (exact port/PVID that caused the lockout), nothing else.
- Frontmatter `approx_tokens: 38000` records what this episode was costing
  per-turn while it lived in context; the whole file is ~600 tokens, the
  digest ~130.
