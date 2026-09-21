# Phase 8F — Official 2024 USD News Calendar (Zero-Cost, Official Sources)

Status: **complete and verified — 80 events across all seven frozen
categories, all four authorities accepted, package
`ACCEPTED_DEVELOPMENT_ONLY` (development only; never holdout or
profitability evidence).**

## Why paid providers were replaced

The owner cannot purchase Trading Economics, EODHD, or any commercial
economic-calendar subscription, and no provider token may be used or
stored. The preregistered replacement policy uses only official United
States government sources, which are public-domain.

## Approved source authorities

| Authority | Source used | Status |
| --- | --- | --- |
| Federal Reserve | `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm` (8 decision dates) + 2024 statement pages as corroboration | RETRIEVED / ACCEPTED |
| U.S. Census Bureau | `https://www.census.gov/economic-indicators/calendar-listview-2024.html` (year-specific archive; 12 Advance Monthly Retail Sales rows) | RETRIEVED / ACCEPTED |
| Bureau of Economic Analysis | 2024 release pages under `https://www.bea.gov/news/2024/...` (embargo line with explicit `EST`/`EDT`); 12 GDP + 12 Personal Income and Outlays releases | RETRIEVED / ACCEPTED |
| U.S. Bureau of Labor Statistics | `https://www.bls.gov/schedule/2024/home.htm` — programmatic access hard-blocked (Akamai 403, including native Schannel `curl`); page delivered by **manual browser download** and ingested with honest `MANUAL_BROWSER_DOWNLOAD` provenance | RETRIEVED (MANUAL) / ACCEPTED |

## Manual BLS acquisition (provenance)

- Owner-supplied file: `…\phase8\official-news\raw\BUREAU_OF_LABOR_STATISTICS.html`
- Byte size: 101,431; SHA-256:
  `989023c355a3a4d179e2a250da476468f3a63ad3e310b6a029b6814a6307f878`
- Official URL recorded: `https://www.bls.gov/schedule/2024/home.htm`
- Acquisition method recorded: `MANUAL_BROWSER_DOWNLOAD` (never passed off
  as automated retrieval; the earlier `RETRIEVAL_BLOCKED` programmatic
  attempt remains stored in the package as historical evidence)
- Ingestion: content-addressed, non-overwriting copy
  (`989023c355a3a4d1-home.htm.raw`); the owner's original file is preserved
  byte-for-byte, untouched
- Authenticity gates before ingestion: "Schedule of Selected Releases
  2024" title, the page-wide "NOTE: All times on calendar are Eastern
  Time." declaration, all three frozen BLS categories present, no
  denial/CAPTCHA markers; empty, denial or non-BLS content fails closed
- Provenance limitation (honest): the byte hash proves the parsed content,
  but browser-retrieval conditions (exact fetch time, TLS path) cannot be
  cryptographically attested the way automated retrieval can

## Frozen high-impact allowlist (preregistered)

1. `FOMC_DECISION`
2. `EMPLOYMENT_SITUATION`
3. `CONSUMER_PRICE_INDEX`
4. `PRODUCER_PRICE_INDEX`
5. `GDP_RELEASE`
6. `PERSONAL_INCOME_OUTLAYS_CORE_PCE`
7. `ADVANCE_RETAIL_SALES`

Unchanged since before any strategy result was examined. The ±30-minute
inclusive blackout, thresholds, confluence, entry/exit, DXY, risk, broker,
execution and symbol parameters were not modified.

## Timezone policy

- Source times are America/New_York (the BLS page declares Eastern Time
  page-wide; BEA pages carry per-page `EST`/`EDT` embargo labels);
  conversions use the IANA database (`zoneinfo`), never a fixed offset.
- BLS wall times carry no per-row label and resolve under the
  unambiguous-wall-time policy; the effective EST/EDT label is recorded
  per event (2024 BLS events: 12 EST / 25 EDT).
- DST spring-forward gaps and fall-back overlap instants are rejected.
- Both the original local time (`scheduled_local`) and the normalized UTC
  time (`event_at_utc`) are preserved in every record.

## Parsing results (final package)

- Package: `…/phase8/evidence/evidence-official_news-v1-78279c5e26c1c6d1`
- Status: `ACCEPTED_DEVELOPMENT_ONLY` (classification
  `DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE`)
- Events: **80** — FOMC 8, Employment Situation 12, CPI 12, PPI 12,
  GDP 12, Personal Income/Core PCE 12, Advance Retail Sales 12
- All 12 months covered (6–7 events each); `coverage_gaps: []`
- All four agencies `ACCEPTED`; stable event IDs unique
- Non-allowlist BLS releases (e.g. "Employment Situation of Veterans",
  Real Earnings, Productivity and Costs) are deterministic non-events;
  the veterans look-alike is excluded by title pattern
- Out-of-year calendar rows are skipped (year isolation); duplicate
  stable identities dedupe; 3 revisions remain published and all verify

## Determinism, succession and readback

- Repeated offline builds from identical stored snapshots produce the
  identical content-addressed package id (`78279c5e26c1c6d1` reproduced).
- `verify` re-parses every stored raw snapshot and re-checks the canonical
  event hash for every published revision (5/5 pass, including the older
  44-event incomplete revisions).
- Evidence-matrix succession on the stable event-ID set: equal sets →
  latest revision wins; proper superset (coverage growth) supersedes;
  accepted status outranks incomplete for the same set; a subset is
  tolerated but never selected; partial overlap (loss/replacement/
  contradiction) fails closed.
- `snapshot` selection uses the same succession (never lexicographic id
  order), so the complete package is served deterministically.

## News-filter integration

`official-news-control.py snapshot` emits the committed
`bot.execution.news_filter` document: provider `OFFICIAL_US_GOVERNMENT`,
`successful: true` (all seven categories complete), 80 UTC-aware events.
The ±30-minute inclusive blackout semantics are unchanged and covered by
exact-boundary tests; missing/stale/corrupt packages still fail closed
(`successful: false` → `DATA_UNSAFE` for new entries).

## Readiness after completion

- `OFFICIAL_USD_NEWS` and `HISTORICAL_USD_NEWS`:
  `ACCEPTED_DEVELOPMENT_ONLY`
- Still missing (blocking): broker metadata, commission, swap/rollover,
  slippage/fill evidence (Phase 8E owner-input kit)
- `accepted_for_final_validation = false`,
  `strategy_evaluation_authorized = false`,
  `holdout_access_authorized = false` — Phase 9 remains blocked until the
  remaining mandatory evidence categories are accepted
