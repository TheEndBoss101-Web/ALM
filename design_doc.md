# Adblock List Manager — Design Document

> **Project:** `/home/agent/.hermes/workspace/adblocklists/`
> **Status:** Design Phase
> **Last Updated:** 2026-07-23

---

## 1. Overview

A CLI tool that consumes adblock lists (remote subscriptions & local custom lists), intelligently **disassembles** each into its constituent categories, and optionally **combines** multiple processed lists into new merged ones.

**Core philosophy:** Take any blocklist format — ABP, hosts, plain domains, plain IPs — and give back every useful representation of that data, stored cleanly by category.

---

## 2. Directory Structure

```
adblocklists/
├── config.yaml            ← You edit this (subscriptions, custom lists, combines)
├── custom_lists/          ← Local list files go here (referenced in config)
├── sources/               ← Cached raw downloads (managed by tool, 24h TTL)
├── lists/                 ← Output: one subdirectory per processed list
│   ├── oisd/
│   │   ├── ipv4
│   │   ├── ipv6
│   │   ├── ips
│   │   ├── domains
│   │   ├── hosts
│   │   ├── urls
│   │   └── abp
│   ├── someonewhocares/
│   │   └── ...
│   └── mega/              ← Combined list, same structure
│       └── ...
└── design_doc.md          ← This file
```

### What goes where

| Path | Role | Who manages it |
|---|---|---|
| `config.yaml` | All configuration | You edit |
| `custom_lists/*` | Your local raw lists | You drop files in |
| `sources/*` | Cached downloads | Tool manages |
| `lists/*` | Processed output | Tool writes |

---

## 3. Config Format (`config.yaml`)

```yaml
# Cache time-to-live in hours
cache_ttl: 24

# Remote subscribed blocklists (name → URL)
lists:
  oisd: https://big.oisd.nl/domainswild2
  someonewhocares: https://someonewhocares.org/hosts/hosts
  easyprivacy: https://easylist.to/easylist/easyprivacy.txt

# Local custom lists (name → filename inside custom_lists/)
custom_lists:
  my_handpicked: my_domains.txt
  pihole_extra: extra_ads.txt

# Combined lists — built from already-processed output in lists/
# Order matters: sources are concatenated in the order listed
combine:
  mega:
    - oisd
    - someonewhocares
    - my_handpicked
  just_domains:
    - oisd
    - my_handpicked
```

### Config rules

- All three sections (`lists`, `custom_lists`, `combine`) are optional. If a section is absent, nothing happens for that category.
- List names must be unique across ALL sections (no name collisions between a subscribed list and a custom list or combine).
- List names should be lowercase, alphanumeric plus underscores/hyphens. The tool may enforce this.
- Custom list file paths are relative to the `custom_lists/` directory.

---

## 4. Processing Pipeline

### 4.1 Execution Order

```
                    ┌─────────────────────┐
                    │     Read config      │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                 ▼
      ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
      │ Fetch remote  │ │ Read local   │ │  (skip if    │
      │ lists (cache) │ │ custom lists │ │   none)      │
      └──────┬───────┘ └──────┬───────┘ └──────────────┘
             └───────┬────────┘
                     ▼
           ┌─────────────────────┐
           │  Process each list  │  ← One at a time
           │  Parse → Classify   │
           │  Separate → Save    │
           └──────────┬──────────┘
                      │
                      ▼
           ┌─────────────────────┐
           │  Process combines   │  ← LAST step
           │  Merge → Dedup      │
           │  Generate → Save    │
           └─────────────────────┘
```

### 4.2 Step-by-Step

**Phase 1 — Fetch**
1. For each entry in `lists:`:
   - Check `sources/<name>` for cached copy
   - If cache is < `cache_ttl` hours old → use it
   - If cache is stale or missing → download URL
   - On download failure → use stale cache if available, otherwise skip with warning
   - Save successful download to `sources/<name>`
2. For each entry in `custom_lists:`:
   - Read `custom_lists/<filename>` directly (no caching needed)

**Phase 2 — Process**
1. For EACH list (subscribed + custom):
   - Read raw content
   - Strip BOM, normalize line endings
   - Classify every line (see Section 5)
   - Separate into 7 categories
   - Dedup on derived categories (see Section 6)
   - Write to `lists/<name>/` (see Section 7)

**Phase 3 — Combine (LAST)**
1. For each entry in `combine:`:
   - Read the already-processed output from `lists/<source>/` for each source
   - Per category file:
     - Strip comment lines
     - Concatenate in source order
     - Dedup (see Section 6)
   - Generate ABP if needed (see Section 8)
   - Write to `lists/<combined_name>/`

---

## 5. Line Classification

Each non-empty, non-whitespace line is classified using the following priority-ordered rules. The **first match wins**.

