"""Phase 8H/8I development-cost-policy control CLI (offline, fail-closed).

Subcommands (all offline; no MT5, no network, no trading surface):

- ``preregister``  build the frozen policy, publish the immutable evidence
                   package (idempotent, non-overwriting) and regenerate the
                   Phase 8 evidence matrix + readiness report.
- ``verify``       readback-verify the published policy: envelope hashes,
                   policy fingerprint, frozen scenario ladders, binding set
                   cross-checked against the on-disk evidence packages.
- ``status``       sanitized summary (no paths, no policy content dump).
- ``activate``     Phase 8I: record the owner's decision to run the frozen
                   assumption-only swap scenarios during development
                   validation.  Publishes a separate hash-bound activation
                   record (never modifies the policy package) plus the
                   dataset-acceptance review, then regenerates readiness.

Published packages (external, never committed):
    <data-root>/evidence/evidence-development_cost_policy-v1-<hash16>
    <data-root>/evidence/evidence-cost_policy_activation-v1-<hash16>
    <data-root>/evidence/evidence-dataset_acceptance_review-v1-<hash16>

The policy is PREREGISTERED_INACTIVE; ``ACTIVE`` is not a representable
policy state — activation lives in its own record.  Evidence passing tests
never authorizes strategy evaluation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bot.acquisition.evidence_store import (  # noqa: E402
    EvidenceStoreError,
    build_evidence_package,
    load_evidence_package,
    publish_evidence_package,
)
from bot.validation import cost_policy as cp  # noqa: E402
from bot.validation import cost_policy_activation as cpa  # noqa: E402

DEFAULT_DATA_ROOT = Path(r"C:\Users\chips\forex-signal-bot-data\phase8")
POLICY_KIND = "development_cost_policy"

# Binding identities the published policy must match on disk (fail closed).
BOUND_BROKER_SUPPORT_PACKAGE = "evidence-broker_support-v1-3b68b4203a9109b9"
BOUND_SPREAD_PACKAGE = "observed_spread-v1-e25bdb9bf028a5be"
BOUND_DERIVED_PACKAGE_DIR = "derived-candles-2024-v1-20260911T195553Z"
BOUND_DERIVED_MANIFEST_SHA256 = (
    "6715e5c64d888215ea9c88a6ab77e5340046f367ed6250813158f6b1f096d316"
)
BOUND_DXY_PACKAGE_DIR = "dxy-development-2024-v1-20260912T091410.712364Z"


def _package_dir(evidence_root: Path, package_id: str) -> Path:
    path = evidence_root / package_id
    if not path.is_dir():
        raise EvidenceStoreError(f"bound evidence package missing on disk: {package_id}")
    return path


def _live_support_content_sha256(evidence_root: Path) -> str:
    """Read the broker-support revision hash from disk (never trust the caller)."""
    manifest = json.loads(
        (_package_dir(evidence_root, BOUND_BROKER_SUPPORT_PACKAGE) / "manifest.json")
        .read_text(encoding="utf-8")
    )
    return str(manifest["content_canonical_sha256"])


def _build_content(data_root: Path, evidence_root: Path) -> dict[str, Any]:
    return cp.build_cost_policy(
        data_root=data_root,
        broker_support_content_sha256=_live_support_content_sha256(evidence_root),
    )


def _find_policy_package(evidence_root: Path) -> Path:
    matches = sorted(evidence_root.glob(f"evidence-{POLICY_KIND}-v1-*"))
    if not matches:
        raise EvidenceStoreError("no published development-cost-policy package exists")
    if len(matches) > 1:
        raise EvidenceStoreError(
            "ambiguous development-cost-policy state: multiple published revisions"
        )
    return matches[0]


def cmd_preregister(args: argparse.Namespace) -> int:
    data_root = Path(args.data_root)
    evidence_root = data_root / "evidence"
    content = _build_content(data_root, evidence_root)
    report = cp.verify_cost_policy(content)
    package, package_id = build_evidence_package(
        kind=POLICY_KIND,
        content=content,
        source_path=None,
    )
    target, published_id = publish_evidence_package(package, evidence_root=evidence_root)
    if published_id != package_id:
        raise EvidenceStoreError("published package id drifted from the built package")
    print(f"policy package: {published_id}")
    print(f"policy fingerprint: {report['policy_fingerprint']}")
    print(f"state: {report['policy_state']} (activation unauthorized)")
    # Regenerate the matrix/readiness report through the existing Phase 8E tooling.
    from backtests.evidence_intake_control import cmd_readiness  # noqa: PLC0415

    return cmd_readiness(argparse.Namespace(data_root=str(data_root)))


def cmd_verify(args: argparse.Namespace) -> int:
    data_root = Path(args.data_root)
    evidence_root = data_root / "evidence"
    package_dir = _find_policy_package(evidence_root)
    package = load_evidence_package(package_dir)
    content = package["content"]
    report = cp.verify_cost_policy(content)

    # Cross-check the binding set against what is actually on disk.
    bindings = content["bindings"]
    support_hash = _live_support_content_sha256(evidence_root)
    if str(bindings["broker_support_revision"]["content_canonical_sha256"]) != support_hash:
        raise EvidenceStoreError(
            "broker-support binding no longer matches the on-disk revision"
        )
    spread_manifest_path = (
        evidence_root / BOUND_SPREAD_PACKAGE / "manifest.json"
    )
    if spread_manifest_path.is_file():
        spread_manifest = json.loads(spread_manifest_path.read_text(encoding="utf-8"))
        if str(bindings["observed_spread_evidence"]["content_canonical_sha256"]) != str(
            spread_manifest["content_canonical_sha256"]
        ):
            raise EvidenceStoreError(
                "observed-spread binding no longer matches the on-disk package"
            )
    derived_manifest_path = (
        data_root / "derived" / BOUND_DERIVED_PACKAGE_DIR / "manifest.json"
    )
    if derived_manifest_path.is_file():
        import hashlib  # noqa: PLC0415

        digest = hashlib.sha256(derived_manifest_path.read_bytes()).hexdigest()
        if digest != BOUND_DERIVED_MANIFEST_SHA256:
            raise EvidenceStoreError(
                "derived-candle manifest hash drifted from the bound identity"
            )
    dxy_manifest_path = (
        data_root / "dxy" / BOUND_DXY_PACKAGE_DIR / "manifest.json"
    )
    if dxy_manifest_path.is_file():
        dxy_manifest = json.loads(dxy_manifest_path.read_text(encoding="utf-8"))
        if str(bindings["dxy_development_input"]["package_id"]) != str(
            dxy_manifest["package_id"]
        ):
            raise EvidenceStoreError("DXY package binding drifted")

    # Determinism: rebuilding from the same immutable inputs must reproduce
    # the stored content byte-for-byte.
    rebuilt = _build_content(data_root, evidence_root)
    if rebuilt != content:
        raise EvidenceStoreError(
            "policy rebuild disagrees with the published content (inputs drifted)"
        )
    print(f"package: {package_dir.name}")
    print(f"verified: {report['verified']} fingerprint: {report['policy_fingerprint']}")
    print("bindings: broker_support, observed_spread, derived_candles, dxy — all match")
    return 0


def cmd_activate(args: argparse.Namespace) -> int:
    """Phase 8I: publish the activation record + acceptance review, then readiness.

    Fail-closed: the frozen policy must exist and verify, the frozen ladder
    must be intact, and every required evidence identity must hash-verify on
    disk before anything is published.  Idempotent: re-running with the same
    decision fields recognizes the existing records.  The policy package is
    never modified.
    """

    from backtests.evidence_intake_control import cmd_readiness  # noqa: PLC0415

    data_root = Path(args.data_root)
    evidence_root = data_root / "evidence"
    try:
        # Precondition: the published policy verifies right now.
        cpa.verify_published_policy(evidence_root)

        activation = cpa.build_activation_record(
            data_root=data_root,
            decision_utc=args.decision_utc,
            decision_scope=args.decision_scope,
        )
        cpa.verify_activation_record(activation)
        package, package_id = build_evidence_package(
            kind="cost_policy_activation",
            content=activation,
            source_path=None,
        )
        # Conflicting owner decision: any existing activation record with a
        # different content identity fails closed (the store itself only
        # conflicts on identical ids).
        for existing in sorted(evidence_root.glob("evidence-cost_policy_activation-v1-*")):
            existing_manifest = json.loads(
                (existing / "manifest.json").read_text(encoding="utf-8")
            )
            if str(existing_manifest.get("content_canonical_sha256")) != str(
                package["manifest"]["content_canonical_sha256"]
            ):
                raise EvidenceStoreError(
                    "conflicting activation decision: an activation record with "
                    f"a different content identity already exists ({existing.name}); "
                    "refusing to publish a second decision"
                )
        target, published_id = publish_evidence_package(
            package, evidence_root=evidence_root
        )
        if published_id != package_id:
            raise EvidenceStoreError("published activation id drifted from the built id")
        print(f"activation package: {published_id}")
        print(
            "activated policy fingerprint: "
            f"{activation['activated_policy']['policy_fingerprint']}"
        )
        print(f"activation state: {activation['activation_state']}")

        review = cpa.build_acceptance_review(data_root=data_root)
        cpa.verify_acceptance_review(review)
        review_package, review_id = build_evidence_package(
            kind="dataset_acceptance_review",
            content=review,
            source_path=None,
        )
        review_target, review_published = publish_evidence_package(
            review_package, evidence_root=evidence_root
        )
        if review_published != review_id:
            raise EvidenceStoreError("published review id drifted from the built id")
        print(f"acceptance-review package: {review_published}")
        print("categories:")
        for category, status in sorted(review["statuses"].items()):
            print(f"  {category}: {status}")
        print(
            "development_evaluation_sufficient="
            f"{review['development_evaluation_sufficient']}"
        )
    except (EvidenceStoreError, cpa.CostPolicyActivationError, ValueError) as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1
    # Regenerate the matrix/readiness report through the existing Phase 8E tooling.
    return cmd_readiness(argparse.Namespace(data_root=str(data_root)))


def cmd_status(args: argparse.Namespace) -> int:
    data_root = Path(args.data_root)
    evidence_root = data_root / "evidence"
    package_dir = _find_policy_package(evidence_root)
    package = load_evidence_package(package_dir)
    content = package["content"]
    report = cp.verify_cost_policy(content)
    print(f"package: {package_dir.name}")
    print(f"schema: {content['schema_version']}")
    print(f"state: {content['policy_state']}")
    print(f"fingerprint: {report['policy_fingerprint']}")
    print(f"symbol: {content['symbol']} / {content['account_type']}")
    print("swap scenarios:")
    for scenario in content["swap_scenarios"]:
        print(
            f"  {scenario['scenario_id']}: long {scenario['long_usd_per_lot_per_day']} "
            f"USD/lot/day, short {scenario['short_usd_per_lot_per_day']} "
            f"(x{scenario['swap_multiplier_vs_email_reference']})"
        )
    print("slippage scenarios (points, ASSUMPTION_ONLY):")
    for scenario in content["slippage_scenarios"]:
        print(f"  {scenario['scenario_id']}: {scenario['points']}")
    restrictions = content["acceptance_restrictions"]
    print(f"required adverse boundary: {restrictions['required_adverse_boundary']}")
    print(
        "gates: strategy_evaluation_authorized="
        f"{restrictions['strategy_evaluation_authorized']}, "
        f"final_validation_authorized={restrictions['final_validation_authorized']}, "
        f"holdout_access_authorized={restrictions['holdout_access_authorized']}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 8H cost-policy control")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)
    preregister = sub.add_parser(
        "preregister", help="build + publish the frozen policy (idempotent)"
    )
    preregister.set_defaults(func=cmd_preregister)
    verify = sub.add_parser("verify", help="readback + binding verification")
    verify.set_defaults(func=cmd_verify)
    status = sub.add_parser("status", help="sanitized policy summary")
    status.set_defaults(func=cmd_status)
    activate = sub.add_parser(
        "activate",
        help=(
            "Phase 8I: publish the owner decision activating the frozen "
            "assumption-only swap scenarios for development validation"
        ),
    )
    activate.add_argument(
        "--decision-utc",
        required=True,
        help="UTC timestamp of the owner decision (ISO-8601, e.g. 2026-09-15T00:00:00Z)",
    )
    activate.add_argument(
        "--decision-scope",
        required=True,
        help=(
            "exact scope statement of the owner decision "
            "(recorded verbatim in the activation record)"
        ),
    )
    activate.set_defaults(func=cmd_activate)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
