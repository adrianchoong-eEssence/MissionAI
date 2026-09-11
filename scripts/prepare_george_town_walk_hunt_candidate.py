#!/usr/bin/env python3
"""Print, but never materialise, the owner-authorised George Town UAT plan."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Direct script execution starts with scripts/ on sys.path rather than the
# repository root. Keep this planning tool importable without packaging it.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content_packs.george_town_walk_hunt_v1.materialize import candidate_plan


if __name__ == "__main__":
    print(json.dumps(candidate_plan(), indent=2, sort_keys=True))