| Priority | Pattern | Classified As | Also Extracts | Example |
|---|---|---|---|---|
| 1 | Empty line or whitespace only | **Skip** | — | |
| 2 | Comment (`!` or `#` at start) | **Comment** | — | `! Title: My List` |
| 3 | Header (`[Adblock` or `[AdBlock` or `[uBlock`) | **ABP** (pass through) | — | `[Adblock Plus 2.0]` |
| 4 | IPv4 (validated, optional CIDR) | **ipv4** + **ips** | — | `1.2.3.4`, `10.0.0.0/8` |
| 5 | IPv6 (validated, optional CIDR) | **ipv6** + **ips** | — | `::1`, `2001:db8::/32` |
| 6 | ABP whitelist `@@||domain^` | **Dropped** (fully excluded) | — | `@@||good.example.com^` |
| 7 | ABP domain rule `||domain^` | **ABP** | domain → domains | `||evil.example.com^$third-party` |
| 9 | ABP exact URL `\|http://...\|` | **ABP** | URL → urls, host → domains + hosts | `|https://example.com/ad.gif|` |
| 10 | ABP element hiding `##selector` | **ABP** | — | `##.ad-banner` |
| 11 | ABP domain-specific element hiding `domain##selector` | **ABP** | domain → domains | `example.com##.ad` |
| 12 | Hosts format (`IP whitespace domain`) | **hosts** | IP → ips, domain → domains | `0.0.0.0 spytrack.example.com` |
| 13 | Plain URL (`http://` or `https://`) | **URLs** | host → domains + hosts | `https://example.com/banner.gif` |
| 14 | Plain naked domain (no wildcards) | **domains** | host → hosts | `example.com` |
| 15 | Wildcard domain (`*.domain.tld`) | **domains** | strip `*.` → domain, host → hosts | `*.evil.example.com` |
| 16 | Anything else | **ABP** (pass through) | — | (unrecognized rule types) |

### Classification notes

- **ABP options** (the `$`-suffix on `||domain^$options`) are preserved verbatim in the ABP output
- **IPv4 validation:** must pass `ipaddress.IPv4Address()` or `ipaddress.IPv4Network()`
- **IPv6 validation:** must pass `ipaddress.IPv6Address()` or `ipaddress.IPv6Network()`
- **Domain validation:** must match `[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}`
- **Wildcard domains:** `*.xyz.com` → strip the `*.` prefix, treat as a plain domain. `.xyz.com` → same treatment
- **Hosts IP extraction:** The IP from a hosts line goes to `ips` and `hosts`, the domain goes to `domains` and `hosts`
- **Whitelist rules** (`@@`) are fully excluded from all output. They are not a blocking rule, so they do not appear in `domains`, `hosts`, `ips`, `urls`, or `abp`. The `abp` file is a clean blocklist — whitelist exceptions are outside its scope.
- **ABP sources are fully extracted:** Extractable data (domains from `||domain^` rules, URLs from `|http://...|` rules, hosts from element hiding rules) are placed into the appropriate derived categories (`domains`, `hosts`, `urls`). The `abp` file is then generated from these extracted categories, not passed through from the source.

---

## 6. Deduplication Policy

| Category | Any list |
|---|---|
| `ipv4` | ✅ Dedup |
| `ipv6` | ✅ Dedup |
| `ips` | ✅ Dedup |
| `domains` | ✅ Dedup |
| `hosts` | ✅ Dedup |
| `urls` | ✅ Dedup |
| `abp` | ✅ Dedup (always generated from extracted data) |

### Dedup rules

- **Case-sensitive** for domains, URLs, IPs (IPs are normalized to canonical form)
- **Within each file independently** — a line in `domains` is not compared against a line in `urls`
- **Whitespace-trimmed** before comparison

---

## 7. Output Format

Each list (normal, custom, or combined) gets a directory under `lists/<name>/` with up to 7 files:

### `ipv4`
```
1.2.3.4
10.0.0.0/8
192.168.1.0/24
```
One IPv4 address or CIDR per line. No comments. Deduped.

### `ipv6`
```
::1
2001:db8::/32
```
One IPv6 address or CIDR per line. No comments. Deduped.

### `ips`
```
1.2.3.4
10.0.0.0/8
::1
2001:db8::/32
```
Merged IPv4 + IPv6. One IP per line. No comments. Deduped.

### `domains`
```
example.com
evil-tracker.net
```
One naked domain per line. No wildcards. No comments. Deduped.

### `hosts`
```
0.0.0.0 example.com
0.0.0.0 evil-tracker.net
```
IP-to-domain mapping in standard hosts file format. One entry per line. No comments. Deduped.

Generated from: hosts sources (pass-through), ABP `||domain^` rules, ABP `|URL|` host extraction, plain domains, wildcard domains, and URL hostnames.

### `urls`
```
https://example.com/banner.gif
https://ads.example.net/pixel.png
```
One full URL per line. No comments. Deduped.

### `abp`
```
! Generated by Adblock List Manager
! Source: list_name
! Format: ABP-style rules
||evil.example.com^$all
||0.0.0.0^$all
||::1^$all
```
Generated from the extracted domains, IPs, and URLs. One rule per line. No comments from the source are preserved. Deduped. The format is always `||domain^$all` for domains and `||IP^$all` for IPs.

