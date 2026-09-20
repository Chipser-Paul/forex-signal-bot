"""Phase 8F official-government USD news calendar CLI (zero-cost, fail-closed).

Subcommands:

- ``fetch``     retrieve official 2024 pages (Fed/BEA/Census; BLS recorded as
                blocked if the site refuses programmatic access), store raw
                snapshots outside Git without overwriting, normalize and
                publish the versioned official-news package.
- ``build``     offline rebuild from stored raw snapshots (owner may drop the
                official BLS schedule page into ``raw/`` after manual download).
- ``verify``    hash-verify the published package, re-parse every stored raw
                snapshot and re-check the deterministic canonical event hash.
- ``snapshot``  emit the news-filter snapshot document for the existing
                ``bot.execution.news_filter`` bridge (NEWS_EVENTS_PATH).

Raw snapshots live under ``<data-root>/official-news/raw``; the published
package lives under ``<data-root>/evidence`` next to the other Phase 8
evidence packages. All artifacts remain
``DEVELOPMENT_ONLY``/``DEVELOPMENT_INCOMPLETE`` — never profitability evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bot.acquisition.evidence_contracts import canonical_hash
from bot.acquisition.evidence_store import (
    EvidenceStoreError,
    build_evidence_package,
    load_evidence_package,
    publish_evidence_package,
)
from bot.acquisition.official_news import (
    APPROVED_SOURCES,
    OfficialNewsError,
    SOURCE_BEA,
    SOURCE_BLS,
    SOURCE_CENSUS,
    SOURCE_FEDERAL_RESERVE,
    make_blocked_snapshot,
    make_raw_snapshot,
    parse_bea_release_page,
    parse_bls_schedule,
    parse_census_calendar,
    parse_fomc_calendar,
    snapshot_content,
)

DEFAULT_DATA_ROOT = Path(r"C:\Users\chips\forex-signal-bot-data\phase8")
OFFICIAL_NEWS_ROOT_NAME = "official-news"
RAW_DIR_NAME = "raw"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
CENSUS_CALENDAR_URL = "https://www.census.gov/economic-indicators/calendar-listview-2024.html"
BLS_SCHEDULE_URL = "https://www.bls.gov/schedule/2024/home.htm"
BEA_RELEASES_SITEMAP = "https://www.bea.gov/releases/sitemap.xml"
FOMC_STATEMENT_URL_RE = re.compile(r"/newsevents/pressreleases/monetary\d{8}a1?\.htm")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _official_news_root(data_root: Path) -> Path:
    return data_root / OFFICIAL_NEWS_ROOT_NAME


def _raw_dir(data_root: Path) -> Path:
    return _official_news_root(data_root) / RAW_DIR_NAME


# ---------------------------------------------------------------------------
# Raw snapshot storage (never overwritten)
# ---------------------------------------------------------------------------


def _store_raw_snapshot(
    raw_dir: Path,
    *,
    source: str,
    url: str,
    content: bytes,
    status: str = "RETRIEVED",
    failure_reason: str = "",
    retrieved_at: datetime | None = None,
    acquisition: str = "AUTOMATED_RETRIEVAL",
) -> dict[str, Any]:
    """Store one raw snapshot file if absent; return its manifest record.

    The file name is content-addressed (hash-prefixed) so absolute paths and
    retrieval order never become identities. Existing snapshots are never
    overwritten; an identical re-fetch is a no-op. ``acquisition`` records
    how the bytes arrived (``AUTOMATED_RETRIEVAL`` or
    ``MANUAL_BROWSER_DOWNLOAD``); manual provenance is never passed off as
    automated retrieval.
    """

    raw_dir.mkdir(parents=True, exist_ok=True)
    retrieved_at = retrieved_at or _now_utc()
    digest = hashlib.sha256(content).hexdigest()
    safe_url = re.sub(r"[^A-Za-z0-9._-]+", "_", url.rsplit("/", 1)[-1] or url)[:60]
    file_name = f"{digest[:16]}-{safe_url}.raw"
    file_path = raw_dir / file_name
    if file_path.exists():
        existing = file_path.read_bytes()
        existing_digest = hashlib.sha256(existing).hexdigest()
        if existing_digest != digest:
            raise EvidenceStoreError(
                f"raw snapshot conflict for {url}: existing file hashes differently — refusing to overwrite"
            )
    else:
        tmp = file_path.with_suffix(".tmp")
        tmp.write_bytes(content)
        tmp.with_suffix(".raw")
        tmp.replace(file_path)
    return {
        "source": source,
        "url": url,
        "retrieved_at": _utc_iso(retrieved_at),
        "content_sha256": digest,
        "byte_size": len(content),
        "raw_file": file_name,
        "status": status,
        "failure_reason": failure_reason,
        "acquisition": acquisition,
    }


def _load_raw_records(raw_dir: Path) -> list[dict[str, Any]]:
    """Reconstruct raw-snapshot records from the stored sidecar manifests."""

    records: list[dict[str, Any]] = []
    sidecar_dir = raw_dir
    if not sidecar_dir.is_dir():
        return records
    for sidecar in sorted(sidecar_dir.glob("*.retrieval.json")):
        record = json.loads(sidecar.read_text(encoding="utf-8"))
        records.append(record)
    return records


def _write_retrieval_sidecar(raw_dir: Path, record: Mapping_like) -> None:
    name = str(record["raw_file"]).removesuffix(".raw")
    sidecar = raw_dir / f"{name}.retrieval.json"
    payload = json.dumps(dict(record), indent=2, sort_keys=True).encode("utf-8")
    tmp = sidecar.with_suffix(".tmp")
    tmp.write_bytes(payload)
    tmp.with_suffix(".json")
    tmp.replace(sidecar)


class Mapping_like(dict):
    pass


# ---------------------------------------------------------------------------
# Network fetch layer (read-only GET; failures recorded, never fabricated)
# ---------------------------------------------------------------------------


def _http_get(url: str, *, timeout: float = 20.0) -> bytes:
    import requests

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code} for {url}")
    return response.content


def _fetch_fomc(raw_dir: Path, *, year: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    # 1) calendars page
    try:
        content = _http_get(FOMC_CALENDAR_URL)
    except Exception as exc:
        record = _store_raw_snapshot(
            raw_dir,
            source=SOURCE_FEDERAL_RESERVE,
            url=FOMC_CALENDAR_URL,
            content=b"",
            status="RETRIEVAL_FAILED",
            failure_reason=str(exc)[:200],
        )
        _write_retrieval_sidecar(raw_dir, record)
        records.append(record)
        return records
    record = _store_raw_snapshot(
        raw_dir, source=SOURCE_FEDERAL_RESERVE, url=FOMC_CALENDAR_URL, content=content
    )
    _write_retrieval_sidecar(raw_dir, record)
    records.append(record)
    # 2) every 2024 statement press-release page (declaration of 2:00 p.m.)
    import html as html_mod

    text = html_mod.unescape(content.decode("utf-8", errors="replace"))
    year_heading = re.search(rf">\s*{year}\s+FOMC Meetings\s*<", text)
    if year_heading is None:
        return records
    window = text[year_heading.end():]
    next_heading = re.search(r">\s*20\d\d\s+FOMC Meetings\s*<", window)
    if next_heading is not None:
        window = window[: next_heading.start()]
    statement_urls = sorted(
        {
            f"https://www.federalreserve.gov{href}"
            for href in re.findall(r'href="(/newsevents/pressreleases/monetary\d{8}a1?\.htm)"', window)
        }
    )
    for url in statement_urls:
        try:
            page = _http_get(url)
        except Exception as exc:
            page_record = _store_raw_snapshot(
                raw_dir,
                source=SOURCE_FEDERAL_RESERVE,
                url=url,
                content=b"",
                status="RETRIEVAL_FAILED",
                failure_reason=str(exc)[:200],
            )
            _write_retrieval_sidecar(raw_dir, page_record)
            records.append(page_record)
            continue
        page_record = _store_raw_snapshot(
            raw_dir, source=SOURCE_FEDERAL_RESERVE, url=url, content=page
        )
        _write_retrieval_sidecar(raw_dir, page_record)
        records.append(page_record)
    return records


def _fetch_census(raw_dir: Path) -> list[dict[str, Any]]:
    try:
        content = _http_get(CENSUS_CALENDAR_URL)
    except Exception as exc:
        record = _store_raw_snapshot(
            raw_dir,
            source=SOURCE_CENSUS,
            url=CENSUS_CALENDAR_URL,
            content=b"",
            status="RETRIEVAL_FAILED",
            failure_reason=str(exc)[:200],
        )
        _write_retrieval_sidecar(raw_dir, record)
        return [record]
    record = _store_raw_snapshot(
        raw_dir, source=SOURCE_CENSUS, url=CENSUS_CALENDAR_URL, content=content
    )
    _write_retrieval_sidecar(raw_dir, record)
    return [record]


def _fetch_bls(raw_dir: Path) -> list[dict[str, Any]]:
    """Attempt the official BLS schedule; the site currently rejects
    programmatic access. The failure is recorded verbatim; the owner can
    manually save the page as ``BUREAU_OF_LABOR_STATISTICS.html`` in ``raw/``
    and re-run ``build``."""

    try:
        content = _http_get(BLS_SCHEDULE_URL)
    except Exception as exc:
        record = _store_raw_snapshot(
            raw_dir,
            source=SOURCE_BLS,
            url=BLS_SCHEDULE_URL,
            content=b"",
            status="RETRIEVAL_BLOCKED",
            failure_reason=str(exc)[:200],
        )
        _write_retrieval_sidecar(raw_dir, record)
        return [record]
    record = _store_raw_snapshot(
        raw_dir, source=SOURCE_BLS, url=BLS_SCHEDULE_URL, content=content
    )
    _write_retrieval_sidecar(raw_dir, record)
    return [record]


def _fetch_bea(raw_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        sitemap = _http_get(BEA_RELEASES_SITEMAP, timeout=30.0)
    except Exception as exc:
        record = _store_raw_snapshot(
            raw_dir,
            source=SOURCE_BEA,
            url=BEA_RELEASES_SITEMAP,
            content=b"",
            status="RETRIEVAL_FAILED",
            failure_reason=str(exc)[:200],
        )
        _write_retrieval_sidecar(raw_dir, record)
        records.append(record)
        return records
    record = _store_raw_snapshot(
        raw_dir, source=SOURCE_BEA, url=BEA_RELEASES_SITEMAP, content=sitemap
    )
    _write_retrieval_sidecar(raw_dir, record)
    records.append(record)
    locs = re.findall(rb"<loc>([^<]+)</loc>", sitemap)
    urls = sorted(
        {
            loc.decode("utf-8")
            for loc in locs
            if b"/news/2024/" in loc
            and (b"gross-domestic-product" in loc or b"personal-income-and-outlays" in loc)
        }
    )
    for url in urls:
        try:
            page = _http_get(url)
        except Exception as exc:
            page_record = _store_raw_snapshot(
                raw_dir,
                source=SOURCE_BEA,
                url=url,
                content=b"",
                status="RETRIEVAL_FAILED",
                failure_reason=str(exc)[:200],
            )
            _write_retrieval_sidecar(raw_dir, page_record)
            records.append(page_record)
            continue
        page_record = _store_raw_snapshot(raw_dir, source=SOURCE_BEA, url=url, content=page)
        _write_retrieval_sidecar(raw_dir, page_record)
        records.append(page_record)
    return records


# ---------------------------------------------------------------------------
# Parsing from stored records (offline, deterministic)
# ---------------------------------------------------------------------------


def _read_raw_content(raw_dir: Path, record: Mapping_like) -> bytes:
    if str(record.get("status")) != "RETRIEVED":
        return b""
    file_path = raw_dir / str(record.get("raw_file", ""))
    if not file_path.is_file():
        raise EvidenceStoreError(f"raw snapshot file missing: {record.get('raw_file')}")
    content = file_path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != str(record.get("content_sha256")):
        raise EvidenceStoreError(
            f"raw snapshot hash mismatch for {record.get('url')}: {digest} != {record.get('content_sha256')}"
        )
    return content


def _select_latest_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deterministic per-URL snapshot selection.

    Official pages can carry dynamic bytes (tracker noise) between fetches.
    When one URL was stored multiple times, the latest retrieval wins; ties
    break on the higher content hash. Every stored snapshot remains recorded
    for full provenance; only the chosen one feeds parsing.
    """

    chosen: dict[str, dict[str, Any]] = {}
    for record in records:
        if str(record.get("status")) != "RETRIEVED":
            continue
        url = str(record["url"])
        current = chosen.get(url)
        if current is None:
            chosen[url] = record
            continue
        key_new = (str(record.get("retrieved_at", "")), str(record.get("content_sha256", "")))
        key_cur = (str(current.get("retrieved_at", "")), str(current.get("content_sha256", "")))
        if key_new > key_cur:
            chosen[url] = record
    selected = [
        r
        for r in records
        if str(r.get("status")) != "RETRIEVED" or chosen.get(str(r["url"])) is r
    ]
    selected.sort(
        key=lambda r: (str(r.get("url", "")), str(r.get("content_sha256", "")))
    )
    return selected


