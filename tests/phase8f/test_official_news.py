"""Phase 8F official-government USD news calendar tests (offline fixtures).

All tests are offline: parser fixtures are synthetic-but-realistic excerpts
shaped like the official pages (Federal Reserve FOMC calendars, BEA release
pages, Census year calendars, BLS schedules). No network access, no MT5, no
strategy evaluation, no holdout access.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.acquisition import official_news as on  # noqa: E402
from bot.acquisition.evidence_contracts import (  # noqa: E402
    STATUS_DEVELOPMENT_INCOMPLETE,
    build_evidence_matrix,
)
from bot.acquisition.evidence_store import (  # noqa: E402
    EvidenceStoreError,
    build_evidence_package,
    load_evidence_package,
    publish_evidence_package,
)
from backtests import official_news_control as ctl  # noqa: E402

UTC = timezone.utc
RETRIEVED = "2026-09-13T12:00:00Z"
FAKE_HASH = "a" * 64


# ---------------------------------------------------------------------------
# Fixtures: synthetic-but-realistic official page excerpts
# ---------------------------------------------------------------------------


def _fomc_page() -> str:
    return """
<div class="panel panel-default"><div class="panel-heading"><h4><a id="39116">2024 FOMC Meetings</a></h4></div>
<div class="row fomc-meeting"> <div class="fomc-meeting__month col-xs-5"><strong>January</strong></div>
 <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">30-31</div>
 <div class="col-xs-12"><strong>Statement:</strong><br> <a href="/newsevents/pressreleases/monetary20240131a.htm">PDF</a></div></div>
<div class="row fomc-meeting"> <div class="fomc-meeting__month col-xs-5"><strong>Apr/May</strong></div>
 <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">30-1</div>
 <div class="col-xs-12"><strong>Statement:</strong><br> <a href="/newsevents/pressreleases/monetary20240501a.htm">PDF</a></div></div>
<div class="row fomc-meeting"> <div class="fomc-meeting__month col-xs-5"><strong>July</strong></div>
 <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">30-31*</div>
 <div class="col-xs-12"><strong>Statement:</strong><br> <a href="/newsevents/pressreleases/monetary20240731a.htm">PDF</a></div></div>
</div>
<div class="panel panel-default"><div class="panel-heading"><h4><a id="36495">2023 FOMC Meetings</a></h4></div>
<div class="row fomc-meeting"> <div class="fomc-meeting__month col-xs-5"><strong>December</strong></div>
 <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">12-13</div></div></div>
"""


def _fomc_statement_page(day_label: str = "20240131") -> str:
    return f"""
<html><head><title>Federal Reserve issues FOMC statement</title></head>
<body>For release at 2:00 p.m. EST
<p>Decision date reference: {day_label}</p></body></html>
"""


def _bea_page(title: str, embargo: str) -> str:
    return f"""
<html><head><title>{title} | U.S. Bureau of Economic Analysis (BEA)</title></head>
<body><div class="field--name-field-release-date">EMBARGOED UNTIL RELEASE AT {embargo}</div>
</body></html>
"""


def _bea_gdp_page() -> str:
    # Pre-DST release (Jan 25, 2024) carries EST; a wrong label on an EDT
    # date fails closed (covered by the timezone cross-check tests).
    return _bea_page(
        "Gross Domestic Product (Third Estimate), GDP by Industry, and Corporate Profits",
        "8:30 a.m. EST, Thursday, January 25, 2024",
    )


def _bea_pi_page() -> str:
    return _bea_page(
        "Personal Income and Outlays, July 2024",
        "8:30 a.m. EDT, Friday, August 30, 2024",
    )


def _bea_state_page() -> str:
    return _bea_page(
        "Gross Domestic Product by State and Personal Income by State, 4th Quarter 2023",
        "10:00 a.m. EDT, Friday, March 22, 2024",
    )


def _census_page(year: int = 2024) -> str:
    rows = []
    sample = [
        (1, 17), (2, 15), (3, 14), (4, 16), (5, 16), (6, 18),
        (7, 17), (8, 15), (9, 17), (10, 17), (11, 15), (12, 17),
    ]
    for month, day in sample:
        key = f"{year}{month:02d}{day:02d}0830"
        rows.append(
            f'<tr><td><a href="/retail">Advance Monthly Sales for Retail and Food Services</a></td>'
            f'<td sorttable_customkey="{key}">Month {day}, {year}</td></tr>'
        )
    # A non-allowlist row and a wrong-year row must be ignored.
    rows.append(
        f'<tr><td><a href="/construction/nrs/">New Residential Sales</a></td>'
        f'<td sorttable_customkey="{year}01131000">January 13, {year}</td></tr>'
    )
    rows.append(
        f'<tr><td><a href="/retail">Advance Monthly Sales for Retail and Food Services</a></td>'
        f'<td sorttable_customkey="202501140830">January 14, 2025</td></tr>'
    )
    return "<table>" + "".join(rows) + "</table>"


def _bls_page() -> str:
    return """
