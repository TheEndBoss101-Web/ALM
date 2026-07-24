#!/usr/bin/env python3
"""
Adblock List Manager — Quick launcher.

Usage:
    ./run.py               Full run (fetch, process, combine)
    ./run.py --no-combine  Skip combine step
    ./run.py --combine-only  Re-process combines only
    ./run.py --status      Show cache status
    ./run.py --refresh     Force re-download all cached lists
"""

import sys
import os

# Ensure we're in the project directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from src.main import main

main()