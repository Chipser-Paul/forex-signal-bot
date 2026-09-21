"""Phase 8C provenance attestation and discovery CLI.

Offline, read-only with respect to the attested package:

  attest   verify the existing derived package and publish its attestation
  register  register an attested package in the external discovery record

Both commands are idempotent for identical immutable inputs and fail closed
on conflicts.  No MT5, no network, no strategy evaluation.

DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from bot.acquisition.candle_attestation import publish_attestation
from bot.acquisition.candle_discovery import (
    code_fingerprint,
    register_attested_package,
)
from bot.acquisition.models import AcquisitionError

logger = logging.getLogger(__name__)


def _git_head(worktree_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(worktree_root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AcquisitionError("DISCOVERY_GIT_HEAD_UNAVAILABLE") from exc


def cmd_attest(args: argparse.Namespace) -> None:
    worktree_root = Path(args.worktree_root).resolve(strict=True)
    implementation_commit = (
        args.implementation_commit
        if args.implementation_commit
        else _git_head(worktree_root)
    )
    verification_commit = (
        args.verification_commit
        if args.verification_commit
        else _git_head(worktree_root)
    )
    fingerprint = code_fingerprint(
        verification_commit, worktree_root=worktree_root
    )
    document, identity = publish_attestation(
        Path(args.derived_root).resolve(strict=True),
        Path(args.attestations_root),
        implementation_commit=implementation_commit,
        verification_commit=verification_commit,
        verification_fingerprint=fingerprint,
        worktree_root=worktree_root,
    )
    logger.info(
        "Attestation %s published (canonical=%s physical=%s)",
        identity.attestation_id,
        identity.attestation_sha256,
        identity.attestation_physical_sha256,
    )
    print(json.dumps({
        "attestation_id": identity.attestation_id,
        "package_id": identity.package_id,
        "manifest_sha256": identity.manifest_sha256,
        "completion_marker_sha256": identity.completion_sha256,
        "attestation_canonical_sha256": identity.attestation_sha256,
        "attestation_physical_sha256": identity.attestation_physical_sha256,
        "generation_commit_equivalence": document["provenance"][
            "generation_commit_equivalence"
        ],
        "verified_compatible": document["provenance"]["verified_compatible"],
    }, indent=2, sort_keys=True))


def cmd_register(args: argparse.Namespace) -> None:
    record, identity = register_attested_package(
        Path(args.attestations_root),
        Path(args.discovery_root),
        attestation_id=args.attestation_id,
    )
    logger.info(
        "Discovery record %s registered (canonical=%s physical=%s)",
        identity.attestation_id,
        identity.discovery_sha256,
        identity.discovery_physical_sha256,
    )
    print(json.dumps({
        "discovery_id": identity.attestation_id,
        "package_id": identity.package_id,
        "discovery_canonical_sha256": identity.discovery_sha256,
        "discovery_physical_sha256": identity.discovery_physical_sha256,
        "verification_status": record["discovery"]["verification_status"],
        "missing_components": record["dataset_readiness"]["missing_components"],
    }, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    logging.Formatter.converter = time.gmtime

    parser = argparse.ArgumentParser(
        description="Phase 8C provenance attestation and discovery control."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    attest = subparsers.add_parser(
        "attest", help="verify the package and publish its attestation"
    )
    attest.add_argument("--derived-root", required=True, type=Path,
                        help="Existing derived-candle package directory")
    attest.add_argument("--attestations-root", required=True, type=Path,
                        help="External non-overwriting attestation area")
    attest.add_argument("--implementation-commit", default=None,
                        help="Implementation commit SHA (default: git HEAD)")
    attest.add_argument("--verification-commit", default=None,
                        help="Verification commit SHA (default: git HEAD)")
    attest.add_argument("--worktree-root", default=".", type=Path,
                        help="Git worktree used to read committed verifier content")

    register = subparsers.add_parser(
        "register", help="register an attested package for discovery"
    )
    register.add_argument("--attestations-root", required=True, type=Path)
    register.add_argument("--discovery-root", required=True, type=Path,
                          help="External non-overwriting discovery area")
    register.add_argument("--attestation-id", default=None,
                          help="Exact attestation id (default: the only one)")

    args = parser.parse_args(argv)
    try:
        if args.command == "attest":
            cmd_attest(args)
        elif args.command == "register":
            cmd_register(args)
    except AcquisitionError as exc:
        logger.error("Provenance control failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
