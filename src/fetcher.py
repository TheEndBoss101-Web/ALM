"""
Fetch remote blocklists with 24-hour caching and stale-fallback.

Cache storage:  sources/<name>
Cache TTL:      configurable (default 24 hours)
On failure:     falls back to stale cache if available
"""

import os
import time
import urllib.request
import urllib.error

CACHE_DIR = 'sources'


def fetch_list(name, url, cache_ttl=24, cache_dir=None):
    """
    Fetch a blocklist from URL with caching.

    Args:
        name:       List name (used as cache filename)
        url:        URL to download
        cache_ttl:  Cache validity in hours (default 24)
        cache_dir:  Cache directory (default: sources/)

    Returns:
        Raw content as string

    Raises:
        RuntimeError if download fails and no cache exists
    """
    cache_dir = cache_dir or CACHE_DIR
    cache_path = os.path.join(cache_dir, name)

    # --- Check cache ---
    cache_valid = False
    if os.path.exists(cache_path):
        mtime = os.path.getmtime(cache_path)
        age_hours = (time.time() - mtime) / 3600
        if age_hours < cache_ttl:
            cache_valid = True

    if cache_valid:
        with open(cache_path, 'r', encoding='utf-8', errors='replace') as fh:
            return fh.read()

    # --- Download ---
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'AdblockListManager/1.0'}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read().decode('utf-8', errors='replace')

        # Save to cache
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as fh:
            fh.write(content)

        return content

    except Exception as exc:
        # Fall back to stale cache
        if os.path.exists(cache_path):
            with open(cache_path, 'r', encoding='utf-8', errors='replace') as fh:
                return fh.read()
        raise RuntimeError(
            f"Failed to download '{name}' from {url}: {exc}"
        ) from exc


def read_custom_list(name, filename, custom_dir=None):
    """
    Read a custom list file from the custom_lists/ directory.

    Args:
        name:       List name (used for output directory naming)
        filename:   Filename inside custom_lists/
        custom_dir: Custom lists directory (default: custom_lists/)

    Returns:
        Raw content as string

    Raises:
        FileNotFoundError if file doesn't exist
    """
    custom_dir = custom_dir or 'custom_lists'
    path = os.path.join(custom_dir, filename)

    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def clear_cache(name=None, cache_dir=None):
    """Remove cache files. If name is None, clear all."""
    cache_dir = cache_dir or CACHE_DIR
    if not os.path.exists(cache_dir):
        return

    if name:
        path = os.path.join(cache_dir, name)
        if os.path.exists(path):
            os.remove(path)
    else:
        for entry in os.listdir(cache_dir):
            os.remove(os.path.join(cache_dir, entry))


def cache_status(cache_dir=None):
    """Return a dict of {name: age_in_hours} for all cached lists."""
    cache_dir = cache_dir or CACHE_DIR
    if not os.path.exists(cache_dir):
        return {}

    now = time.time()
    status = {}
    for entry in os.listdir(cache_dir):
        path = os.path.join(cache_dir, entry)
        if os.path.isfile(path):
            mtime = os.path.getmtime(path)
            status[entry] = (now - mtime) / 3600
    return status