def build_events_from_records(
    raw_dir: Path,
    records: list[dict[str, Any]],
    *,
    year: int,
    retrieved_at: str,
):
    """Deterministically parse all stored snapshots into events."""

    from bot.acquisition.official_news import OfficialNewsEvent  # local import for typing

    events: list[OfficialNewsEvent] = []

    selected = _select_latest_records(records)

    by_source: dict[str, list[dict[str, Any]]] = {}
    for record in selected:
        by_source.setdefault(str(record["source"]), []).append(record)

    corroborations: list[dict[str, Any]] = []

    fed_records = by_source.get(SOURCE_FEDERAL_RESERVE, [])
    for record in fed_records:
        content = _read_raw_content(raw_dir, record)
        if not content:
            continue
        url = str(record["url"])
        if url == FOMC_CALENDAR_URL:
            events.extend(
                parse_fomc_calendar(
                    content.decode("utf-8", errors="replace"),
                    year=year,
                    retrieved_at=retrieved_at,
                    raw_source_sha256=str(record["content_sha256"]),
                )
            )
        else:
            event = parse_fomc_statement_page(
                content.decode("utf-8", errors="replace"),
                page_url=url,
                year=year,
                retrieved_at=retrieved_at,
                raw_source_sha256=str(record["content_sha256"]),
            )
            if event is not None:
                # Statement pages CORROBORATE the calendar-derived decision
                # instants (same real-world event attested by two official
                # documents); they never add duplicate event records.
                corroborations.append(
                    {
                        "url": url,
                        "event_at_utc": event.event_at_utc,
                        "raw_source_sha256": str(record["content_sha256"]),
                    }
                )

    for record in by_source.get(SOURCE_BEA, []):
        content = _read_raw_content(raw_dir, record)
        if not content:
            continue
        url = str(record["url"])
        if url == BEA_RELEASES_SITEMAP:
            continue
        event = parse_bea_release_page(
            content.decode("utf-8", errors="replace"),
            page_url=url,
            retrieved_at=retrieved_at,
            raw_source_sha256=str(record["content_sha256"]),
        )
        if event is not None:
            events.append(event)

    for record in by_source.get(SOURCE_CENSUS, []):
        content = _read_raw_content(raw_dir, record)
        if not content:
            continue
        if str(record["url"]) == CENSUS_CALENDAR_URL:
            events.extend(
                parse_census_calendar(
                    content.decode("utf-8", errors="replace"),
                    year=year,
                    retrieved_at=retrieved_at,
                    raw_source_sha256=str(record["content_sha256"]),
                )
            )

    for record in by_source.get(SOURCE_BLS, []):
        content = _read_raw_content(raw_dir, record)
        if not content:
            continue
        events.extend(
            parse_bls_schedule(
                content.decode("utf-8", errors="replace"),
                year=year,
                retrieved_at=retrieved_at,
                raw_source_sha256=str(record["content_sha256"]),
            )
        )
    return events, corroborations


