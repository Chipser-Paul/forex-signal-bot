from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Iterable, Mapping

from .models import AcquisitionError, utc_datetime


UTC = timezone.utc
KNOWN_IMPACTS = {"LOW", "MEDIUM", "HIGH"}


def _raw_hash(record: Mapping[str, object]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_timestamp(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise AcquisitionError("news event timestamp is malformed") from exc
    if parsed.tzinfo is None:
        raise AcquisitionError("news event timestamp timezone is ambiguous")
    return parsed.astimezone(UTC)


def normalize_historical_news(
    records: Iterable[Mapping[str, object]],
    *,
    provider: str,
    retrieved_at: datetime,
) -> tuple[dict[str, object], ...]:
    provider_name = provider.strip().upper()
    if provider_name not in {"TRADING_ECONOMICS", "EODHD"}:
        raise AcquisitionError("unsupported historical news provider")
    retrieval = utc_datetime(retrieved_at, "news retrieval time")
    normalized: dict[str, dict[str, object]] = {}
    for raw in records:
        country = str(raw.get("Country") or raw.get("country") or "").strip().upper()
        currency = str(raw.get("Currency") or raw.get("currency") or "").strip().upper()
        if country not in {"UNITED STATES", "US", "USA"} and currency != "USD":
            continue
        event_name = str(raw.get("Event") or raw.get("event") or raw.get("name") or "").strip()
        event_id = str(raw.get("CalendarId") or raw.get("id") or "").strip()
        impact = str(raw.get("Importance") or raw.get("importance") or raw.get("impact") or "").strip().upper()
        impact = {"1": "LOW", "2": "MEDIUM", "3": "HIGH"}.get(impact, impact)
        timestamp_value = raw.get("Date") or raw.get("date") or raw.get("timestamp")
        if not event_name or not event_id or impact not in KNOWN_IMPACTS or timestamp_value is None:
            raise AcquisitionError("historical news record lacks required identity or impact")
        timestamp = _parse_timestamp(timestamp_value)
        item = {
            "event_id": event_id,
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "currency": "USD",
            "impact": impact,
            "name": event_name,
            "source": provider_name,
            "provider": provider_name,
            "retrieved_at": retrieval.isoformat().replace("+00:00", "Z"),
            "raw_record_sha256": _raw_hash(raw),
        }
        existing = normalized.get(event_id)
        if existing is not None and existing != item:
            raise AcquisitionError("duplicate news event identity has conflicting content")
        normalized[event_id] = item
    return tuple(sorted(normalized.values(), key=lambda item: (item["timestamp"], item["event_id"])))
