"""Phase 8G extension: Exness support-email evidence and the swap-unit conflict.

Parses the owner-supplied official support email (``.eml``) offline and
classifies its statements claim-by-claim:

- commission statements become ``BROKER_SUPPORT_ASSERTED`` (development-usable
  under the exact evidence contract, no historical effective dates claimed);
- the email's swap values are ``CURRENT_SUPPORT_REFERENCE`` — a current
  support statement, explicitly NOT historical 2024 evidence;
- the broker's inability to provide dated 2024 swap history is
  ``HISTORICAL_VALUE_UNAVAILABLE``;
- the triple-Wednesday rule is ``BROKER_SUPPORT_ASSERTED``.

The email conflicts with the MT5 screenshot swap display (points vs USD per
lot). The conflict is recorded verbatim — source units, observation dates,
source hashes, calculation modes, possible explanations, and the
non-establishable equivalence — and is never silently reconciled, converted,
averaged, or resolved. The proposed swap stress policy remains inactive and
becomes conflict-gated until a separate review decides the basis.

Sensitive handling: the raw ``.eml`` is never copied anywhere. Derived text
is deterministically redacted (email addresses, the owner greeting name, the
support thread id) before any strict sensitive scan and before any claim
carries a quote. Only statements actually present in the email are accepted;
expected-but-absent statements (e.g. contract size is NOT restated in the
email) are recorded as scope notes, never fabricated as claims.
"""

from __future__ import annotations

import email
import re
from datetime import datetime, timezone
from email import policy
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Mapping

from .broker_evidence import (
    CLASS_BROKER_SUPPORT_ASSERTED,
    CLASS_CURRENT_ONLY_NOT_HISTORICAL,
    CLASS_CURRENT_SUPPORT_REFERENCE,
    CLASS_HISTORICAL_VALUE_UNAVAILABLE,
    CLASS_REJECTED_CONFLICTING,
    BrokerClaim,
    EvidenceError,
    EvidenceFile,
    _claim,
    _require_quote,
    scan_for_sensitive_content,
    sha256_file,
    stat_evidence_file,
)
from .evidence_contracts import canonical_hash

EMAIL_SUPPORT_SCHEMA_VERSION = "phase8g.broker-support-email.v1"
SWAP_UNIT_CONFLICT_SCHEMA_VERSION = "phase8g.swap-unit-conflict.v1"

CLASS_CURRENT_SUPPORT_REFERENCE = "CURRENT_SUPPORT_REFERENCE"

EMAIL_ACQUISITION_MODE = "MANUAL_EMAIL_EXPORT"
EMAIL_SOURCE_ROLE = "support_email"
PDF_SOURCE_ROLE = "support_email_pdf_attachment"

EMAIL_SUBJECT_EXPECTED = "Exness - Trading Inquiries"

# Completeness markers: the email must be the full conditions reply, not a
# fragment. Checked against the redacted body.
_EMAIL_COMPLETENESS_MARKERS = (
    "How Standard Accounts work",
    "Swap (rollover) on XAUUSDm",
    "On historical values and change dates",
    "Best regards,",
)

# Owner greeting + reply-chain identifiers are personal information: they are
# redacted from every derived payload (raw file untouched).
_OWNER_GREETING_RE = re.compile(r"Dear [A-Z][a-z]+,")
_EMAIL_ADDRESS_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_THREAD_ID_RE = re.compile(r"thread::[A-Za-z0-9._:\-]+")

# Strict scan applied to the *redacted* body: credential/account categories
# must be absent (the expected email-address category is already redacted).
_EMAIL_STRICT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("support_pin", re.compile(r"\b(?:support\s*)?pin\s*[:#]?\s*\d{4,8}\b", re.IGNORECASE)),
    ("password", re.compile(r"\bpassword\b\s*[:=]\s*\S+", re.IGNORECASE)),
    ("token", re.compile(r"\b(?:api[_-]?key|token|bearer)\b\s*[:=]\s*\S+", re.IGNORECASE)),
    ("account_number", re.compile(r"(?<![\w/\-])\d{8,}(?![\w\-])")),
    ("long_hex_secret", re.compile(r"\b[0-9a-fA-F]{40,}\b")),
)