def parse_fomc_statement_page(
    html: str,
    *,
    page_url: str,
    year: int,
    retrieved_at: str,
    raw_source_sha256: str,
):
    """Cross-check a statement press-release page's declared release time.

    The calendars page supplies the meeting date; the statement page
    supplies the official "For release at 2:00 p.m. EST/EDT" declaration.
    Returns the event only when the page declares 2:00 p.m. — otherwise
    fails closed (a statement page without a time declaration is malformed
    evidence, not an event).
    """

    import html as html_mod
    from datetime import date as _date, time as _time

    from bot.acquisition.official_news import (
        CATEGORY_FOMC,
        FOMC_RELEASE_LOCAL_TIME,
        OFFICIAL_NEWS_SCHEMA_VERSION,
        OFFICIAL_SOURCE_LICENSE,
        SOURCE_FEDERAL_RESERVE,
        SOURCE_URLS,
        OfficialNewsEvent,
        _event_id,
        _local_iso,
        _utc_iso,
        resolve_new_york_instant,
    )

    text = html_mod.unescape(html)
    match = re.search(
        r"For\s+release\s+at\s+(\d{1,2}):(\d{2})\s*([ap])\.?\s*m\.?\s+(EST|EDT)",
        text,
        re.I,
    )
    if match is None:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if match.group(3).lower() == "p" and hour != 12:
        hour += 12
    if match.group(3).lower() == "a" and hour == 12:
        hour = 0
    declared = match.group(4).upper()
    url_day = re.search(r"monetary(\d{4})(\d{2})(\d{2})a1?\.htm", page_url)
    if url_day is None:
        raise OfficialNewsError(f"FOMC statement URL lacks an encoded decision date: {page_url}")
    day = _date(int(url_day.group(1)), int(url_day.group(2)), int(url_day.group(3)))
    if day.year != year:
        return None
    local_time = _time(hour, minute)
    if local_time != FOMC_RELEASE_LOCAL_TIME:
        raise OfficialNewsError(
            f"FOMC statement page declares {local_time}, not the official 2:00 p.m. release"
        )
    when_utc, tz_label = resolve_new_york_instant(day, local_time, declared)
    return OfficialNewsEvent(
        event_id=_event_id(CATEGORY_FOMC, SOURCE_FEDERAL_RESERVE, when_utc),
        category=CATEGORY_FOMC,
        original_title="FOMC monetary policy decision and statement",
        source_agency=SOURCE_FEDERAL_RESERVE,
        source_url=SOURCE_URLS[SOURCE_FEDERAL_RESERVE],
        scheduled_local=_local_iso(day, local_time, tz_label),
        source_timezone=tz_label,
        event_at_utc=_utc_iso(when_utc),
        currency="USD",
        country="UNITED STATES",
        impact="HIGH",
        retrieved_at=retrieved_at,
        raw_source_sha256=raw_source_sha256,
        parser_version=OFFICIAL_NEWS_SCHEMA_VERSION,
        license=OFFICIAL_SOURCE_LICENSE,
    )


