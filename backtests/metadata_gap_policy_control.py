"""Offline Phase 8J broker-metadata gap-policy publisher.

This control surface only reads existing Phase 8 evidence and atomically adds
the two hash-bound Phase 8J records.  It has no market-data, network, MT5, or
strategy-evaluation capability.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.validation.metadata_gap_policy import publish_from_evidence_root


DEFAULT_DATA_ROOT = Path(r"C:\Users\chips\forex-signal-bot-data\phase8")
OWNER_DECISION_UTC = "2026-09-15T00:00:00Z"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("publish", nargs="?", choices=("publish",), default="publish")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--decision-utc", default=OWNER_DECISION_UTC)
    args = parser.parse_args(argv)
    result = publish_from_evidence_root(data_root=args.data_root, decision_utc=args.decision_utc)
    print(f"published metadata-gap policy {result['policy_package_id']}")
    print(f"published metadata-gap readiness {result['readiness_package_id']}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main
    raise SystemExit(main())