---

## 8. ABP Generation

The ABP file is always generated from the extracted data (domains, IPs, URLs). There is no raw pass-through — every list, regardless of source format, produces a clean synthetic ABP file.

### Generation rules

| Source category | Generated ABP format |
|---|---|
| Domain | `||domain.tld^$all` |
| URL | Full URL as-is |
| IPv4 / IPv6 (bare IP) | `||IP^$all` |
| Hosts entry domain | `||domain.tld^$all` |
| Hosts entry IP | `||IP^$all` |

### Header

```
! Generated by Adblock List Manager
! Source: <list_name>
! Format: ABP-style rules
```

### What's excluded

- **Comments** (`!` and `#` lines) — not preserved
- **Headers** (`[Adblock ...]`) — not preserved
- **Whitelist rules** (`@@||domain^`) — fully excluded (not a blocking rule)
- **Non-extractable ABP rules** (regex patterns, cosmetic filters without domains) — dropped

---

## 9. Caching

### Cache storage
- Raw downloaded content stored in `sources/<name>`
- File named exactly as the list name from config (no extension added)

### Cache lifecycle
```
[Download] → save to sources/<name>
              ↓
              ↓ (cache_ttl hours pass)
              ↓
[Next run] → check sources/<name>
              ↓
         ┌────┴────┐
         ▼         ▼
      Fresh?    Stale?
         │         │
    Use cache    Try download
         │         │
         │    ┌────┴────┐
         │    ▼         ▼
         │  Success?  Fail?
         │    │         │
         │  Update    Use stale
         │  cache     cache
         │    │         │
         └────┴─────────┘
              ▼
         Process list
```

### Cache file format
- Raw content, exactly as downloaded
- No metadata, no wrapper
- BOM preserved (tool strips it during processing)

---

## 10. Combine Mechanics (Detail)

### What gets combined

For each source in a `combine:` entry, the tool reads from `lists/<source>/`:

```
mega (combines: oisd + someonewhocares + my_handpicked)
  ├── ipv4     = lists/oisd/ipv4 + lists/someonewhocares/ipv4 + lists/my_handpicked/ipv4
  ├── ipv6     = same pattern
  ├── ips      = same pattern
  ├── domains  = same pattern
  ├── hosts    = same pattern
  ├── urls     = same pattern
  └── abp      = same pattern
```

### Processing per category

1. **Read** each source's category file
2. **Strip** comment lines (`!` and `#` prefix)
3. **Concatenate** in source order (as listed in config)
4. **Deduplicate** (all categories, including ABP)
5. **Write** to `lists/<combined_name>/<category>`

### Combine is LAST

Combines are processed AFTER all normal and custom lists are fully processed. This means:
- Sources referenced in a combine must exist as processed lists in `lists/`
- If a source list fails to process, the combine will skip it with a warning
- You can re-run combines without re-fetching sources (since they read from processed output)

---

## 11. Invocation

The tool is run as a CLI command:

```bash
# Full run — fetch, process, combine
python3 run.py

# Fetch and process only (skip combine)
python3 run.py --no-combine

# Combine only (re-process combines without fetching)
python3 run.py --combine-only

# Check cache status without running
python3 run.py --status

# Force re-download all cached lists
python3 run.py --refresh
```

---

## 12. Error Handling

| Scenario | Behavior |
|---|---|
| Download fails, no cache | Skip list, log warning, continue |
| Download fails, stale cache exists | Use stale cache, log warning |
| Config file missing | Error and exit |
| Config parse error | Error and exit with YAML parser details |
| Custom list file not found | Skip list, log warning, continue |
| Combine source not found | Skip that source in combine, log warning |
| Corrupted cache file | Delete cache, re-download, fallback to skip on failure |
| Invalid line in list | Skip that line, log debug message, continue |
| Disk write failure | Error and exit (data integrity) |

---

## 13. Future Considerations (Not In Scope Yet)

These are documented but not implemented in v1:

- **Filter on combine** — e.g., "only take domains from A and URLs from B"
- **Exclusion sets** — "combine A and B, but remove anything from C"
- **Format auto-detection improvements** — better heuristic for mixed-format lists
- **Progress output** — per-list progress bar for large lists
- **Cache invalidation per-URL** — force-refresh specific lists only
- **Stats output** — "oisd: 50,000 domains, 200 IPs, 120,000 ABP rules"
- **Export formats** — dnsmasq, unbound, pfBlockerNG, AdGuard Home
- **Diff mode** — show what changed since last run

---

## 14. Summary of Key Decisions

| Decision | Choice |
|---|---|
| Config format | YAML (`config.yaml`) |
| List naming | Explicit in config (name → URL/file) |
| Cache TTL | 24 hours |
| Cache fallback | Use stale on download failure |
| Dedup | All categories, all lists |
| Combine timing | Last step, after all lists processed |
| IPs in ABP output | Generated as `||IP^$all` |
| Wildcard domain handling | Strip `*.`, treat as plain domain |
| Custom lists | Must be declared in config |