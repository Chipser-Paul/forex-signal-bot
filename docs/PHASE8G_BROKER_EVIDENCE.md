# Phase 8G — Exness Broker-Conditions Evidence Intake

Status: **intake verified; swap-unit conflict recorded; swap-policy decision required.**
All artifacts remain `DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE`.

## Addendum — official support email (primary evidence)

The promised official Exness support email arrived and was ingested as a new,
hash-bound source revision of the broker-evidence package.

**Email identity:** `Support/Private/Exness_XAUUSDm_Standard_Conditions_2026-09-14.eml`
— 14,737 bytes, SHA-256 `45574111e8c07f6eb3cf57f4907ae5da119b8622cdd46eaf303412ee5095fcaa`,
sent `2026-09-14T14:29:42Z`, subject "Exness - Trading Inquiries", sender domain
`mail.exness.com`. PDF rendition bound by hash:
`Exness_XAUUSDm_Standard_Conditions_2026-09-14.pdf` — 166,468 bytes, SHA-256
`72f43d4dbc28dd7b32f9b9c74426bf27928adcd46f6812b780d980b3367b8acb` (provenance
only; the `.eml` remains the parsed source). Personal data (owner greeting
name, addresses, thread id) is deterministically redacted from every derived
payload; the raw files are untouched and never committed.

**Accepted claims (only statements actually present in the email):**
- Standard accounts carry no trading commissions; XAUUSDm Standard commission
  is zero; trading costs are built into the variable spread —
  `BROKER_SUPPORT_ASSERTED`, corroborating the chat transcript (development-usable
  under the exact evidence contract; still no historical effective dates claimed).
- Market execution (no requotes) — `BROKER_SUPPORT_ASSERTED`.
- Triple-swap on Wednesday, three times the daily value — `BROKER_SUPPORT_ASSERTED`.
- Account statements record actual swap charged each day, useful only for
  trades that existed — `BROKER_SUPPORT_ASSERTED` (with the scope note: no 2024
  statements should be expected if the owner had no relevant trades then).
- Swap long **-3.85 USD per 1.00 lot per day**, swap short **-0.25 USD per 1.00
  lot per day** — `CURRENT_SUPPORT_REFERENCE`, **not** historical 2024 evidence.
- "We cannot provide a dated record of what the swap was throughout 2024 or the
  dates it changed" — `HISTORICAL_VALUE_UNAVAILABLE`, reconfirming the limitation.
- Scope note: the email does **not** restate contract size; that fact remains
  bound to the chat transcript and the current screenshots.

## Swap-unit conflict (recorded verbatim, unresolved by design)

| | MT5 screenshot (2026-09-13) | Support email (2026-09-14) |
|---|---|---|
| Swap long | -534.9 (points per lot/day) | -3.85 (USD per lot/day) |
| Swap short | not clearly readable | -0.25 USD per lot/day |
| Source SHA-256 | `084e9441…7a3e3` | `45574111…fcaa` |
| Calculation mode | Forex, swap type "In points" (platform display) | USD per lot as stated by support |
| Classification | `CURRENT_ONLY_NOT_HISTORICAL` | `CURRENT_SUPPORT_REFERENCE` |

No official points-to-USD conversion rule was supplied, so equivalence cannot
be established: the record keeps both sources verbatim (units, observation
dates, hashes, calculation modes, possible account/server/date differences)
and prohibits conversion, averaging, and selection. Consequences:
- The proposed swap stress policy remains **inactive** and is now additionally
  **conflict-gated** (`PROPOSED_INACTIVE_CONFLICT_GATED`, gate
  `swap.units_points_vs_usd_per_lot`); its email-derived scenario values
  (-3.85 ×1/×2/×3 USD per lot/day, adverse-only, Wednesday triple preserved)
  are `ASSUMPTION_ONLY` proposals, never observed evidence.
- Historical 2024 swap values and change dates remain `HISTORICAL_VALUE_UNAVAILABLE`;
  historical 2024 spread evidence remains the observed 2024 bid/ask tick dataset.

