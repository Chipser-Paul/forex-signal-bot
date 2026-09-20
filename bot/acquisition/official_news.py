"""Phase 8F zero-cost official-United-States-government news calendar pipeline.

Replaces paid/aggregator calendar providers with official U.S. government
sources only. Approved source authorities (preregistered):

- Federal Reserve: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
  plus official press-release pages (``For release at 2:00 p.m. EST/EDT``).
- Bureau of Economic Analysis: official ``/news/2024/...`` release pages with
  per-release embargo lines (``EMBARGOED UNTIL RELEASE AT 8:30 a.m. EST, ...``).
- U.S. Census Bureau: official year-scoped release calendar
  (``calendar-listview-2024.html``) with structured Eastern-time datetime keys.
- U.S. Bureau of Labor Statistics (release schedule pages): the adapter and
  parser are implemented and tested, but www.bls.gov currently rejects
  programmatic access; retrieval failures are recorded as raw retrieval
  records and the package is classified honestly as incomplete until the
  owner supplies the official file. Commercial substitutes are never used.

Scientific policy (frozen before any strategy evaluation; must not be tuned
against results): only the seven preregistered high-impact USD categories are
kept. The ±30-minute blackout semantics live in ``bot.strategy.news`` /
``bot.strategy.config`` and are NOT modified here.

Everything except the fetch helpers is offline; tests run from local
fixtures without network access. Raw source snapshots are stored outside Git
with SHA-256 hashes and are never overwritten.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")

# ---------------------------------------------------------------------------
# Frozen preregistered policy
# ---------------------------------------------------------------------------

OFFICIAL_NEWS_SCHEMA_VERSION = "phase8f.official-usd-news.v1"

SOURCE_FEDERAL_RESERVE = "FEDERAL_RESERVE"
SOURCE_BLS = "BUREAU_OF_LABOR_STATISTICS"
SOURCE_BEA = "BUREAU_OF_ECONOMIC_ANALYSIS"
SOURCE_CENSUS = "CENSUS_BUREAU"
APPROVED_SOURCES = (
    SOURCE_FEDERAL_RESERVE,
    SOURCE_BLS,
    SOURCE_BEA,
    SOURCE_CENSUS,
)

SOURCE_URLS = {
    SOURCE_FEDERAL_RESERVE: "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    SOURCE_BLS: "https://www.bls.gov/schedule/2024/home.htm",
    SOURCE_BEA: "https://www.bea.gov/news/2024/",
    SOURCE_CENSUS: "https://www.census.gov/economic-indicators/calendar-listview-2024.html",
}

# Frozen high-impact allowlist (preregistered validation-data policy).
CATEGORY_FOMC = "FOMC_DECISION"
CATEGORY_NFP = "EMPLOYMENT_SITUATION"
CATEGORY_CPI = "CONSUMER_PRICE_INDEX"
CATEGORY_PPI = "PRODUCER_PRICE_INDEX"
CATEGORY_GDP = "GDP_RELEASE"
CATEGORY_PCE = "PERSONAL_INCOME_OUTLAYS_CORE_PCE"
CATEGORY_RETAIL = "ADVANCE_RETAIL_SALES"

HIGH_IMPACT_CATEGORIES = (
    CATEGORY_FOMC,
    CATEGORY_NFP,
    CATEGORY_CPI,
    CATEGORY_PPI,
    CATEGORY_GDP,
    CATEGORY_PCE,
    CATEGORY_RETAIL,
)

# Expected 2024 release counts per category (weekly/monthly/quarterly
# cadence of the official schedules). The package stays DEVELOPMENT_INCOMPLETE
# while any category is below its expected count.
EXPECTED_CATEGORY_COUNTS: dict[str, int] = {
    CATEGORY_FOMC: 8,   # eight yearly meetings; statement on day two
    CATEGORY_NFP: 12,   # monthly Employment Situation
    CATEGORY_CPI: 12,   # monthly CPI
    CATEGORY_PPI: 12,   # monthly PPI
    CATEGORY_GDP: 12,   # quarterly estimates released monthly
    CATEGORY_PCE: 12,   # monthly Personal Income and Outlays
    CATEGORY_RETAIL: 12,# monthly Advance Monthly Sales
}

# Agency-specific event-title matchers (official agency categories only).
# Headline monthly Employment Situation (NFP) only; "Employment Situation
# of Veterans" (annual veterans statistics) is a different BLS release and
# must not match, exactly like BEA's state/county GDP exclusions.
_BLS_TITLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (CATEGORY_NFP, re.compile(r"employment situation(?!\s+of\s+veterans)", re.I)),
    (CATEGORY_CPI, re.compile(r"consumer price index", re.I)),
    (CATEGORY_PPI, re.compile(r"producer price index", re.I)),
)
_CENSUS_TITLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (CATEGORY_RETAIL, re.compile(r"advance monthly sales", re.I)),
)
# Headline GDP releases only; "GDP by State/County/Metro/Island area"
# releases are NOT the national headline release and must not match.
_BEA_TITLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (CATEGORY_GDP, re.compile(r"gross domestic product", re.I)),
    (CATEGORY_PCE, re.compile(r"personal income and outlays", re.I)),
)
_BEA_TITLE_EXCLUSIONS: tuple[re.Pattern[str], ...] = (
    re.compile(r"by state|by county|by metropolitan|puerto rico|guam|u\.s\. virgin|"
               r"northern mariana|american samoa|district of columbia", re.I),
)

DEV_INTERVAL_START = "2024-01-01T00:00:00Z"
DEV_INTERVAL_END = "2025-01-01T00:00:00Z"

# FOMC statement release time, declared by official press-release pages
# ("For release at 2:00 p.m. EST/EDT") and unchanged across 2024.
FOMC_RELEASE_LOCAL_TIME = time(14, 0)

OFFICIAL_SOURCE_LICENSE = (
    "United States government public-domain material: works of the U.S. "
    "federal government (including BLS, Federal Reserve, BEA and Census "
    "releases) are not subject to domestic copyright protection under 17 "
    "U.S.C. 105. Retrieved from official agency websites; no commercial "
    "calendar provider involved."
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
# Capitalized names, longest first so the alternation prefers full forms.
_MONTH_ALTERNATION = "|".join(
    sorted((name.capitalize() for name in _MONTHS), key=lambda name: -len(name))
)


class OfficialNewsError(ValueError):
    """Raised for malformed, ambiguous or unsupported official-news input."""


# ---------------------------------------------------------------------------
# Typed immutable records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawSourceSnapshot:
    source: str
    url: str
    retrieved_at: str  # ISO-8601 UTC
    content_sha256: str
    byte_size: int
    content_zlib_b64: str = ""
    status: str = "RETRIEVED"  # RETRIEVED | RETRIEVAL_BLOCKED | RETRIEVAL_FAILED
    failure_reason: str = ""

    def __post_init__(self) -> None:
        if self.source not in APPROVED_SOURCES:
            raise OfficialNewsError(f"raw snapshot source {self.source!r} is not an approved authority")
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_sha256):
            raise OfficialNewsError("raw snapshot content_sha256 must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True)
class OfficialNewsEvent:
    """Normalized high-impact USD event with full official provenance."""

    event_id: str
    category: str
    original_title: str
    source_agency: str
    source_url: str
    scheduled_local: str  # ISO-8601 with the America/New_York offset
    source_timezone: str  # EST / EDT (as declared by the source or resolved)
    event_at_utc: str  # ISO-8601 Z
    currency: str  # fixed USD
    country: str  # fixed UNITED STATES
    impact: str  # fixed HIGH
    retrieved_at: str
    raw_source_sha256: str
    parser_version: str
    license: str

    def __post_init__(self) -> None:
        if self.category not in HIGH_IMPACT_CATEGORIES:
            raise OfficialNewsError(f"event category {self.category!r} is outside the frozen allowlist")
        if self.source_agency not in APPROVED_SOURCES:
            raise OfficialNewsError(f"event agency {self.source_agency!r} is not an approved authority")
        if self.currency != "USD" or self.impact != "HIGH" or self.country != "UNITED STATES":
            raise OfficialNewsError("official events are USD/UNITED STATES/HIGH by construction")


# ---------------------------------------------------------------------------
# Timezone handling (explicit DST policy)
# ---------------------------------------------------------------------------


def resolve_new_york_instant(day: date, local: time, tz_label: str) -> tuple[datetime, str]:
    """Convert an official America/New_York local time to UTC, DST-aware.

    ``tz_label`` must be the timezone the official source declared (``EST``
    or ``EDT``) or ``UNDECLARED`` when the archive carries no label. The
    conversion always uses the real IANA rules (never a fixed offset for the
    year). Fail-closed policy:

    - a declared EST/EDT that contradicts the IANA offset for that wall time
      fails (e.g. an ``EST`` stamp on a July date);
    - an ``UNDECLARED`` stamp resolves via the IANA rules only when the wall
      time is unambiguous;
    - nonexistent local times (spring-forward gap) and ambiguous local times
      (fall-back overlap) fail closed in both modes.
    """

    if tz_label not in {"EST", "EDT", "UNDECLARED"}:
        raise OfficialNewsError(f"unknown source timezone label {tz_label!r}")
    naive = datetime.combine(day, local)
    # DST gap (nonexistent wall time) detection: the fold-0 interpretation
    # must round-trip to the same wall time.
    fold0 = naive.replace(tzinfo=NEW_YORK, fold=0)
    round_trip = fold0.astimezone(UTC).astimezone(NEW_YORK)
    if round_trip.replace(tzinfo=None) != naive:
        raise OfficialNewsError(
            f"local time {naive} is nonexistent in America/New_York (DST gap) and fails closed"
        )
    # Ambiguity (fall-back overlap) detection: the two fold interpretations
    # must denote the same instant.
    fold1 = naive.replace(tzinfo=NEW_YORK, fold=1)
    if fold0.astimezone(UTC) != fold1.astimezone(UTC):
        raise OfficialNewsError(
            f"local time {naive} is ambiguous in America/New_York (fall-back overlap) and fails closed"
        )
    candidate = fold0
    actual = candidate.utcoffset()
    actual_minutes = int(actual.total_seconds() // 60) if actual is not None else 0
    effective_label = "EST" if actual_minutes == -300 else "EDT" if actual_minutes == -240 else "UNK"
    if tz_label in {"EST", "EDT"}:
        expected_minutes = -300 if tz_label == "EST" else -240
        if actual is None or actual_minutes != expected_minutes:
            raise OfficialNewsError(
                f"declared timezone {tz_label} contradicts the IANA America/New_York offset {actual}"
            )
    elif effective_label == "UNK":
        raise OfficialNewsError("America/New_York offset is neither EST nor EDT; refusing to guess")
    return candidate.astimezone(UTC), effective_label


def _event_id(category: str, agency: str, when_utc: datetime) -> str:
    material = f"{agency}|{category}|{when_utc.astimezone(UTC).isoformat().replace('+00:00', 'Z')}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _utc_iso(when: datetime) -> str:
    return when.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _local_iso(day: date, local: time, tz_label: str) -> str:
    offset_hours = -5 if tz_label == "EST" else -4
    return datetime.combine(day, local).isoformat() + f"-0{abs(offset_hours)}:00"


def _match_category(
    patterns: tuple[tuple[str, re.Pattern[str]], ...], title: str
) -> str | None:
    for category, pattern in patterns:
        if pattern.search(title):
            return category
    return None


# ---------------------------------------------------------------------------
# Federal Reserve adapter (FOMC calendars page)
# ---------------------------------------------------------------------------

_FOMC_MEETING_RE = re.compile(
    rf'fomc-meeting__month[^>]*>\s*<strong>({ _MONTH_ALTERNATION })'
    rf'(?:\s*/\s*({ _MONTH_ALTERNATION }))?\s*</strong>\s*</div>\s*'
    r'<div class="fomc-meeting__date[^"]*">\s*(\d{1,2})\s*-\s*(\d{1,2})\*?\s*</div>'
)


def parse_fomc_calendar(
    html: str,
    *,
    year: int,
    retrieved_at: str,
    raw_source_sha256: str,
) -> tuple[OfficialNewsEvent, ...]:
    """Parse the official FOMC calendars page for ``year`` decision days.

    The page lists meetings per year heading (``>2024 FOMC Meetings<``) as
    ``fomc-meeting__month``/``fomc-meeting__date`` pairs (``27-28``). The
    monetary-policy statement is released on the second meeting day at
    2:00 p.m. Eastern — the exact instant the official press-release pages
    declare (``For release at 2:00 p.m. EST/EDT``). The EST/EDT label is
    derived from the IANA rules and cross-checked; the page content itself
    is HTML-unescaped before matching (it contains raw ``&amp;`` entities).
    """

    import html as html_mod

    text = html_mod.unescape(html)
    year_heading = re.search(rf">\s*{year}\s+FOMC Meetings\s*<", text)
    if year_heading is None:
        raise OfficialNewsError(f"FOMC calendars page does not contain a {year} meetings heading")
    window = text[year_heading.end():]
    next_heading = re.search(r">\s*20\d\d\s+FOMC Meetings\s*<", window)
    if next_heading is not None:
        window = window[: next_heading.start()]
    events: list[OfficialNewsEvent] = []
    for month_name, second_month_name, first_day, second_day in _FOMC_MEETING_RE.findall(window):
        month = _MONTHS[month_name.lower()]
        # A meeting spanning two calendar months (e.g. Apr 30 - May 1) puts
        # the statement day in the second month when it precedes the first.
        if second_month_name and int(second_day) < int(first_day):
            month = _MONTHS[second_month_name.lower()]
        day = date(year, month, int(second_day))
        # 2:00 p.m. Eastern; label resolved by the IANA rules (unambiguous
        # wall time — the Fed never releases inside the DST transitions).
        when_utc, tz_label = resolve_new_york_instant(day, FOMC_RELEASE_LOCAL_TIME, "UNDECLARED")
        # Cross-check against the declared convention on the release pages.
        if (tz_label == "EST") != (day.month in (1, 2, 11, 12)):
            raise OfficialNewsError(
                f"FOMC statement timezone {tz_label} contradicts the official EST/EDT convention for {day}"
            )
        events.append(
            OfficialNewsEvent(
                event_id=_event_id(CATEGORY_FOMC, SOURCE_FEDERAL_RESERVE, when_utc),
                category=CATEGORY_FOMC,
                original_title="FOMC monetary policy decision and statement",
                source_agency=SOURCE_FEDERAL_RESERVE,
                source_url=SOURCE_URLS[SOURCE_FEDERAL_RESERVE],
                scheduled_local=_local_iso(day, FOMC_RELEASE_LOCAL_TIME, tz_label),
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
        )
    if not events:
        raise OfficialNewsError(f"FOMC calendars page yielded no {year} meetings")
    return tuple(sorted(events, key=lambda e: e.event_at_utc))


# ---------------------------------------------------------------------------
# Bureau of Economic Analysis adapter (official release pages)
# ---------------------------------------------------------------------------

_BEA_EMBARGO_RE = re.compile(
    r"EMBARGOED UNTIL RELEASE AT\s+(\d{1,2}):(\d{2})\s*([ap])\.?\s*m\.?\s+(EST|EDT),?\s+"
    rf"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
    rf"({ _MONTH_ALTERNATION })\s+(\d{{1,2}}),\s+(\d{{4}})",
    re.I,
)

_BEA_URL_RE = re.compile(r"/news/(\d{4})/([a-z0-9-]+)")


def parse_bea_release_page(
    html: str,
    *,
    page_url: str,
    retrieved_at: str,
    raw_source_sha256: str,
) -> OfficialNewsEvent | None:
    """Parse one official BEA release page.

    The embargo line carries the exact release instant with an explicit
    EST/EDT declaration; the page title supplies the category via the frozen
    BEA patterns (headline GDP and Personal Income and Outlays only —
    state/county/territory releases are deterministic non-events). Returns
    ``None`` for out-of-allowlist releases (drop, not an error).
    """

    import html as html_mod

    text = html_mod.unescape(html)
    match = _BEA_EMBARGO_RE.search(text)
    if match is None:
        raise OfficialNewsError(f"BEA release page {page_url} lacks an embargo release line")
    hour = int(match.group(1))
    minute = int(match.group(2))
    meridiem = match.group(3).lower()
    if meridiem == "p" and hour != 12:
        hour += 12
    if meridiem == "a" and hour == 12:
        hour = 0
    tz_label = match.group(4).upper()
    day = date(int(match.group(7)), _MONTHS[match.group(5).lower()], int(match.group(6)))
    local_time = time(hour, minute)
    when_utc, tz_label = resolve_new_york_instant(day, local_time, tz_label)

    url_match = _BEA_URL_RE.search(page_url)
    title_match = re.search(r"<title>([^<]+)</title>", text, re.I)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else (
        url_match.group(2).replace("-", " ") if url_match else page_url
    )
    # Strip BEA's site-title suffix ("<...> | U.S. Bureau of Economic Analysis").
    title = re.split(r"\|\s*U\.S\. Bureau", title)[0].strip()
    category = _match_category(_BEA_TITLE_PATTERNS, title)
    if category is None:
        return None
    if any(pattern.search(title) for pattern in _BEA_TITLE_EXCLUSIONS):
        return None
    return OfficialNewsEvent(
        event_id=_event_id(category, SOURCE_BEA, when_utc),
        category=category,
        original_title=title,
        source_agency=SOURCE_BEA,
        source_url=page_url,
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
# Census Bureau adapter (year-scoped release calendar)
# ---------------------------------------------------------------------------

_CENSUS_ROW_RE = re.compile(
    r'<td[^>]*><a href="([^"]+)">([^<]+)</a></td>\s*'
    r'<td sorttable_customkey="(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})">'
)


def parse_census_calendar(
    html: str,
    *,
    year: int,
    retrieved_at: str,
    raw_source_sha256: str,
) -> tuple[OfficialNewsEvent, ...]:
    """Parse the official Census year-scoped release calendar.

    Rows pair an indicator link with a ``sorttable_customkey`` release
    instant (``YYYYMMDDHHMM``, Eastern per the calendar's published
    schedule). Advance Monthly Sales releases are 08:30; any allowlist match
    at a different hour fails closed rather than guessing.
    """

    import html as html_mod

    text = html_mod.unescape(html)
    events: list[OfficialNewsEvent] = []
    seen_ids: set[str] = set()
    for href, name, y, mo, d, hh, mm in _CENSUS_ROW_RE.findall(text):
        if int(y) != year:
            continue
        category = _match_category(_CENSUS_TITLE_PATTERNS, name)
        if category is None:
            continue
        local_time = time(int(hh), int(mm))
        if local_time != time(8, 30):
            raise OfficialNewsError(
                f"Census {category} release at {hh}:{mm} deviates from the official 8:30 schedule"
            )
        day = date(int(y), int(mo), int(d))
        # Census keys carry no EST/EDT label; resolve via the IANA rules
        # under the unambiguous-wall-time policy.
        when_utc, tz_label = resolve_new_york_instant(day, local_time, "UNDECLARED")
        event_id = _event_id(category, SOURCE_CENSUS, when_utc)
        if event_id in seen_ids:
            continue
        seen_ids.add(event_id)
        events.append(
            OfficialNewsEvent(
                event_id=event_id,
                category=category,
                original_title=re.sub(r"\s+", " ", name).strip(),
                source_agency=SOURCE_CENSUS,
                source_url=SOURCE_URLS[SOURCE_CENSUS],
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
        )
    if not events:
        raise OfficialNewsError(f"Census calendar yielded no {year} allowlist releases")
    return tuple(sorted(events, key=lambda e: e.event_at_utc))


# ---------------------------------------------------------------------------
# Bureau of Labor Statistics adapter (release schedule page)
# ---------------------------------------------------------------------------

_BLS_ROW_RE = re.compile(
    rf"({ _MONTH_ALTERNATION })\s+(\d{{1,2}})(?:\s*</a>)?\s*</td>\s*"
    r"<td[^>]*>\s*(\d{1,2}):(\d{2})\s*([ap])\.?\s*m\.?\s*(?:ET)?\s*</td>\s*"
    r"<td[^>]*>\s*<a[^>]*>([^<]+)</a>",
    re.I,
)

# The 2024 schedule page is a three-cell calendar table:
#   <td class="date-cell"><p>Friday, February 02, 2024</p></td>
#   <td class="time-cell"><p>08:30 AM</p></td>
#   <td class="desc-cell"><p><strong>Employment Situation</strong> for January 2024</p></td>
# with the page-wide declaration "NOTE: All times on calendar are Eastern
# Time." The page never prints per-row EST/EDT labels, so wall times resolve
# via the IANA rules under the unambiguous-wall-time policy.
_BLS_CALENDAR_ROW_RE = re.compile(
    r"date-cell\"?><p>[A-Za-z]+,\s*(" + _MONTH_ALTERNATION + r")\s+(\d{1,2}),\s*(\d{4})</p></td>\s*"
    r"<td class=\"time-cell\"><p>(\d{1,2}):(\d{2})\s*([AP])M</p></td>\s*"
    r"<td class=\"desc-cell\"><p><strong>([^<]+)</strong>([^<]*)</p></td>",
    re.I,
)


def parse_bls_schedule(
    html: str,
    *,
    year: int,
    retrieved_at: str,
    raw_source_sha256: str,
) -> tuple[OfficialNewsEvent, ...]:
    """Parse the official BLS release schedule for ``year``.

    Schedule rows carry release date, Eastern release time and the linked
    release title (Employment Situation, CPI, PPI within the frozen
    allowlist). The schedule page prints times without an EST/EDT label, so
    they resolve via the IANA rules under the unambiguous-wall-time policy.
    """

    import html as html_mod

    text = html_mod.unescape(html)
    events: list[OfficialNewsEvent] = []
    seen_ids: set[str] = set()

    # Preferred layout: the dated 2024 calendar table (date/time/desc cells).
    # Rows carry a full year, so rows outside ``year`` are out of scope and
    # are skipped (deterministic year isolation).
    for month_name, day_num, row_year, hh, mm, meridiem, title, _rest in _BLS_CALENDAR_ROW_RE.findall(
        text
    ):
        if int(row_year) != year:
            continue
        events.extend(
            _bls_event_from_row(
                month_name=month_name,
                day_num=day_num,
                hh=hh,
                mm=mm,
                meridiem=meridiem,
                title=title,
                year=year,
                retrieved_at=retrieved_at,
                raw_source_sha256=raw_source_sha256,
                seen_ids=seen_ids,
            )
        )
    if events:
        return tuple(sorted(events, key=lambda e: e.event_at_utc))

    # Legacy layout: the linked schedule listing without full calendar cells.
    for month_name, day_num, hh, mm, meridiem, title in _BLS_ROW_RE.findall(text):
        events.extend(
            _bls_event_from_row(
                month_name=month_name,
                day_num=day_num,
                hh=hh,
                mm=mm,
                meridiem=meridiem,
                title=title,
                year=year,
                retrieved_at=retrieved_at,
                raw_source_sha256=raw_source_sha256,
                seen_ids=seen_ids,
            )
        )
    if not events:
        raise OfficialNewsError(f"BLS schedule yielded no {year} allowlist releases")
    return tuple(sorted(events, key=lambda e: e.event_at_utc))


def _bls_event_from_row(
    *,
    month_name: str,
    day_num: str,
    hh: str,
    mm: str,
    meridiem: str,
    title: str,
    year: int,
    retrieved_at: str,
    raw_source_sha256: str,
    seen_ids: set[str],
) -> list[OfficialNewsEvent]:
    """Turn one BLS schedule row into zero or one allowlist event.

    Non-allowlist titles (Real Earnings, Productivity and Costs, and every
    other BLS release) are deterministic non-events. Times carry no per-row
    EST/EDT label; the page declares Eastern Time, so the IANA rules decide
    the offset and the effective label is recorded.
    """

    category = _match_category(_BLS_TITLE_PATTERNS, title)
    if category is None:
        return []
    hour = int(hh)
    if meridiem.lower() == "p" and hour != 12:
        hour += 12
    if meridiem.lower() == "a" and hour == 12:
        hour = 0
    local_time = time(hour, int(mm))
    day = date(year, _MONTHS[month_name.lower()], int(day_num))
    when_utc, tz_label = resolve_new_york_instant(day, local_time, "UNDECLARED")
    event_id = _event_id(category, SOURCE_BLS, when_utc)
    if event_id in seen_ids:
        return []
    seen_ids.add(event_id)
    return [
        OfficialNewsEvent(
            event_id=event_id,
            category=category,
            original_title=re.sub(r"\s+", " ", title).strip(),
            source_agency=SOURCE_BLS,
            source_url=SOURCE_URLS[SOURCE_BLS],
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
    ]


# ---------------------------------------------------------------------------
# Normalization (dedup, ordering, package assembly)
# ---------------------------------------------------------------------------

DEV_END = datetime.fromisoformat(DEV_INTERVAL_END.replace("Z", "+00:00"))


def normalize_official_events(
    events: Iterable[OfficialNewsEvent],
    *,
    year: int,
) -> tuple[OfficialNewsEvent, ...]:
    """Deduplicate and validate events into canonical order.

    Dedup key: (agency, category, event_at_utc) — the stable
    agency/category/release-time identity. Two agencies releasing distinct
    real-world events at the same instant remain separate records (the
    blackout window is time-based, so shared timestamps are harmless).
    Conflicting content under the same identity fails closed.
    """

    by_key: dict[tuple[str, str, str], OfficialNewsEvent] = {}
    for event in events:
        key = (event.source_agency, event.category, event.event_at_utc)
        existing = by_key.get(key)
        if existing is not None:
            if existing != event:
                raise OfficialNewsError(
                    f"conflicting duplicate official event {key} differs in content"
                )
            continue
        by_key[key] = event
    ordered = sorted(
        by_key.values(), key=lambda e: (e.event_at_utc, e.category, e.source_agency)
    )
    for event in ordered:
        when = datetime.fromisoformat(event.event_at_utc.replace("Z", "+00:00"))
        if when.year != year:
            raise OfficialNewsError(f"event {event.event_id} lies outside {year}")
        if when >= DEV_END:
            raise OfficialNewsError(f"event {event.event_id} touches the 2025 holdout boundary")
    return tuple(ordered)


def canonical_events_hash(events: Iterable[OfficialNewsEvent]) -> str:
    ordered = sorted(events, key=lambda e: (e.event_at_utc, e.category, e.source_agency))
    payload = "|".join(
        f"{e.event_id}:{e.category}:{e.event_at_utc}:{e.source_agency}:{e.raw_source_sha256}"
        for e in ordered
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_official_news_package(
    *,
    year: int,
    events: Iterable[OfficialNewsEvent],
    raw_snapshots: Iterable[Mapping[str, object]],
    retrieval_utc: str,
    corroboration: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Assemble the versioned official-news package (fail-closed)."""

    ordered = normalize_official_events(events, year=year)
    events_canonical = canonical_events_hash(ordered)
    categories = sorted({e.category for e in ordered})
    agency_status: dict[str, str] = {}
    snapshots = [dict(s) for s in raw_snapshots]
    for source in APPROVED_SOURCES:
        present = any(e.source_agency == source for e in ordered)
        source_snaps = [s for s in snapshots if str(s.get("source")) == source]
        if present:
            agency_status[source] = "ACCEPTED"
        elif source_snaps:
            agency_status[source] = str(source_snaps[0].get("status", "RETRIEVAL_FAILED"))
        else:
            agency_status[source] = "MISSING_RAW_SNAPSHOT"
    actual_counts = {
        category: sum(1 for e in ordered if e.category == category)
        for category in HIGH_IMPACT_CATEGORIES
    }
    gaps: list[str] = []
    for category, expected in EXPECTED_CATEGORY_COUNTS.items():
        actual = actual_counts.get(category, 0)
        if actual < expected:
            gaps.append(f"{category}: {actual}/{expected} releases parsed")
    months_covered = sorted({int(e.event_at_utc[5:7]) for e in ordered})
    for month in range(1, 13):
        if month not in months_covered:
            gaps.append(f"month {month:02d} has no allowlist event")
    complete = not gaps and categories == sorted(HIGH_IMPACT_CATEGORIES)
    classification = (
        "DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE"
        if complete
        else "DEVELOPMENT_INCOMPLETE — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE"
    )
    return {
        "schema_version": OFFICIAL_NEWS_SCHEMA_VERSION,
        "classification": classification,
        "status": "ACCEPTED_DEVELOPMENT_ONLY" if complete else "DEVELOPMENT_INCOMPLETE",
        "year": year,
        "frozen_allowlist": list(HIGH_IMPACT_CATEGORIES),
        "retrieval_utc": retrieval_utc,
        "licensing": OFFICIAL_SOURCE_LICENSE,
        "source_urls": dict(SOURCE_URLS),
        "agency_status": agency_status,
        "category_counts": actual_counts,
        "expected_category_counts": dict(EXPECTED_CATEGORY_COUNTS),
        "months_covered": months_covered,
        "coverage_gaps": gaps,
        "raw_snapshots": snapshots,
        "events": [
            {
                "event_id": e.event_id,
                "category": e.category,
                "original_title": e.original_title,
                "source_agency": e.source_agency,
                "source_url": e.source_url,
                "scheduled_local": e.scheduled_local,
                "source_timezone": e.source_timezone,
                "event_at_utc": e.event_at_utc,
                "currency": e.currency,
                "country": e.country,
                "impact": e.impact,
                "retrieved_at": e.retrieved_at,
                "raw_source_sha256": e.raw_source_sha256,
                "parser_version": e.parser_version,
                "license": e.license,
            }
            for e in ordered
        ],
        "events_canonical_sha256": events_canonical,
        "statement_page_corroboration": dict(corroboration or {}),
        "complete": complete,
    }


