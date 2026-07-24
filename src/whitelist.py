"""
Whitelist — prune output lines that match unwanted patterns.

A whitelist.txt file at the project root. Each line is a substring pattern:
  If any output line contains the pattern, that line is removed.

Lines starting with # are comments. Blank lines ignored.
"""

import os

_WHITELIST_PATH = 'whitelist.txt'


def load_whitelist(path=None):
    """
    Load whitelist patterns from file.

    Returns a list of (compiled) patterns, or empty list if no file exists.
    Patterns are just strings — matching is substring containment.
    """
    path = path or _WHITELIST_PATH
    if not os.path.isfile(path):
        return []

    patterns = []
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            patterns.append(stripped)

    return patterns


def apply_whitelist(lines, patterns):
    """
    Filter a list of lines through whitelist patterns.

    Any line that contains a whitelist pattern (substring match) is removed.
    """
    if not patterns:
        return lines

    result = []
    for line in lines:
        matched = False
        for pattern in patterns:
            if pattern in line:
                matched = True
                break
        if not matched:
            result.append(line)

    return result