Published revision: `evidence-broker_support-v1-3b68b4203a9109b9` (27 claims).
The earlier chat-only revision remains published as immutable provenance.

## What this checkpoint ingested

Owner-supplied, sanitized evidence for Exness **Standard MT5 XAUUSDm** conditions,
classified claim-by-claim and published as one immutable external package:

| File | Size | SHA-256 |
|---|---|---|
| `Support/Exness_Support_2024_Conditions_2026-09-14.txt` | 7,342 B | `f7dd8d15e922d2583ab8b5a50e1a974506b30166fb67c1360fb459c5c3304af5` |
| `Exness_Standard_XAUUSDm_Specification_2026-09-13_01.png` | 45,857 B | `6c2d7304b36bbc1c46330ff4b3dbfd88c860a14325401ba0ebafc944a090f4cb` |
| `Exness_Standard_XAUUSDm_Specification_2026-09-13_02.png` | 49,770 B | `084e9441de7257eb1880ffbb6be3086870dd7fb82a94d68f431d5bab37a7a3e3` |

Raw files live under `C:\Users\chips\forex-signal-bot-data\phase8\evidence\owner-input\broker-metadata\`
and are never committed, modified, or copied. The fail-closed sensitive scan passed:
no credentials, tokens, emails, Support PINs, or account numbers (URL help-article IDs
are excluded by the pattern's word guards and are not account identifiers). The
support agent's display name is redacted from every derived quote; the raw file is
untouched.

## What Exness support actually confirmed (BROKER_SUPPORT_ASSERTED)

From the complete two-session transcript (both the initial chat and the 14:12
follow-up are present; the classifier refuses truncated exports):

- Account context: Standard MT5, XAUUSDm.
- **No separate fixed trading commission on Standard**; trading cost is included in
  the variable spread. (Zero/Raw-Spread figures of 5.5/3.5 USD concern *other*
  account types — classified `REJECTED_CONFLICTING` for Standard scope.)
- Exness does **not** provide archived spread data by email.
- Contract size 100 troy ounces; pip size 0.01; min volume 0.01 lot; max volume
  200 lots daytime / 20 lots nighttime.
- Fixed margin 1:200 (0.5%); hedged margin 0%; market execution.
- Triple swap charged on Wednesdays; swap schedule may change on public/bank holidays.
- **No investigation ticket/email was ever created.**

## What remains unavailable (HISTORICAL_VALUE_UNAVAILABLE)

- Historical 2024 swap-long/short values and their change dates: **never supplied.**
- A demonstrated archived-specification mechanism: support suggested chart replay
  ("I'm not quite sure if it'll stretch to 2024") but could not confirm it shows
  historical commission/swap/contract conditions.
- Rollover time: asked for 21:00 UTC **and never answered** (the transcript's only
  "21:00" occurrences are the two question snippets; any answer would fail closed).
- Historical holiday swap adjustments: unspecified.
- Complete daytime/nighttime session definitions: not supplied.
- Historical effective dates for the commission statement: not established by the
  transcript; the commission record's effective interval is honestly marked
  `established: false`.

## Current-only observations (CURRENT_ONLY_NOT_HISTORICAL)

OCR-extracted (WinRT OCR with PIL 3×–8× upscaling) from the sanitized screenshots,
bound to their hashes, and never promoted to historical evidence:

- Screenshot 01: digits 3, contract size 100 (XAU), floating spread, **stops level 0**,
  margin currency XAU, profit currency USD, Forex calculation, bid-price chart mode.
- Screenshot 02: full access, market execution, GTC, FOK + IOC, volumes
  0.01/200/0.01, swap type "In points", swap long −534.9 points, weekday
  multipliers Mon 1 / Tue 1 / Wed 3 / Thu 1 / Fri 1.
- **Not clearly readable (recorded, never guessed):** swap-short value and the
  margin-display context (screenshot 02). Swap short therefore has no adopted value.

**Documented, unresolved conflict:** the current platform margin display shows
Initial/Maintenance `1.0000000` while support asserted a fixed 1:200 (0.5%)
requirement. Neither value is adopted; the display is current-only and the support
statement lacks a demonstrated 2024 effective date.

## Unit normalization (arithmetically verified and tested)

- MT5 point/tick increment: **0.001** (kept distinct from the broker pip).
- Broker pip size: **0.01** → one pip = ten 0.001 points.
- Contract size: **100 XAU**.
- One 0.01 pip move at one lot = **1 USD**; one 0.001 point move at one lot = **0.10 USD**.
- Point is never overwritten with pip; tick size is never overwritten with pip size.

## Commission representation

`mode NONE`, amount 0, currency USD, per-side 0, round-turn 0, minimum 0 — bound to
the support-transcript hash. Non-zero commission sensitivity cases (3.5/5.5 USD
round-turn) exist **only as `ASSUMPTION_ONLY` proposed stress cases**, never as
observed Standard-account commission.

## Spread evidence precedence

The broker statement "Standard cost is included in the variable spread" is linked to
the existing **observed** 2024 XAUUSDm bid/ask spread evidence package (verified tick
manifest). Current calculator/advertised/typed/screenshot spreads are explicitly
prohibited substitutes. The 39.7-million-row dataset was not recomputed.

## Proposed swap stress policy (INACTIVE)

A machine-readable template derives deterministic proxies **only** from the
clearly-readable current swap-long (−534.9 points → −53.49 USD per lot per day):

- scenarios: `neutral_current_proxy` (×1), `adverse_x2`, `severe_x3`;
- every numeric proxy is `ASSUMPTION_ONLY`;
- no scenario applies a favorable positive swap credit; swap-short stays 0/adverse-only;
- Wednesday triple charging is preserved (weekday multipliers 1/1/3/1/1);
- units and conversion formula are explicit: `usd_per_lot = points × 0.001 × 100`;
- values were fixed without reference to any strategy performance (no strategy has run);
- activation requires a **separate owner-authorized preregistration checkpoint**.

Status: `PROPOSED_INACTIVE`, `active: false`. It is not wired into any evaluation path.

## Package identity and verification

- Published (external, outside Git):
  `C:\Users\chips\forex-signal-bot-data\phase8\evidence\evidence-broker_support-v1-5ddf97d85fccc633`
- Atomic, non-overwriting, content-addressed; ingestion provenance (wall-clock,
  hashes, scan result) is stored **outside** the hashed content, so re-ingestion of
  unchanged evidence is idempotent (identical package id, verified twice).
- `verify` re-reads and hash-checks the package, recomputes the canonical content
  hash, re-verifies unit arithmetic, and asserts the stress template stays
  `PROPOSED_INACTIVE` with no favorable credit.
- Evidence matrix: `BROKER_SUPPORT = ACCEPTED_DEVELOPMENT_ONLY`;
  `BROKER_METADATA`, `COMMISSION`, `SWAP_ROLLOVER`, `SLIPPAGE_FILLS` remain `MISSING`.
- Readiness: `accepted_for_final_validation = false`,
  `strategy_evaluation_authorized = false`, `holdout_access_authorized = false`.
  A broker-support statement does **not** by itself make the standalone
  metadata/commission/swap categories accepted.

## Limitations

- A support-chat statement is broker-asserted evidence, not archived documentation.
- Screenshot OCR is current-state only; the swap-short cell could not be resolved.
- No historical swap values exist; any swap cost in a future development evaluation
  must come from the owner-activated stress policy or genuinely dated evidence.

## Next owner decision

Choose the swap-stress route (activate the proposed `PROPOSED_INACTIVE` template via
a preregistration checkpoint), supply genuinely dated 2024 swap evidence, or proceed
to the remaining owner-kit categories (commission beyond Standard, slippage/fill
logs) with the documented zero-swap-cost development caveat.