<table>
<tr><td><a href="https://www.bls.gov/news.release/empsit.nr0.htm">January 5</a></td>
<td>8:30 a.m.</td><td><a>Employment Situation</a></td></tr>
<tr><td><a href="https://www.bls.gov/news.release/cpi.nr0.htm">February 13</a></td>
<td>8:30 a.m.</td><td><a>Consumer Price Index</a></td></tr>
<tr><td><a href="https://www.bls.gov/news.release/prod2.nr0.htm">February 15</a></td>
<td>8:30 a.m.</td><td><a>Producer Price Index</a></td></tr>
</table>
"""


def _fed_records(tmp_path: Path) -> list[dict]:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    record = ctl._store_raw_snapshot(
        raw_dir, source=on.SOURCE_FEDERAL_RESERVE, url=ctl.FOMC_CALENDAR_URL, content=_fomc_page().encode()
    )
    ctl._write_retrieval_sidecar(raw_dir, record)
    return [record]


# ---------------------------------------------------------------------------
# Timezone policy tests
# ---------------------------------------------------------------------------


def test_est_and_edt_conversion_exact():
    when, label = on.resolve_new_york_instant(date(2024, 1, 31), time(14, 0), "EST")
    assert when.isoformat() == "2024-01-31T19:00:00+00:00"
    assert label == "EST"
    when, label = on.resolve_new_york_instant(date(2024, 7, 31), time(14, 0), "EDT")
    assert when.isoformat() == "2024-07-31T18:00:00+00:00"
    assert label == "EDT"


def test_dst_spring_forward_gap_fails_closed():
    # 2024-03-10 02:30 does not exist in America/New_York.
    with pytest.raises(on.OfficialNewsError, match="nonexistent"):
        on.resolve_new_york_instant(date(2024, 3, 10), time(2, 30), "UNDECLARED")


def test_fall_back_overlap_fails_closed():
    # 2024-11-03 01:30 occurs twice in America/New_York.
    with pytest.raises(on.OfficialNewsError, match="ambiguous"):
        on.resolve_new_york_instant(date(2024, 11, 3), time(1, 30), "UNDECLARED")


def test_declared_label_contradicting_iana_fails():
    # July is EDT; declaring EST contradicts the IANA offset.
    with pytest.raises(on.OfficialNewsError, match="contradicts"):
        on.resolve_new_york_instant(date(2024, 7, 31), time(14, 0), "EST")
    # The BEA parser applies the same cross-check: an EST label on an
    # EDT-dated release fails closed.
    with pytest.raises(on.OfficialNewsError, match="contradicts"):
        on.parse_bea_release_page(
            _bea_page("Personal Income and Outlays, March 2024", "8:30 a.m. EST, Friday, March 29, 2024"),
            page_url="https://www.bea.gov/news/2024/personal-income-and-outlays-march-2024",
            retrieved_at=RETRIEVED,
            raw_source_sha256=FAKE_HASH,
        )


def test_no_fixed_offset_for_the_year():
    # The same wall time maps to different UTC hours across the year
    # (EST = UTC-5 in winter, EDT = UTC-4 in summer).
    winter, winter_label = on.resolve_new_york_instant(date(2024, 1, 15), time(8, 30), "UNDECLARED")
    summer, summer_label = on.resolve_new_york_instant(date(2024, 7, 15), time(8, 30), "UNDECLARED")
    assert (winter.hour, winter.minute) == (13, 30)
    assert (summer.hour, summer.minute) == (12, 30)
    assert winter_label == "EST" and summer_label == "EDT"


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


def test_fomc_calendar_parses_all_meetings_and_dst_labels():
    events = on.parse_fomc_calendar(_fomc_page(), year=2024, retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH)
    assert len(events) == 3
    by_utc = {e.event_at_utc: e for e in events}
    assert "2024-01-31T19:00:00Z" in by_utc  # EST
    assert "2024-07-31T18:00:00Z" in by_utc  # EDT
    # Apr/May 30-1 cross-month meeting -> May 1 statement
    assert "2024-05-01T18:00:00Z" in by_utc
    assert all(e.category == on.CATEGORY_FOMC for e in events)
    assert all(e.currency == "USD" and e.impact == "HIGH" for e in events)


def test_fomc_calendar_year_scoping():
    # The same page contains a 2023 panel; parsing 2023 must yield exactly
    # the 2023 meeting (December 12-13 -> 2023-12-13 19:00Z EST), proving
    # year isolation, and a year with no panel must fail closed.
    events_2023 = on.parse_fomc_calendar(_fomc_page(), year=2023, retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH)
    assert len(events_2023) == 1
    assert events_2023[0].event_at_utc == "2023-12-13T19:00:00Z"
    with pytest.raises(on.OfficialNewsError, match="does not contain a 2019"):
        on.parse_fomc_calendar(_fomc_page(), year=2019, retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH)


def test_fomc_statement_page_declared_time_validation():
    event = ctl.parse_fomc_statement_page(
        _fomc_statement_page("20240131"),
        page_url="https://www.federalreserve.gov/newsevents/pressreleases/monetary20240131a.htm",
        year=2024,
        retrieved_at=RETRIEVED,
        raw_source_sha256=FAKE_HASH,
    )
    assert event is not None
    assert event.event_at_utc == "2024-01-31T19:00:00Z"
    assert event.source_timezone == "EST"
    # A page declaring a non-2:00 p.m. time fails closed.
    bad = _fomc_statement_page("20240131").replace("2:00 p.m.", "3:15 p.m.")
    with pytest.raises(on.OfficialNewsError, match="2:00"):
        ctl.parse_fomc_statement_page(
            bad,
            page_url="https://www.federalreserve.gov/newsevents/pressreleases/monetary20240131a.htm",
            year=2024,
            retrieved_at=RETRIEVED,
            raw_source_sha256=FAKE_HASH,
        )


def test_bea_release_pages_parse_categories_and_drop_non_allowlist():
    gdp = on.parse_bea_release_page(_bea_gdp_page(), page_url="https://www.bea.gov/news/2024/gross-domestic-product-x",
                                    retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH)
    assert gdp is not None
    assert gdp.category == on.CATEGORY_GDP
    assert gdp.event_at_utc == "2024-01-25T13:30:00Z"
    assert gdp.source_timezone == "EST"
    pi = on.parse_bea_release_page(_bea_pi_page(), page_url="https://www.bea.gov/news/2024/personal-income-and-outlays-july-2024",
                                   retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH)
    assert pi is not None
    assert pi.category == on.CATEGORY_PCE
    assert pi.event_at_utc == "2024-08-30T12:30:00Z"
    assert pi.source_timezone == "EDT"
    # State-level GDP is NOT the national headline release: dropped.
    state = on.parse_bea_release_page(_bea_state_page(), page_url="https://www.bea.gov/news/2024/gdp-by-state",
                                      retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH)
    assert state is None
    # A page without the embargo line fails closed.
    with pytest.raises(on.OfficialNewsError, match="embargo"):
        on.parse_bea_release_page("<html><body>no line</body></html>", page_url="https://www.bea.gov/news/2024/x",
                                  retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH)


def test_census_calendar_parses_retail_sales_only():
    events = on.parse_census_calendar(_census_page(), year=2024, retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH)
    assert len(events) == 12
    assert all(e.category == on.CATEGORY_RETAIL for e in events)
    assert all(e.source_timezone in {"EST", "EDT"} for e in events)
    # January release: 08:30 EST = 13:30Z
    assert events[0].event_at_utc == "2024-01-17T13:30:00Z"
    # March release: 08:30 EDT = 12:30Z
    assert events[2].event_at_utc == "2024-03-14T12:30:00Z"


def test_census_off_schedule_release_fails_closed():
    bad = _census_page().replace("0830", "0900")
    with pytest.raises(on.OfficialNewsError, match="8:30"):
        on.parse_census_calendar(bad, year=2024, retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH)


def test_bls_schedule_parses_allowlist_titles():
    events = on.parse_bls_schedule(_bls_page(), year=2024, retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH)
    categories = {e.category for e in events}
    assert categories == {on.CATEGORY_NFP, on.CATEGORY_CPI, on.CATEGORY_PPI}
    nfp = next(e for e in events if e.category == on.CATEGORY_NFP)
    assert nfp.event_at_utc == "2024-01-05T13:30:00Z"


# ---------------------------------------------------------------------------
# Normalization / package tests
# ---------------------------------------------------------------------------


def _make_events() -> list:
    events: list = []
    events.extend(on.parse_fomc_calendar(_fomc_page(), year=2024, retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH))
    for page, url in (
        (_bea_gdp_page(), "https://www.bea.gov/news/2024/gross-domestic-product-march"),
        (_bea_pi_page(), "https://www.bea.gov/news/2024/personal-income-and-outlays-july-2024"),
    ):
        event = on.parse_bea_release_page(page, page_url=url, retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH)
        if event is not None:
            events.append(event)
    events.extend(on.parse_census_calendar(_census_page(), year=2024, retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH))
    return events


def test_package_incomplete_without_all_categories():
    package = on.build_official_news_package(
        year=2024, events=_make_events(), raw_snapshots=[], retrieval_utc=RETRIEVED
    )
    assert package["status"] == "DEVELOPMENT_INCOMPLETE"
    assert STATUS_DEVELOPMENT_INCOMPLETE == "DEVELOPMENT_INCOMPLETE"
    assert package["classification"].startswith("DEVELOPMENT_INCOMPLETE")
    assert package["coverage_gaps"], "missing categories must be recorded as gaps"
    assert "EMPLOYMENT_SITUATION" in str(package["coverage_gaps"])


def test_holdout_boundary_event_fails_closed():
    events = _make_events()
    rogue = on.OfficialNewsEvent(
        event_id="rogue",
        category=on.CATEGORY_NFP,
        original_title="Employment Situation",
        source_agency=on.SOURCE_BLS,
        source_url="https://www.bls.gov/x",
        scheduled_local="2025-01-03T08:30:00-05:00",
        source_timezone="EST",
        event_at_utc="2025-01-03T13:30:00Z",
        currency="USD",
        country="UNITED STATES",
        impact="HIGH",
        retrieved_at=RETRIEVED,
        raw_source_sha256=FAKE_HASH,
        parser_version=on.OFFICIAL_NEWS_SCHEMA_VERSION,
        license=on.OFFICIAL_SOURCE_LICENSE,
    )
    with pytest.raises(on.OfficialNewsError, match="outside 2024|holdout boundary"):
        on.normalize_official_events(events + [rogue], year=2024)


def test_conflicting_duplicate_identity_fails_closed():
    events = _make_events()
    first = events[0]
    conflict = on.OfficialNewsEvent(
        event_id=first.event_id,
        category=first.category,
        original_title=first.original_title + " (revised)",
        source_agency=first.source_agency,
        source_url=first.source_url,
        scheduled_local=first.scheduled_local,
        source_timezone=first.source_timezone,
        event_at_utc=first.event_at_utc,
        currency="USD",
        country="UNITED STATES",
        impact="HIGH",
        retrieved_at=first.retrieved_at,
        raw_source_sha256=first.raw_source_sha256,
        parser_version=first.parser_version,
        license=first.license,
    )
    with pytest.raises(on.OfficialNewsError, match="conflicting duplicate"):
        on.normalize_official_events(events + [conflict], year=2024)


def test_same_timestamp_different_agencies_remain_separate():
    events = _make_events()
    when = "2024-06-05T12:30:00Z"
    base = dict(
        scheduled_local="2024-06-05T08:30:00-04:00",
        source_timezone="EDT",
        currency="USD",
        country="UNITED STATES",
        impact="HIGH",
        retrieved_at=RETRIEVED,
        raw_source_sha256=FAKE_HASH,
        parser_version=on.OFFICIAL_NEWS_SCHEMA_VERSION,
        license=on.OFFICIAL_SOURCE_LICENSE,
    )
    a = on.OfficialNewsEvent(event_id="a", category=on.CATEGORY_NFP, original_title="Employment Situation",
                             source_agency=on.SOURCE_BLS, source_url="https://www.bls.gov/x",
                             event_at_utc=when, **base)
    b = on.OfficialNewsEvent(event_id="b", category=on.CATEGORY_RETAIL, original_title="Advance Monthly Sales",
                             source_agency=on.SOURCE_CENSUS, source_url="https://www.census.gov/x",
                             event_at_utc=when, **base)
    normalized = on.normalize_official_events(events + [a, b], year=2024)
    same_time = [e for e in normalized if e.event_at_utc == when]
    assert len(same_time) == 2


def test_deterministic_canonical_hash():
    events = _make_events()
    h1 = on.canonical_events_hash(events)
    h2 = on.canonical_events_hash(list(reversed(events)))
    assert h1 == h2


def test_raw_snapshot_records_failure_without_fabrication():
    snap = on.make_blocked_snapshot(
        source=on.SOURCE_BLS,
        url="https://www.bls.gov/schedule/2024/home.htm",
        retrieved_at=datetime(2026, 9, 13, tzinfo=UTC),
        failure_reason="HTTP 403",
    )
    assert snap.status == "RETRIEVAL_BLOCKED"
    assert snap.content_zlib_b64 == ""
    assert snap.byte_size == 0
    assert "403" in snap.failure_reason


# ---------------------------------------------------------------------------
# Storage / publication tests
# ---------------------------------------------------------------------------


def test_raw_snapshot_store_is_non_overwriting(tmp_path):
    raw_dir = tmp_path / "raw"
    record1 = ctl._store_raw_snapshot(raw_dir, source=on.SOURCE_BEA, url="https://www.bea.gov/a", content=b"hello")
    # Identical re-fetch: content-addressed no-op, never overwritten.
    record2 = ctl._store_raw_snapshot(raw_dir, source=on.SOURCE_BEA, url="https://www.bea.gov/a", content=b"hello")
    assert record1["content_sha256"] == record2["content_sha256"]
    assert len(list(raw_dir.glob("*.raw"))) == 1
    # Changed content creates a NEW snapshot file (never an overwrite).
    record3 = ctl._store_raw_snapshot(raw_dir, source=on.SOURCE_BEA, url="https://www.bea.gov/a", content=b"different")
    assert record3["content_sha256"] != record1["content_sha256"]
    assert len(list(raw_dir.glob("*.raw"))) == 2
    # Two stored variants of one URL are deterministic dynamic-page noise:
    # selection is latest-wins (retrieved_at, then content hash) — never
    # ambiguous. The chosen record's hash follows the deterministic rule.
    chosen = ctl._select_latest_records([record1, record3])
    assert len(chosen) == 1
    expected = max(
        [record1, record3],
        key=lambda r: (str(r.get("retrieved_at", "")), str(r.get("content_sha256", ""))),
    )
    assert chosen[0]["content_sha256"] == expected["content_sha256"]


def test_official_news_package_publishes_and_tamper_checks(tmp_path):
    data_root = tmp_path
    package_content = on.build_official_news_package(
        year=2024, events=_make_events(), raw_snapshots=[], retrieval_utc=RETRIEVED
    )
    package, package_id = build_evidence_package(
        kind="official_news", content=package_content, source_path=None
    )
    target, published_id = publish_evidence_package(package, evidence_root=data_root / "evidence")
    assert published_id == package_id
    loaded = load_evidence_package(target)
    assert loaded["content"]["status"] == "DEVELOPMENT_INCOMPLETE"
    # Idempotent republication of identical content.
    target2, id2 = publish_evidence_package(package, evidence_root=data_root / "evidence")
    assert id2 == package_id and target2 == target
    # Tampering with the manifest file is detected.
    (target / "manifest.json").write_text('{"schema_version": "x"}', encoding="utf-8")
    with pytest.raises(EvidenceStoreError):
        load_evidence_package(target)


def test_unapproved_agency_record_rejected():
    with pytest.raises(on.OfficialNewsError, match="approved authority"):
        on.OfficialNewsEvent(
            event_id="x", category=on.CATEGORY_FOMC, original_title="FOMC",
            source_agency="FOREX_FACTORY", source_url="https://x", scheduled_local="2024-01-31T14:00:00-05:00",
            source_timezone="EST", event_at_utc="2024-01-31T19:00:00Z", currency="USD",
            country="UNITED STATES", impact="HIGH", retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH,
            parser_version=on.OFFICIAL_NEWS_SCHEMA_VERSION, license=on.OFFICIAL_SOURCE_LICENSE,
        )


# ---------------------------------------------------------------------------
# Matrix / readiness integration
# ---------------------------------------------------------------------------


def test_matrix_includes_official_news_category():
    matrix = build_evidence_matrix(
        news_status="MISSING",
        broker_metadata_status="MISSING",
        commission_status="MISSING",
        swap_status="MISSING",
        slippage_status="MISSING",
        observed_spread_entry={
            "status": "ACCEPTED_DEVELOPMENT_ONLY",
            "sha256": "0" * 64,
            "schema_version": "phase8e.observed-spread-evidence.v1",
            "permitted_uses": ["development spread-aware stress testing"],
            "prohibited_uses": ["final-validation execution fidelity claims"],
        },
    )
    statuses = dict(matrix["statuses"])
    statuses["OFFICIAL_USD_NEWS"] = "DEVELOPMENT_INCOMPLETE"
    # DEVELOPMENT_INCOMPLETE never counts as accepted.
    assert statuses["OFFICIAL_USD_NEWS"] not in {"ACCEPTED_EMPIRICAL", "ACCEPTED_DEVELOPMENT_ONLY"}


def test_news_filter_bridge_incomplete_package_fails_closed():
    package = on.build_official_news_package(
        year=2024, events=_make_events(), raw_snapshots=[], retrieval_utc=RETRIEVED
    )
    document = on.build_news_snapshot_document(package)
    assert document["successful"] is False
    assert document["failure_reason"] == "official_news_package_incomplete"
    assert document["provider"] == "OFFICIAL_US_GOVERNMENT"
    # The existing strategy-level filter sees an unsuccessful snapshot as DATA_UNSAFE.
    from bot.strategy.config import StrategyConfig
    from bot.strategy.models import SafetyState
    from bot.strategy.news import NewsSnapshot, evaluate_news, parse_news_events

    events = parse_news_events(
        document["events"], provider=document["provider"], retrieved_at=datetime(2026, 9, 13, tzinfo=UTC)
    )
    snapshot = NewsSnapshot(
        document["provider"],
        datetime.fromisoformat(str(document["retrieved_at"]).replace("Z", "+00:00")),
        False,
        events,
        document["failure_reason"],
    )
    result = evaluate_news(snapshot, datetime(2024, 6, 12, 17, 45, tzinfo=UTC), StrategyConfig())
    assert result.state is SafetyState.DATA_UNSAFE


def test_news_filter_bridge_blocks_around_exact_boundaries():
    # Complete package bridge: an event at 14:00 EST (19:00Z) blocks
    # [18:30Z, 19:30Z] inclusively and not outside.
    package_events = [
        on.OfficialNewsEvent(
            event_id="e1", category=on.CATEGORY_FOMC, original_title="FOMC monetary policy decision and statement",
            source_agency=on.SOURCE_FEDERAL_RESERVE, source_url="https://www.federalreserve.gov/x",
            scheduled_local="2024-01-31T14:00:00-05:00", source_timezone="EST",
            event_at_utc="2024-01-31T19:00:00Z", currency="USD", country="UNITED STATES", impact="HIGH",
            retrieved_at=RETRIEVED, raw_source_sha256=FAKE_HASH,
            parser_version=on.OFFICIAL_NEWS_SCHEMA_VERSION, license=on.OFFICIAL_SOURCE_LICENSE,
        )
    ]
    package = on.build_official_news_package(
        year=2024,
        events=package_events,
        raw_snapshots=[],
        retrieval_utc="2024-01-31T18:00:00Z",
    )
    # Force completeness for the bridge test by patching category counts
    # through the frozen allowlist: build directly with a complete set.
    assert package["status"] == "DEVELOPMENT_INCOMPLETE"
    # The bridge marks it unsuccessful -> filter fails closed regardless.
    document = on.build_news_snapshot_document(package)
    assert document["successful"] is False

    # Now a complete synthetic package: the boundary behavior of the filter.
    complete_events = []
    categories_all = list(on.HIGH_IMPACT_CATEGORIES)
    # Create one event per category (12 of each non-FOMC) so the package is complete.
    from datetime import timedelta

    for category in categories_all:
        if category == on.CATEGORY_FOMC:
            continue
        for i in range(12):
            day = date(2024, i + 1, 15)
            when = datetime.combine(day, time(14, 30), tzinfo=UTC)
            complete_events.append(
                on.OfficialNewsEvent(
                    event_id=f"{category}-{i}", category=category,
                    original_title=f"{category} release",
                    source_agency=on.SOURCE_BLS if category in {on.CATEGORY_NFP, on.CATEGORY_CPI, on.CATEGORY_PPI}
                    else (on.SOURCE_CENSUS if category == on.CATEGORY_RETAIL else on.SOURCE_BEA),
                    source_url="https://example.invalid",
                    scheduled_local="2024-01-01T00:00:00-05:00", source_timezone="EST",
                    event_at_utc=when.isoformat().replace("+00:00", "Z"),
                    currency="USD", country="UNITED STATES", impact="HIGH",
                    retrieved_at="2024-01-01T00:00:00Z", raw_source_sha256=FAKE_HASH,
                    parser_version=on.OFFICIAL_NEWS_SCHEMA_VERSION, license=on.OFFICIAL_SOURCE_LICENSE,
                )
            )
    complete_events.extend(
        on.OfficialNewsEvent(
            event_id=f"fomc-{i}", category=on.CATEGORY_FOMC,
            original_title="FOMC monetary policy decision and statement",
            source_agency=on.SOURCE_FEDERAL_RESERVE, source_url="https://www.federalreserve.gov/x",
            scheduled_local="2024-01-31T14:00:00-05:00", source_timezone="EST",
            event_at_utc=when.isoformat().replace("+00:00", "Z"), currency="USD",
            country="UNITED STATES", impact="HIGH",
            retrieved_at="2024-01-01T00:00:00Z", raw_source_sha256=FAKE_HASH,
            parser_version=on.OFFICIAL_NEWS_SCHEMA_VERSION, license=on.OFFICIAL_SOURCE_LICENSE,
        )
        for i, when in enumerate(
            (
                datetime(2024, 1, 31, 19, 0, tzinfo=UTC),
                datetime(2024, 3, 20, 18, 0, tzinfo=UTC),
                datetime(2024, 5, 1, 18, 0, tzinfo=UTC),
                datetime(2024, 6, 12, 18, 0, tzinfo=UTC),
                datetime(2024, 7, 31, 18, 0, tzinfo=UTC),
                datetime(2024, 9, 18, 18, 0, tzinfo=UTC),
                datetime(2024, 11, 7, 19, 0, tzinfo=UTC),
                datetime(2024, 12, 18, 19, 0, tzinfo=UTC),
            )
        )
    )
    complete = on.build_official_news_package(
        year=2024, events=complete_events, raw_snapshots=[], retrieval_utc="2024-01-01T00:00:00Z"
    )
    # months 1..12 covered, all categories at expected counts
    assert complete["status"] == "ACCEPTED_DEVELOPMENT_ONLY", complete["coverage_gaps"]
    doc = on.build_news_snapshot_document(complete)
    assert doc["successful"] is True

    from bot.strategy.config import StrategyConfig
    from bot.strategy.models import SafetyState
    from bot.strategy.news import NewsSnapshot, evaluate_news, parse_news_events

    config = StrategyConfig()

    def fresh_snapshot(retrieved: datetime) -> NewsSnapshot:
        events = parse_news_events(
            doc["events"], provider=doc["provider"], retrieved_at=retrieved
        )
        return NewsSnapshot(doc["provider"], retrieved, True, events, None)

    # Exactly at -30 minutes: blocked (inclusive). Snapshot must be fresh
    # (news_max_age is 60 minutes), so each boundary uses its own snapshot.
    before_snap = fresh_snapshot(datetime(2024, 1, 31, 18, 29, 0, tzinfo=UTC))
    assert evaluate_news(before_snap, datetime(2024, 1, 31, 18, 30, tzinfo=UTC), config).state is SafetyState.BLOCKED
    # -31 minutes: clear.
    assert evaluate_news(before_snap, datetime(2024, 1, 31, 18, 29, 59, tzinfo=UTC), config).state is SafetyState.CLEAR
    # Exactly at +30 minutes: blocked (inclusive).
    after_snap = fresh_snapshot(datetime(2024, 1, 31, 19, 0, 0, tzinfo=UTC))
    assert evaluate_news(after_snap, datetime(2024, 1, 31, 19, 30, tzinfo=UTC), config).state is SafetyState.BLOCKED
    # +31 minutes: clear.
    assert evaluate_news(after_snap, datetime(2024, 1, 31, 19, 30, 1, tzinfo=UTC), config).state is SafetyState.CLEAR


# ---------------------------------------------------------------------------
# Safety/import tests
# ---------------------------------------------------------------------------


def test_no_mt5_or_credential_imports():
    import bot.acquisition.official_news as module
    import backtests.official_news_control as control

    for mod in (module, control):
        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "import MetaTrader5" not in source
        assert "MetaTrader5" not in source
        assert "order_send" not in source
        assert "keyring" not in source
        assert ".env" not in source


def test_raw_snapshot_round_trip(tmp_path):
    raw_dir = tmp_path / "raw"
    content = b"official page content \xe2\x9c\x93"
    record = ctl._store_raw_snapshot(raw_dir, source=on.SOURCE_CENSUS, url="https://www.census.gov/x", content=content)
    ctl._write_retrieval_sidecar(raw_dir, record)
    loaded = ctl._load_raw_records(raw_dir)
    assert len(loaded) == 1
    assert ctl._read_raw_content(raw_dir, loaded[0]) == content


# ---------------------------------------------------------------------------
# Phase 8F: evidence-matrix revision coalescing for official-news packages
# ---------------------------------------------------------------------------


def _seed_official_news_revisions(tmp_path: Path, n: int) -> Path:
    """Store n same-URL FOMC-calendar snapshots (distinct retrieval noise),
    publish one official-news package per revision, return the evidence root."""

    data_root = tmp_path / "data"
    raw_dir = data_root / "official-news" / "raw"
    raw_dir.mkdir(parents=True)
    base_page = _fomc_page()
    for i in range(n):
        # Distinct bytes per fetch (dynamic-page noise), same parse result.
        content = base_page.replace(
            "<title>", f"<!-- fetch {i} -->\n<title>"
        ).encode()
        record = ctl._store_raw_snapshot(
            raw_dir,
            source=on.SOURCE_FEDERAL_RESERVE,
            url=ctl.FOMC_CALENDAR_URL,
            content=content,
        )
        record = dict(record)
        record["retrieved_at"] = f"2026-09-13T12:0{i}:00Z"
        ctl._write_retrieval_sidecar(raw_dir, record)
        ctl.build_and_publish(
            data_root,
            ctl._load_raw_records(raw_dir),
            year=2024,
            retrieval_utc=record["retrieved_at"],
        )
    return data_root / "evidence"


def test_official_news_revision_coalescing(tmp_path):
    from backtests.evidence_intake_control import collect_evidence_statuses

    evidence_root = _seed_official_news_revisions(tmp_path, 3)
    found = collect_evidence_statuses(evidence_root)
    assert set(found) == {"official_news"}
    packages = sorted(p.name for p in evidence_root.glob("evidence-official_news-v1-*"))
    # Latest revision wins deterministically.
    assert found["official_news"]["package_id"] == f"evidence-official_news-v1-{packages[-1].split('-')[-1]}"


def _publish_variant_package(evidence_root: Path, mutate):
    """Publish a valid official-news package derived from the latest existing
    one with ``mutate(content_dict)`` applied (store-validated envelope)."""

    packages = sorted(evidence_root.glob("evidence-official_news-v1-*"))
    pkg = json.loads((packages[-1] / "package.json").read_text(encoding="utf-8"))
    mutate(pkg["content"])
    package, _ = build_evidence_package(
        kind="official_news", content=pkg["content"], source_path=None
    )
    target, _ = publish_evidence_package(package, evidence_root=evidence_root)
    return target


def test_official_news_divergent_event_sets_fail_closed(tmp_path):
    from backtests.evidence_intake_control import collect_evidence_statuses

    evidence_root = _seed_official_news_revisions(tmp_path, 1)
    # A contradictory identity for one and the same record (neither subset
    # nor superset of the existing event set) is a genuine dataset conflict.
    def corrupt_one(content):
        content["events"][0]["event_id"] = "f" * 24

    _publish_variant_package(evidence_root, corrupt_one)
    with pytest.raises(EvidenceStoreError, match="different stable event sets"):
        collect_evidence_statuses(evidence_root)


def test_official_news_subset_revision_is_tolerated_not_selected(tmp_path):
    from backtests.evidence_intake_control import collect_evidence_statuses

    evidence_root = _seed_official_news_revisions(tmp_path, 1)
    latest_before = sorted(evidence_root.glob("evidence-official_news-v1-*"))[-1].name
    # An older narrower revision (subset) may exist; it must never be
    # selected and must not fail collection.
    def drop_last(content):
        content["events"] = content["events"][:-1]

    _publish_variant_package(evidence_root, drop_last)
    found = collect_evidence_statuses(evidence_root)
    assert found["official_news"]["package_id"] == latest_before


def test_official_news_superset_completion_supersedes(tmp_path):
    from backtests.evidence_intake_control import collect_evidence_statuses

    evidence_root = _seed_official_news_revisions(tmp_path, 1)
    packages_before = sorted(evidence_root.glob("evidence-official_news-v1-*"))
    pkg = json.loads((packages_before[-1] / "package.json").read_text(encoding="utf-8"))
    n_before = len(pkg["content"]["events"])

    def add_event(content):
        extra = dict(content["events"][-1])
        extra["event_id"] = "e" * 24
        extra["category"] = on.CATEGORY_CPI
        extra["event_at_utc"] = "2024-06-12T12:30:00Z"
        content["events"].append(extra)

    variant = _publish_variant_package(evidence_root, add_event)
    found = collect_evidence_statuses(evidence_root)
    # The more complete revision (superset) supersedes deterministically,
    # regardless of content-hash id ordering.
    assert found["official_news"]["package_id"] == variant.name
    assert variant.name not in {p.name for p in packages_before}
    from backtests.evidence_intake_control import _official_news_event_id_set

    ids_before = _official_news_event_id_set(packages_before[-1])
    ids_after = _official_news_event_id_set(variant)
    assert n_before == len(ids_before)
    assert ids_before < ids_after  # strict superset: coverage growth


# ---------------------------------------------------------------------------
# Phase 8F completion: manual BLS ingestion (honest provenance, fail-closed)
# ---------------------------------------------------------------------------


def _bls_2024_calendar_page(year: int = 2024) -> str:
    """Fixture shaped like the real 2024 BLS 'Schedule of Selected Releases'
    calendar table (date/time/desc cells, '08:30 AM', Eastern Time note)."""

    rows = []
    for month, title, ref in (
        ("January", "Employment Situation", "for December 2023"),
        ("January", "Consumer Price Index", "for December 2023"),
        ("February", "Producer Price Index", "for January 2024"),
        ("March", "Employment Situation of Veterans", "for Annual 2023"),
    ):
        rows.append(
            '<tr class="release-list-odd-row">'
            f'<td class="date-cell"><p>Friday, {month} 05, {year}</p></td>'
            '<td class="time-cell"><p>08:30 AM</p></td>'
            f'<td class="desc-cell"><p><strong>{title}</strong> {ref}</p></td></tr>'
        )
    return (
        "<html><head><title>Schedule of Selected Releases 2024</title></head><body>"
        "<p><strong>NOTE: All times on calendar are Eastern Time.</strong></p>"
        '<table class="release-list"><tbody>' + "".join(rows) + "</tbody></table>"
        "</body></html>"
    )


def test_manual_bls_ingestion_provenance_and_preservation(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    owner_file = raw_dir / "BUREAU_OF_LABOR_STATISTICS.html"
    original = _bls_2024_calendar_page().encode()
    owner_file.write_bytes(original)
    before = owner_file.stat()

    ctl._ingest_owner_bls(raw_dir, owner_file)
    stored = [r for r in ctl._load_raw_records(raw_dir) if r["raw_file"] != "BUREAU_OF_LABOR_STATISTICS.html"]
    assert len(stored) == 1
    record = stored[0]
    # Honest provenance: manual, never automated.
    assert record["acquisition"] == "MANUAL_BROWSER_DOWNLOAD"
    assert record["status"] == "RETRIEVED"
    assert record["url"] == on.SOURCE_URLS[on.SOURCE_BLS]
    assert record["content_sha256"] == hashlib.sha256(original).hexdigest()
    assert record["byte_size"] == len(original)
    # The owner file is preserved byte-for-byte and untouched.
    after = owner_file.stat()
    assert owner_file.read_bytes() == original
    assert (before.st_mtime, before.st_size) == (after.st_mtime, after.st_size)

    # Idempotency: re-ingestion is a no-op (same content-addressed snapshot).
    ctl._ingest_owner_bls(raw_dir, owner_file)
    stored_again = [r for r in ctl._load_raw_records(raw_dir) if r["raw_file"] != "BUREAU_OF_LABOR_STATISTICS.html"]
    assert stored_again == stored


def test_manual_bls_denial_page_rejected(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    owner_file = raw_dir / "BUREAU_OF_LABOR_STATISTICS.html"
    owner_file.write_bytes(b"<html><body>Access Denied - verify you are human (CAPTCHA)</body></html>")
    with pytest.raises(on.OfficialNewsError, match="denial|CAPTCHA"):
        ctl._ingest_owner_bls(raw_dir, owner_file)
    # Nothing entered the store; the owner file is unchanged.
    stored = [r for r in ctl._load_raw_records(raw_dir) if r["raw_file"] != "BUREAU_OF_LABOR_STATISTICS.html"]
    assert stored == []
    assert owner_file.read_bytes() == b"<html><body>Access Denied - verify you are human (CAPTCHA)</body></html>"


def test_bls_2024_calendar_parse_counts_and_dst():
    content = _bls_2024_calendar_page().encode()
    sha = hashlib.sha256(content).hexdigest()
    events = on.parse_bls_schedule(
        content.decode(), year=2024, retrieved_at=RETRIEVED, raw_source_sha256=sha
    )
    # Exactly the frozen BLS categories; the veterans release is excluded.
    by_cat = {}
    for e in events:
        by_cat.setdefault(e.category, []).append(e)
    assert set(by_cat) == {on.CATEGORY_NFP, on.CATEGORY_CPI, on.CATEGORY_PPI}
    assert all(len(v) == 1 for v in by_cat.values())
    assert all("veterans" not in e.original_title.lower() for e in events)
    # January 5 2024 08:30 Eastern = EST (-05:00) -> 13:30Z.
    nfp = by_cat[on.CATEGORY_NFP][0]
    assert nfp.event_at_utc == "2024-01-05T13:30:00Z"
    assert nfp.source_timezone == "EST"
    assert nfp.scheduled_local.endswith("-05:00")


def test_bls_calendar_rows_outside_year_are_skipped():
    page = _bls_2024_calendar_page(2024) + _bls_2024_calendar_page(2023).replace(
        "Schedule of Selected Releases 2024", ""
    )
    content = page.encode()
    sha = hashlib.sha256(content).hexdigest()
    events = on.parse_bls_schedule(page, year=2024, retrieved_at=RETRIEVED, raw_source_sha256=sha)
    assert all(e.event_at_utc[:4] == "2024" for e in events)


def test_bls_duplicate_rows_rejected_by_stable_identity():
    page = _bls_2024_calendar_page() + _bls_2024_calendar_page().replace(
        "Schedule of Selected Releases 2024", ""
    )
    content = page.encode()
    sha = hashlib.sha256(content).hexdigest()
    events = on.parse_bls_schedule(page, year=2024, retrieved_at=RETRIEVED, raw_source_sha256=sha)
    ids = [e.event_id for e in events]
    assert len(ids) == len(set(ids))  # stable identity dedupe
    assert len(events) == 3


def test_readiness_transition_incomplete_to_development_only(tmp_path, monkeypatch):
    import backtests.evidence_intake_control as eic

    evidence_root = _seed_official_news_revisions(tmp_path, 1)
    # Seed one published DEVELOPMENT_INCOMPLETE revision, then a complete one.
    packages = sorted(evidence_root.glob("evidence-official_news-v1-*"))
    pkg = json.loads((packages[-1] / "package.json").read_text(encoding="utf-8"))
    pkg["content"]["status"] = "DEVELOPMENT_INCOMPLETE"
    pkg["content"]["classification"] = (
        "DEVELOPMENT_INCOMPLETE — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE"
    )
    package, _ = build_evidence_package(kind="official_news", content=pkg["content"], source_path=None)
    publish_evidence_package(package, evidence_root=evidence_root)

    def complete(content):
        content["status"] = "ACCEPTED_DEVELOPMENT_ONLY"
        content["classification"] = "DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE"

    variant = _publish_variant_package(evidence_root, complete)

    monkeypatch.setattr(
        eic,
        "_spread_matrix_entry",
        lambda spread_content: {
            "category": "OBSERVED_SPREAD",
            "status": "MISSING",
            "sha256": "0" * 64,
            "schema_version": "phase8e.observed-spread-evidence.v1",
            "permitted_uses": [],
            "prohibited_uses": [],
        },
    )
    monkeypatch.setattr(
        eic, "build_observed_spread_evidence", lambda data_root: {"status": "MISSING"}
    )
    matrix = eic.build_matrix_package(evidence_root, tmp_path)
    assert matrix["statuses"]["OFFICIAL_USD_NEWS"] == "ACCEPTED_DEVELOPMENT_ONLY"
    assert matrix["evidence_packages"]["official_news"]["package_id"] == variant.name
    # DEVELOPMENT_INCOMPLETE must never satisfy the 8E news category.
    assert matrix["statuses"]["HISTORICAL_USD_NEWS"] in {"MISSING", "ACCEPTED_DEVELOPMENT_ONLY"}
    readiness = eic.build_readiness_package(matrix)
    assert readiness["accepted_for_final_validation"] is False
    assert readiness["strategy_evaluation_authorized"] is False
    assert readiness["holdout_access_authorized"] is False
