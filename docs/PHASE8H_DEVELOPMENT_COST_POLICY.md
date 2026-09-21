# Phase 8H — Frozen Development Transaction-Cost Policy

Status: **preregistered, hash-bound, INACTIVE.** No strategy evaluation is
authorized by this checkpoint. Every artifact remains
`DEVELOPMENT_ONLY — NOT HOLDOUT — NOT PROFITABILITY EVIDENCE`.

## What this checkpoint did

Preregistered `phase8h.development-cost-policy.v1` — a frozen, content-hashed
description of how transaction costs are accounted during 2024 development
evaluation — **before** any strategy result is observed.  The policy freezes
the evidence basis of every cost component, the ordered swap/slippage
scenario ladders, the acceptance restrictions and the binding set.  It is
published as an immutable, non-overwriting evidence package and remains
inactive; `ACTIVE` is not a representable state.

## Evidence used and its limitations

| Component | Basis | Classification | Limitation |
|---|---|---|---|
| Spread | `observed_spread-v1-e25bdb9bf028a5be` (2024 bid/ask ticks) | `OBSERVED_EMPIRICAL` | candle-level aggregation cannot reconstruct the exact tick path |
| Commission | broker-support revision `evidence-broker_support-v1-3b68b4203a9109b9` (chat + email) | `DEVELOPMENT_ONLY`, mode `NONE` | no historically dated 2024 change archive; final-validation eligibility **false** |
| Swap | email −3.85/−0.25 USD/lot/day; screenshot −534.9 points (short unreadable) | `CURRENT_SUPPORT_REFERENCE` / `CURRENT_ONLY_NOT_HISTORICAL` | units conflict unresolved; historical 2024 values and change dates **unavailable** |
| Slippage | no calibrated fills | `ASSUMPTION_ONLY` | silent zero prohibited for acceptance claims |

The points-versus-USD swap conflict is preserved verbatim: conversion,
averaging and single-source selection are prohibited fields in the policy
(`conversion_prohibited`, `averaging_prohibited`,
`single_source_selection_prohibited`), and verification fails closed if any
is relaxed.

## Frozen scenario tables

Swap ladder (order is part of the contract; USD per 1.00 lot per day,
Wednesday ×3 retained in every scenario, no positive swap credit permitted):

| Scenario | Long | Short | Multiplier | Role |
|---|---|---|---|---|
| `SWAP_NO_OVERNIGHT_EXPOSURE_DIAGNOSTIC` | 0.0 | 0.0 | ×0 | diagnostic; never the primary acceptance result when trades cross rollover |
| `SWAP_EMAIL_REFERENCE` | −3.85 | −0.25 | ×1 | development reference |
| `SWAP_EMAIL_2X_ADVERSE` | −7.70 | −0.50 | ×2 | adverse rung |
| `SWAP_EMAIL_3X_ADVERSE` | −11.55 | −0.75 | ×3 | **required adverse boundary** |

Slippage ladder (MT5 points; 1 point = 0.001 = 0.10 USD per lot; all
`ASSUMPTION_ONLY`; anchored to the Phase 7 execution-model boundary
`FIXED_ADVERSE_POINTS=1` used by the realistic-execution replay, extended by
a priori integer multiples — no strategy outcome was inspected):

| Scenario | Points | USD per lot |
|---|---|---|
| `SLIPPAGE_NEUTRAL_DIAGNOSTIC` | 0.0 | 0.00 |
| `SLIPPAGE_MODERATE_ADVERSE` | 1.0 | 0.10 |
| `SLIPPAGE_SEVERE_ADVERSE` | 3.0 | 0.30 |

Applicability is recorded per scenario: long/short positions, pro-rata
partial-volume daily charging, and rollover-crossing requirement.

## Acceptance restrictions (frozen)

- All scenarios must be disclosed; cheapest-scenario pass selection is
  `PROHIBITED`.
- Results failing `SWAP_EMAIL_3X_ADVERSE` are visible and cannot be
  discarded.
- Per-scenario expectancy, profit factor, drawdown and circuit behaviour
  must be reported.
- Automatic parameter selection is `PROHIBITED`.
- Every relevant result carries the `HISTORICAL_SWAP_UNCERTAIN` label.
- `strategy_evaluation_authorized`, `final_validation_authorized` and
  `holdout_access_authorized` are frozen `false`.