# Email claims (stable IDs). Only claims whose needle exists in the email are
# created; the classifier fails closed if an expected needle is absent.
EMAIL_CLAIM_NEEDLES: tuple[tuple[str, str, str, str], ...] = (
    (
        "email.standard_no_trading_commission",
        "Standard accounts carry no trading commissions",
        CLASS_BROKER_SUPPORT_ASSERTED,
        "no trading commissions",
    ),
    (
        "email.xauusdm_commission_zero",
        "Standard XAUUSDm commission is zero; the Standard account is commission-free",
        CLASS_BROKER_SUPPORT_ASSERTED,
        "Yes, commission is zero. The Standard account is commission-free",
    ),
    (
        "email.costs_built_into_spread",
        "Trading costs are incorporated into the variable spread rather than charged per lot",
        CLASS_BROKER_SUPPORT_ASSERTED,
        "trading costs are built into the spread rather than charged per lot",
    ),
    (
        "email.market_execution",
        "Orders are executed on market execution (no requotes)",
        CLASS_BROKER_SUPPORT_ASSERTED,
        "Orders executed on market execution",
    ),
    (
        "email.swap_long_usd_per_lot",
        "Current stated swap long is -3.85 USD per 1.00 lot per day",
        CLASS_CURRENT_SUPPORT_REFERENCE,
        "-3.85 USD per lot per day",
    ),
    (
        "email.swap_short_usd_per_lot",
        "Current stated swap short is -0.25 USD per 1.00 lot per day",
        CLASS_CURRENT_SUPPORT_REFERENCE,
        "-0.25 USD per lot per day",
    ),
    (
        "email.triple_swap_wednesday",
        "Weekly triple-swap applies on the third rollover day (Wednesday), three times the daily value",
        CLASS_BROKER_SUPPORT_ASSERTED,
        "triple-swap applies on the third rollover day (Wednesday)",
    ),
    (
        "email.historical_swaps_unavailable",
        "Exness cannot provide a dated record of the swap throughout 2024 or the dates it changed",
        CLASS_HISTORICAL_VALUE_UNAVAILABLE,
        "cannot provide a dated record of what the swap was throughout 2024",
    ),
    (
        "email.statements_show_only_existing_trades",
        "Account statements record the actual swap charged each day, which may help only for trades that existed",
        CLASS_BROKER_SUPPORT_ASSERTED,
        "record the actual swap charged each day",
    ),
)


def _redact_personal(text: str) -> str:
    text = _EMAIL_ADDRESS_RE.sub("[EMAIL_REDACTED]", text)
    text = _OWNER_GREETING_RE.sub("Dear [OWNER],", text)
    text = _THREAD_ID_RE.sub("[THREAD_ID]", text)
    return text


def discover_pdf_file(support_dir: Path, base_name: str = "Exness_XAUUSDm_Standard_Conditions_2026-09-14") -> Path | None:
    """Resolve the optional PDF rendition; absent is honest, ambiguous fails."""

    support_dir = Path(support_dir)
    matches: list[Path] = []
    for pattern in (f"{base_name}.pdf",):
        if support_dir.is_dir():
            matches.extend(child for child in support_dir.rglob(pattern) if child.is_file())
    unique = {child.resolve(): child for child in matches}
    if not unique:
        return None
    if len(unique) > 1:
        raise EvidenceError(
            "ambiguous support email PDF files discovered: "
            + ", ".join(sorted(str(p) for p in unique))
        )
    return next(iter(unique))


def discover_email_file(
    support_dir: Path, base_name: str = "Exness_XAUUSDm_Standard_Conditions_2026-09-14"
) -> Path:
    """Resolve the .eml anywhere directly under the support tree (incl. Private)."""

    support_dir = Path(support_dir)
    if not support_dir.is_dir():
        raise EvidenceError(f"support directory missing: {support_dir}")
    matches: list[Path] = []
    for pattern in (f"{base_name}.eml", base_name):
        matches.extend(child for child in support_dir.rglob(pattern) if child.is_file())
    unique = {child.resolve(): child for child in matches}
    if not unique:
        raise EvidenceError(
            f"support email not found under {support_dir} (base name {base_name!r})"
        )
    if len(unique) > 1:
        raise EvidenceError(
            "ambiguous support email files discovered: "
            + ", ".join(sorted(str(p) for p in unique))
        )
    return next(iter(unique))


