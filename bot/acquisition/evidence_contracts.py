"""Phase 8E offline evidence intake contracts.

Versioned, fail-closed contracts for owner-supplied historical evidence:

- high-impact USD news (offline, provenance-bearing);
- effective-dated XAUUSDm broker metadata;
- commission schedules;
- swap / rollover / triple-swap rules;
- sanitized slippage / fill evidence;
- the Phase 8E evidence matrix classification.

Every contract validates offline against explicit inputs. Nothing here
contacts a network provider, MT5, or any trading surface. Missing or
ambiguous provenance, licensing, coverage, units, or effective dates fail
closed: evidence is either genuinely accepted or classified MISSING.

Empirical acceptance always requires an owner-supplied source document and
its SHA-256; fictional tracked examples carry the ``EXAMPLE_ONLY`` marker
and are rejected as empirical evidence by construction.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

UTC = timezone.utc

DEVELOPMENT_INTERVAL_START = "2024-01-01T00:00:00Z"
DEVELOPMENT_INTERVAL_END = "2025-01-01T00:00:00Z"
DEVELOPMENT_ONLY_CLASSIFICATION = "DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE"

EXAMPLE_MARKERS = ("EXAMPLE_ONLY", "DUMMY_PROVIDER", "NOT_EMPIRICAL")
EXAMPLE_MARKER = "EXAMPLE_ONLY"

# Evidence matrix statuses (STEP 2).
STATUS_ACCEPTED_EMPIRICAL = "ACCEPTED_EMPIRICAL"
STATUS_ACCEPTED_DEVELOPMENT_ONLY = "ACCEPTED_DEVELOPMENT_ONLY"
STATUS_PRESENT_UNVERIFIED = "PRESENT_UNVERIFIED"
STATUS_CURRENT_ONLY_NOT_HISTORICAL = "CURRENT_ONLY_NOT_HISTORICAL"
STATUS_ASSUMPTION_ONLY = "ASSUMPTION_ONLY"
STATUS_MISSING = "MISSING"
STATUS_REJECTED = "REJECTED"
# Honest incomplete state: evidence exists and is bound to official sources,
# but required coverage/categories are still missing. Never counts as
# accepted; keeps dataset acceptance blocked without erasing progress.
STATUS_DEVELOPMENT_INCOMPLETE = "DEVELOPMENT_INCOMPLETE"

KNOWN_STATUSES = frozenset(
    {
        STATUS_ACCEPTED_EMPIRICAL,
        STATUS_ACCEPTED_DEVELOPMENT_ONLY,
        STATUS_PRESENT_UNVERIFIED,
        STATUS_CURRENT_ONLY_NOT_HISTORICAL,
        STATUS_ASSUMPTION_ONLY,
        STATUS_MISSING,
        STATUS_REJECTED,
        STATUS_DEVELOPMENT_INCOMPLETE,
    }
)

NEWS_SCHEMA_VERSION = "phase8e.historical-news.v1"
BROKER_METADATA_SCHEMA_VERSION = "phase8e.broker-metadata.v1"
COMMISSION_SCHEMA_VERSION = "phase8e.commission-schedule.v1"
SWAP_SCHEMA_VERSION = "phase8e.swap-rollover.v1"
SLIPPAGE_SCHEMA_VERSION = "phase8e.slippage-fill-evidence.v1"
EVIDENCE_MATRIX_SCHEMA_VERSION = "phase8e.evidence-matrix.v1"

SUPPORTED_NEWS_PROVIDERS = ("TRADING_ECONOMICS", "EODHD")
NEWS_IMPACTS = ("LOW", "MEDIUM", "HIGH")
IMPACT_ALIASES = {"1": "LOW", "2": "MEDIUM", "3": "HIGH", "RED": "HIGH"}

# Valid IANA timezone names are validated through zoneinfo at use time.
_TZNAME_RE = re.compile(r"^[A-Za-z0-9_+\-/]+$")

# Credential-bearing field names rejected anywhere in sanitized evidence.
PROHIBITED_FIELDS = frozenset(
    {
        "account_number",
        "account_id",
        "accountlogin",
        "account_login",
        "login",
        "password",
        "passphrase",
        "token",
        "api_key",
        "apikey",
        "secret",
        "private_key",
        "server_password",
        "session",
        "session_id",
        "cookie",
    }
)


class EvidenceError(ValueError):
    """Raised when evidence fails a fail-closed contract check."""


def sha256_file(path: Any) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def parse_utc(value: object, field_name: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise EvidenceError(f"{field_name} is required and must be explicit UTC")
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EvidenceError(f"{field_name} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise EvidenceError(f"{field_name} is naive/ambiguous and fails closed")
    return parsed.astimezone(UTC)


def require_utc_iso(value: object, field_name: str) -> str:
    return parse_utc(value, field_name).isoformat().replace("+00:00", "Z")


def require_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise EvidenceError(f"{field_name} is required")
    return text


def require_positive(value: object, field_name: str, *, allow_zero: bool = False) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number) or number < 0 or (number == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise EvidenceError(f"{field_name} must be finite and {qualifier}")
    return number


PROHIBITED_FIELDS_NORMALIZED = frozenset(
    re.sub(r"[^a-z0-9]", "", name) for name in PROHIBITED_FIELDS
)


def _require_no_prohibited_fields(record: Mapping[str, object], context: str) -> None:
    for key in record:
        normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
        if normalized in PROHIBITED_FIELDS_NORMALIZED:
            raise EvidenceError(
                f"{context} contains prohibited credential/account field {key!r}"
            )


def _reject_example_evidence(record: Mapping[str, object], context: str) -> None:
    """Fictional examples are never acceptable as empirical evidence."""
    for value in record.values():
        if isinstance(value, str) and any(marker in value for marker in EXAMPLE_MARKERS):
            raise EvidenceError(
                f"{context} carries the EXAMPLE_ONLY marker and cannot be accepted as empirical evidence"
            )


def validate_timezone_name(name: object, field_name: str) -> str:
    text = require_text(name, field_name)
    if not _TZNAME_RE.match(text):
        raise EvidenceError(f"{field_name} is not a valid timezone identifier")
    return text


def validate_effective_interval(
    effective_from: object,
    effective_to: object,
    field_prefix: str,
) -> tuple[str, str | None]:
    start = parse_utc(effective_from, f"{field_prefix}.effective_from")
    end = None if effective_to in (None, "") else parse_utc(effective_to, f"{field_prefix}.effective_to")
    if end is not None and end <= start:
        raise EvidenceError(f"{field_prefix} effective interval is empty or reversed")
    return start.isoformat().replace("+00:00", "Z"), (
        None if end is None else end.isoformat().replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# Historical USD news contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NewsAcceptance:
    schema_version: str
    provider: str
    retrieval_utc: str
    event_count: int
    high_impact_count: int
    coverage_start_utc: str
    coverage_end_utc: str
    covers_development_interval: bool
    licensing_declaration: str
    source_file_sha256: str
    events_canonical_sha256: str
    warnings: tuple[str, ...]

    @property
    def status(self) -> str:
        if self.covers_development_interval:
            return STATUS_ACCEPTED_EMPIRICAL
        return STATUS_PRESENT_UNVERIFIED


def _news_event_key(event: Mapping[str, object]) -> str:
    """Stable event identity: provider, timestamp, currency, name.

    Provider-local numeric IDs are recorded but deliberately NOT part of the
    stable key, so the same real-world event is deduplicated even when a row
    was re-fetched under a different calendar id. A provider id reused across
    two different identities fails closed.
    """

    material = "|".join(
        (
            str(event["provider"]).upper(),
            str(event["event_at_utc"]),
            str(event["currency"]).upper(),
            str(event["name"]).strip(),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def build_news_package(
    records: Sequence[Mapping[str, object]],
    *,
    provider: str,
    retrieval_utc: object,
    licensing_declaration: str,
    source_file_sha256: object,
    declared_coverage_start: object = None,
    declared_coverage_end: object = None,
) -> dict[str, object]:
    """Normalize owner-supplied historical news records into a package.

    ``records`` are raw provider rows already loaded from an owner-supplied
    offline file (no network). Currency filtering keeps exactly USD rows for
    the strategy filter. DST handling is explicit: timestamps must carry a
    real timezone offset (naive timestamps fail closed) and are converted to
    UTC with :meth:`datetime.astimezone`.

    Coverage is inferred from the events themselves (first..last). If the
    owner supplies an explicit declared coverage window (from the export's
    own documented range), it is validated (must contain every event and
    cover the development interval) and recorded immutably in the package;
    conflicting declarations fail closed.
    """

    provider_name = require_text(provider, "news provider").upper()
    if provider_name not in SUPPORTED_NEWS_PROVIDERS:
        raise EvidenceError(
            f"news provider {provider_name!r} is not supported; expected one of {SUPPORTED_NEWS_PROVIDERS}"
        )
    retrieval = parse_utc(retrieval_utc, "news retrieval time")
    declaration = require_text(licensing_declaration, "news licensing declaration")
    source_hash = require_text(source_file_sha256, "news source_file_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise EvidenceError("news source_file_sha256 must be a lowercase SHA-256 hex digest")
    _reject_example_evidence({"licensing_declaration": declaration}, "historical news")

    by_key: dict[str, dict[str, object]] = {}
    provider_local_ids: dict[str, str] = {}
    skipped_non_usd = 0
    for raw in records:
        if not isinstance(raw, Mapping):
            raise EvidenceError("historical news rows must be JSON objects")
        _require_no_prohibited_fields(raw, "historical news row")
        _reject_example_evidence(raw, "historical news row")
        country = str(raw.get("Country") or raw.get("country") or "").strip().upper()
        currency = str(raw.get("Currency") or raw.get("currency") or "").strip().upper()
        if country not in {"UNITED STATES", "US", "USA"} and currency != "USD":
            skipped_non_usd += 1
            continue
        name = require_text(raw.get("Event") or raw.get("event") or raw.get("name"), "news event name")
        provider_event_id = str(raw.get("CalendarId") or raw.get("id") or "").strip()
        if not provider_event_id:
            raise EvidenceError("historical news row lacks the provider event id")
        impact_raw = str(raw.get("Importance") or raw.get("importance") or raw.get("impact") or "").strip().upper()
        impact = IMPACT_ALIASES.get(impact_raw, impact_raw)
        if impact not in NEWS_IMPACTS:
            raise EvidenceError(f"historical news impact {impact_raw!r} is unknown and fails closed")
        timestamp = parse_utc(raw.get("Date") or raw.get("date") or raw.get("timestamp"), "news event timestamp")
        if timestamp >= parse_utc(DEVELOPMENT_INTERVAL_END, "development interval end"):
            raise EvidenceError(
                "news row lies on or after the 2025-01-01 holdout boundary and fails closed"
            )
        raw_record_hash = sha256_bytes(canonical_json(dict(raw)).encode("utf-8"))
        event: dict[str, object] = {
            "event_at_utc": timestamp.isoformat().replace("+00:00", "Z"),
            "currency": "USD",
            "impact": impact,
            "name": name,
            "provider": provider_name,
            "provider_event_id": provider_event_id,
            "retrieval_utc": retrieval.isoformat().replace("+00:00", "Z"),
            "raw_record_sha256": raw_record_hash,
        }
        key = _news_event_key(event)
        event["event_id"] = key
        existing = by_key.get(key)
        if existing is not None:
            if existing != event:
                raise EvidenceError(
                    "conflicting duplicate news event (same provider/time/currency/name with different content)"
                )
            if provider_event_id != str(existing["provider_event_id"]):
                raise EvidenceError(
                    "conflicting duplicate news event: same identity maps to two provider event ids"
                )
            continue
        prior_local = provider_local_ids.get(provider_event_id)
        if prior_local is not None and prior_local != key:
            raise EvidenceError("conflicting duplicate news event: provider event id reused across identities")
        provider_local_ids[provider_event_id] = key
        by_key[key] = event

    events = tuple(sorted(by_key.values(), key=lambda item: (str(item["event_at_utc"]), str(item["event_id"]))))
    warnings: list[str] = []
    if not events:
        warnings.append("NO_EVENTS_PARSED — missing dates must never be interpreted as no news")
    dev_start = parse_utc(DEVELOPMENT_INTERVAL_START, "dev start")
    dev_end = parse_utc(DEVELOPMENT_INTERVAL_END, "dev end")
    if events:
        coverage_start = str(events[0]["event_at_utc"])
        coverage_end = str(events[-1]["event_at_utc"])
        declared_start = (
            parse_utc(declared_coverage_start, "declared coverage start")
            if declared_coverage_start not in (None, "")
            else None
        )
        declared_end = (
            parse_utc(declared_coverage_end, "declared coverage end")
            if declared_coverage_end not in (None, "")
            else None
        )
        if declared_start is not None and declared_start > parse_utc(coverage_start, "first event"):
            raise EvidenceError("declared news coverage starts after the first event")
        if declared_end is not None and declared_end < parse_utc(coverage_end, "last event"):
            raise EvidenceError("declared news coverage ends before the last event")
        if declared_start is not None and declared_end is not None and declared_end <= declared_start:
            raise EvidenceError("declared news coverage window is empty or reversed")
        if declared_start is not None:
            coverage_start = declared_start.isoformat().replace("+00:00", "Z")
        if declared_end is not None:
            coverage_end = declared_end.isoformat().replace("+00:00", "Z")
        covers = parse_utc(coverage_start, "coverage start") <= dev_start and parse_utc(
            coverage_end, "coverage end"
        ) >= dev_end - timedelta(seconds=1)
    else:
        coverage_start = ""
        coverage_end = ""
        covers = False
    high_impact_count = sum(1 for event in events if event["impact"] == "HIGH")

    acceptance = NewsAcceptance(
        schema_version=NEWS_SCHEMA_VERSION,
        provider=provider_name,
        retrieval_utc=retrieval.isoformat().replace("+00:00", "Z"),
        event_count=len(events),
        high_impact_count=high_impact_count,
        coverage_start_utc=coverage_start,
        coverage_end_utc=coverage_end,
        covers_development_interval=covers,
        licensing_declaration=declaration,
        source_file_sha256=source_hash,
        events_canonical_sha256=canonical_hash(events),
        warnings=tuple(warnings),
    )
    return {
        "schema_version": NEWS_SCHEMA_VERSION,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "status": acceptance.status,
        "acceptance": {
            "provider": acceptance.provider,
            "retrieval_utc": acceptance.retrieval_utc,
            "event_count": acceptance.event_count,
            "high_impact_count": acceptance.high_impact_count,
            "coverage_start_utc": acceptance.coverage_start_utc,
            "coverage_end_utc": acceptance.coverage_end_utc,
            "covers_development_interval": acceptance.covers_development_interval,
            "declared_coverage_start_utc": (
                "" if declared_coverage_start in (None, "") else require_utc_iso(declared_coverage_start, "declared coverage start")
            ),
            "declared_coverage_end_utc": (
                "" if declared_coverage_end in (None, "") else require_utc_iso(declared_coverage_end, "declared coverage end")
            ),
            "licensing_declaration": acceptance.licensing_declaration,
            "source_file_sha256": acceptance.source_file_sha256,
            "events_canonical_sha256": acceptance.events_canonical_sha256,
            "warnings": list(acceptance.warnings),
        },
        "events": [dict(event) for event in events],
        "skipped_non_usd_rows": skipped_non_usd,
    }


# ---------------------------------------------------------------------------
# Broker metadata contract
# ---------------------------------------------------------------------------


SYMBOL_XAUUSDM = "XAUUSDm"

_BROKER_REQUIRED_TEXT = (
    "broker",
    "account_type",
    "account_currency",
    "profit_currency",
    "margin_currency",
    "base_currency",
    "source_description",
    "licensing_declaration",
)
_BROKER_REQUIRED_POSITIVE = (
    "digits",
    "point",
    "tick_size",
    "tick_value",
    "tick_value_profit",
    "tick_value_loss",
    "contract_size",
    "volume_min",
    "volume_max",
    "volume_step",
    "stops_level",
    "freeze_level",
    "margin_rate",
)


def build_broker_metadata_record(record: Mapping[str, object]) -> dict[str, object]:
    """Validate one effective-dated XAUUSDm metadata record (STEP 4)."""

    if not isinstance(record, Mapping):
        raise EvidenceError("broker metadata record must be a JSON object")
    _require_no_prohibited_fields(record, "broker metadata")
    if require_text(record.get("symbol"), "metadata symbol") != SYMBOL_XAUUSDM:
        raise EvidenceError("broker metadata must describe exactly XAUUSDm")
    for key in _BROKER_REQUIRED_TEXT:
        require_text(record.get(key), f"metadata {key}")
    for key in _BROKER_REQUIRED_POSITIVE:
        require_positive(record.get(key), f"metadata {key}", allow_zero=("level" in key))
    filling_modes = record.get("filling_modes")
    if not isinstance(filling_modes, Sequence) or isinstance(filling_modes, (str, bytes)) or not filling_modes:
        raise EvidenceError("metadata filling_modes must be a non-empty list")
    require_text(record.get("execution_mode"), "metadata execution_mode")
    margin_rules = record.get("margin_rules")
    if not isinstance(margin_rules, Mapping) or not margin_rules:
        raise EvidenceError("metadata margin_rules must be a non-empty object")
    effective_from, effective_to = validate_effective_interval(
        record.get("effective_from"), record.get("effective_to"), "metadata"
    )
    observed = require_text(record.get("observation_utc"), "metadata observation_utc")
    source_hash = require_text(record.get("source_file_sha256"), "metadata source_file_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise EvidenceError("metadata source_file_sha256 must be a lowercase SHA-256 hex digest")
    declaration = require_text(record.get("licensing_declaration"), "metadata licensing_declaration")
    _reject_example_evidence(record, "broker metadata")
    historical_evidence = bool(record.get("historical_evidence", False))
    out = dict(record)
    out["effective_from"] = effective_from
    out["effective_to"] = effective_to
    out["observation_utc"] = parse_utc(observed, "metadata observation_utc").isoformat().replace("+00:00", "Z")
    out["historical_evidence"] = historical_evidence
    if historical_evidence:
        # Only independently dated evidence may claim it applied during 2024.
        if parse_utc(effective_from, "effective_from") > parse_utc(
            "2024-12-31T23:59:59Z", "dev end"
        ) or (
            effective_to is not None
            and parse_utc(effective_to, "effective_to") <= parse_utc(DEVELOPMENT_INTERVAL_START, "dev start")
        ):
            raise EvidenceError(
                "metadata effective interval does not intersect the 2024 development interval"
            )
        out["status"] = STATUS_ACCEPTED_EMPIRICAL
    else:
        # Current observations are never historical 2024 evidence.
        out["status"] = STATUS_CURRENT_ONLY_NOT_HISTORICAL
    out["record_canonical_sha256"] = canonical_hash(
        {k: v for k, v in out.items() if k not in {"record_canonical_sha256", "status"}}
    )
    return out


def build_broker_metadata_package(records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    validated = [build_broker_metadata_record(record) for record in records]
    if not validated:
        raise EvidenceError("broker metadata package requires at least one record")
    validated.sort(key=lambda item: (str(item["effective_from"]), str(item["record_canonical_sha256"])))
    # Fail closed on overlapping effective segments.
    for previous, current in zip(validated, validated[1:]):
        prev_end = previous.get("effective_to")
        if prev_end is None or parse_utc(prev_end, "effective_to") > parse_utc(
            current["effective_from"], "effective_from"
        ):
            raise EvidenceError("broker metadata effective intervals overlap")
    statuses = {str(item["status"]) for item in validated}
    package_status = (
        STATUS_ACCEPTED_EMPIRICAL if statuses == {STATUS_ACCEPTED_EMPIRICAL} else str(sorted(statuses)[0])
    )
    return {
        "schema_version": BROKER_METADATA_SCHEMA_VERSION,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "status": package_status,
        "records": validated,
        "package_canonical_sha256": canonical_hash(validated),
    }


# ---------------------------------------------------------------------------
# Commission contract
# ---------------------------------------------------------------------------

COMMISSION_MODES = (
    "NONE",
    "PER_LOT_PER_SIDE",
    "PER_LOT_ROUND_TURN",
    "FIXED_PER_ORDER",
    "PERCENT_NOTIONAL",
)

COMMISSION_CHARGING_POINTS = ("PER_SIDE", "ROUND_TURN", "ORDER")
COMMISSION_ROUNDING = ("NONE", "NEAREST", "UP", "DOWN")


def build_commission_record(record: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(record, Mapping):
        raise EvidenceError("commission record must be a JSON object")
    _require_no_prohibited_fields(record, "commission record")
    mode = require_text(record.get("mode"), "commission mode").upper()
    if mode not in COMMISSION_MODES:
        raise EvidenceError(f"commission mode {mode!r} is unsupported; expected one of {COMMISSION_MODES}")
    symbol = require_text(record.get("symbol"), "commission symbol")
    if symbol != SYMBOL_XAUUSDM:
        raise EvidenceError("commission evidence must describe exactly XAUUSDm")
    require_text(record.get("account_type"), "commission account_type")
    currency = require_text(record.get("currency"), "commission currency")
    amount = require_positive(record.get("amount"), "commission amount", allow_zero=(mode == "NONE"))
    if mode in {"PER_LOT_PER_SIDE", "PER_LOT_ROUND_TURN", "FIXED_PER_ORDER"} and currency.upper() not in {
        "USD",
        "USC",
        "CENTS",
    }:
        raise EvidenceError(
            "commission currency conversion is unavailable; account-currency (USD) commission is required"
        )
    if mode == "PERCENT_NOTIONAL":
        if not 0 < amount < 1:
            raise EvidenceError("notional commission must be a fraction below one")
    charging_point = require_text(record.get("charging_point"), "commission charging_point").upper()
    if charging_point not in COMMISSION_CHARGING_POINTS:
        raise EvidenceError(f"commission charging_point {charging_point!r} is unknown")
    rounding = require_text(record.get("rounding"), "commission rounding").upper()
    if rounding not in COMMISSION_ROUNDING:
        raise EvidenceError(f"commission rounding {rounding!r} is unknown")
    minimum_charge = record.get("minimum_charge")
    minimum_value = (
        0.0
        if minimum_charge in (None, "")
        else require_positive(minimum_charge, "commission minimum_charge", allow_zero=True)
    )
    effective_from, effective_to = validate_effective_interval(
        record.get("effective_from"), record.get("effective_to"), "commission"
    )
    require_text(record.get("source_description"), "commission source_description")
    source_hash = require_text(record.get("source_file_sha256"), "commission source_file_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise EvidenceError("commission source_file_sha256 must be a lowercase SHA-256 hex digest")
    declaration = require_text(record.get("licensing_declaration"), "commission licensing_declaration")
    _reject_example_evidence(record, "commission")
    require_text(record.get("units"), "commission units")
    out = dict(record)
    out["mode"] = mode
    out["charging_point"] = charging_point
    out["rounding"] = rounding
    out["minimum_charge"] = minimum_value
    out["effective_from"] = effective_from
    out["effective_to"] = effective_to
    out["status"] = STATUS_ACCEPTED_EMPIRICAL
    out["record_canonical_sha256"] = canonical_hash(
        {k: v for k, v in out.items() if k not in {"record_canonical_sha256", "status"}}
    )
    return out


def build_commission_package(records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    validated = [build_commission_record(record) for record in records]
    if not validated:
        raise EvidenceError("commission package requires at least one record")
    validated.sort(key=lambda item: (str(item["effective_from"]), str(item["record_canonical_sha256"])))
    for previous, current in zip(validated, validated[1:]):
        prev_end = previous.get("effective_to")
        if prev_end is None or parse_utc(prev_end, "effective_to") > parse_utc(
            current["effective_from"], "effective_from"
        ):
            raise EvidenceError("commission effective intervals overlap")
    return {
        "schema_version": COMMISSION_SCHEMA_VERSION,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "status": STATUS_ACCEPTED_EMPIRICAL,
        "records": validated,
        "package_canonical_sha256": canonical_hash(validated),
    }


# ---------------------------------------------------------------------------
# Swap / rollover contract
# ---------------------------------------------------------------------------

SWAP_UNITS = (
    "ACCOUNT_CURRENCY_PER_LOT",
    "POINTS_PER_LOT",
)
WEEKDAY_NAMES = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)(:[0-5]\d)?$")


def build_swap_record(record: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(record, Mapping):
        raise EvidenceError("swap record must be a JSON object")
    _require_no_prohibited_fields(record, "swap record")
    symbol = require_text(record.get("symbol"), "swap symbol")
    if symbol != SYMBOL_XAUUSDM:
        raise EvidenceError("swap evidence must describe exactly XAUUSDm")
    require_text(record.get("account_type"), "swap account_type")
    units = require_text(record.get("units"), "swap units").upper()
    if units not in SWAP_UNITS:
        raise EvidenceError(f"swap units {units!r} are unknown; conversion method must be explicit")
    for key in ("swap_long", "swap_short"):
        try:
            number = float(record.get(key))  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise EvidenceError(f"swap {key} must be numeric") from exc
        if not math.isfinite(number):
            raise EvidenceError(f"swap {key} must be finite")
    rollover_timezone = validate_timezone_name(record.get("rollover_timezone"), "swap rollover_timezone")
    from zoneinfo import ZoneInfo

    try:
        ZoneInfo(rollover_timezone)
    except Exception as exc:  # ZoneInfoNotFoundError and platform tz database issues
        raise EvidenceError(f"swap rollover_timezone {rollover_timezone!r} is unknown") from exc
    rollover_time = require_text(record.get("rollover_time"), "swap rollover_time")
    if not _TIME_RE.match(rollover_time):
        raise EvidenceError("swap rollover_time must be local HH:MM or HH:MM:SS without a timezone")
    triple_raw = require_text(record.get("triple_swap_weekday"), "swap triple_swap_weekday").upper()
    if triple_raw not in WEEKDAY_NAMES:
        raise EvidenceError(f"swap triple_swap_weekday {triple_raw!r} is unknown")
    effective_from, effective_to = validate_effective_interval(
        record.get("effective_from"), record.get("effective_to"), "swap"
    )
    require_text(record.get("source_description"), "swap source_description")
    source_hash = require_text(record.get("source_file_sha256"), "swap source_file_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise EvidenceError("swap source_file_sha256 must be a lowercase SHA-256 hex digest")
    declaration = require_text(record.get("licensing_declaration"), "swap licensing_declaration")
    _reject_example_evidence(record, "swap")
    # Zero current swaps are NOT proof of zero historical swap; a record that
    # claims zero rates must carry an explicit dated justification.
    if float(record.get("swap_long", "nan")) == 0.0 and float(record.get("swap_short", "nan")) == 0.0:
        require_text(record.get("zero_swap_justification"), "swap zero_swap_justification")
    out = dict(record)
    out["units"] = units
    out["rollover_timezone"] = rollover_timezone
    out["rollover_time"] = rollover_time
    out["triple_swap_weekday"] = triple_raw
    out["effective_from"] = effective_from
    out["effective_to"] = effective_to
    out["status"] = STATUS_ACCEPTED_EMPIRICAL
    out["record_canonical_sha256"] = canonical_hash(
        {k: v for k, v in out.items() if k not in {"record_canonical_sha256", "status"}}
    )
    return out


def build_swap_package(records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    validated = [build_swap_record(record) for record in records]
    if not validated:
        raise EvidenceError("swap package requires at least one record")
    validated.sort(key=lambda item: (str(item["effective_from"]), str(item["record_canonical_sha256"])))
    for previous, current in zip(validated, validated[1:]):
        prev_end = previous.get("effective_to")
        if prev_end is None or parse_utc(prev_end, "effective_to") > parse_utc(
            current["effective_from"], "effective_from"
        ):
            raise EvidenceError("swap effective intervals overlap")
    return {
        "schema_version": SWAP_SCHEMA_VERSION,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "status": STATUS_ACCEPTED_EMPIRICAL,
        "records": validated,
        "package_canonical_sha256": canonical_hash(validated),
    }


# ---------------------------------------------------------------------------
# Slippage / fill evidence contract
# ---------------------------------------------------------------------------

SLIPPAGE_ACTIONS = ("ENTRY_MARKET", "EXIT_MARKET", "STOP_LOSS", "TAKE_PROFIT")


def build_slippage_record(record: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(record, Mapping):
        raise EvidenceError("slippage record must be a JSON object")
    _require_no_prohibited_fields(record, "slippage record")
    _reject_example_evidence(record, "slippage evidence")
    fill_id = require_text(record.get("fill_id"), "slippage fill_id")
    symbol = require_text(record.get("symbol"), "slippage symbol")
    if symbol != SYMBOL_XAUUSDM:
        raise EvidenceError("slippage evidence is restricted to XAUUSDm")
    side = require_text(record.get("side"), "slippage side").upper()
    if side not in {"BUY", "SELL"}:
        raise EvidenceError("slippage side must be BUY or SELL")
    action = require_text(record.get("action"), "slippage action").upper()
    if action not in SLIPPAGE_ACTIONS:
        raise EvidenceError(f"slippage action {action!r} is unknown")
    request_at = parse_utc(record.get("request_utc"), "slippage request_utc")
    quote_at = parse_utc(record.get("quote_utc"), "slippage quote_utc")
    requested_price = require_positive(record.get("requested_price"), "slippage requested_price")
    fill_price = require_positive(record.get("fill_price"), "slippage fill_price")
    # Signed slippage is adverse-positive: buys slip up, sells slip down.
    sign = 1.0 if side == "BUY" else -1.0
    slippage_price = (fill_price - requested_price) * sign
    if slippage_price < 0:
        raise EvidenceError("slippage must be adverse or neutral (never favorable-negative)")
    requested_volume = require_positive(record.get("requested_volume"), "slippage requested_volume")
    filled_volume = require_positive(record.get("filled_volume"), "slippage filled_volume")
    if filled_volume > requested_volume:
        raise EvidenceError("slippage filled_volume cannot exceed requested_volume")
    source_hash = require_text(record.get("source_log_sha256"), "slippage source_log_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise EvidenceError("slippage source_log_sha256 must be a lowercase SHA-256 hex digest")
    account_type = require_text(record.get("account_type"), "slippage account_type")
    point = record.get("point", record.get("point_size"))
    if point in (None, ""):
        raise EvidenceError("slippage point (point size in price units) is required")
    out = dict(record)
    out["fill_id"] = fill_id
    out["side"] = side
    out["action"] = action
    out["request_utc"] = request_at.isoformat().replace("+00:00", "Z")
    out["quote_utc"] = quote_at.isoformat().replace("+00:00", "Z")
    out["slippage_price"] = slippage_price
    out["slippage_points"] = slippage_price / require_positive(point, "slippage point")
    out["partial_fill"] = filled_volume < requested_volume
    out["account_type"] = account_type
    out["status"] = STATUS_ACCEPTED_EMPIRICAL
    out["record_canonical_sha256"] = canonical_hash(
        {k: v for k, v in out.items() if k not in {"record_canonical_sha256", "status"}}
    )
    return out


def build_slippage_package(records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    validated = [build_slippage_record(record) for record in records]
    if not validated:
        raise EvidenceError("slippage package requires at least one sanitized fill record")
    seen: set[str] = set()
    for item in validated:
        if str(item["fill_id"]) in seen:
            raise EvidenceError("duplicate slippage fill_id fails closed")
        seen.add(str(item["fill_id"]))
    validated.sort(key=lambda item: (str(item["request_utc"]), str(item["fill_id"])))
    adverse = sum(1 for item in validated if float(item["slippage_price"]) > 0)
    return {
        "schema_version": SLIPPAGE_SCHEMA_VERSION,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "status": STATUS_ACCEPTED_EMPIRICAL,
        "record_count": len(validated),
        "adverse_fill_count": adverse,
        "neutral_fill_count": len(validated) - adverse,
        "partial_fill_count": sum(1 for item in validated if item["partial_fill"]),
        "records": validated,
        "package_canonical_sha256": canonical_hash(validated),
    }


# ---------------------------------------------------------------------------
# Evidence matrix
# ---------------------------------------------------------------------------

EVIDENCE_CATEGORIES = (
    "HISTORICAL_USD_NEWS",
    "BROKER_METADATA",
    "COMMISSION",
    "SWAP_ROLLOVER",
    "SLIPPAGE_FILLS",
    "OBSERVED_SPREAD",
)


def matrix_entry(
    *,
    category: str,
    status: str,
    source_identity: str = "",
    provider: str = "",
    coverage_interval: str = "",
    effective_interval: str = "",
    retrieval_or_observation_utc: str = "",
    sha256: str = "",
    schema_version: str = "",
    provenance: str = "",
    licensing: str = "",
    completeness: str = "",
    units: str = "",
    account_type_dependency: str = "",
    validation_errors: Sequence[str] = (),
    permitted_uses: Sequence[str] = (),
    prohibited_uses: Sequence[str] = (),
) -> dict[str, object]:
    if category not in EVIDENCE_CATEGORIES:
        raise EvidenceError(f"unknown evidence category {category!r}")
    if status not in KNOWN_STATUSES:
        raise EvidenceError(f"unknown evidence status {status!r}")
    return {
        "category": category,
        "status": status,
        "source_identity": source_identity,
        "provider": provider,
        "coverage_interval": coverage_interval,
        "effective_interval": effective_interval,
        "retrieval_or_observation_utc": retrieval_or_observation_utc,
        "sha256": sha256,
        "schema_version": schema_version,
        "provenance": provenance,
        "licensing": licensing,
        "completeness": completeness,
        "units": units,
        "account_type_dependency": account_type_dependency,
        "validation_errors": list(validation_errors),
        "permitted_uses": list(permitted_uses),
        "prohibited_uses": list(prohibited_uses),
    }


def build_evidence_matrix(
    *,
    news_status: str,
    broker_metadata_status: str,
    commission_status: str,
    swap_status: str,
    slippage_status: str,
    observed_spread_entry: Mapping[str, object],
    notes: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Assemble the machine-readable Phase 8E evidence matrix (STEP 2)."""

    entries: list[dict[str, object]] = [
        matrix_entry(
            category="HISTORICAL_USD_NEWS",
            status=news_status,
            schema_version=NEWS_SCHEMA_VERSION,
            permitted_uses=["development news-window filtering once accepted"],
            prohibited_uses=["holdout evaluation", "profitability evidence"],
        ),
        matrix_entry(
            category="BROKER_METADATA",
            status=broker_metadata_status,
            schema_version=BROKER_METADATA_SCHEMA_VERSION,
            permitted_uses=["effective-dated backtest cost model once accepted"],
            prohibited_uses=["treating current conditions as historical"],
        ),
        matrix_entry(
            category="COMMISSION",
            status=commission_status,
            schema_version=COMMISSION_SCHEMA_VERSION,
            permitted_uses=["backtest commission model once accepted"],
            prohibited_uses=["assuming zero commission from missing data"],
        ),
        matrix_entry(
            category="SWAP_ROLLOVER",
            status=swap_status,
            schema_version=SWAP_SCHEMA_VERSION,
            permitted_uses=["backtest swap/rollover model once accepted"],
            prohibited_uses=["assuming zero swap from zero current fields"],
        ),
        matrix_entry(
            category="SLIPPAGE_FILLS",
            status=slippage_status,
            schema_version=SLIPPAGE_SCHEMA_VERSION,
            permitted_uses=["stress-testing via the deterministic assumption model"],
            prohibited_uses=["claiming empirical execution fidelity"],
        ),
    ]
    spread = dict(observed_spread_entry)
    spread["category"] = "OBSERVED_SPREAD"
    for required_key in ("status", "sha256", "schema_version", "permitted_uses", "prohibited_uses"):
        if required_key not in spread:
            raise EvidenceError(
                f"observed spread matrix entry lacks required field {required_key!r}"
            )
    if spread["status"] not in KNOWN_STATUSES:
        raise EvidenceError("observed spread matrix entry carries an unknown status")
    entries.append(spread)
    for entry in entries:
        if entry["category"] == "OBSERVED_SPREAD":
            continue
        note = (notes or {}).get(str(entry["category"]))
        if note:
            entry["note"] = note
    statuses = {str(entry["category"]): str(entry["status"]) for entry in entries}
    return {
        "schema_version": EVIDENCE_MATRIX_SCHEMA_VERSION,
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "statuses": statuses,
        "entries": entries,
        "all_categories_accepted": all(
            status in {STATUS_ACCEPTED_EMPIRICAL, STATUS_ACCEPTED_DEVELOPMENT_ONLY}
            for status in statuses.values()
        ),
    }