## Binding set

The policy is bound (SHA-256, content identity, no absolute paths) to:

- `strategy_fingerprint` — canonical hash of `StrategyConfig().fingerprint()`
- `execution_model_fingerprint` — content hash of the committed cost surface
  (`bot/backtesting/costs.py`, `models.py`, `engine.py`); verification
  recomputes it and fails closed on drift
- `risk_policy_fingerprint` — canonical hash of the default `RiskPolicy`
- 2024 development dataset — year package
  `exness-xauusdm-2024-development-b2a0234a470dd397`
  (39,715,935 rows, source canonical `b2a0234a…f47e73`)
- derived candles — `derived-candles-2024-v1-6715e5c64d888215` +
  attestation `derived-candles-attestation-v1-6715e5c64d888215`
- broker-support revision — `evidence-broker_support-v1-3b68b4203a9109b9`
- observed-spread evidence — `observed_spread-v1-e25bdb9bf028a5be`
- DXY development input — 6,216 causal rows,
  canonical `b6a180756b42ba65c4fd050c6cd10ad35347e4804223fe1cca60f29da44bb531`

## Policy identity

- Package: `evidence-development_cost_policy-v1-6b1a986b1f8d7b81`
  (external, beneath `C:\Users\chips\forex-signal-bot-data\phase8\evidence\`)
- Content canonical SHA-256: `6b1a986b1f8d7b81ff10616fd848cb93d6dd0b19d4a96f1a512d629716b42b42`
- Policy fingerprint (canonical JSON excluding the fingerprint field):
  `aa0ccc9368c0cf55b4775b4295f0424d4bdb0e5fd6cbfaf27137763be58e9404`
- State: `PREREGISTERED_INACTIVE`; publication is idempotent; conflicting
  content under the same id fails closed.

## CLI

`backtests/cost_policy_control.py` (offline only):

- `preregister` — build + publish (idempotent) and regenerate the Phase 8
  evidence matrix/readiness through the existing 8E tooling;
- `verify` — readback verification plus binding cross-checks against the
  on-disk packages (broker-support hash, observed-spread hash, derived
  manifest hash, DXY package id) and a full deterministic rebuild;
- `status` — sanitized summary.

## Import-safety correction (production, behaviour-preserving)

Phase 8H's MT5-free import test exposed that importing pure modules
(`bot.strategy.config`, the validation chain) transitively imported
MetaTrader5 via eager package `__init__` re-exports:
`bot/analysis/__init__` → `bias_engine` → `bot.data.market_data`, and
`bot/strategy/dxy.py` → `bot/analysis/dxy_filter` → `market_data`; plus
`bot/execution/__init__` → `risk_engine` (module-level MT5).  Corrections:
PEP 562 lazy re-exports in `bot/analysis/__init__.py` and
`bot/execution/__init__.py`; deferred `fetch_ohlcv` imports inside the three
live-fetch helpers of `bot/analysis/dxy_filter.py`.  Call-time behaviour is
unchanged; the complete suite is byte-identical in outcome (960 passed /
1 opt-in skip / 10 subtests before and after).

## Readiness effect

`DEVELOPMENT_COST_POLICY: PREREGISTERED_INACTIVE` appears in the evidence
matrix as an honest informational category.  It never flips
`all_categories_accepted` and never promotes commission/swap/slippage to
accepted historical evidence.  `commission`, `swap_rollover`,
`slippage_fills` and `broker_metadata` remain `MISSING`;
`accepted_for_final_validation=false`,
`strategy_evaluation_authorized=false`,
`holdout_access_authorized=false`; Phase 9 remains blocked.

## Remaining before development evaluation

1. Owner decision on the swap route (activate the assumption-only stress
   policy via its own preregistration checkpoint, supply genuinely dated
   2024 swap evidence, or accept the documented zero-credit uncertainty
   labelling).
2. Broker metadata with effective-dated 2024 values (current observations
   remain current-only).
3. Commission/swap evidence that satisfies final-validation strength
   (currently development-strength only).
4. Empirical slippage/fill evidence or explicit stress-only treatment.

## Safety confirmation

No strategy evaluation, backtest, optimization or profitability calculation
occurred.  No holdout or 2025+ data was accessed.  No MT5, bot, Streamlit or
owner process was started.  No account, credential, network or trading
operation occurred.  The policy is inactive by construction.