# ---------------------------------------------------------------------------
# Package assembly / publication
# ---------------------------------------------------------------------------


def build_and_publish(
    data_root: Path,
    records: list[dict[str, Any]],
    *,
    year: int,
    retrieval_utc: str,
) -> tuple[Path, str, dict[str, Any]]:
    from bot.acquisition.official_news import build_official_news_package

    raw_dir = _raw_dir(data_root)
    events, corroborations = build_events_from_records(
        raw_dir, records, year=year, retrieved_at=retrieval_utc
    )
    corroborations.sort(key=lambda item: str(item["url"]))
    calendar_instants = {e.event_at_utc for e in events if e.category == "FOMC_DECISION"}
    matched = sum(1 for c in corroborations if str(c["event_at_utc"]) in calendar_instants)
    corroboration_summary = {
        "statement_pages": len(corroborations),
        "matched_calendar_instants": matched,
        "records": corroborations,
    }
    if corroborations and matched != len(corroborations):
        raise OfficialNewsError(
            f"FOMC statement pages corroborate {matched}/{len(corroborations)} calendar instants — divergence fails closed"
        )
    package_content = build_official_news_package(
        year=year,
        events=events,
        raw_snapshots=records,
        retrieval_utc=retrieval_utc,
        corroboration=corroboration_summary,
    )
    package, package_id = build_evidence_package(
        kind="official_news",
        content=package_content,
        source_path=None,
    )
    target, published_id = publish_evidence_package(package, evidence_root=data_root / "evidence")
    return target, published_id, package_content


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def cmd_fetch(args: argparse.Namespace) -> int:
    data_root = Path(args.data_root)
    raw_dir = _raw_dir(data_root)
    records: list[dict[str, Any]] = []
    records.extend(_fetch_fomc(raw_dir, year=args.year))
    records.extend(_fetch_census(raw_dir))
    records.extend(_fetch_bea(raw_dir))
    records.extend(_fetch_bls(raw_dir))
    # Bind the package to the complete stored record set (sidecars), so
    # fetch and build produce identical packages from the same inputs.
    records = _load_raw_records(raw_dir)
    # Determinism: the package's retrieval identity derives from the stored
    # snapshot records (immutable sidecars), never from wall-clock time, so
    # repeated runs over the same inputs produce the same canonical hash.
    retrieval_utc = max(str(r.get("retrieved_at", "")) for r in records)
    try:
        target, package_id, content = build_and_publish(
            data_root, records, year=args.year, retrieval_utc=retrieval_utc
        )
    except (EvidenceStoreError, OfficialNewsError) as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1
    print(f"raw snapshots stored under {raw_dir} ({len(records)} records)")
    print(f"published official-news package {package_id} at {target}")
    print(json.dumps(content["category_counts"], indent=2, sort_keys=True))
    print(f"status: {content['status']}")
    if content["coverage_gaps"]:
        print("coverage gaps:")
        for gap in content["coverage_gaps"]:
            print(f"  - {gap}")
    return 0