def parse_email_evidence(eml_path: Path, pdf_path: Path | None = None) -> tuple[EvidenceFile, dict[str, Any]]:
    """Parse the .eml read-only into a hash-bound, redacted evidence record."""

    file = stat_evidence_file(eml_path, EMAIL_SOURCE_ROLE)
    pdf_attachment: dict[str, Any] | None = None
    if pdf_path is not None:
        pdf_file = stat_evidence_file(pdf_path, PDF_SOURCE_ROLE)
        pdf_head = pdf_path.read_bytes()[:5]
        if pdf_head != b"%PDF-":
            raise EvidenceError("declared PDF attachment is not a PDF document")
        pdf_attachment = {
            "source_role": PDF_SOURCE_ROLE,
            "file_name": pdf_file.path.name,
            "size_bytes": pdf_file.size_bytes,
            "sha256": pdf_file.sha256,
            "rendition_note": (
                "PDF rendition bound by hash for provenance; the .eml remains "
                "the primary parsed source"
            ),
        }
    raw_bytes = eml_path.read_bytes()
    msg = email.message_from_bytes(raw_bytes, policy=policy.default)
    subject = str(msg.get("Subject", "")).strip()
    if subject != EMAIL_SUBJECT_EXPECTED:
        raise EvidenceError(
            f"unexpected email subject {subject!r}; expected {EMAIL_SUBJECT_EXPECTED!r}"
        )
    date_header = str(msg.get("Date", "")).strip()
    if not date_header:
        raise EvidenceError("email lacks a Date header; fails closed")
    sent_dt = parsedate_to_datetime(date_header)
    if sent_dt.tzinfo is None:
        raise EvidenceError("email Date header is naive; fails closed")
    sent_utc = sent_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    body_plain: str | None = None
    body_html: str | None = None
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == "text/plain" and body_plain is None:
            body_plain = part.get_content()
        elif ctype == "text/html" and body_html is None:
            body_html = part.get_content()
    body_source = body_plain if body_plain is not None else body_html
    if not body_source:
        raise EvidenceError("email has no parsable text body")
    body = _redact_personal(body_source)
    for marker in _EMAIL_COMPLETENESS_MARKERS:
        if marker not in body:
            raise EvidenceError(
                f"email appears truncated or off-topic: missing marker {marker!r}"
            )
    # Strict sensitive scan AFTER redaction: credential/account categories must
    # be absent; personal identifiers have already been redacted by design.
    for label, pattern in _EMAIL_STRICT_PATTERNS:
        if pattern.search(body):
            raise EvidenceError(
                f"support email contains sensitive content of category {label!r}; "
                "refusing to process — owner must sanitize the source manually"
            )
    record: dict[str, Any] = {
        "schema_version": EMAIL_SUPPORT_SCHEMA_VERSION,
        "classification": CLASS_CURRENT_SUPPORT_REFERENCE,
        "source_role": EMAIL_SOURCE_ROLE,
        "source_file": file.as_dict(),
        "acquisition": EMAIL_ACQUISITION_MODE,
        "subject": subject,
        "pdf_attachment": pdf_attachment,
        "sent_utc": sent_utc,
        "sender_domain": _domain_of(str(msg.get("From", ""))),
        "recipient_domain": _domain_of(str(msg.get("To", ""))),
        "mime_parts": [part.get_content_type() for part in msg.walk()],
        "scope_notes": [
            "The email does not restate contract size; contract-size evidence "
            "remains the support chat transcript and the current screenshots.",
            "No 2024 account statements should be expected if the owner had no "
            "relevant trades in that period.",
            "Swap values in this email are a current support reference, not "
            "historical 2024 evidence.",
        ],
        "record_canonical_sha256": "",
    }
    record["record_canonical_sha256"] = canonical_hash(
        {k: v for k, v in record.items() if k != "record_canonical_sha256"}
    )
    return file, {"record": record, "body": body}


def _domain_of(address_header: str) -> str:
    match = re.search(r"@([A-Za-z0-9.\-]+)", address_header)
    return match.group(1).lower() if match else "[not-supplied]"


