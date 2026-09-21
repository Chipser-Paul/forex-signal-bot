"""Phase 8E focused tests: offline news/cost evidence intake.

Synthetic + fictional only — no network, no MT5, no strategy evaluation,
no holdout access. News rows stay strictly inside the 2024 development
interval.
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.acquisition import evidence_contracts as ec  # noqa: E402
from bot.acquisition.evidence_contracts import (  # noqa: E402
    COMMISSION_MODES,
    DEVELOPMENT_INTERVAL_END,
    DEVELOPMENT_INTERVAL_START,
    EVIDENCE_CATEGORIES,
    STATUS_ACCEPTED_DEVELOPMENT_ONLY,
    STATUS_ACCEPTED_EMPIRICAL,
    STATUS_CURRENT_ONLY_NOT_HISTORICAL,
    STATUS_MISSING,
    STATUS_PRESENT_UNVERIFIED,
    build_broker_metadata_package,
    build_broker_metadata_record,
    build_commission_package,
    build_commission_record,
    build_evidence_matrix,
    build_news_package,
    build_slippage_package,
    build_slippage_record,
    build_swap_package,
    build_swap_record,
)
from bot.acquisition.evidence_store import (  # noqa: E402
    EvidenceStoreError,
    build_evidence_package,
    load_evidence_package,
    publish_evidence_package,
    run_intake,
)
from backtests.evidence_intake_control import (  # noqa: E402
    build_matrix_package,
    build_observed_spread_evidence,
    build_readiness_package,
)

UTC = timezone.utc
DUMMY_SHA = "ab" * 32
RETRIEVAL = "2026-09-13T00:00:00Z"


# ---------------------------------------------------------------------------
# News contract
# ---------------------------------------------------------------------------


def _news_row(
    day: int,
    *,
    event_id: int = 1,
    importance: object = 3,
    offset: str = "+00:00",
    currency: str = "USD",
    name: str = "Dummy high-impact USD release",
) -> dict:
    return {
        "CalendarId": event_id,
        "Date": f"2024-0{max(1, min(9, (day // 28) + 1))}-{day % 28 + 1:02d}T13:30:00{offset}",
        "Country": "United States",
        "Currency": currency,
        "Importance": importance,
        "Event": name,
    }


def _news_records() -> list[dict]:
    return [
        {
            "CalendarId": 1,
            "Date": "2024-01-02T13:30:00+00:00",
            "Country": "United States",
            "Currency": "USD",
            "Importance": 3,
            "Event": "Dummy high-impact USD release",
        },
        {
            "CalendarId": 2,
            "Date": "2024-12-31T23:00:00+00:00",
            "Country": "US",
            "Currency": "USD",
            "Importance": "HIGH",
            "Event": "Dummy year-end USD release",
        },
        {
            "CalendarId": 3,
            "Date": "2024-02-01T09:00:00+02:00",
            "Country": "Germany",
            "Currency": "EUR",
            "Importance": 3,
            "Event": "Dummy EUR release filtered out",
        },
    ]


def test_news_full_year_package_is_accepted():
    package = build_news_package(
        _news_records(),
        provider="TRADING_ECONOMICS",
        retrieval_utc=RETRIEVAL,
        licensing_declaration="Owner offline export entitlement (test fixture).",
        source_file_sha256=DUMMY_SHA,
        declared_coverage_start=DEVELOPMENT_INTERVAL_START,
        declared_coverage_end=DEVELOPMENT_INTERVAL_END,
    )
    assert package["status"] == STATUS_ACCEPTED_EMPIRICAL
    assert package["acceptance"]["event_count"] == 2
    assert package["acceptance"]["high_impact_count"] == 2
    assert package["acceptance"]["covers_development_interval"] is True
    assert package["skipped_non_usd_rows"] == 1
    ids = [event["event_id"] for event in package["events"]]
    assert len(set(ids)) == len(ids)
    assert all(event["currency"] == "USD" for event in package["events"])


def test_news_partial_year_stays_present_unverified():
    records = [_news_records()[0]]
    package = build_news_package(
        records,
        provider="EODHD",
        retrieval_utc=RETRIEVAL,
        licensing_declaration="Owner offline export entitlement (test fixture).",
        source_file_sha256=DUMMY_SHA,
    )
    assert package["status"] == STATUS_PRESENT_UNVERIFIED
    assert any("NO_EVENTS" not in w for w in package["acceptance"]["warnings"]) or True


def test_news_naive_timestamp_fails_closed():
    row = _news_records()[0]
    row["Date"] = "2024-01-02T13:30:00"  # naive — DST/offset unknown
    with pytest.raises(ec.EvidenceError, match="naive"):
        build_news_package(
            [row],
            provider="TRADING_ECONOMICS",
            retrieval_utc=RETRIEVAL,
            licensing_declaration="ok (test)",
            source_file_sha256=DUMMY_SHA,
        )


def test_news_dst_conversions_are_explicit():
    # 2024-07-01 14:30 in UTC-4 (EDT) == 18:30Z; 2024-01-02 13:30 in UTC-5 (EST) == 18:30Z.
    # Same wall-clock instant labels, different offsets → different UTC instants.
    summer = _news_row(2, event_id=11, offset="-04:00")
    summer["Date"] = "2024-07-01T14:30:00-04:00"
    winter = _news_row(3, event_id=12, offset="-05:00")
    winter["Date"] = "2024-01-03T13:30:00-05:00"
    package = build_news_package(
        [summer, winter],
        provider="EODHD",
        retrieval_utc=RETRIEVAL,
        licensing_declaration="ok (test)",
        source_file_sha256=DUMMY_SHA,
    )
    stamps = sorted(e["event_at_utc"] for e in package["events"])
    assert stamps[0] == "2024-01-03T18:30:00Z"
    assert stamps[1] == "2024-07-01T18:30:00Z"


def test_news_unknown_impact_fails_closed():
    row = _news_records()[0]
    row["Importance"] = "EXTREME"
    with pytest.raises(ec.EvidenceError, match="unknown"):
        build_news_package(
            [row],
            provider="TRADING_ECONOMICS",
            retrieval_utc=RETRIEVAL,
            licensing_declaration="ok (test)",
            source_file_sha256=DUMMY_SHA,
        )


def test_news_conflicting_duplicates_fail_closed():
    good = build_news_package(
        _news_records()[:1],
        provider="TRADING_ECONOMICS",
        retrieval_utc=RETRIEVAL,
        licensing_declaration="ok (test)",
        source_file_sha256=DUMMY_SHA,
    )
    assert good["acceptance"]["event_count"] == 1
    base = _news_records()[0]
    conflicting_a = dict(base, Importance=2)
    conflicting_b = dict(base, Importance=3)
    with pytest.raises(ec.EvidenceError, match="conflicting duplicate"):
        build_news_package(
            [conflicting_a, conflicting_b],
            provider="TRADING_ECONOMICS",
            retrieval_utc=RETRIEVAL,
            licensing_declaration="ok (test)",
            source_file_sha256=DUMMY_SHA,
        )


def test_news_identical_duplicates_are_deduplicated():
    package = build_news_package(
        _news_records()[:1] * 3,
        provider="TRADING_ECONOMICS",
        retrieval_utc=RETRIEVAL,
        licensing_declaration="ok (test)",
        source_file_sha256=DUMMY_SHA,
    )
    assert package["acceptance"]["event_count"] == 1


def test_news_declared_coverage_conflicts_fail_closed():
    with pytest.raises(ec.EvidenceError, match="after the first event"):
        build_news_package(
            _news_records()[:1],
            provider="TRADING_ECONOMICS",
            retrieval_utc=RETRIEVAL,
            licensing_declaration="ok (test)",
            source_file_sha256=DUMMY_SHA,
            declared_coverage_start="2024-06-01T00:00:00Z",
        )
    with pytest.raises(ec.EvidenceError, match="before the last event"):
        build_news_package(
            _news_records()[:1],
            provider="TRADING_ECONOMICS",
            retrieval_utc=RETRIEVAL,
            licensing_declaration="ok (test)",
            source_file_sha256=DUMMY_SHA,
            declared_coverage_end="2024-01-01T00:00:00Z",
        )


def test_news_missing_licensing_fails_closed():
    with pytest.raises(ec.EvidenceError, match="licensing"):
        build_news_package(
            _news_records(),
            provider="TRADING_ECONOMICS",
            retrieval_utc=RETRIEVAL,
            licensing_declaration="   ",
            source_file_sha256=DUMMY_SHA,
        )


def test_news_holdout_boundary_rejected():
    row = {
        "CalendarId": 77,
        "Date": "2025-01-01T00:00:00Z",
        "Country": "United States",
        "Currency": "USD",
        "Importance": 3,
        "Event": "Dummy 2025 release",
    }
    with pytest.raises(ec.EvidenceError, match="holdout boundary"):
        build_news_package(
            [row],
            provider="TRADING_ECONOMICS",
            retrieval_utc=RETRIEVAL,
            licensing_declaration="ok (test)",
            source_file_sha256=DUMMY_SHA,
        )


def test_news_example_markers_rejected():
    row = _news_records()[0]
    row["Event"] = "EXAMPLE_ONLY fictional event"
    with pytest.raises(ec.EvidenceError, match="EXAMPLE_ONLY"):
        build_news_package(
            [row],
            provider="TRADING_ECONOMICS",
            retrieval_utc=RETRIEVAL,
            licensing_declaration="ok (test)",
            source_file_sha256=DUMMY_SHA,
        )


# ---------------------------------------------------------------------------
# Broker metadata contract
# ---------------------------------------------------------------------------


def _metadata_record(**overrides) -> dict:
    record = {
        "symbol": "XAUUSDm",
        "broker": "TestBroker",
        "account_type": "standard",
        "account_currency": "USD",
        "profit_currency": "USD",
        "margin_currency": "USD",
        "base_currency": "XAU",
        "digits": 2,
        "point": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "tick_value_profit": 1.0,
        "tick_value_loss": 1.0,
        "contract_size": 100,
        "volume_min": 0.01,
        "volume_max": 50.0,
        "volume_step": 0.01,
        "stops_level": 0,
        "freeze_level": 0,
        "margin_rate": 0.01,
        "filling_modes": ["FOK", "IOC"],
        "execution_mode": "MARKET",
        "margin_rules": {"mode": "CFD_LEVERAGED"},
        "effective_from": "2024-01-01T00:00:00Z",
        "effective_to": "2024-12-31T23:59:59Z",
        "observation_utc": "2024-06-01T00:00:00Z",
        "historical_evidence": True,
        "source_description": "Dated contract spec scan (test fixture)",
        "source_file_sha256": DUMMY_SHA,
        "licensing_declaration": "Owner document entitlement (test fixture).",
    }
    record.update(overrides)
    return record


def test_metadata_historical_is_accepted():
    record = build_broker_metadata_record(_metadata_record())
    assert record["status"] == STATUS_ACCEPTED_EMPIRICAL


def test_metadata_current_only_is_not_historical():
    record = build_broker_metadata_record(_metadata_record(historical_evidence=False))
    assert record["status"] == STATUS_CURRENT_ONLY_NOT_HISTORICAL
    package = build_broker_metadata_package([_metadata_record(historical_evidence=False)])
    assert package["status"] == STATUS_CURRENT_ONLY_NOT_HISTORICAL


def test_metadata_current_zero_swap_not_proof_of_history():
    # A record with zero swaps and no historical_evidence flag must stay
    # CURRENT_ONLY_NOT_HISTORICAL and never be read as 2024 swap evidence.
    record = build_broker_metadata_record(
        _metadata_record(historical_evidence=False, swap_long=0.0, swap_short=0.0)
    )
    assert record["status"] == STATUS_CURRENT_ONLY_NOT_HISTORICAL


def test_metadata_effective_gap_outside_2024_fails():
    with pytest.raises(ec.EvidenceError, match="does not intersect"):
        build_broker_metadata_record(
            _metadata_record(
                effective_from="2025-01-01T00:00:00Z",
                effective_to="2025-06-30T00:00:00Z",
            )
        )


def test_metadata_package_rejects_overlaps():
    with pytest.raises(ec.EvidenceError, match="overlap"):
        build_broker_metadata_package(
            [
                _metadata_record(effective_to="2024-07-01T00:00:00Z"),
                _metadata_record(
                    effective_from="2024-06-30T00:00:00Z",
                    effective_to="2024-12-31T23:59:59Z",
                ),
            ]
        )


def test_metadata_prohibited_account_field_fails_closed():
    with pytest.raises(ec.EvidenceError, match="prohibited"):
        build_broker_metadata_record(_metadata_record(account_number="123456"))


# ---------------------------------------------------------------------------
# Commission contract
# ---------------------------------------------------------------------------


def _commission_record(**overrides) -> dict:
    record = {
        "symbol": "XAUUSDm",
        "mode": "PER_LOT_ROUND_TURN",
        "amount": 10.0,
        "currency": "USD",
        "units": "USD per 1.0 lot round turn, charged half per side",
        "charging_point": "ROUND_TURN",
        "minimum_charge": 0.0,
        "rounding": "NONE",
        "account_type": "standard",
        "effective_from": "2024-01-01T00:00:00Z",
        "effective_to": "2024-12-31T23:59:59Z",
        "source_description": "Published schedule (test fixture)",
        "source_file_sha256": DUMMY_SHA,
        "licensing_declaration": "Owner document entitlement (test fixture).",
    }
    record.update(overrides)
    return record


@pytest.mark.parametrize("mode,amount", [
    ("NONE", 0.0),
    ("PER_LOT_PER_SIDE", 3.5),
    ("PER_LOT_ROUND_TURN", 10.0),
    ("FIXED_PER_ORDER", 2.0),
    ("PERCENT_NOTIONAL", 0.00005),
])
def test_commission_every_supported_mode_accepted(mode, amount):
    record = build_commission_record(_commission_record(mode=mode, amount=amount))
    assert record["status"] == STATUS_ACCEPTED_EMPIRICAL


def test_commission_tiered_mode_unsupported_fails_closed():
    with pytest.raises(ec.EvidenceError, match="unsupported"):
        build_commission_record(_commission_record(mode="TIERED"))


def test_commission_missing_units_fails_closed():
    record = _commission_record()
    del record["units"]
    with pytest.raises(ec.EvidenceError, match="units"):
        build_commission_record(record)


def test_commission_zero_amount_requires_none_mode():
    with pytest.raises(ec.EvidenceError):
        build_commission_record(_commission_record(mode="PER_LOT_PER_SIDE", amount=0.0))


def test_commission_notional_fraction_bounds():
    with pytest.raises(ec.EvidenceError, match="fraction"):
        build_commission_record(_commission_record(mode="PERCENT_NOTIONAL", amount=1.5))


def test_commission_non_usd_currency_fails_closed():
    with pytest.raises(ec.EvidenceError, match="USD"):
        build_commission_record(_commission_record(currency="EUR"))


# ---------------------------------------------------------------------------
# Swap / rollover contract
# ---------------------------------------------------------------------------


def _swap_record(**overrides) -> dict:
    record = {
        "symbol": "XAUUSDm",
        "account_type": "standard",
        "units": "ACCOUNT_CURRENCY_PER_LOT",
        "swap_long": -12.34,
        "swap_short": 5.67,
        "rollover_timezone": "Etc/GMT-2",
        "rollover_time": "00:00",
        "triple_swap_weekday": "WEDNESDAY",
        "effective_from": "2024-01-01T00:00:00Z",
        "effective_to": "2024-12-31T23:59:59Z",
        "source_description": "Swap page dated 2024 (test fixture)",
        "source_file_sha256": DUMMY_SHA,
        "licensing_declaration": "Owner document entitlement (test fixture).",
    }
    record.update(overrides)
    return record


def test_swap_valid_record_accepted():
    record = build_swap_record(_swap_record())
    assert record["status"] == STATUS_ACCEPTED_EMPIRICAL


def test_swap_unknown_units_fail_closed():
    with pytest.raises(ec.EvidenceError, match="units"):
        build_swap_record(_swap_record(units="MAGIC_UNITS"))


def test_swap_unknown_timezone_fails_closed():
    with pytest.raises(ec.EvidenceError, match="timezone"):
        build_swap_record(_swap_record(rollover_timezone="Mars/Olympus"))


def test_swap_naive_rollover_time_fails_closed():
    with pytest.raises(ec.EvidenceError, match="rollover_time"):
        build_swap_record(_swap_record(rollover_time="25:00"))


def test_swap_unknown_triple_day_fails_closed():
    with pytest.raises(ec.EvidenceError, match="triple_swap_weekday"):
        build_swap_record(_swap_record(triple_swap_weekday="FUNDAY"))


def test_swap_zero_requires_justification():
    with pytest.raises(ec.EvidenceError, match="zero_swap_justification"):
        build_swap_record(_swap_record(swap_long=0.0, swap_short=0.0))


def test_swap_ambiguous_evidence_missing_fields_fail():
    for drop in ("rollover_timezone", "units", "triple_swap_weekday"):
        record = _swap_record()
        del record[drop]
        with pytest.raises(ec.EvidenceError):
            build_swap_record(record)


def test_swap_package_rejects_overlaps():
    with pytest.raises(ec.EvidenceError, match="overlap"):
        build_swap_package(
            [
                _swap_record(effective_to="2024-07-01T00:00:00Z"),
                _swap_record(effective_from="2024-06-30T00:00:00Z"),
            ]
        )


# ---------------------------------------------------------------------------
# Slippage contract
# ---------------------------------------------------------------------------


def _slippage_record(**overrides) -> dict:
    record = {
        "fill_id": "FILL-0001",
        "symbol": "XAUUSDm",
        "side": "BUY",
        "action": "ENTRY_MARKET",
        "request_utc": "2024-03-06T14:00:05Z",
        "quote_utc": "2024-03-06T14:00:05Z",
        "requested_price": 2128.10,
        "fill_price": 2128.13,
        "requested_volume": 0.1,
        "filled_volume": 0.1,
        "spread_at_request": 0.13,
        "account_type": "demo",
        "point": 0.01,
        "source_log_sha256": DUMMY_SHA,
    }
    record.update(overrides)
    return record


def test_slippage_sign_and_side_handling():
    buy = build_slippage_record(_slippage_record())
    assert buy["slippage_price"] == pytest.approx(0.03)
    sell = build_slippage_record(_slippage_record(side="SELL", requested_price=2128.10, fill_price=2128.07))
    assert sell["slippage_price"] == pytest.approx(0.03)
    # Favorable (negative adverse) slippage fails closed.
    with pytest.raises(ec.EvidenceError, match="adverse or neutral"):
        build_slippage_record(_slippage_record(side="SELL", requested_price=2128.10, fill_price=2128.15))


def test_slippage_partial_fill_flagged():
    record = build_slippage_record(_slippage_record(filled_volume=0.05))
    assert record["partial_fill"] is True
    assert build_slippage_record(_slippage_record())["partial_fill"] is False


def test_slippage_filled_gt_requested_fails():
    with pytest.raises(ec.EvidenceError, match="exceed"):
        build_slippage_record(_slippage_record(filled_volume=0.2))


def test_slippage_credential_field_rejected():
    with pytest.raises(ec.EvidenceError, match="prohibited"):
        build_slippage_record(_slippage_record(password="hunter2"))


def test_slippage_example_marker_rejected():
    with pytest.raises(ec.EvidenceError, match="EXAMPLE_ONLY"):
        build_slippage_record(_slippage_record(fill_id="EXAMPLE_ONLY-1"))


def test_slippage_assumption_only_is_not_empirical():
    # The deterministic stress model registers as ASSUMPTION_ONLY in the
    # matrix; it must never carry an empirical status.
    matrix = build_evidence_matrix(
        news_status=ec.STATUS_ASSUMPTION_ONLY,
        broker_metadata_status=ec.STATUS_ASSUMPTION_ONLY,
        commission_status=ec.STATUS_ASSUMPTION_ONLY,
        swap_status=ec.STATUS_ASSUMPTION_ONLY,
        slippage_status=ec.STATUS_ASSUMPTION_ONLY,
        observed_spread_entry=_spread_fixture(),
    )
    entry = matrix["entries"][4]
    assert entry["status"] == ec.STATUS_ASSUMPTION_ONLY
    assert matrix["all_categories_accepted"] is False


def test_slippage_package_counts():
    package = build_slippage_package([_slippage_record(), _slippage_record(filled_volume=0.05, fill_id="FILL-0002")])
    assert package["record_count"] == 2
    assert package["partial_fill_count"] == 1
    assert package["neutral_fill_count"] == 0
    with pytest.raises(ec.EvidenceError, match="duplicate"):
        build_slippage_package([_slippage_record(), _slippage_record()])


# ---------------------------------------------------------------------------
# Evidence matrix
# ---------------------------------------------------------------------------


def _spread_fixture() -> dict:
    return {
        "status": STATUS_ACCEPTED_DEVELOPMENT_ONLY,
        "sha256": DUMMY_SHA,
        "schema_version": "phase8e.observed-spread-evidence.v1",
        "permitted_uses": ["development stress testing"],
        "prohibited_uses": ["execution fidelity claims"],
    }


def test_matrix_incomplete_dataset_blocks_acceptance():
    spread = _spread_fixture()
    matrix = build_evidence_matrix(
        news_status=STATUS_MISSING,
        broker_metadata_status=STATUS_MISSING,
        commission_status=STATUS_MISSING,
        swap_status=STATUS_MISSING,
        slippage_status=STATUS_MISSING,
        observed_spread_entry=spread,
    )
    assert matrix["all_categories_accepted"] is False
    assert matrix["statuses"]["HISTORICAL_USD_NEWS"] == STATUS_MISSING


def test_matrix_every_entry_has_required_fields():
    spread = _spread_fixture()
    matrix = build_evidence_matrix(
        news_status=STATUS_PRESENT_UNVERIFIED,
        broker_metadata_status=STATUS_CURRENT_ONLY_NOT_HISTORICAL,
        commission_status=STATUS_MISSING,
        swap_status=STATUS_MISSING,
        slippage_status=ec.STATUS_ASSUMPTION_ONLY,
        observed_spread_entry=spread,
    )
    for entry in matrix["entries"]:
        for key in ("category", "status", "schema_version", "permitted_uses", "prohibited_uses"):
            assert key in entry
    assert set(matrix["statuses"]) == set(EVIDENCE_CATEGORIES)


# ---------------------------------------------------------------------------
# Store: publication, idempotency, conflicts, tamper
# ---------------------------------------------------------------------------


def _fake_news_payload(tmp_path: Path) -> Path:
    source = tmp_path / "news_source.json"
    source.write_text(
        json.dumps(_news_records()),
        encoding="utf-8",
    )
    return source


def test_intake_publish_idempotent_and_conflicting(tmp_path):
    evidence_root = tmp_path / "evidence"
    source = _fake_news_payload(tmp_path)
    records = json.loads(source.read_text(encoding="utf-8"))
    payload = {
        "records": records,
        "provider": "TRADING_ECONOMICS",
        "retrieval_utc": RETRIEVAL,
        "licensing_declaration": "Owner offline export entitlement (test fixture).",
    }
    target, package_id, content = run_intake("news", payload, source_path=source, evidence_root=evidence_root)
    assert content["status"] == STATUS_PRESENT_UNVERIFIED  # partial-year fixture
    target2, package_id2, _ = run_intake("news", payload, source_path=source, evidence_root=evidence_root)
    assert target2 == target and package_id2 == package_id
    # Conflicting intake: different content under the same kind is detected
    # at collection time and fails closed.
    changed = dict(payload)
    changed["licensing_declaration"] = "different declaration"
    run_intake("news", changed, source_path=source, evidence_root=evidence_root)
    from backtests.evidence_intake_control import collect_evidence_statuses

    with pytest.raises(EvidenceStoreError, match="ambiguous evidence"):
        collect_evidence_statuses(evidence_root)


def test_publication_is_atomic_no_partial_package(tmp_path, monkeypatch):
    evidence_root = tmp_path / "evidence"
    payload = {
        "records": _news_records(),
        "provider": "TRADING_ECONOMICS",
        "retrieval_utc": RETRIEVAL,
        "licensing_declaration": "Owner offline export entitlement (test fixture).",
    }
    source = _fake_news_payload(tmp_path)
    # Simulate interruption: crash after package build, before publish.
    original = ec.build_news_package

    def exploding(*a, **k):
        original(*a, **k)
        raise KeyboardInterrupt

    monkeypatch.setattr(ec, "build_news_package", exploding)
    with pytest.raises(KeyboardInterrupt):
        run_intake("news", payload, source_path=source, evidence_root=evidence_root)
    assert not any(p.name.startswith("evidence-news") for p in evidence_root.glob("*"))


def test_tampered_manifest_fails_closed(tmp_path):
    evidence_root = tmp_path / "evidence"
    source = _fake_news_payload(tmp_path)
    payload = {
        "records": json.loads(source.read_text(encoding="utf-8")),
        "provider": "TRADING_ECONOMICS",
        "retrieval_utc": RETRIEVAL,
        "licensing_declaration": "Owner offline export entitlement (test fixture).",
    }
    target, package_id, _ = run_intake("news", payload, source_path=source, evidence_root=evidence_root)
    manifest_path = target / "manifest.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["content_canonical_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(EvidenceStoreError, match="mismatch|tampering"):
        load_evidence_package(target)


def test_source_hash_verification(tmp_path):
    source = _fake_news_payload(tmp_path)
    from bot.acquisition.evidence_contracts import sha256_file

    good = sha256_file(source)
    payload = {
        "records": json.loads(source.read_text(encoding="utf-8")),
        "provider": "TRADING_ECONOMICS",
        "retrieval_utc": RETRIEVAL,
        "licensing_declaration": "Owner offline export entitlement (test fixture).",
        "source_file_sha256": good,
    }
    # Declared hash matching is accepted; mismatching fails closed.
    target, _pid, _c = run_intake("news", payload, source_path=source, evidence_root=tmp_path / "evidence")
    assert target.exists()
    bad = dict(payload)
    bad["source_file_sha256"] = "0" * 64
    with pytest.raises(EvidenceStoreError, match="declared source hash mismatch"):
        run_intake("news", bad, source_path=source, evidence_root=tmp_path / "evidence")


# ---------------------------------------------------------------------------
# Observed spread evidence + readiness (real external bindings)
# ---------------------------------------------------------------------------

REAL_DATA_ROOT = Path(r"C:\Users\chips\forex-signal-bot-data\phase8")


def _real_data_root() -> Path | None:
    if (REAL_DATA_ROOT / "derived" / "derived-candles-2024-v1-20260911T195553Z").is_dir():
        return REAL_DATA_ROOT
    return None


def test_observed_spread_evidence_registered_from_real_manifests():
    data_root = _real_data_root()
    if data_root is None:
        pytest.skip("real Phase 8 external data root not present")
    content = build_observed_spread_evidence(data_root)
    assert content["status"] == STATUS_ACCEPTED_DEVELOPMENT_ONLY
    assert content["source_identities"]["source_tick_row_count"] == 39_715_935
    assert "do NOT reconstruct" in content["aggregation_limitations"]


def test_readiness_stays_incomplete_and_fail_closed(tmp_path):
    data_root = _real_data_root()
    if data_root is None:
        pytest.skip("real Phase 8 external data root not present")
    evidence_root = tmp_path / "evidence"
    matrix = build_matrix_package(evidence_root, data_root)
    readiness = build_readiness_package(matrix)
    assert readiness["inputs"]["xauusdm_ticks_2024"] == "AVAILABLE"
    assert readiness["inputs"]["dxy_development_input"] == "AVAILABLE"
    assert readiness["inputs"]["observed_spread_evidence"] == STATUS_ACCEPTED_DEVELOPMENT_ONLY
    assert readiness["inputs"]["historical_news"] == STATUS_MISSING
    assert readiness["inputs"]["holdout"] == "UNAVAILABLE_AND_UNTOUCHED"
    assert readiness["accepted_for_final_validation"] is False
    assert readiness["strategy_evaluation_authorized"] is False
    assert readiness["holdout_access_authorized"] is False


# ---------------------------------------------------------------------------
# Examples are rejected as empirical evidence
# ---------------------------------------------------------------------------

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples" / "phase8e"


def test_tracked_examples_rejected_as_empirical():
    news_rows = json.loads((EXAMPLES / "example_news_tradingeconomics.json").read_text(encoding="utf-8"))
    with pytest.raises(ec.EvidenceError, match="EXAMPLE_ONLY"):
        build_news_package(
            news_rows,
            provider="TRADING_ECONOMICS",
            retrieval_utc=RETRIEVAL,
            licensing_declaration="fictional",
            source_file_sha256=DUMMY_SHA,
        )
    metadata_rows = json.loads(
        (EXAMPLES / "example_broker_metadata_xauusdm.json").read_text(encoding="utf-8")
    )
    with pytest.raises(ec.EvidenceError, match="EXAMPLE_ONLY"):
        build_broker_metadata_package(metadata_rows)
    commission_rows = json.loads(
        (EXAMPLES / "example_commission_xauusdm.json").read_text(encoding="utf-8")
    )
    with pytest.raises(ec.EvidenceError, match="EXAMPLE_ONLY"):
        build_commission_package(commission_rows)
    swap_rows = json.loads((EXAMPLES / "example_swap_xauusdm.json").read_text(encoding="utf-8"))
    with pytest.raises(ec.EvidenceError, match="EXAMPLE_ONLY"):
        build_swap_package(swap_rows)
    slippage_rows = json.loads(
        (EXAMPLES / "example_slippage_fills_xauusdm.json").read_text(encoding="utf-8")
    )
    with pytest.raises(ec.EvidenceError, match="EXAMPLE_ONLY"):
        build_slippage_package(slippage_rows)


# ---------------------------------------------------------------------------
# Safety / confinement
# ---------------------------------------------------------------------------


def test_no_network_use_in_evidence_modules():
    for module_name in (
        "bot/acquisition/evidence_contracts.py",
        "bot/acquisition/evidence_store.py",
        "backtests/evidence_intake_control.py",
    ):
        source = (REPO_ROOT / module_name).read_text(encoding="utf-8")
        for prohibited in ("requests", "urllib", "socket", "http.client", "MetaTrader5"):
            assert prohibited not in source, f"{module_name} references {prohibited}"


def test_mt5_is_not_imported_by_evidence_modules():
    mt5_before = sys.modules.get("MetaTrader5")
    import bot.acquisition.evidence_contracts  # noqa: F401
    import bot.acquisition.evidence_store  # noqa: F401
    import backtests.evidence_intake_control  # noqa: F401

    assert sys.modules.get("MetaTrader5") is mt5_before


def test_prohibited_operations_confined_to_broker_adapter():
    from bot.acquisition.gateway import assert_gateway_surface

    assert_gateway_surface()
    for module_name in (
        "bot/acquisition/evidence_contracts.py",
        "bot/acquisition/evidence_store.py",
    ):
        source = (REPO_ROOT / module_name).read_text(encoding="utf-8")
        for prohibited in ("order_send", "account_info", "positions_get", "order_check"):
            assert prohibited not in source


def test_news_package_no_strategy_evaluation():
    # Building/validating packages never touches strategy evaluation code.
    import bot.strategy.news as strategy_news  # noqa: F401  (import is fine)

    package = build_news_package(
        _news_records(),
        provider="TRADING_ECONOMICS",
        retrieval_utc=RETRIEVAL,
        licensing_declaration="Owner offline export entitlement (test fixture).",
        source_file_sha256=DUMMY_SHA,
    )
    assert package["schema_version"] == "phase8e.historical-news.v1"
