# Adblock List Manager

Take any blocklist format — ABP, hosts files, plain domains, plain IPs — and **disassemble** it into its constituent parts. Subscribe to remote lists, drop in local custom lists, and optionally merge processed outputs into combined lists.

## Quick Start

```bash
# 1. Edit config.yaml — add your subscriptions
# 2. Run it
./run.py

# Or via module:
python -m src.main
```

## Installation

No installation needed. Requires **Python 3.8+** and **PyYAML** (usually pre-installed on Kali/Debian).

```bash
# If you need PyYAML:
sudo apt install python3-yaml
# or
pip install pyyaml
```

## Configuration

Everything lives in **`config.yaml`**:

```yaml
# How often to re-download (hours). Default: 24
cache_ttl: 24

# Remote subscriptions (name → URL)
lists:
  oisd: https://big.oisd.nl/domainswild2

# Local files in custom_lists/ (name → filename)
custom_lists:
  my_handpicked: my_domains.txt

# Combined lists (name → list of source names)
combine:
  mega:
    - oisd
    - my_handpicked
```

All names **must be unique** across all three sections.

### Custom lists

Put your files in `custom_lists/` and reference them in config:

```
adblocklists/
├── config.yaml
└── custom_lists/
    ├── my_domains.txt
    └── extra_ads.txt
```

## Usage

```bash
# Full run — fetch, process, combine
./run.py

# Skip combine step
./run.py --no-combine

# Re-process combines only (no fetching)
./run.py --combine-only

# Check cache status
./run.py --status

# Force re-download everything
./run.py --refresh
```

## Output Structure

Each list (subscribed, custom, or combined) gets its own directory:

```
lists/
├── oisd/
│   ├── ipv4        # IPv4 addresses & CIDR ranges
│   ├── ipv6        # IPv6 addresses & CIDR ranges
│   ├── ips         # IPv4 + IPv6 merged
│   ├── domains     # Naked domains (no wildcards, no protocols)
│   ├── hosts       # hosts-file format: IP → domain
│   ├── urls        # Full URL patterns
│   └── abp         # AdBlock Plus format rules
├── my_handpicked/
│   └── ...
└── mega/           # Combined list, same structure
    └── ...
```

### What each file contains

| File | Contains | Example |
|---|---|---|
| `ipv4` | One IPv4 address or CIDR per line | `1.2.3.4`, `10.0.0.0/8` |
| `ipv6` | One IPv6 address or CIDR per line | `::1`, `2001:db8::/32` |
| `ips` | Merged IPv4 + IPv6 | Combined from above |
| `domains` | Naked domains only (no `*.` wildcards) | `example.com` |
| `hosts` | hosts-file format entries | `0.0.0.0 example.com` |
| `urls` | Full URL patterns | `https://example.com/ad.gif` |
| `abp` | Generated ABP rules (always from extracted data) | `||example.com^$all`, `||1.2.3.4^$all` |

## How It Works

### Pipeline

```
Phase 1: Fetch
  ├── Download subscribed lists (cached for cache_ttl hours)
  └── Read custom lists from custom_lists/

Phase 2: Process
  └── For each list:
       ├── Classify every line (see Line Classification below)
       ├── Separate into 7 categories
       ├── Deduplicate according to policy
       └── Write to lists/<name>/

Phase 3: Combine (LAST)
  └── For each combine entry:
       ├── Read processed output from lists/<source>/
       ├── Strip comments → Concatenate in order → Dedup
       └── Write to lists/<combined_name>/
```

### Line Classification

Every line is classified using priority-ordered rules (first match wins):

| Priority | Pattern | Goes To | Also Extracts |
|---|---|---|---|
| 1 | Empty / whitespace | Skipped | — |
| 2 | `!` or `#` comment | ABP (preserved) | — |
| 3 | `[Adblock ...]` header | ABP (preserved) | — |
| 4 | Validated IPv4 (with CIDR) | ipv4 + ips | — |
| 5 | Validated IPv6 (with CIDR) | ipv6 + ips | — |
| 6 | `@@||domain^` (ABP whitelist) | **Dropped** (fully excluded from all output) | — |
| 7 | `||domain^` (ABP domain rule) | ABP | domain → domains + hosts |
| 8 | `\|http://...\|` (ABP exact URL) | ABP | URL → urls, host → domains + hosts |
| 9 | `domain##selector` (element hiding) | ABP | domain → domains |
| 10 | `IP domain` (hosts format) | hosts | IP → ips, domain → domains + hosts |
| 11 | `http://...` or `https://...` (plain URL) | urls | host → domains + hosts |
| 12 | `*.domain.tld` (wildcard domain) | domains | stripped → domains + hosts |
| 13 | `domain.tld` (plain domain) | domains | host → hosts |
| 14 | Everything else | ABP (not extractable, dropped) | — |

### Dedup Policy

| Category | Any list |
|---|---|
| ipv4 | ✅ Dedup |
| ipv6 | ✅ Dedup |
| ips | ✅ Dedup |
| domains | ✅ Dedup |
| hosts | ✅ Dedup |
| urls | ✅ Dedup |
| abp | ✅ Dedup (always generated from extracted data) |

### Generated ABP

The ABP file is always generated from extracted data, regardless of source format. No raw pass-through.

| Extracted data | Generated ABP |
|---|---|
| `example.com` | `||example.com^$all` |
| `https://ads.example/pixel` | `https://ads.example/pixel` |
| `1.2.3.4` | `||1.2.3.4^$all` |
| `0.0.0.0 ad.example.com` | domain → `||ad.example.com^$all`, IP → `||0.0.0.0^$all` |

### What's excluded from ABP

- Comments (`!` and `#`) — not preserved
- Headers (`[Adblock ...]`) — not preserved
- Whitelist rules (`@@||domain^`) — fully excluded
- Non-extractable rules (regex, cosmetic filters without domains) — dropped

## Caching

- Downloaded lists are stored in `sources/<name>`
- Default TTL: **24 hours**
- On download failure: **falls back to stale cache** if available
- Use `--refresh` to force re-download everything
- Use `--status` to check cache ages

## Design

See **[design_doc.md](./design_doc.md)** for the full design document covering:
- Processing pipeline
- Line classification rules
- Dedup policy details
- Error handling
- Future considerations

## License

MIT — do whatever you want with it.
