"""Phase 8G broker-conditions evidence intake and honest classification.

Normalizes the owner-supplied, sanitized evidence for Exness Standard
XAUUSDm trading conditions into machine-readable, hash-bound facts:

- a support transcript (``Support/Exness_Support_2024_Conditions_*.txt``),
  parsed claim-by-claim — never promoted wholesale to historical evidence;
- MT5 Specification screenshots, whose values are always
  ``CURRENT_ONLY_NOT_HISTORICAL`` unless independently dated evidence
  establishes a 2024 effective date;
- unit normalization separating the MT5 point (0.001), the broker pip
  (0.01), and the contract size (100 XAU);
- commission represented honestly as mode ``NONE`` bound to the support
  statement (with its scope limitation), never assumed from missing data;
- historical 2024 swap values recorded as unavailable — never invented —
  with the triple-Wednesday rule kept as a broker-asserted fact;
- a deterministic, machine-readable *proposed* swap stress-policy template
  that stays INACTIVE: every numeric proxy is ``ASSUMPTION_ONLY``, no
  scenario applies a favorable positive swap credit, and use requires a
  separate owner-authorized preregistration checkpoint.

Everything is offline: no MT5, no network, no account or trading surface.
Sensitive content (credentials, account numbers, emails, Support PINs,
owner PII) fails closed before any storage. Raw owner files are read-only
and are never modified or committed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evidence_contracts import (
    BROKER_METADATA_SCHEMA_VERSION,
    COMMISSION_SCHEMA_VERSION,
    EvidenceError,
    SWAP_SCHEMA_VERSION,
    SYMBOL_XAUUSDM,
    canonical_hash,
    require_text,
    sha256_bytes,
)

BROKER_SUPPORT_SCHEMA_VERSION = "phase8g.broker-support-evidence.v1"
CLASS_CURRENT_SUPPORT_REFERENCE = "CURRENT_SUPPORT_REFERENCE"
BROKER_SCREENSHOT_SCHEMA_VERSION = "phase8g.broker-screenshot-evidence.v1"
SWAP_STRESS_TEMPLATE_SCHEMA_VERSION = "phase8g.swap-stress-policy-proposal.v1"
BROKER_EVIDENCE_PACKAGE_SCHEMA_VERSION = "phase8g.broker-evidence-package.v1"

# Stable classifications reusing the existing Phase 8E vocabulary where an
# equivalent exists, plus the two honest subclasses this checkpoint adds.
CLASS_BROKER_SUPPORT_ASSERTED = "BROKER_SUPPORT_ASSERTED"
CLASS_CURRENT_ONLY_NOT_HISTORICAL = "CURRENT_ONLY_NOT_HISTORICAL"
CLASS_OBSERVED_EMPIRICAL = "OBSERVED_EMPIRICAL"
CLASS_HISTORICAL_VALUE_UNAVAILABLE = "HISTORICAL_VALUE_UNAVAILABLE"
CLASS_ASSUMPTION_ONLY = "ASSUMPTION_ONLY"
CLASS_REJECTED_CONFLICTING = "REJECTED_CONFLICTING"
CLASS_DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"

BROKER_CLAIM_CLASSES = frozenset(
    {
        CLASS_BROKER_SUPPORT_ASSERTED,
        CLASS_CURRENT_ONLY_NOT_HISTORICAL,
        CLASS_CURRENT_SUPPORT_REFERENCE,
        CLASS_OBSERVED_EMPIRICAL,
        CLASS_HISTORICAL_VALUE_UNAVAILABLE,
        CLASS_ASSUMPTION_ONLY,
        CLASS_REJECTED_CONFLICTING,
        CLASS_DEVELOPMENT_ONLY,
    }
)

# Rollover time asked in the chat but never answered by support.
ROLLOVER_TIME_UTC_SUPPLIED: str | None = None

TRANSCRIPT_ACQUISITION_MODE = "MANUAL_CHAT_EXPORT"
SCREENSHOT_ACQUISITION_MODE = "MANUAL_SCREENSHOT"

# Sensitive-content scanning (fail closed before any storage).  The support
# agent's own first name is part of the chat record but is still kept out of
# any derived artifact; it is checked generically below, never printed.
# Bare 8+ digit runs outside URL context. The (?<![\w/\-]) / (?![\w\-])
# guards exclude help-article IDs embedded in URLs (e.g.
# ``/articles/4405235684498-Instrument``), which are not account numbers;
# a genuine bare account number in prose still matches.
SENSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("support_pin", re.compile(r"\b(?:support\s*)?pin\s*[:#]?\s*\d{4,8}\b", re.IGNORECASE)),
    ("password", re.compile(r"\bpassword\b\s*[:=]\s*\S+", re.IGNORECASE)),
    ("token", re.compile(r"\b(?:api[_-]?key|token|bearer)\b\s*[:=]\s*\S+", re.IGNORECASE)),
    ("account_number", re.compile(r"(?<![\w/\-])\d{8,}(?![\w\-])")),
    ("long_hex_secret", re.compile(r"\b[0-9a-fA-F]{40,}\b")),
)

# Person names observed in the transcript (support agent). They stay out of
# every derived artifact; the raw transcript file itself is never copied.
_TRANSCRIPT_AGENT_NAMES = ("Kuhlekonke",)


@dataclass(frozen=True)
class EvidenceFile:
    """Hash-bound identity of one owner evidence file."""

    path: Path
    role: str
    size_bytes: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "role": self.role,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


DEFAULT_TRANSCRIPT_BASE = "Exness_Support_2024_Conditions_2026-09-14"


def discover_transcript_file(evidence_root: Path, base_name: str = DEFAULT_TRANSCRIPT_BASE) -> Path:
    """Resolve the support transcript even when Windows hides the .txt suffix.

    Accepts the expected base name with any of the documented extensions
    (``.txt`` visible or hidden, plus case variants), never a directory or
    symlink, and only under the support directory.
    """

    support_dir = Path(evidence_root) / "Support"
    base = base_name
    candidates: list[Path] = []
    for name in (base, f"{base}.txt", f"{base}.TXT", f"{base}.txt.txt"):
        candidate = support_dir / name
        if candidate.exists():
            candidates.append(candidate)
    if not candidates:
        # Last resort: case-insensitive scan of the support directory only.
        if support_dir.is_dir():
            for child in sorted(support_dir.iterdir()):
                if child.stem.lower() == base.lower() and child.suffix.lower() in {"", ".txt"}:
                    candidates.append(child)
    unique = {c.resolve(): c for c in candidates}
    if not unique:
        raise EvidenceError(
            f"support transcript not found under {support_dir} "
            f"(expected base name {base!r} with an optional .txt extension)"
        )
    if len(unique) > 1:
        raise EvidenceError(
            "ambiguous transcript files discovered: " + ", ".join(sorted(str(p) for p in unique))
        )
    resolved = next(iter(unique))
    if not resolved.is_file() or resolved.is_symlink():
        raise EvidenceError(f"transcript is not a regular file: {resolved}")
    return resolved


def scan_for_sensitive_content(text: str, context: str) -> None:
    """Fail closed when sensitive content is present (without printing it)."""

    for label, pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            raise EvidenceError(
                f"{context} contains sensitive content of category {label!r}; "
                "refusing to process — owner must sanitize the source manually"
            )


def _redact_agent_names(text: str) -> str:
    for name in _TRANSCRIPT_AGENT_NAMES:
        text = text.replace(name, "[SUPPORT_AGENT]")
    return text


def stat_evidence_file(path: Path, role: str) -> EvidenceFile:
    # Symlink check happens on the raw path BEFORE resolution, otherwise
    # resolving hides the symlink behind its target.
    raw = Path(path)
    if raw.is_symlink():
        raise EvidenceError(f"evidence file is a symlink, refusing: {path}")
    resolved = raw.resolve()
    if not resolved.is_file():
        raise EvidenceError(f"evidence file is not a regular file: {path}")
    return EvidenceFile(
        path=resolved,
        role=role,
        size_bytes=resolved.stat().st_size,
        sha256=sha256_file(resolved),
    )


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Transcript claim classification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrokerClaim:
    """One classified statement extracted from the owner evidence."""

    claim_id: str
    statement: str
    classification: str
    source_file_role: str
    source_file_sha256: str
    quote: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "statement": self.statement,
            "classification": self.classification,
            "source_file_role": self.source_file_role,
            "source_file_sha256": self.source_file_sha256,
            "quote": self.quote,
        }


def _claim(claim_id: str, statement: str, classification: str, file: EvidenceFile, quote: str) -> BrokerClaim:
    if classification not in BROKER_CLAIM_CLASSES:
        raise EvidenceError(f"unknown claim classification {classification!r}")
    return BrokerClaim(
        claim_id=claim_id,
        statement=statement,
        classification=classification,
        source_file_role=file.role,
        source_file_sha256=file.sha256,
        quote=_redact_agent_names(quote),
    )


def _require_quote(text: str, needle: str) -> str:
    if needle not in text:
        raise EvidenceError(
            f"expected support statement not found in transcript: {needle[:72]!r}"
        )
    index = text.index(needle)
    start = max(0, index - 40)
    end = min(len(text), index + len(needle) + 40)
    return text[start:end].strip()


def classify_transcript(text: str, file: EvidenceFile) -> list[BrokerClaim]:
    """Classify the transcript claim-by-claim; only present statements accepted.

    Every expected statement must actually appear in the transcript, or the
    classifier fails closed — nothing is assumed from silence.
    """

    scan_for_sensitive_content(text, "support transcript")
    claims: list[BrokerClaim] = []

    def q(needle: str) -> str:
        return _require_quote(text, needle)

    claims.append(
        _claim(
            "support.account_type",
            "Account type discussed is Exness Standard MT5",
            CLASS_BROKER_SUPPORT_ASSERTED,
            file,
            q("Here is the available information regarding XAUUSDm (Gold) on a Standard MT5 account"),
        )
    )
    claims.append(
        _claim(
            "support.commission_none",
            "Standard accounts carry no separate fixed trading commission for XAUUSDm; cost is included in the variable spread",
            CLASS_BROKER_SUPPORT_ASSERTED,
            file,
            q("On Standard accounts, there is no fixed trading commission for XAUUSDm"),
        )
    )
    claims.append(
        _claim(
            "support.spread_costs_in_spread",
            "Trading cost on Standard is included in the variable spread",
            CLASS_BROKER_SUPPORT_ASSERTED,
            file,
            q("the trading cost is included in the spread"),
        )
    )
    claims.append(
        _claim(
            "support.no_archived_spread_by_email",
            "Exness does not provide archived spread data by email",
            CLASS_BROKER_SUPPORT_ASSERTED,
            file,
            q("Exness does not provide archived spread data by email"),
        )
    )
    claims.append(
        _claim(
            "support.contract_size_100_oz",
            "Contract size is 100 troy ounces",
            CLASS_BROKER_SUPPORT_ASSERTED,
            file,
            q("Contract size: 100 troy ounces"),
        )
    )
    claims.append(
        _claim(
            "support.pip_size_0_01",
            "Broker pip size is 0.01",
            CLASS_BROKER_SUPPORT_ASSERTED,
            file,
            q("Pip size: 0.01"),
        )
    )
    claims.append(
        _claim(
            "support.volume_min_0_01",
            "Minimum trading volume is 0.01 lot",
            CLASS_BROKER_SUPPORT_ASSERTED,
            file,
            q("Minimum trading volume: 0.01 lot"),
        )
    )
    claims.append(
        _claim(
            "support.volume_max_day_night",
            "Maximum volume is 200 lots daytime and 20 lots nighttime",
            CLASS_BROKER_SUPPORT_ASSERTED,
            file,
            q("200 lots (daytime), 20 lots (nighttime)"),
        )
    )
    claims.append(
        _claim(
            "support.margin_fixed_1_200",
            "Fixed margin requirement is 1:200 (0.5%)",
            CLASS_BROKER_SUPPORT_ASSERTED,
            file,
            q("Fixed margin requirement: 1:200 (0.5%)"),
        )
    )
    claims.append(
        _claim(
            "support.hedged_margin_zero",
            "Hedged margin is 0%",
            CLASS_BROKER_SUPPORT_ASSERTED,
            file,
            q("Hedged margin: 0%"),
        )
    )
    claims.append(
        _claim(
            "support.market_execution",
            "Execution is market execution",
            CLASS_BROKER_SUPPORT_ASSERTED,
            file,
            q("Market execution"),
        )
    )
    claims.append(
        _claim(
            "support.triple_swap_wednesday",
            "Triple swap is charged on Wednesdays",
            CLASS_BROKER_SUPPORT_ASSERTED,
            file,
            q("triple swap charged on Wednesdays"),
        )
    )
    claims.append(
        _claim(
            "support.swap_holiday_changes_possible",
            "The swap schedule may change due to public/bank holidays (no historical holiday adjustments supplied)",
            CLASS_BROKER_SUPPORT_ASSERTED,
            file,
            q("swap schedule may change due to public"),
        )
    )
    claims.append(
        _claim(
            "support.no_investigation_ticket_created",
            "No ticket/reference number or record of an investigation or email was created",
            CLASS_BROKER_SUPPORT_ASSERTED,
            file,
            q("There is no ticket/reference number or record of an investigation"),
        )
    )
    claims.append(
        _claim(
            "support.no_public_historical_specification_archive",
            "Support could not provide archived 2024 specifications; the replay suggestion was not a demonstrated archived-specification mechanism",
            CLASS_HISTORICAL_VALUE_UNAVAILABLE,
            file,
            q("I'm not quite sure if it'll stretch to 2024"),
        )
    )
    # Rollover at 21:00 UTC was asked (twice: the automated preamble and the
    # owner's follow-up) and never answered. "21:00" may appear only inside
    # those two known question snippets; any other occurrence fails closed so
    # an answered rollover time can never be silently missed.
    question_1 = "rollover at 21:00 UTC; daytime/nighttime session times; margin rules"
    question_2 = (
        "rollover at 21:00 UTC and Wednesday triple swap applied throughout "
        "2024, or whether these are current conditions only"
    )
    expected_21_00 = sum(q(snippet).count("21:00") for snippet in (question_1, question_2))
    if text.count("21:00") != expected_21_00:
        raise EvidenceError(
            "transcript contains a rollover-time statement outside the known "
            "question snippets; classify it explicitly instead of assuming it unanswered"
        )
    claims.append(
        _claim(
            "support.rollover_time_unanswered",
            "Rollover time (asked for 21:00 UTC) was never answered in the transcript",
            CLASS_HISTORICAL_VALUE_UNAVAILABLE,
            file,
            q("rollover at 21:00 UTC and Wednesday triple swap applied throughout 2024, or whether these are current conditions only"),
        )
    )
    # Historical swap values were never actually supplied.
    claims.append(
        _claim(
            "support.historical_swap_values_unsupplied",
            "Historical 2024 swap-long/short values and change dates were not supplied",
            CLASS_HISTORICAL_VALUE_UNAVAILABLE,
            file,
            q("The actual swap rates for specific dates can be checked in your MT5 platform"),
        )
    )
    # The Zero/Raw-Spread commission figures are other account types and are
    # explicitly out of scope; recorded as rejected-for-this-scope, not
    # silently dropped.
    claims.append(
        _claim(
            "support.non_standard_commission_out_of_scope",
            "Zero (5.5 USD) and Raw Spread (3.5 USD) commission figures concern other account types and are out of scope for Standard",
            CLASS_REJECTED_CONFLICTING,
            file,
            q("5.5 USD for Zero accounts and 3.5 USD for Raw Spread accounts"),
        )
    )
    return claims


def load_transcript_claims(transcript_path: Path) -> tuple[EvidenceFile, list[BrokerClaim]]:
    file = stat_evidence_file(transcript_path, "support_transcript")
    text = transcript_path.read_text(encoding="utf-8")
    if not text.strip():
        raise EvidenceError("support transcript is empty")
    # Conversation-completeness gate: the full two-session chat, not just the
    # final consolidated answer.
    for marker in ("Connecting you to one of our agents", "Chat started at 14:12"):
        if marker not in text:
            raise EvidenceError(
                f"transcript appears truncated: missing conversation marker {marker!r}"
            )
    return file, classify_transcript(text, file)


# ---------------------------------------------------------------------------
# Screenshot observations (CURRENT_ONLY_NOT_HISTORICAL)
# ---------------------------------------------------------------------------

# Values OCR-extracted from the sanitized MT5 Specification screenshots at
# ingestion time are supplied by the control script as explicit records; the
# contract only accepts clearly readable values and records anything else as
# not readable. Nothing here guesses a truncated value.


def build_screenshot_record(
    *,
    file: EvidenceFile,
    ocr_note: str,
    observed: Mapping[str, Any],
    not_readable: Sequence[str],
) -> dict[str, Any]:
    if not ocr_note.strip():
        raise EvidenceError("screenshot record requires an OCR extraction note")
    if not isinstance(observed, Mapping):
        raise EvidenceError("screenshot observed values must be an object")
    if file.role != "mt5_screenshot":
        raise EvidenceError("screenshot record requires role mt5_screenshot")
    clean_observed: dict[str, str] = {}
    for key, value in observed.items():
        require_text(key, "screenshot observed key")
        clean_observed[str(key)] = _redact_agent_names(require_text(value, f"screenshot observed {key}"))
    missing = [str(item) for item in not_readable if not str(item).strip()]
    if missing:
        raise EvidenceError("not_readable entries must be non-empty")
    record: dict[str, Any] = {
        "schema_version": BROKER_SCREENSHOT_SCHEMA_VERSION,
        "classification": CLASS_CURRENT_ONLY_NOT_HISTORICAL,
        "status": "CURRENT_ONLY_NOT_HISTORICAL",
        "symbol": SYMBOL_XAUUSDM,
        "source_file": file.as_dict(),
        "ocr_note": _redact_agent_names(ocr_note),
        "observed_values": clean_observed,
        "not_readable_fields": sorted(set(str(item) for item in not_readable)),
        "acquisition": SCREENSHOT_ACQUISITION_MODE,
        "limitation": (
            "Current platform display; no 2024 effective date is established. "
            "Every value is CURRENT_ONLY_NOT_HISTORICAL unless another source "
            "proves it applied during the development interval."
        ),
        "record_canonical_sha256": "",
    }
    record["record_canonical_sha256"] = canonical_hash(
        {k: v for k, v in record.items() if k != "record_canonical_sha256"}
    )
    return record


# ---------------------------------------------------------------------------
# Unit normalization
# ---------------------------------------------------------------------------

MT5_POINT = 0.001
BROKER_PIP = 0.01
CONTRACT_SIZE_XAU = 100.0


def verify_unit_normalization() -> dict[str, Any]:
    """Arithmetically verify point/pip/contract relationships; fail closed."""

    checks: list[dict[str, Any]] = []
    one_pip_points = BROKER_PIP / MT5_POINT
    if abs(one_pip_points - 10.0) > 1e-9:
        raise EvidenceError("unit normalization failed: one pip must equal ten 0.001 points")
    pip_value_usd_per_lot = BROKER_PIP * CONTRACT_SIZE_XAU
    if abs(pip_value_usd_per_lot - 1.0) > 1e-9:
        raise EvidenceError("unit normalization failed: one 0.01 pip move at one lot must equal 1 USD")
    point_value_usd_per_lot = MT5_POINT * CONTRACT_SIZE_XAU
    if abs(point_value_usd_per_lot - 0.10) > 1e-9:
        raise EvidenceError("unit normalization failed: one 0.001 point move at one lot must equal 0.10 USD")
    checks.append({"one_pip_in_points": one_pip_points})
    checks.append({"pip_value_usd_per_lot": pip_value_usd_per_lot})
    checks.append({"point_value_usd_per_lot": point_value_usd_per_lot})
    return {
        "mt5_point": MT5_POINT,
        "broker_pip": BROKER_PIP,
        "contract_size_xau": CONTRACT_SIZE_XAU,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Commission NONE + swap unavailability + stress template
# ---------------------------------------------------------------------------


def build_commission_none_record(
    *,
    support_claims: Sequence[BrokerClaim],
    transcript_sha256: str,
) -> dict[str, Any]:
    ids = {claim.claim_id for claim in support_claims}
    if "support.commission_none" not in ids or "support.account_type" not in ids:
        raise EvidenceError("commission NONE requires the transcript commission + account-type statements")
    record: dict[str, Any] = {
        "schema_version": COMMISSION_SCHEMA_VERSION,
        "classification": CLASS_DEVELOPMENT_ONLY,
        "status": "ACCEPTED_DEVELOPMENT_ONLY",
        "mode": "NONE",
        "amount": 0,
        "currency": "USD",
        "charging_point": "PER_SIDE",
        "per_side_charge": 0,
        "round_turn_charge": 0,
        "minimum_charge": 0,
        "rounding": "NONE",
        "symbol": SYMBOL_XAUUSDM,
        "account_type": "Exness Standard MT5",
        "source_description": "Exness support transcript (Standard MT5 XAUUSDm commission statement)",
        "source_file_sha256": transcript_sha256,
        "source_claim_ids": ["support.account_type", "support.commission_none"],
        "units": "USD per lot",
        "provenance": "broker support statement bound to transcript SHA-256",
        "licensing_declaration": (
            "owner-supplied sanitized support transcript; development-only use"
        ),
        "effective_interval": {
            "effective_from": None,
            "effective_to": None,
            "established": False,
            "limitation": (
                "The transcript does not scope the commission answer to the "
                "complete 2024 development interval; no historical effective "
                "dates are claimed beyond what the transcript establishes."
            ),
        },
        "stress_sensitivity_proposals": [
            {
                "label": "commission_per_lot_round_turn_3_5",
                "mode": "PER_LOT_ROUND_TURN",
                "amount": 3.5,
                "currency": "USD",
                "classification": CLASS_ASSUMPTION_ONLY,
                "note": "proposed stress case only; NOT an observed Standard-account commission",
            },
            {
                "label": "commission_per_lot_round_turn_5_5",
                "mode": "PER_LOT_ROUND_TURN",
                "amount": 5.5,
                "currency": "USD",
                "classification": CLASS_ASSUMPTION_ONLY,
                "note": "proposed stress case only; NOT an observed Standard-account commission",
            },
        ],
        "record_canonical_sha256": "",
    }
    record["record_canonical_sha256"] = canonical_hash(
        {k: v for k, v in record.items() if k != "record_canonical_sha256"}
    )
    return record


def build_swap_unavailability_record(
    *,
    support_claims: Sequence[BrokerClaim],
    screenshots: Sequence[Mapping[str, Any]],
    transcript_sha256: str,
    prior_swap_snapshots: Sequence[Mapping[str, Any]] = (),
    email_claims: Sequence[BrokerClaim] = (),
    email_file: EvidenceFile | None = None,
    email_swap_long_usd: str | None = None,
    email_swap_short_usd: str | None = None,
    email_sent_utc: str | None = None,
) -> dict[str, Any]:
    ids = {claim.claim_id for claim in support_claims}
    if "support.triple_swap_wednesday" not in ids:
        raise EvidenceError("swap record requires the broker triple-Wednesday statement")
    swap_long_current: str | None = None
    swap_short_current: str | None = None
    for screenshot in screenshots:
        observed = screenshot.get("observed_values") or {}
        if observed.get("swap_long") is not None:
            swap_long_current = str(observed["swap_long"])
        if observed.get("swap_short") is not None:
            swap_short_current = str(observed["swap_short"])
    record: dict[str, Any] = {
        "schema_version": SWAP_SCHEMA_VERSION,
        "classification": CLASS_DEVELOPMENT_ONLY,
        "status": "HISTORICAL_VALUE_UNAVAILABLE",
        "symbol": SYMBOL_XAUUSDM,
        "account_type": "Exness Standard MT5",
        "broker_asserted": {
            "triple_swap_weekday": "WEDNESDAY",
            "classification": CLASS_BROKER_SUPPORT_ASSERTED,
            "source_file_sha256": transcript_sha256,
        },
        "rollover": {
            "rollover_time_utc_supplied": ROLLOVER_TIME_UTC_SUPPLIED,
            "classification": CLASS_HISTORICAL_VALUE_UNAVAILABLE,
            "note": "rollover time was asked in the chat but never answered",
        },
        "current_observation": {
            "swap_type": "points",
            "swap_long": swap_long_current,
            "swap_short": swap_short_current,
            "swap_short_readability": (
                "clearly readable" if swap_short_current is not None else "NOT_CLEARLY_READABLE_TRUNCATED"
            ),
            "classification": CLASS_CURRENT_ONLY_NOT_HISTORICAL,
            "holiday_adjustments": "unspecified",
        },
        **(
            {
                "email_current_reference": {
                    "swap_long": email_swap_long_usd,
                    "swap_short": email_swap_short_usd,
                    "units": "USD per 1.00 lot per day",
                    "observation_utc": email_sent_utc,
                    "source_file_sha256": email_file.sha256 if email_file is not None else "",
                    "classification": CLASS_CURRENT_SUPPORT_REFERENCE,
                    "historical_status": "NOT_HISTORICAL_2024_EVIDENCE",
                    "claim_ids": sorted(
                        c.claim_id for c in email_claims if c.classification == CLASS_CURRENT_SUPPORT_REFERENCE
                    ),
                }
            }
            if email_swap_long_usd is not None
            else {}
        ),
        "historical_2024": {
            "swap_long": None,
            "swap_short": None,
            "change_dates": None,
            "holiday_adjustments": None,
            "classification": CLASS_HISTORICAL_VALUE_UNAVAILABLE,
            "note": (
                "Historical 2024 swap values and change dates were never "
                "supplied; current display values must not be projected back."
            ),
        },
        "prior_snapshot_conflict_check": {
            "previous_metadata_snapshots_with_swap_values": len(prior_swap_snapshots),
            "conflicts_detected": [
                {
                    "snapshot": str(item.get("snapshot_id", "")),
                    "swap_long": str(item.get("swap_long", "")),
                    "swap_short": str(item.get("swap_short", "")),
                }
                for item in prior_swap_snapshots
            ],
        },
        "source_description": "Exness support transcript + sanitized MT5 specification screenshots",
        "source_file_sha256": transcript_sha256,
        "licensing_declaration": "owner-supplied sanitized evidence; development-only use",
        "record_canonical_sha256": "",
    }
    record["record_canonical_sha256"] = canonical_hash(
        {k: v for k, v in record.items() if k != "record_canonical_sha256"}
    )
    return record


def build_email_stress_template(
    *,
    email_swap_long_usd: str,
    unit_normalization: Mapping[str, Any],
    derivation_utc: str | None = None,
) -> dict[str, Any]:
    """Conflict-gated, INACTIVE stress template from the email values.

    The email states swap in USD per lot per day, so the scenario values are
    expressed in those units directly — no points conversion is performed and
    no equivalence with the screenshot points display is asserted. The
    template stays inactive and is additionally gated on the unresolved
    swap-unit conflict being reviewed separately.
    """

    swap_long_usd = float(email_swap_long_usd)
    if swap_long_usd >= 0:
        raise EvidenceError(
            "email swap-long is not adverse; refusing to derive an adverse proxy set"
        )
    point_value_usd_per_lot = float(unit_normalization["mt5_point"]) * float(
        unit_normalization["contract_size_xau"]
    )
    if abs(point_value_usd_per_lot - 0.10) > 1e-9:
        raise EvidenceError("unexpected point value in unit normalization")

    def scenario(label: str, multiplier: float) -> dict[str, Any]:
        value = round(swap_long_usd * multiplier, 6)
        return {
            "label": label,
            "swap_long_usd_per_lot_per_day": value,
            "swap_short_usd_per_lot_per_day": 0.0,
            "multiplier": multiplier,
            "triple_swap_weekday": "WEDNESDAY",
            "triple_weekday_multiplier": 3,
            "classification": CLASS_ASSUMPTION_ONLY,
        }

    template: dict[str, Any] = {
        "schema_version": SWAP_STRESS_TEMPLATE_SCHEMA_VERSION,
        "classification": CLASS_ASSUMPTION_ONLY,
        "status": "PROPOSED_INACTIVE_CONFLICT_GATED",
        "active": False,
        "activation_requires": (
            "separate owner-authorized preregistration checkpoint AFTER the "
            "screenshot-points vs email-USD swap-unit conflict is reviewed"
        ),
        "conflict_gate": "swap.units_points_vs_usd_per_lot",
        "units": "USD per 1.00 lot per day (as stated by Exness support; no points conversion applied)",
        "base_observation": {
            "source": "official support email",
            "classification": CLASS_CURRENT_SUPPORT_REFERENCE,
            "swap_long_usd_per_lot_per_day": swap_long_usd,
        },
        "policy_constraints": {
            "no_favorable_positive_swap_credit": True,
            "swap_short_fixed_at_zero_or_adverse_only": True,
            "triple_charging_preserved": True,
            "values_selected_without_strategy_performance": True,
        },
        "scenarios": [
            scenario("neutral_current_proxy", 1.0),
            scenario("adverse_x2", 2.0),
            scenario("severe_x3", 3.0),
        ],
        "holiday_adjustments": "unspecified — remain excluded",
        "derived_at_utc": derivation_utc,
        "record_canonical_sha256": "",
    }
    template["record_canonical_sha256"] = canonical_hash(
        {k: v for k, v in template.items() if k != "record_canonical_sha256"}
    )
    return template


def build_swap_stress_template(
    *,
    swap_unavailability: Mapping[str, Any],
    unit_normalization: Mapping[str, Any],
    derivation_utc: str | None = None,
) -> dict[str, Any]:
    """PROPOSED, INACTIVE swap stress-policy template (never auto-activated)."""

    current = swap_unavailability.get("current_observation") or {}
    swap_long_text = current.get("swap_long")
    if swap_long_text is None:
        raise EvidenceError(
            "stress template requires the clearly-readable current swap-long value; without it no deterministic proxy can be derived"
        )
    swap_long_points = float(swap_long_text)
    if swap_long_points >= 0:
        raise EvidenceError(
            "current swap-long observation is not adverse; refusing to derive an adverse proxy set from it"
        )
    point_value_usd_per_lot = float(unit_normalization["mt5_point"]) * float(
        unit_normalization["contract_size_xau"]
    )
    if abs(point_value_usd_per_lot - 0.10) > 1e-9:
        raise EvidenceError("unexpected point value in unit normalization")
    base_long_usd_per_lot = swap_long_points * point_value_usd_per_lot

    def scenario(label: str, multiplier: float) -> dict[str, Any]:
        value = round(base_long_usd_per_lot * multiplier, 6)
        return {
            "label": label,
            "swap_long_points_per_lot": swap_long_points * multiplier,
            "swap_long_usd_per_lot": value,
            "swap_short_points_per_lot": 0.0,
            "swap_short_usd_per_lot": 0.0,
            "multiplier": multiplier,
            "triple_swap_weekday": "WEDNESDAY",
            "triple_weekday_multiplier": 3,
            "classification": CLASS_ASSUMPTION_ONLY,
        }

    template: dict[str, Any] = {
        "schema_version": SWAP_STRESS_TEMPLATE_SCHEMA_VERSION,
        "classification": CLASS_ASSUMPTION_ONLY,
        "status": "PROPOSED_INACTIVE",
        "active": False,
        "activation_requires": "separate owner-authorized preregistration checkpoint",
        "symbol": SYMBOL_XAUUSDM,
        "account_type": "Exness Standard MT5",
        "units": (
            "swap rates in MT5 points per 1.00 lot; conversion formula: "
            "usd_per_lot = points * mt5_point(0.001) * contract_size(100)"
        ),
        "conversion_formula": "usd_per_lot = swap_points * 0.001 * 100",
        "base_observation": {
            "source": "current MT5 specification display",
            "classification": CLASS_CURRENT_ONLY_NOT_HISTORICAL,
            "swap_long_points_per_lot": swap_long_points,
        },
        "policy_constraints": {
            "no_favorable_positive_swap_credit": True,
            "swap_short_fixed_at_zero_or_adverse_only": True,
            "triple_charging_preserved": True,
            "values_selected_without_strategy_performance": True,
        },
        "scenarios": [
            scenario("neutral_current_proxy", 1.0),
            scenario("adverse_x2", 2.0),
            scenario("severe_x3", 3.0),
        ],
        "derived_at_utc": derivation_utc,
        "holiday_adjustments": "unspecified — remain excluded",
        "record_canonical_sha256": "",
    }
    template["record_canonical_sha256"] = canonical_hash(
        {k: v for k, v in template.items() if k != "record_canonical_sha256"}
    )
    return template


# ---------------------------------------------------------------------------
# Package assembly
# ---------------------------------------------------------------------------


def build_broker_evidence_package(
    *,
    transcript_file: EvidenceFile,
    claims: Sequence[BrokerClaim],
    screenshots: Sequence[Mapping[str, Any]],
    observed_spread_package_id: str,
    observed_spread_canonical_sha256: str,
    margin_conflicts: Sequence[Mapping[str, Any]] = (),
    prior_swap_snapshots: Sequence[Mapping[str, Any]] = (),
    stress_derived_at_utc: str | None = None,
    email_file: EvidenceFile | None = None,
    email_claims: Sequence[BrokerClaim] = (),
    email_record: Mapping[str, Any] | None = None,
    swap_unit_conflict: Mapping[str, Any] | None = None,
    email_stress_template: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the immutable Phase 8G broker-evidence package content.

    The support email is an additive, hash-bound source: its claims are
    appended, its record embedded, and — when the swap-unit conflict is
    present — the stress template must come from the email-derived,
    conflict-gated variant. The conflict itself is never resolved here.
    """

    all_claims = [*claims, *email_claims]
    if not all_claims:
        raise EvidenceError("broker evidence package requires at least one classified claim")
    if (email_file is not None) != bool(email_claims):
        raise EvidenceError("email evidence requires both the file identity and its claims")
    if (email_file is None) != (email_record is None):
        raise EvidenceError("email evidence requires the parsed record alongside the file")
    if (swap_unit_conflict is None) != (email_stress_template is None):
        raise EvidenceError(
            "the email-derived stress template requires the swap-unit conflict record"
        )
    from . import broker_email_evidence  # local import avoids import cycle

    units = verify_unit_normalization()
    screenshot_records = [dict(item) for item in screenshots]
    for record in screenshot_records:
        if record.get("classification") != CLASS_CURRENT_ONLY_NOT_HISTORICAL:
            raise EvidenceError("screenshot observations must remain CURRENT_ONLY_NOT_HISTORICAL")
    commission = build_commission_none_record(
        support_claims=claims, transcript_sha256=transcript_file.sha256
    )
    swap = build_swap_unavailability_record(
        support_claims=claims,
        screenshots=screenshot_records,
        transcript_sha256=transcript_file.sha256,
        prior_swap_snapshots=prior_swap_snapshots,
    )
    if email_stress_template is not None:
        stress = dict(email_stress_template)
    else:
        stress = build_swap_stress_template(
            swap_unavailability=swap,
            unit_normalization=units,
            derivation_utc=stress_derived_at_utc,
        )
    claim_dicts = [claim.as_dict() for claim in all_claims]
    claim_ids = sorted({str(claim["claim_id"]) for claim in claim_dicts})
    spread_linkage = {
        "broker_statement_claim_id": "support.spread_costs_in_spread",
        "statement": "Standard-account trading cost is included in the variable spread",
        "primary_2024_spread_evidence": {
            "package_id": observed_spread_package_id,
            "content_canonical_sha256": observed_spread_canonical_sha256,
            "classification": CLASS_OBSERVED_EMPIRICAL,
            "note": (
                "Observed Exness XAUUSDm bid/ask tick evidence remains the only "
                "2024 spread evidence; current calculator/advertised/screenshot "
                "spreads are never substituted for it."
            ),
        },
        "substitution_prohibited": [
            "current calculator spread",
            "average advertised spread",
            "manually typed spread",
            "screenshot spread display",
        ],
    }
    content: dict[str, Any] = {
        "schema_version": BROKER_EVIDENCE_PACKAGE_SCHEMA_VERSION,
        "classification": CLASS_DEVELOPMENT_ONLY,
        "full_classification": (
            "DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE"
        ),
        "status": "ACCEPTED_DEVELOPMENT_ONLY",
        "symbol": SYMBOL_XAUUSDM,
        "account_type": "Exness Standard MT5",
        "source_files": [
            transcript_file.as_dict(),
            *[dict(item["source_file"]) for item in screenshot_records],
            *( [email_file.as_dict()] if email_file is not None else [] ),
        ],
        "acquisition_modes": {
            "transcript": TRANSCRIPT_ACQUISITION_MODE,
            "screenshots": SCREENSHOT_ACQUISITION_MODE,
            **(
                {"support_email": broker_email_evidence.EMAIL_ACQUISITION_MODE}
                if email_file is not None
                else {}
            ),
        },
        "claims": claim_dicts,
        "screenshot_observations": screenshot_records,
        "claim_class_summary": {
            cls: sorted(
                str(claim["claim_id"]) for claim in claim_dicts if claim["classification"] == cls
            )
            for cls in sorted({str(claim["classification"]) for claim in claim_dicts})
        },
        "commission_none": commission,
        **(
            {
                "commission_email_corroboration": {
                    "claim_ids": sorted(
                        str(c.claim_id)
                        for c in email_claims
                        if c.claim_id
                        in {"email.standard_no_trading_commission", "email.xauusdm_commission_zero", "email.costs_built_into_spread"}
                    ),
                    "note": (
                        "The official support email corroborates the chat "
                        "transcript's zero-commission statements; no historical "
                        "effective dates are claimed by either source."
                    ),
                }
            }
            if email_claims
            else {}
        ),
        "unit_normalization": units,
        "swap_rollover": swap,
        **({"support_email": dict(email_record)} if email_record is not None else {}),
        **({"swap_unit_conflict": dict(swap_unit_conflict)} if swap_unit_conflict is not None else {}),
        "swap_stress_policy_proposal": stress,
        "spread_evidence_linkage": spread_linkage,
        "margin_conflicts": [dict(item) for item in margin_conflicts],
        "conflict_policy": (
            "Conflicts are documented, never silently resolved: the current "
            "platform margin display (1.0000000 initial/maintenance) diverges "
            "from the support-asserted fixed 1:200 (0.5%) requirement, and "
            "screenshot values are CURRENT_ONLY_NOT_HISTORICAL while the "
            "support statements describe Standard-account conditions without "
            "a demonstrated 2024 effective date."
        ),
        "claim_id_index": claim_ids,
        "record_canonical_sha256": "",
    }
    content["record_canonical_sha256"] = canonical_hash(
        {k: v for k, v in content.items() if k != "record_canonical_sha256"}
    )
    return content


def build_broker_evidence_envelope(content: Mapping[str, Any]) -> dict[str, Any]:
    """Wrap the package content into the evidence-store envelope shape."""

    from .evidence_contracts import DEVELOPMENT_ONLY_CLASSIFICATION

    content_hash = canonical_hash(dict(content))
    package_id = f"evidence-broker_support-v1-{content_hash[:16]}"
    return {
        "manifest": {
            "schema_version": "phase8e.evidence-package.v1",
            "package_id": package_id,
            "kind": "broker_support",
            "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
            "content_canonical_sha256": content_hash,
        },
        "content": dict(content),
    }