def classify_email_claims(email_record: Mapping[str, Any], file: EvidenceFile) -> list[BrokerClaim]:
    """Classify the email claim-by-claim; every expected needle must be present."""

    claims: list[BrokerClaim] = []
    for claim_id, statement, classification, needle in EMAIL_CLAIM_NEEDLES:
        claims.append(
            _claim(
                claim_id,
                statement,
                classification,
                file,
                _require_quote(str(email_record["body"]), needle),
            )
        )
    return claims


# ---------------------------------------------------------------------------
# Swap-unit conflict (screenshot points vs email USD/lot) — never resolved
# ---------------------------------------------------------------------------

SCREENSHOT_OBSERVATION_DATE_UTC = "2026-09-13"  # source filename timestamp


def build_swap_unit_conflict_record(
    *,
    screenshot_file: EvidenceFile,
    screenshot_swap_long_points: str,
    screenshot_swap_short: str | None,
    screenshot_swap_short_readability: str,
    email_file: EvidenceFile,
    email_swap_long_usd: str,
    email_swap_short_usd: str,
    email_sent_utc: str,
) -> dict[str, Any]:
    """Record the swap-unit conflict without reconciling, converting or selecting."""

    return {
        "schema_version": SWAP_UNIT_CONFLICT_SCHEMA_VERSION,
        "classification": CLASS_REJECTED_CONFLICTING,
        "conflict_id": "swap.units_points_vs_usd_per_lot",
        "resolution": (
            "unresolved by design: the two sources state swap rates in "
            "different units and no official conversion rule was supplied; "
            "equivalence cannot be established"
        ),
        "values": {
            "screenshot_current_observation": {
                "source_role": "mt5_screenshot",
                "source_file_sha256": screenshot_file.sha256,
                "observation_date_utc": SCREENSHOT_OBSERVATION_DATE_UTC,
                "observation_date_basis": "source filename timestamp (screenshot export)",
                "units": "MT5 points per 1.00 lot per day",
                "swap_long": screenshot_swap_long_points,
                "swap_short": screenshot_swap_short,
                "swap_short_readability": screenshot_swap_short_readability,
                "calculation_mode": (
                    "Forex, swap type 'In points' (platform display); the "
                    "points-to-USD conversion rule is not stated by the source"
                ),
                "classification": CLASS_CURRENT_ONLY_NOT_HISTORICAL,
            },
            "email_support_reference": {
                "source_role": EMAIL_SOURCE_ROLE,
                "source_file_sha256": email_file.sha256,
                "observation_date_utc": email_sent_utc,
                "observation_date_basis": "email Date header",
                "units": "USD per 1.00 lot per day",
                "swap_long": email_swap_long_usd,
                "swap_short": email_swap_short_usd,
                "calculation_mode": (
                    "USD per lot as stated by Exness support; no points "
                    "conversion rule provided"
                ),
                "classification": CLASS_CURRENT_SUPPORT_REFERENCE,
            },
        },
        "equivalence_established": False,
        "possible_explanations": [
            "different observation dates (screenshot 2026-09-13 vs email "
            "2026-09-14); swap values change over time",
            "possible account/server or swap-calculation-mode differences "
            "behind the platform display vs the support statement",
            "the points display may embed an unstated per-point conversion; "
            "no official rule was provided",
        ],
        "reconciliation_prohibited": [
            "converting between units without an official rule",
            "averaging the two sources",
            "selecting one value as authoritative",
            "silently preferring either source",
        ],
        "record_canonical_sha256": "",
    }


def finalize_conflict_record(record: dict[str, Any]) -> dict[str, Any]:
    record["record_canonical_sha256"] = canonical_hash(
        {k: v for k, v in record.items() if k != "record_canonical_sha256"}
    )
    return record


def email_swap_values_from_claims(claims: Mapping[str, str]) -> tuple[str, str]:
    """Extract the email USD swap values from the classified claim statements."""

    long_needle = "-3.85"
    short_needle = "-0.25"
    long_stmt = claims.get("email.swap_long_usd_per_lot", "")
    short_stmt = claims.get("email.swap_short_usd_per_lot", "")
    if long_needle not in long_stmt or short_needle not in short_stmt:
        raise EvidenceError("email swap claims are missing expected values; fails closed")
    return long_needle, short_needle