# ---------------------------------------------------------------------------
# Raw snapshot helpers (network-layer results; never fabricated)
# ---------------------------------------------------------------------------


def make_raw_snapshot(
    *,
    source: str,
    url: str,
    retrieved_at: datetime,
    content: bytes,
) -> RawSourceSnapshot:
    import base64
    import zlib

    digest = hashlib.sha256(content).hexdigest()
    compressed = base64.b64encode(zlib.compress(content, 6)).decode("ascii") if content else ""
    return RawSourceSnapshot(
        source=source,
        url=url,
        retrieved_at=retrieved_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        content_sha256=digest,
        byte_size=len(content),
        content_zlib_b64=compressed,
        status="RETRIEVED",
        failure_reason="",
    )


def make_blocked_snapshot(
    *,
    source: str,
    url: str,
    retrieved_at: datetime,
    failure_reason: str,
) -> RawSourceSnapshot:
    """Record a retrieval failure without fabricating any calendar content."""

    return RawSourceSnapshot(
        source=source,
        url=url,
        retrieved_at=retrieved_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        content_sha256=hashlib.sha256(
            f"BLOCKED:{source}:{failure_reason}".encode("utf-8")
        ).hexdigest(),
        byte_size=0,
        content_zlib_b64="",
        status="RETRIEVAL_BLOCKED",
        failure_reason=failure_reason,
    )


