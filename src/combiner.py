"""
Combine multiple already-processed lists into a new merged list.

Takes the per-category output files from lists/<source>/,
strips comments, concatenates in source order, deduplicates,
and writes to lists/<combined_name>/.
"""

import os
from .whitelist import load_whitelist, apply_whitelist

CATEGORIES = ['ipv4', 'ipv6', 'ips', 'domains', 'hosts', 'urls', 'abp']


def _dedup(lines):
    """Remove duplicates while preserving order."""
    seen = set()
    result = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            result.append(line)
    return result


def combine_lists(combined_name, source_names, lists_dir=None):
    """
    Combine multiple processed lists into one.

    Args:
        combined_name: Name for the new combined list
        source_names:  List of source list names to merge
        lists_dir:     Base directory for processed lists (default: lists/)

    Returns:
        dict of {category: line_count} for the combined result, or
        None if no sources were successfully processed.
    """
    lists_dir = lists_dir or 'lists'

    merged = {cat: [] for cat in CATEGORIES}

    for source in source_names:
        source_dir = os.path.join(lists_dir, source)
        if not os.path.isdir(source_dir):
            print(f"  ⚠  Source '{source}' not found in {lists_dir}/, skipping")
            continue

        for cat in CATEGORIES:
            cat_file = os.path.join(source_dir, cat)
            if not os.path.isfile(cat_file):
                continue

            with open(cat_file, 'r', encoding='utf-8', errors='replace') as fh:
                lines = fh.read().splitlines()

            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                # Strip comments
                if stripped.startswith('!') or stripped.startswith('#'):
                    continue
                merged[cat].append(stripped)

    # Check if anything was merged
    total = sum(len(merged[cat]) for cat in CATEGORIES)
    if total == 0:
        print(f"  ⚠  No data from combine '{combined_name}' — no valid sources")
        return None

    # Dedup ALL categories (combined lists dedup everything, including ABP)
    for cat in CATEGORIES:
        merged[cat] = _dedup(merged[cat])

    # --- Apply whitelist pruning (post-combine) ---
    wl_patterns = load_whitelist()
    if wl_patterns:
        for cat in CATEGORIES:
            merged[cat] = apply_whitelist(merged[cat], wl_patterns)

    # Write output
    out_dir = os.path.join(lists_dir, combined_name)
    os.makedirs(out_dir, exist_ok=True)

    stats = {}
    for cat, lines in merged.items():
        file_path = os.path.join(out_dir, cat)
        with open(file_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines))
            if lines:
                fh.write('\n')
        stats[cat] = len(lines)

    return stats