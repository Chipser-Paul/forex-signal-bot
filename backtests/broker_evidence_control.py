"""Phase 8G broker-conditions evidence intake CLI (offline, fail-closed).

Subcommands (all offline; no MT5, no network, no trading surface):

- ``ingest``    classify the sanitized support transcript + MT5 screenshots,
                publish the immutable broker-evidence package (idempotent),
                and register it via the existing Phase 8E evidence store.
- ``verify``    hash-verify the published package end to end (readback,
                canonical hashes, claim classifications, unit arithmetic,
                stress-template inactivity).

Owner evidence root (read-only):
    <data-root>/evidence/owner-input/broker-metadata/
Published package (external, never committed):
    <data-root>/evidence/evidence-broker_support-v1-<hash16>

All artifacts remain DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY
EVIDENCE. Raw owner files are never modified, copied into Git, or printed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bot.acquisition import broker_evidence as be  # noqa: E402
from bot.acquisition import broker_email_evidence as bee  # noqa: E402
from bot.acquisition.evidence_store import (  # noqa: E402
    EvidenceStoreError,
    load_evidence_package,
    publish_evidence_package,
)

DEFAULT_DATA_ROOT = Path(r"C:\Users\chips\forex-signal-bot-data\phase8")
OWNER_BROKER_DIR = Path("evidence/owner-input/broker-metadata")

# Values OCR-extracted from the sanitized screenshots at ingestion time.
# Only clearly readable values are recorded; everything else is listed in
# not_readable. Screenshot 01 (top block) and screenshot 02 (trade block).
SCREENSHOT_OBSERVATIONS: dict[str, tuple[dict[str, str], tuple[str, ...], str]] = {
    "Exness_Standard_XAUUSDm_Specification_2026-09-13_01.png": (
        {
            "symbol_display": "XAUUSDm, XAU/USD, Gold vs US Dollar",
            "category": "Metals",
            "digits": "3",
            "contract_size": "100 (XAU)",
            "spread": "floating",
            "stops_level": "0",
            "margin_currency": "XAU",
            "profit_currency": "USD",
            "calculation": "Forex",
            "chart_mode": "By bid price",
        },
        ("trade_access",),
        "WinRT OCR at 3x and 6x upscale (PIL LANCZOS + sharpen + autocontrast); "
        "label/value rows resolved from the top specification block.",
    ),
    "Exness_Standard_XAUUSDm_Specification_2026-09-13_02.png": (
        {
            "trade_access": "Full access",
            "execution": "Market",
            "gtc_mode": "Good till cancelled",
            "filling": "Fill or Kill, Immediate or Cancel",
            "expiration": "All",
            "orders": "All",
            "volume_min": "0.01",
            "volume_max": "200",
            "volume_step": "0.01",
            "swap_type": "In points",
            "swap_long": "-534.9",
            "swap_weekday_multipliers": "Mon 1, Tue 1, Wed 3, Thu 1, Fri 1",
            "margin_initial_display": "1.0000000",
            "margin_maintenance_display": "1.0000000",
        },
        ("swap_short", "margin_display_context"),
        "WinRT OCR at 3x, 5x and 8x upscale; the swap-short value cell and "
        "the margin-rate display context could not be resolved and are "
        "recorded as not readable rather than guessed.",
    ),
}

# Margin conflict: current platform display vs support-asserted fixed margin.
MARGIN_CONFLICTS: tuple[dict[str, str], ...] = (
    {
        "conflict_id": "margin.fixed_1_200_vs_display_1_0000000",
        "support_statement": "Fixed margin requirement: 1:200 (0.5%)",
        "current_display": "Initial/Maintenance margin rates shown as 1.0000000",
        "classification": "REJECTED_CONFLICTING",
        "resolution": (
            "unresolved by design: the display is CURRENT_ONLY_NOT_HISTORICAL "
            "and the support statement lacks a demonstrated 2024 effective "
            "date; neither value is adopted as historical fact"
        ),
    },
)


def _owner_dir(args: argparse.Namespace) -> Path:
    return Path(args.data_root) / OWNER_BROKER_DIR


def _resolve_screenshots(owner_dir: Path) -> list[Path]:
    found: list[Path] = []
    if not owner_dir.is_dir():
        raise EvidenceStoreError(f"owner evidence directory missing: {owner_dir}")
    for name in sorted(SCREENSHOT_OBSERVATIONS):
        candidate = owner_dir / name
        if candidate.is_file() and not candidate.is_symlink():
            found.append(candidate)
    if not found:
        raise EvidenceStoreError(
            "no sanitized MT5 specification screenshots found in " + str(owner_dir)
        )
    return found


def _observed_spread_identity(data_root: Path) -> tuple[str, str]:
    """Locate the accepted observed-spread package by kind, not by path."""

    evidence_root = data_root / "evidence"
    matches: list[tuple[str, str]] = []
    if evidence_root.is_dir():
        for child in sorted(evidence_root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            manifest_path = child / "manifest.json"
            if not manifest_path.is_file():
                continue
            package = load_evidence_package(child)
            if str(package["manifest"].get("kind")) != "observed_spread":
                continue
            status = str(package["content"].get("status"))
            if status not in {"ACCEPTED_EMPIRICAL", "ACCEPTED_DEVELOPMENT_ONLY"}:
                continue
            matches.append(
                (
                    str(package["manifest"]["package_id"]),
                    str(package["manifest"]["content_canonical_sha256"]),
                )
            )
    if not matches:
        raise EvidenceStoreError(
            "no accepted observed-spread evidence package is published; "
            "run evidence_intake_control.py register-spread first"
        )
    if len(matches) > 1:
        raise EvidenceStoreError(
            "ambiguous observed-spread evidence: multiple accepted packages published"
        )
    return matches[0]


def _ingest_email(support_dir: Path) -> tuple[be.EvidenceFile, list[be.BrokerClaim], dict[str, Any], dict[str, Any] | None]:
    """Ingest the official support email (+ optional PDF) if present.

    Returns (email_file, claims, parsed_record, pdf_path). Absent email is a
    no-op; a present-but-invalid email fails closed inside the parsers.
    """

    try:
        eml_path = bee.discover_email_file(support_dir)
    except be.EvidenceError:
        return None, [], {}, None  # type: ignore[return-value]
    pdf_path = bee.discover_pdf_file(support_dir)
    email_file, parsed = bee.parse_email_evidence(eml_path, pdf_path)
    email_claims = bee.classify_email_claims(parsed, email_file)
    return email_file, email_claims, parsed, pdf_path


def cmd_ingest(args: argparse.Namespace) -> int:
    data_root = Path(args.data_root)
    owner_dir = _owner_dir(args)
    transcript_path = be.discover_transcript_file(owner_dir)
    transcript_file, claims = be.load_transcript_claims(transcript_path)
    email_file, email_claims, email_parsed, pdf_path = _ingest_email(owner_dir / "Support")
    screenshots: list[dict[str, Any]] = []
    screenshot_files: list[be.EvidenceFile] = []
    for path in _resolve_screenshots(owner_dir):
        file = be.stat_evidence_file(path, "mt5_screenshot")
        observed, not_readable, ocr_note = SCREENSHOT_OBSERVATIONS[path.name]
        screenshots.append(
            be.build_screenshot_record(
                file=file,
                ocr_note=ocr_note,
                observed=observed,
                not_readable=not_readable,
            )
        )
        screenshot_files.append(file)
    spread_package_id, spread_canonical = _observed_spread_identity(data_root)
    swap_unit_conflict = None
    email_stress_template = None
    if email_file is not None:
        # The email's current swap reference conflicts with the screenshot's
        # points display. Record it verbatim; never reconcile/convert/select.
        values = bee.email_swap_values_from_claims(
            {c.claim_id: c.statement for c in email_claims}
        )
        # The conflict binds the screenshot that actually displays the swap
        # values (screenshot 02), not merely the first screenshot.
        if "swap_long" not in screenshots[0]["observed_values"] and not any(
            "swap_long" in rec["observed_values"] for rec in screenshots
        ):
            raise EvidenceStoreError(
                "no screenshot observation carries the swap-long display value; "
                "cannot record the swap-unit conflict"
            )
        screenshot_record = next(
            rec for rec in screenshots if "swap_long" in rec["observed_values"]
        )
        screenshot_file_index = screenshots.index(screenshot_record)
        screenshot_short = screenshot_record["observed_values"].get("swap_short")
        conflict = bee.build_swap_unit_conflict_record(
            screenshot_file=screenshot_files[screenshot_file_index],
            screenshot_swap_long_points=str(screenshot_record["observed_values"]["swap_long"]),
            screenshot_swap_short=screenshot_short,
            screenshot_swap_short_readability=(
                "clearly readable" if screenshot_short is not None else "NOT_CLEARLY_READABLE_TRUNCATED"
            ),
            email_file=email_file,
            email_swap_long_usd=values[0],
            email_swap_short_usd=values[1],
            email_sent_utc=str(email_parsed["record"]["sent_utc"]),
        )
        swap_unit_conflict = bee.finalize_conflict_record(conflict)
        email_stress_template = be.build_email_stress_template(
            email_swap_long_usd=values[0],
            unit_normalization=be.verify_unit_normalization(),
        )
    # Deterministic content: wall-clock never enters the hashed evidence
    # fields, so repeated ingestion of unchanged evidence is idempotent.
    content = be.build_broker_evidence_package(
        transcript_file=transcript_file,
        claims=claims,
        screenshots=screenshots,
        observed_spread_package_id=spread_package_id,
        observed_spread_canonical_sha256=spread_canonical,
        margin_conflicts=MARGIN_CONFLICTS,
        email_file=email_file,
        email_claims=email_claims,
        email_record=email_parsed["record"] if email_file is not None else None,
        swap_unit_conflict=swap_unit_conflict,
        email_stress_template=email_stress_template,
    )
    # Ingestion provenance lives OUTSIDE the hashed content: the content is
    # fully deterministic (hash-identical across runs), while the wall-clock
    # ingestion record is carried as envelope provenance.
    ingestion_record = {
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": "backtests/broker_evidence_control.py ingest",
        "sensitive_scan": "fail-closed scan passed (no credentials/PINs/account numbers/emails)",
        "transcript_sha256": transcript_file.sha256,
        "screenshot_sha256s": {f.path.name: f.sha256 for f in screenshot_files},
        **(
            {
                "support_email_sha256": email_file.sha256,
                "support_email_pdf_sha256": (
                    pdf_path and __import__("hashlib").sha256(pdf_path.read_bytes()).hexdigest()
                ),
            }
            if email_file is not None
            else {}
        ),
    }
    envelope = be.build_broker_evidence_envelope(content)
    envelope["ingestion"] = ingestion_record
    target, package_id = publish_evidence_package(envelope, evidence_root=data_root / "evidence")
    print(f"published broker-support evidence package {package_id} at {target}")
    print(f"status: {content['status']}")
    print(f"claims: {len(content['claims'])}")
    print(f"commission mode: {content['commission_none']['mode']}")
    print(f"swap status: {content['swap_rollover']['status']}")
    if "swap_unit_conflict" in content:
        print(
            "swap-unit conflict: "
            f"{content['swap_unit_conflict']['conflict_id']} (equivalence_established="
            f"{content['swap_unit_conflict']['equivalence_established']})"
        )
    print(f"stress template: {content['swap_stress_policy_proposal']['status']}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    data_root = Path(args.data_root)
    evidence_root = data_root / "evidence"
    prefix = "evidence-broker_support-v1-"
    matches = sorted(child for child in evidence_root.glob(prefix + "*") if child.is_dir())
    if not matches:
        print("FAIL: no published broker-support package found", file=sys.stderr)
        return 1
    failures = 0
    for package_dir in matches:
        try:
            package = load_evidence_package(package_dir)
            content = package["content"]
            # Re-derive the canonical content hash from the deterministic
            # fields (ingestion provenance lives outside content).
            from bot.acquisition.evidence_contracts import canonical_hash

            recomputed = canonical_hash(
                {k: v for k, v in content.items() if k not in {"record_canonical_sha256"}}
            )
            if recomputed != str(content["record_canonical_sha256"]):
                raise EvidenceStoreError("content canonical hash mismatch on readback")
            ingestion = package.get("ingestion")
            if not isinstance(ingestion, Mapping) or "ingested_at_utc" not in ingestion:
                raise EvidenceStoreError("package lacks the ingestion provenance record")
            stress = content["swap_stress_policy_proposal"]
            if "swap_unit_conflict" in content:
                conflict = content["swap_unit_conflict"]
                if conflict.get("equivalence_established") is not False:
                    raise EvidenceStoreError("swap-unit conflict must stay unresolved")
                if stress.get("status") != "PROPOSED_INACTIVE_CONFLICT_GATED":
                    raise EvidenceStoreError(
                        "email stress template must remain conflict-gated inactive"
                    )
                gate_key = stress.get("conflict_gate")
                if gate_key != conflict.get("conflict_id"):
                    raise EvidenceStoreError("stress template gate must bind the conflict id")
            units = be.verify_unit_normalization()
            if stress["active"] is not False:
                raise EvidenceStoreError("stress template must remain inactive")
            if "swap_unit_conflict" in content:
                for scenario in stress["scenarios"]:
                    if scenario["swap_long_usd_per_lot_per_day"] > 0 or scenario["swap_short_usd_per_lot_per_day"] > 0:
                        raise EvidenceStoreError("stress scenario applies a favorable swap credit")
            else:
                for scenario in stress["scenarios"]:
                    if scenario["swap_long_usd_per_lot"] > 0 or scenario["swap_short_usd_per_lot"] > 0:
                        raise EvidenceStoreError("stress scenario applies a favorable swap credit")
            screenshots = content.get("screenshot_observations", [])
            swap = content["swap_rollover"]
            if swap["status"] != "HISTORICAL_VALUE_UNAVAILABLE":
                raise EvidenceStoreError("swap record must remain HISTORICAL_VALUE_UNAVAILABLE")
            print(
                f"verified {package_dir.name}: claims={len(content['claims'])} "
                f"screenshots={len(screenshots)} unit_pip={units['checks'][0]['one_pip_in_points']} "
                f"stress={stress['status']}"
            )
        except (EvidenceStoreError, be.EvidenceError) as exc:
            failures += 1
            print(f"TAMPER/FAIL: {package_dir.name}: {exc}", file=sys.stderr)
    print(f"verified {len(matches)} broker-support packages, {failures} failures")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 8G broker evidence intake")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="classify + publish broker evidence (idempotent)")
    ingest.set_defaults(func=cmd_ingest)
    verify = sub.add_parser("verify", help="readback-verify published broker evidence")
    verify.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