def snapshot_content(snapshot: Mapping[str, object]) -> bytes:
    """Decode stored snapshot content (empty for blocked snapshots)."""

    import base64
    import zlib

    payload = str(snapshot.get("content_zlib_b64", ""))
    if not payload:
        return b""
    return zlib.decompress(base64.b64decode(payload))


# ---------------------------------------------------------------------------
# News-filter bridge (bot.strategy.news / bot.execution.news_filter)
# ---------------------------------------------------------------------------

OFFICIAL_NEWS_PROVIDER = "OFFICIAL_US_GOVERNMENT"


def build_news_snapshot_document(package: Mapping[str, object]) -> dict[str, object]:
    """Bridge the official package into the existing news-filter snapshot
    schema: ``{provider, retrieved_at, successful, events:[...]}``.

    Only complete packages (status ``ACCEPTED_DEVELOPMENT_ONLY``) bridge as
    successful snapshots; an incomplete package bridges with
    ``successful=false`` so the existing filter fails closed (DATA_UNSAFE)
    rather than silently under-blocking.
    """

    complete = package.get("status") == "ACCEPTED_DEVELOPMENT_ONLY"
    events = [
        {
            "event_id": str(event["event_id"]),
            "event_at": str(event["event_at_utc"]),
            "currency": "USD",
            "impact": "HIGH",
            "name": str(event["original_title"]),
        }
        for event in package.get("events", [])
    ]
    return {
        "provider": OFFICIAL_NEWS_PROVIDER,
        "retrieved_at": str(package.get("retrieval_utc")),
        "successful": bool(complete),
        "failure_reason": None if complete else "official_news_package_incomplete",
        "events": events,
    }
