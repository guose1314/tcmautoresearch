from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.real_observe_smoke import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PROFILE_PATH,
    execute_real_observe_smoke,
    load_smoke_profile,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the fixed 20-file real Observe smoke validation profile."
    )
    parser.add_argument(
        "--profile",
        default=str(DEFAULT_PROFILE_PATH),
        help="Path to the real Observe smoke profile JSON.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for latest.json, dossier.md, and timeline.jsonl.",
    )
    args = parser.parse_args()

    profile = load_smoke_profile(Path(args.profile))
    summary = execute_real_observe_smoke(
        profile,
        output_dir=Path(args.output_dir),
        root=ROOT,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("validation_status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())