_BLS_DENIAL_MARKERS = re.compile(
    r"captcha|access denied|unusual traffic|verify you are|enable javascript|"
    r"just a moment|request blocked",
    re.I,
)


def _validate_owner_bls(content: bytes) -> None:
    """Fail-closed authenticity gate for the manually downloaded BLS page.

    Rejects denial/CAPTCHA/browser-error pages and pages without the BLS
    schedule identity before any bytes enter the raw store. The owner file
    itself is never modified.
    """

    if not content:
        raise OfficialNewsError("owner BLS file is empty")
    if _BLS_DENIAL_MARKERS.search(content.decode("utf-8", errors="replace")):
        raise OfficialNewsError(
            "owner BLS file looks like an access-denial/CAPTCHA page; refusing to ingest"
        )
    text = content.decode("utf-8", errors="replace")
    if "Schedule of" not in text or "Eastern Time" not in text:
        raise OfficialNewsError(
            "owner BLS file lacks the official BLS schedule identity (Schedule of … / Eastern Time)"
        )
    if not any(
        pattern.search(text)
        for _, pattern in (
            ("nfp", re.compile(r"employment situation", re.I)),
            ("cpi", re.compile(r"consumer price index", re.I)),
            ("ppi", re.compile(r"producer price index", re.I)),
        )
    ):
        raise OfficialNewsError("owner BLS file contains none of the frozen BLS release categories")


