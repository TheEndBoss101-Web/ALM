"""
Configuration loader for Adblock List Manager.

Reads config.yaml and returns a validated config dict.
Creates a default config if none exists.
"""

import os
import yaml

_CONFIG_PATH = 'config.yaml'

DEFAULT_CONFIG = {
    'cache_ttl': 24,
    'lists': {},
    'custom_lists': {},
    'combine': {},
}


def _generate_default(path):
    """Write a default config file and return it."""
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('# Adblock List Manager Configuration\n')
        fh.write('# See README.md for documentation.\n\n')
        yaml.dump(DEFAULT_CONFIG, fh, default_flow_style=False, sort_keys=False)
    return dict(DEFAULT_CONFIG)


def load_config(path=None):
    """
    Load and validate config from a YAML file.

    Returns a dict with keys: cache_ttl, lists, custom_lists, combine.
    """
    path = path or _CONFIG_PATH

    if not os.path.exists(path):
        return _generate_default(path)

    with open(path, 'r', encoding='utf-8') as fh:
        raw = yaml.safe_load(fh) or {}

    config = dict(DEFAULT_CONFIG)
    for key in config:
        if key in raw and raw[key] is not None:
            config[key] = raw[key]

    # Validation
    if not isinstance(config['cache_ttl'], (int, float)) or config['cache_ttl'] < 0:
        print("  ⚠  cache_ttl must be a positive number, resetting to 24")
        config['cache_ttl'] = 24

    if not isinstance(config['lists'], dict):
        print("  ⚠  'lists' must be a mapping (name → URL), resetting")
        config['lists'] = {}

    if not isinstance(config['custom_lists'], dict):
        print("  ⚠  'custom_lists' must be a mapping (name → filename), resetting")
        config['custom_lists'] = {}

    if not isinstance(config['combine'], dict):
        print("  ⚠  'combine' must be a mapping (name → list of source names), resetting")
        config['combine'] = {}

    # --- Auto-detect custom list files ---
    # Any .txt file in custom_lists/ gets registered as custom_<filename>
    custom_dir = 'custom_lists'
    if os.path.isdir(custom_dir):
        for entry in sorted(os.listdir(custom_dir)):
            if not entry.endswith('.txt'):
                continue
            stem = entry[:-4]  # strip .txt
            name = f'custom_{stem}'
            if name not in config['custom_lists']:
                config['custom_lists'][name] = entry
                print(f"  ✓ Auto-registered custom list '{name}' from {entry}")

    # Check for name collisions across sections
    names = set()
    for section in ('lists', 'custom_lists', 'combine'):
        for name in config[section]:
            if name in names:
                raise ValueError(
                    f"Name collision: '{name}' appears in multiple sections. "
                    "All list names must be unique."
                )
            names.add(name)

    return config