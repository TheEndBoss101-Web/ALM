"""
Adblock List Manager — CLI entry point.

Usage:
    python -m src.main               Full run (fetch, process, combine)
    python -m src.main --no-combine  Skip combine step
    python -m src.main --combine-only  Re-process combines only
    python -m src.main --status      Show cache status
    python -m src.main --refresh     Force re-download all cached lists
"""

import os
import sys
import time

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.config import load_config
from src.fetcher import fetch_list, read_custom_list, clear_cache, cache_status
from src.processor import process_list
from src.combiner import combine_lists


def _print_stats(name, stats, label=None):
    """Print a formatted stats line for a list."""
    prefix = f"  {label or '→'}"
    parts = []
    for cat in ('ipv4', 'ipv6', 'ips', 'domains', 'hosts', 'urls', 'abp'):
        count = stats.get(cat, 0)
        if count > 0:
            parts.append(f"{cat}:{count}")
    print(f"{prefix} {name}  ({', '.join(parts)})")


def run_fetch_and_process(config, force_refresh=False):
    """Phase 1+2: Fetch subscribed lists, read custom lists, process all."""
    cache_ttl = 0 if force_refresh else config['cache_ttl']
    total_lists = len(config['lists']) + len(config['custom_lists'])
    if total_lists == 0:
        print("  No lists configured (add some to config.yaml)")
        return

    # --- Fetch subscribed lists ---
    for name, url in config['lists'].items():
        print(f"  Fetching '{name}'...")
        try:
            content = fetch_list(name, url, cache_ttl=cache_ttl)
        except RuntimeError as e:
            print(f"  ✗  {e}")
            continue

        print(f"  Processing '{name}'...")
        try:
            stats = process_list(content, name)
            _print_stats(name, stats)
        except Exception as e:
            print(f"  ✗  Failed to process '{name}': {e}")

    # --- Read custom lists ---
    for name, filename in config['custom_lists'].items():
        print(f"  Reading custom list '{name}' ({filename})...")
        try:
            content = read_custom_list(name, filename)
        except FileNotFoundError:
            print(f"  ✗  Custom list file 'custom_lists/{filename}' not found")
            continue
        except Exception as e:
            print(f"  ✗  Failed to read 'custom_lists/{filename}': {e}")
            continue

        print(f"  Processing '{name}'...")
        try:
            stats = process_list(content, name)
            _print_stats(name, stats)
        except Exception as e:
            print(f"  ✗  Failed to process '{name}': {e}")


def run_combine(config):
    """Phase 3: Process all combine entries."""
    if not config['combine']:
        return

    print("  Combining lists...")
    for name, sources in config['combine'].items():
        if not sources:
            print(f"  ⚠  Combine '{name}' has no sources, skipping")
            continue
        print(f"  Combining '{name}' from {sources}...")
        try:
            stats = combine_lists(name, sources)
            if stats:
                _print_stats(name, stats, label='→')
        except Exception as e:
            print(f"  ✗  Failed to combine '{name}': {e}")


def show_status():
    """Show cache status for all cached lists."""
    status = cache_status()
    if not status:
        print("  No cached lists.")
        return
    for name, age in sorted(status.items()):
        hours = f"{age:.1f}h"
        stale = " (STALE)" if age >= 24 else ""
        print(f"  {name:30s} {hours:>8s}{stale}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    flags = set(a for a in sys.argv[1:] if a.startswith('-'))

    # --- Load config ---
    try:
        config = load_config(args[0] if args else None)
    except ValueError as e:
        print(f"✗  Config error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗  Failed to load config: {e}")
        sys.exit(1)

    # --- --status ---
    if '--status' in flags:
        show_status()
        return

    # --- --refresh ---
    if '--refresh' in flags:
        print("Clearing cache...")
        clear_cache()
        # Continue with normal run, but force refresh

    # --- Determine run mode ---
    no_combine = '--no-combine' in flags
    combine_only = '--combine-only' in flags
    force_refresh = '--refresh' in flags

    if combine_only:
        print("=== Combine only ===")
        run_combine(config)
        return

    # --- Full run ---
    print("=== Adblock List Manager ===")
    t0 = time.time()

    print("Phase 1/2: Fetch & Process")
    run_fetch_and_process(config, force_refresh=force_refresh)

    if not no_combine:
        print("Phase 3: Combine")
        run_combine(config)

    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s")


if __name__ == '__main__':
    main()