def _ingest_owner_bls(raw_dir: Path, owner_file: Path) -> dict[str, Any] | None:
    """Ingest the manually downloaded BLS page with honest provenance.

    Validates authenticity, stores the bytes content-addressed (never
    overwriting), stamps MANUAL_BROWSER_DOWNLOAD, and leaves the owner file
    byte-for-byte untouched. Returns the stored record, or None when no
    owner file exists. Raises OfficialNewsError on rejected content.
    """

    if not owner_file.is_file():
        return None
    content = owner_file.read_bytes()
    _validate_owner_bls(content)
    record = _store_raw_snapshot(
        raw_dir,
        source=SOURCE_BLS,
        url=BLS_SCHEDULE_URL,
        content=content,
        status="RETRIEVED",
        failure_reason="",
        retrieved_at=datetime.fromtimestamp(owner_file.stat().st_mtime, tz=timezone.utc),
        acquisition="MANUAL_BROWSER_DOWNLOAD",
    )
    _write_retrieval_sidecar(raw_dir, record)
    return record


def cmd_build(args: argparse.Namespace) -> int:
    data_root = Path(args.data_root)
    raw_dir = _raw_dir(data_root)
    records = _load_raw_records(raw_dir)
    # Owner-dropped BLS file support: a manual browser download, ingested
    # with honest provenance (see _ingest_owner_bls).
    owner_bls = raw_dir / "BUREAU_OF_LABOR_STATISTICS.html"
    if owner_bls.is_file():
        try:
            record = _ingest_owner_bls(raw_dir, owner_bls)
        except OfficialNewsError as exc:
            print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
            return 1
        manual_digest = str((record or {}).get("content_sha256", ""))
        # Dedupe: drop only superseded successful BLS retrievals whose
        # stored bytes differ from the manual content (the automatic
        # retriever would have produced the identical snapshot had it not
        # been blocked). Retrieval-failure records are always retained as
        # historical evidence of the programmatic block.
        records = [
            r
            for r in records
            if r.get("source") != SOURCE_BLS
            or r.get("status") != "RETRIEVED"
            or str(r.get("content_sha256")) == manual_digest
        ]
        if record is not None:
            records.append(record)
        # Idempotent re-ingestion: the freshly stored record may duplicate
        # an identical sidecar loaded above; collapse by snapshot identity.
        seen: set[tuple[str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for r in records:
            key = (str(r.get("raw_file")), str(r.get("status")))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        records = deduped
    if not records:
        print("FAIL-CLOSED: no raw snapshots stored; run 'fetch' first", file=sys.stderr)
        return 1
    retrieval_utc = max(str(r.get("retrieved_at", "")) for r in records)
    try:
        target, package_id, content = build_and_publish(
            data_root, records, year=args.year, retrieval_utc=retrieval_utc
        )
    except (EvidenceStoreError, OfficialNewsError) as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1
    print(f"published official-news package {package_id} at {target}")
    print(f"status: {content['status']}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    data_root = Path(args.data_root)
    evidence_root = data_root / "evidence"
    matches = sorted(evidence_root.glob("evidence-official_news-v1-*"))
    if not matches:
        print("FAIL-CLOSED: no published official-news package found", file=sys.stderr)
        return 1
    failures = 0
    for package_dir in matches:
        try:
            package = load_evidence_package(package_dir)
        except EvidenceStoreError as exc:
            print(f"TAMPER/FAIL: {package_dir.name}: {exc}", file=sys.stderr)
            failures += 1
            continue
        content = package["content"]
        raw_dir = _raw_dir(data_root)
        records = [dict(s) for s in content.get("raw_snapshots", [])]
        try:
            events, _ = build_events_from_records(
                raw_dir,
                records,
                year=int(content["year"]),
                retrieved_at=str(content["retrieval_utc"]),
            )
        except (EvidenceStoreError, OfficialNewsError) as exc:
            print(f"FAIL: {package_dir.name}: raw re-parse failed: {exc}", file=sys.stderr)
            failures += 1
            continue
        from bot.acquisition.official_news import canonical_events_hash

        rebuilt = canonical_events_hash(events)
        if rebuilt != str(content.get("events_canonical_sha256")):
            print(
                f"FAIL: {package_dir.name}: canonical event hash mismatch "
                f"{rebuilt} != {content.get('events_canonical_sha256')}",
                file=sys.stderr,
            )
            failures += 1
            continue
        print(f"verified {package_dir.name}: {len(events)} events, status {content['status']}")
    return 1 if failures else 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    from bot.acquisition.official_news import build_news_snapshot_document

    data_root = Path(args.data_root)
    evidence_root = data_root / "evidence"
    matches = sorted(evidence_root.glob("evidence-official_news-v1-*"))
    if not matches:
        print("FAIL-CLOSED: no published official-news package found", file=sys.stderr)
        return 1
    if len(matches) > 1:
        # Same deterministic succession as the evidence matrix: coverage
        # (stable event-set size), then accepted status, then package id.
        # Never lexicographic id order — content-addressed ids carry no
        # semantics and the most complete verified revision must win.
        candidates: list[tuple[int, int, str, Path]] = []
        for path in matches:
            try:
                pkg = load_evidence_package(path)
            except EvidenceStoreError as exc:
                print(f"TAMPER/FAIL: {path.name}: {exc}", file=sys.stderr)
                return 1
            content = pkg["content"]
            ids = {str(e.get("event_id")) for e in content.get("events", [])}
            accepted = content.get("status") in {"ACCEPTED_EMPIRICAL", "ACCEPTED_DEVELOPMENT_ONLY"}
            candidates.append((len(ids), 1 if accepted else 0, str(pkg["manifest"]["package_id"]), path))
        candidates.sort()
        chosen_path = candidates[-1][3]
        if len(matches) > 1:
            print(f"NOTE: multiple official-news packages present; selected {chosen_path.name}", file=sys.stderr)
    else:
        chosen_path = matches[0]
    package = load_evidence_package(chosen_path)
    document = build_news_snapshot_document(package["content"])
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 8F official news calendar control")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch")
    fetch.add_argument("--year", type=int, default=2024)
    fetch.set_defaults(func=cmd_fetch)

    build = sub.add_parser("build")
    build.add_argument("--year", type=int, default=2024)
    build.set_defaults(func=cmd_build)

    sub.add_parser("verify").set_defaults(func=cmd_verify)
    sub.add_parser("snapshot").set_defaults(func=cmd_snapshot)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
