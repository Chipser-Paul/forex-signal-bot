"""Offline Phase 8L metadata-bound publisher; no MT5, network, or evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.validation.development_metadata_bounds import publish_from_evidence_root


DEFAULT_DATA_ROOT = Path(r"C:\Users\chips\forex-signal-bot-data\phase8")
DEFAULT_SUPPORT_ROOT = DEFAULT_DATA_ROOT / "evidence" / "owner-input" / "broker-metadata" / "Support"
OWNER_DECISION_UTC = "2026-09-15T00:00:00Z"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("publish", nargs="?", choices=("publish",), default="publish")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--eml", type=Path, default=DEFAULT_SUPPORT_ROOT / "Private" / "Exness_2024_Historical_Metadata_Unavailable_2026-09-15.eml")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_SUPPORT_ROOT / "Exness_2024_Historical_Metadata_Unavailable_2026-09-15.pdf")
    parser.add_argument("--decision-utc", default=OWNER_DECISION_UTC)
    args = parser.parse_args(argv)
    result = publish_from_evidence_root(data_root=args.data_root, eml_path=args.eml, pdf_path=args.pdf, decision_utc=args.decision_utc)
    for name, value in result.items():
        print(f"published {name} {value}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
