# Phase 8E — Owner Evidence Input Kit

**Development interval:** `[2024-01-01T00:00:00Z, 2025-01-01T00:00:00Z)` — never include
2025+ data. **Everything accepted stays** `DEVELOPMENT_ONLY — NOT HOLDOUT — NOT
PROFITABILITY EVIDENCE`.

**How to supply:** place files under
`C:\Users\chips\forex-signal-bot-data\phase8\evidence\owner-input\<category>\`, then run the
matching subcommand of `backtests/evidence_intake_control.py` (see each section). Validation is
offline and fail-closed; source files are hashed, never modified. **Never send credentials, API
keys, account numbers or passwords through chat or commit them.**

---

## A. Historical high-impact USD news — REQUIRED for development evaluation

- **Accepted formats:** one JSON array of raw provider rows (the same field names the offline
  normalizers already accept: `CalendarId`/`id`, `Date`, `Country`, `Currency`,
  `Importance`/`importance`, `Event`/`event`/`name`).
- **Required columns:** event id, event timestamp, country/currency, importance, event name.
- **Required coverage:** every high-impact USD event in the **complete 2024** interval. A file
  that does not span 2024-01-01 → 2024-12-31 stays `PRESENT_UNVERIFIED`; missing dates are
  **not** treated as "no news".
- **Required timezone evidence:** timestamps must be ISO-8601 **with explicit UTC offset**
  (naive timestamps are rejected). DST transitions are handled explicitly at conversion.
- **Required license/entitlement statement:** passed as `--license-declaration`, e.g. *"Owner is
  entitled to offline use of this exported calendar export for personal research."*
- **Suggested supported providers already implemented by the repository:**
  `TRADING_ECONOMICS`, `EODHD` — supply an **offline export** of their calendar. Do **not**
  contact the provider, do **not** put an API key in the file, chat, or a commit.

```bash
& 'C:\Users\chips\forex-signal-bot\.venv\Scripts\python.exe' backtests/evidence_intake_control.py `
  validate-news --file <path-to-export.json> --provider TRADING_ECONOMICS `
  --retrieved-at 2026-09-13T12:00:00Z --license-declaration "<your entitlement statement>"
```

## B. Broker / account pricing evidence — REQUIRED for development evaluation

- **Exact Exness account type** used or intended (e.g. the exact account-type name on the
  contract spec page).
- **Sanitized contract specification** for `XAUUSDm`: digits, point, tick size/value (profit and
  loss variants), contract size, volume min/max/step, stops/freeze levels, filling modes,
  execution mode, margin rules and currencies.
- **Commission schedule:** mode (`NONE`, `PER_LOT_PER_SIDE`, `PER_LOT_ROUND_TURN`,
  `FIXED_PER_ORDER`, `PERCENT_NOTIONAL`), amount, currency, charging point, rounding, minimum
  charge. **Never leave this out because "there probably is none".**
- **XAUUSDm swap long/short**, units/conversion method, **rollover timezone and time**,
  **triple-swap weekday**, holiday exceptions if supplied.
- **Effective dates** the document itself establishes (e.g. "published 2024-03-01, superseded
  2024-09-01" → `effective_from`/`effective_to`). A document without a date inside the 2024
  interval is `CURRENT_ONLY_NOT_HISTORICAL`, not evidence.
- **Source-document date** and the file itself (we hash it).
- **No account number, password, or server name with credentials** — strip them before supply.

Three files, one JSON array each: broker metadata, commission, swap (see
`docs/examples/phase8e/` for the exact shapes — the examples are fictional).

## C. Slippage / fill evidence — REQUIRED for final holdout validation; optional for development

- **Sanitized bot/demo execution logs**, if available: one fill per record with `fill_id`,
  `symbol` (XAUUSDm only), `side`, `action`, `request_utc`, `quote_utc`, `requested_price`,
  `fill_price`, `requested_volume`, `filled_volume`, `spread_at_request`, `account_type`,
  `point`, and a `source_log_sha256` (we can compute it with `verify-source`). Remove account
  numbers, names, comments and session data first.
- **Minimum useful sample:** the committed validation contract defines **no minimum count**; we
  deliberately do not invent one. More fills = tighter stress bounds.
- **Alternative if no empirical fills exist:** the deterministic adverse/neutral slippage model
  stays registered `ASSUMPTION_ONLY` and is used **only for stress testing**; it never becomes
  empirical evidence, and final validation remains blocked until real fills are supplied.

## What is required vs optional

| Category | Development evaluation | Final holdout validation |
|---|---|---|
| Ticks, causal candles, spread, DXY | available | available |
| Historical USD news (full 2024, licensed) | **required** | **required** |
| Effective-dated broker metadata + commission + swap | **required** | **required** |
| Empirical slippage/fills | optional (stress model used) | **required** |
| Untouched holdout | n/a | n/a — owner moves/creates it later |

## Recovery

If an evidence package directory is missing or corrupted (tamper check fails on
`reverify`), delete **only that** package directory and re-run the same `validate-*`
command with the same unchanged source file; publication is content-addressed and will
recreate it atomically. Never edit a published package by hand.
