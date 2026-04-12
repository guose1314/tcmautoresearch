#!/usr/bin/env python3
"""Alias entry point for backfilling the full structured research graph into Neo4j."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from backfill_research_session_nodes import main

if __name__ == "__main__":
    raise SystemExit(main())