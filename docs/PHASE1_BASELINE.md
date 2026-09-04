# Phase 1 Reproducible Baseline

## 1. Provenance and scope

- Phase 0 parent: `55f7dd3488eec695fa1b7c1810177e5d40c6932a`
- Security parent: `6ac9222a38b6545516ec16fa403fcc6ca7f83bdc`
- Tested platform: Windows, CPython 3.10.9, 64-bit
- Phase 1 branch: `phase/1-baseline`
- Isolated worktree: `C:\Users\chips\forex-signal-bot-phase1`

This document records the system as it exists at the Phase 0 boundary. Phase 1
adds tests, documentation, dependency metadata, and CI preparation only. It does
not change strategy, execution, risk, market-data alignment, or stored results.

## 2. Entry-point inventory

| Entry point | Purpose and interpreter | MT5 / order capability | Configuration | Status |
| --- | --- | --- | --- | --- |
| `frontend/app.py` | Streamlit dashboard via project Python and `streamlit run` | Login and dashboard helpers can initialize MT5 and read account data; UI itself does not submit orders | `.env`, Streamlit state, keyring, `.session.json`, `.streamlit/config.toml` | Supported, unsafe in tests |
| `frontend/utils/bot_runner.py:start_bot` | Child-process launcher for `main.py` | Child can connect and trade | In-memory credentials passed once through child environment, `BOT_CAPITAL` | Supported, unsafe in tests |
| `main.py` | Direct live trading process via project Python | Initializes MT5, retrieves data, submits/modifies/closes orders | Child environment or `.env`, module constants, symbol profiles, session preferences | Supported live entry, unsafe |
| `runtime/loop.py:main_loop_once` | One deterministic outer-loop iteration injected by `main.py` | Capability comes from callbacks | `RuntimeContext`, `.bot_state.json` | Supported internal boundary |
| `backtests/shadow_mode_backtest.py` | CLI historical shadow backtest via project Python | Reads MT5 history/cache and symbol metadata; simulation does not submit orders | CLI arguments, symbol profiles, cached pickle data | Research entry; live MT5 retrieval is unsafe in tests |
| `trade_executor.py:backtest_trade` | Small legacy dataframe trade simulator | No MT5 order, despite module importing MT5 | Function arguments and fixed pip assumptions | Legacy helper |
| `utils/analyze_setup_logs.py` | CLI setup/journal analysis | No MT5 | `--date`, `--trades`, `--output`, logs/results | Supported diagnostic |
| `backtests/_analyze_v2.py` | Hard-coded analysis of one result CSV | No MT5 | Embedded result path | Legacy diagnostic |
| `start_mobile_access.bat` | Starts Streamlit bound to all interfaces for Tailscale access | Dashboard may initialize/read MT5 after authentication | `dl_env`, fixed port 8501, `FOREX_REMOTE_ACCESS=1`, application token | Operational launcher, unsafe in tests |
| `frontend/utils/ui_launcher.py:start_ui` | Starts a separate Streamlit subprocess | Same dashboard capability as above | Project interpreter, chosen port, process JSON | Supported launcher, unsafe in tests |
| `mobile_app/lib/main.dart:main` | Flutter WebView shell and Firebase notification client | Does not call MT5 directly | Saved URL, compiled Firebase options, default LAN URL | Mobile client; separately built |
| `utils/loop_ai.py:queue_loop_analysis` | Lazily starts a daemon worker for Groq commentary | No order authority; receives loop snapshots | `AI_LOOP_ANALYST_*`, `GROQ_API_KEY` | Optional background analysis |
| `utils/analytics_db.py` | In-process analytics persistence/query API | No MT5 | Relative DB and journal paths | Supported internal service |

The six diagnostic files present only in the owner's dirty original worktree are
not part of this baseline branch and were not read, copied, or modified.

## 3. Module boundaries

| Boundary | Primary modules | Responsibility |
| --- | --- | --- |
| Security/config loading | `app_security/environment.py`, `models.py`, `identity.py`, frontend auth/keyring helpers | One-shot credentials, redaction, account identity, dashboard access |
| Market data | `bot/data/market_data.py`, `utils/fetch.py` | MT5 timeframe mapping, closed-candle fetch, normalized OHLCV frames |
| Analysis | `bot/analysis/*`, `strategies/smc_engine/*` | HTF bias, DXY, liquidity, FVG, structure, displacement, OB/breaker, entry model |
| State/orchestration | `bot/state/orchestrator.py`, `strategies/smc_engine/strategy_state.py`, `runtime/*` | Gate sequence, per-symbol state, outer-loop callback order |
| Risk | `bot/execution/risk_engine.py`, `utils/risk.py` | Modular and legacy sizing, RR, drawdown and trade-count checks |
| Execution | `trade_executor.py`, live execution helpers in `main.py` | Market requests, invalid-stop retry, post-fill guard, registry updates |
| Position management | `main.py:monitor_trades`, `trade_manager.py` | Partial close, kill switch, ATR/HTF trailing, profit-lock telemetry |
| Persistence/analytics | `utils/trade_journal.py`, `analytics_db.py`, `trade_logger.py`, setup/trade loggers | JSONL/JSON/CSV/SQLite telemetry and queries |
| Frontend | `frontend/app.py`, `frontend/ui_pages/*`, `frontend/utils/*` | Authentication, control, process launch, dashboard and settings |
| Notifications | `utils/notifications.py`, Firebase and Telegram settings | External alerts after trade events |
| AI analysis | `utils/loop_ai.py`, frontend Groq/Ollama helpers | Optional commentary and user-initiated analysis |
| Backtesting | `backtests/shadow_mode_backtest.py` | Independent historical loop, simulated positions/exits/costs, result export |
| Mobile/remote | `mobile_app/`, `start_mobile_access.bat`, remote-access gate | WebView client, push notifications, Tailscale-hosted dashboard |

## 4. Live runtime sequence

1. `bot_runner.start_bot` constructs a child environment containing capital and
   MT5 identity, then launches `main.py`. Direct execution instead loads `.env`.
2. `main.py` consumes and scrubs the one-shot credential contract before normal
   imports. `connect_mt5` initializes MT5 and verifies account/server identity.
3. Startup loads `open_trades.json`, normalizes integer tickets, initializes
   realized daily profit from MT5 history, and creates `RuntimeContext`.
4. `main_loop_once` refreshes session settings, records profit, reconciles open
   positions/history, and reads `.bot_state.json` for pause behavior.
5. Each enabled symbol enters `evaluate_symbol`; the active engine is selected by
   `BOT_ACTIVE_ENGINE` (`orchestrator` by default, legacy for three aliases).
6. The orchestrator applies session, news, daily-loss, concurrency, HTF bias,
   cascade, DXY, liquidity, displacement, internal structure, score, and entry
   gates. It emits a structured setup record for every terminal action.
7. A `candidate_ready` result returns to `execute_orchestrator_live`, which builds
   levels, checks RR, derives score/profile risk, asks `RiskEngine` for volume,
   and calls `trade_executor.execute_trade`.
8. `execute_trade` builds the MT5 deal request and calls `order_send`; on success
   it sends alerts and writes trade logs/journal records.
9. The post-fill guard rechecks direction and execution RR. A rejected fill is
   immediately closed through another MT5 deal request.
10. `monitor_trades` reconciles missing tickets, takes a 50% partial at 1R where
    broker volume permits, applies structure kill-switch and trailing updates,
    and writes journal events.
11. `trade_manager.manage_open_trades` runs 15 times per outer loop to update
    profit-lock metadata; current breaches are telemetry-only and defer exit to
    trailing logic.
12. Closed-position history is journaled to JSONL and SQLite. Loop snapshots and
    optional AI reviews are stored in SQLite for dashboard queries.

## 5. Backtest runtime sequence

1. CLI arguments choose symbol, dates, capital, output, trail mode, optional RR,
   spread, slippage, and commission.
2. `_fetch_range` uses cached pickles when available; otherwise it calls MT5
   `copy_rates_range` in chunks and writes a cache.
3. The symbol profile mutates the same analysis module constants used by live
   code. W1/D1/H4/H1/M15/entry frames and a synthetic DXY basket are loaded.
4. For each entry-timeframe row, existing simulated positions are checked against
   prior SL/TP, kill-switch logic, then trailing logic.
5. Timeframe slices, bias, liquidity, displacement, FVG, OB, score and entry are
   evaluated. A valid candidate is sized by `RiskEngine` and appended as a
   simulated `Position`.
6. Remaining positions close at the final price. Trades, equity and summary files
   are written to the chosen output directory.

This path is independent of `StrategyOrchestrator.evaluate_symbol` and currently
reimplements many gates. Parity is therefore an observed goal, not an assumption.

## 6. Configuration precedence

| Setting | Sources, highest precedence first | Live source | Backtest source | Known mismatch / repair |
| --- | --- | --- | --- | --- |
| MT5 identity | Bot child environment, then direct-run `.env`; expected identity defaults to supplied identity | One-shot child contract, scrubbed after use | Terminal used only for history/cache misses | Backtest still requires terminal for uncached data; later offline-data work |
| Enabled symbols | `main.py:SYMBOLS`; session can disable BTC only | `XAUUSDm`, `BTCUSDm`, `btc_enabled` | CLI `--symbol` | Different selection models; later configuration work |
| Capital | Latest valid `.session.json` capital, then `BOT_CAPITAL`, then 1000 | Session refresh wins after startup | `--capital`, default 1000 | UI and backtest are separate; documented only |
| Risk per trade | Confluence score risk (1.5%/2%) when nonzero, then profile; DXY may multiply by 0.75 | Score-derived caller value sent to `RiskEngine` | Same score/profile expression | Exceeds central 1% field; `KD-RISK-001`, Phase 4 |
| Maximum risk | No enforced cap on caller `risk_pct`; `RiskEngine.max_risk_per_trade` is only a default | Nominal 1% field | Same | Not actually a maximum; Phase 4 |
| Daily drawdown | `RiskEngine.max_daily_drawdown=3%` of account balance | Realized daily P/L argument | Simulated realized daily P/L | Floating loss excluded; `KD-RISK-002`, Phase 4 |
| Minimum R:R target | Symbol `min_rr` deep-merged over default 3.0 | XAU 1.5; BTC inherits 3.0 | Profile unless `--min-rr` overrides | CLI can diverge; Phase 3 parity work |
| Execution R:R floor | Symbol `min_execution_rr` over default 1.2 | Post-fill guard, XAU 1.2/BTC 1.4 | No post-fill broker drift | Live-only concept; retain but model in Phase 3 |
| Session permission | Sunday and UTC hours 0/11 hard blocked; session context otherwise informational | Wall-clock UTC | Row timestamp | Wall-clock injection is incomplete; later runtime work |
| Spread/slippage | Broker bid/ask and request deviation; setup log uses placeholder spread 20 | Live tick plus deviation | CLI defaults both to zero | Historical evidence often optimistic; later cost-model work |
| News source | `NEWS_EVENTS_PATH`; absent/invalid feed becomes clear fallback | Optional local JSON | No equivalent real feed in loop | Fails open; `KD-NEWS-001`, Phase 6 |
| Entry mode | `entry_model.determine_entry` from score/context | Market or limit readiness check | Market at row close or same-row limit range | Same-candle fill risk; `KD-BACKTEST-001`, Phase 3 |
| Partial close | Hard-coded `PARTIAL_CLOSE_RATIO=0.5` | 50% at 1R if broker volume allows | Not simulated | `KD-EXIT-001`, Phase 3 |
| Trailing | Symbol `trailing`, then `htf_bos` fallback | XAU `atr_3x`; BTC default fallback | CLI defaults `live_atr_3x` for all symbols | Mode naming and fallback differ; Phase 3 |
| Profit lock | Hard-coded runtime tiers passed by `runtime/loop.py`; function defaults otherwise | 8/12/16/20 currency-unit tiers | Not modeled | UI `lock_pct` is not the runtime source; Phase 3 |
| DXY | Resolved DXY broker symbol/correlation analysis | Live MT5 series | Synthetic weighted FX basket | Timestamp alignment repaired in Phase 2; instrument/formula policy remains Phase 6 |
| Symbol thresholds | Deep-merged profile mutates analysis module globals | Applied before evaluation/monitoring | Applied before backtest | Global mutation can leak between symbols/tests; later configuration work |
| Backtest costs | CLI values | Not applicable | Spread/slippage/commission, all default zero | Older result files omit cost metadata; later cost-model work |
| Engine mode | `BOT_ACTIVE_ENGINE`, default orchestrator | Orchestrator or legacy | Reimplemented orchestrator-like loop | Backtest does not call live orchestrator; Phase 3 |

## 7. State and persistence inventory

| Store | Writer / reader | Format and tracking | Atomic / recovery behavior |
| --- | --- | --- | --- |
| `frontend/utils/.session.json` | `session_manager`; frontend and `main.py` | JSON, ignored | Atomic temp + `os.replace`; corrupt data returns `None`; runtime settings depend on it |
| OS keyring | `credential_store`; frontend login/logout | Windows credential store, outside repository | Backend-managed; optional password recovery |
| `open_trades.json` | `trade_executor`; `main.py`, manager | JSON, ignored | Non-atomic overwrite; corrupt/missing returns `{}`; restart ticket recovery consults MT5 positions |
| `.bot_state.json` | `bot_control`; `runtime/loop.py`, `main.py` | JSON, ignored | Non-atomic overwrite; missing/error has safe defaults; controls pause/stop loop paths |
| `.bot_process.json` | `bot_runner` | JSON, ignored | Non-atomic; stale PID is treated as stopped |
| `.ui_process.json` | `ui_launcher` | JSON, ignored | Non-atomic; stale PID is treated as stopped |
| `data/analytics.db` | `analytics_db`; frontend adapter and AI/dashboard pages | SQLite WAL, ignored | Transactional commits under process-local write lock; schema auto-created |
| `logs/trade_journal.jsonl` | `trade_journal`; analytics backfill/AI | JSONL, ignored | Append is non-transactional with SQLite; DB failures are swallowed |
| `logs/setup_evaluations/*.jsonl` | `setup_logger`; analysis CLI | JSONL, ignored | Append/flush, no cross-process transaction |
| Trade CSV/JSON files under `logs/` | `trade_logger`; analytics helpers | CSV/JSON, ignored | JSON rewrites are non-atomic |
| `logs/last_scan.json` and shadow JSONL | `bot.utils.logger`; UI/diagnostics | JSON/JSONL, ignored | Last-scan rewrite is non-atomic |
| Backtest cache | `_fetch_range` | Pickle under `backtests/cached_data`, currently tracked historical files plus ignore rule for new files | Direct pickle writes; cache permits offline reruns but has no embedded code hash |
| Backtest outputs | `run_backtest` | Summary JSON and trade/equity CSV, existing files tracked | Direct writes; research evidence, not restart state |
| `bot.sqlite`, `history.db` | No active writer found in traced runtime | Legacy SQLite files, ignored locally | Not used for active recovery |
| `StrategyState` dictionaries | `main.py`, orchestrator | In-memory only | Lost on process restart; only open-ticket JSON is recovered |

## 8. Test architecture

- `tests/conftest.py` installs `FakeMT5` into `sys.modules` before test modules are
  collected. Real `MetaTrader5` cannot be reached by ordinary test imports.
- Fake `initialize` always raises. Fake `order_check` and `order_send` raise unless
  a test explicitly enables a fake response.
- Account, symbol, tick, candle, order, position and history state are reset for
  each test and recorded for boundary assertions.
- Relative writes occur under a session-level temporary working directory;
  persistence tests additionally patch every store to `tmp_path`.
- Subprocess, shell, browser and HTTP launch APIs are blocked by an autouse fixture.
  The only exception is the literal read-only Windows `ver` query used internally
  by Python/keyring platform detection; arbitrary arguments remain prohibited.
- Credential and integration environment variables are deleted for every test.
- `pytest.ini` uses strict markers and strict xfail handling. Unexpected passes are
  failures, and warning behavior is not globally hidden.

## 9. Known-defect register

| ID | Expected correct behavior | Evidence | Status | Repair phase |
| --- | --- | --- | --- | --- |
| KD-DATA-001 | Historical HTF analysis sees only candles completed by the simulated timestamp | Baseline found opening-time `ffill`; Phase 2 regression: `test_kd_data_001_m5_decision_during_h1_excludes_current_h1` | Repaired in Phase 2 | Phase 2 |
| KD-BACKTEST-001 | Signal evaluation and entry fill cannot use the same candle's full range | Baseline found same-row fill evaluation; Phase 3 regression: `test_kd_backtest_001_source_candle_cannot_fill_its_own_signal` | Repaired in Phase 3 | Phase 3 |
| KD-EXIT-001 | Backtest models the live 50% partial close at 1R | Baseline found no live-equivalent partial path; Phase 3 regressions: `test_kd_exit_001_partial_close_is_shared_and_one_shot`, `test_kd_exit_002_trailing_rule_checks_old_stop_then_activates_next_event`, `test_kd_exit_003_partial_and_final_gross_pnl_reconcile` | Repaired in Phase 3 | Phase 3 |
| KD-RISK-001 | Central max risk caps all caller-derived percentages | Baseline strict xfail; Phase 4 regression: `test_risk_engine_caps_caller_risk_at_the_central_maximum` | Repaired in Phase 4 | Phase 4 |
| KD-RISK-002 | Daily breaker includes floating P/L | Baseline received realized scalar only; Phase 4 regressions under `tests/phase4/test_drawdown_and_circuits.py` | Repaired in Phase 4 | Phase 4 |
| KD-REGIME-001 | Regime compares current normalized ATR with a causal trailing distribution | Known-defect regression and Phase 6 regime tests | Repaired in Phase 6 | Phase 6 |
| KD-NEWS-001 | Missing required news data fails closed | Known-defect regression and Phase 6 news tests | Repaired in Phase 6 | Phase 6 |
| KD-OB-001 | Mitigation means a valid post-confirmation revisit/consumption | Known-defect regression and Phase 6 lifecycle tests | Repaired in Phase 6 | Phase 6 |
| KD-STOPS-001 | Retry converts stop distances into direction-aware absolute prices | `test_invalid_stop_retry_converts_distances_to_absolute_prices` and Phase 5 broker retry tests | Repaired in Phase 5; passing regression | Phase 5 |
| KD-CIRCUIT-001 | Completed live outcomes update the authoritative loss-streak circuit once | Baseline found no live consumption; Phase 4 regression: `test_live_completed_outcome_is_consumed_once_across_store_reload` | Repaired for normal Phase 3 lifecycle closes in Phase 4; broker reconciliation remains Phase 5 | Phase 4/5 |
| KD-PERSIST-001 | Risk/circuit protection survives atomic restart state | Baseline found no durable risk state; Phase 4 tests under `tests/phase4/test_risk_store.py` | Risk state repaired in Phase 4; unrelated runtime JSON/journal coordination remains deferred | Phase 4/later |

## 10. Live/backtest mismatch register

The central mismatches are HTF visibility, same-candle fills, separate gate
implementations, synthetic versus broker DXY, absent partial closes, trailing-mode
fallback differences, realized-only drawdown, and zero-default historical costs.
These issues invalidate parity and profitability conclusions until their assigned
future phases are complete.

Phase 2 repaired only the causal HTF and timestamp-alignment findings. Phase 3
subsequently repaired same-source-candle fills, shared partial/trailing behavior,
and gross exit accounting. Their contracts and regression evidence are recorded
in `docs/PHASE2_CAUSAL_DATA.md` and `docs/PHASE3_EXECUTION_PARITY.md`. Phase 4
subsequently repaired central risk authority, floating drawdown, normal lifecycle
outcome consumption and durable risk state; see `docs/PHASE4_RISK_PROTECTION.md`.
Broker-safety, strategy-policy and cost-realism findings remain open.

## 11. Existing backtest evidence

All rows are XAUUSDm, start with 1000, and are **non-validated**. `Max DD` is the
stored absolute drawdown field, not a percentage. Older rows do not record cost
assumptions. No summary embeds code/config/data hashes.

| Result directory | Range | End | Trades | Win % | PF | Max DD | Costs (spread/slip/commission) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `shadow_3m_rr15` | 2026-04-17 to 2026-07-18 | 1348.55 | 55 | 69.09 | 2.3067 | 49.62 | 20/0/0 |
| `shadow_3m_rr15_aligned` | 2026-04-17 to 2026-07-18 | 1440.56 | 71 | 66.20 | 2.0712 | 57.86 | 20/0/0 |
| `shadow_3m_rr15_phase0_baseline` | 2026-04-17 to 2026-07-18 | 1440.56 | 71 | 66.20 | 2.0712 | 57.86 | 20/0/0 |
| `shadow_3m_rr2` | 2026-04-17 to 2026-07-18 | 1213.86 | 58 | 60.34 | 1.6378 | 68.03 | 20/0/0 |
| `shadow_3m_rr3` | 2026-04-17 to 2026-07-18 | 1185.97 | 54 | 59.26 | 1.5566 | 63.49 | 20/0/0 |
| `shadow_mode_atr3x_maxcap40` | 2026-03-01 to 2026-06-02 | 2240.79 | 59 | 72.88 | 4.9603 | 42.36 | unrecorded |
| `shadow_mode_atr3x_maxcap40_oos` | 2025-10-01 to 2026-03-01 | 1422.22 | 22 | 77.27 | 4.8646 | 40.00 | unrecorded |
| `shadow_mode_early_bos` | 2026-03-01 to 2026-06-02 | 1279.16 | 58 | 22.41 | 2.1399 | 71.45 | unrecorded |
| `shadow_mode_july_test` | 2026-07-01 to 2026-07-14 | 973.47 | 7 | 57.14 | 0.2458 | 33.65 | unrecorded |
| `shadow_mode_trail_1_5x` | 2026-03-01 to 2026-06-02 | 1542.01 | 49 | 59.18 | 3.0770 | 56.55 | unrecorded |
| `shadow_mode_trail_2stage` | 2026-03-01 to 2026-06-02 | 1558.39 | 52 | 59.62 | 3.0153 | 56.55 | unrecorded |
| `shadow_mode_trail_2x` | 2026-03-01 to 2026-06-02 | 1840.30 | 46 | 54.35 | 3.7110 | 66.05 | unrecorded |
| `shadow_mode_trail_atr3x` | 2026-03-01 to 2026-06-02 | 1732.50 | 54 | 68.52 | 3.7979 | 50.47 | unrecorded |
| `shadow_mode_v5` | 2026-03-01 to 2026-06-02 | 2510.10 | 49 | 48.98 | 4.1758 | 73.24 | unrecorded |
| `shadow_mode_wider_sl_v2` | 2026-03-01 to 2026-06-02 | 1459.60 | 59 | 72.88 | 2.6447 | 49.64 | unrecorded |
| `shadow_mode_wider_sl_v2_short` | 2026-03-01 to 2026-03-09 | 1000.00 | 0 | 0.00 | undefined/infinite | 0.00 | unrecorded |

The repository contains 44 tracked cached pickle files and 16 result sets, each
with summary/trades/equity artifacts. The cached-data Git tree identifier is
recorded in `baseline/phase1_manifest.json`; this is inventory provenance, not a
claim that the datasets or result methodology are valid.

Phase 7 formally classifies all of these artifacts as
`INSUFFICIENT_FOR_VALIDATION` without modifying them. See
`baseline/phase7_legacy_inventory.json` and
`docs/PHASE7_REALISTIC_BACKTESTING.md`.

## 12. Dependency reproduction

Human-maintained direct dependencies remain separate:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Reproduce the exact tested Windows/Python 3.10 environment in a fresh virtual
environment with:

```powershell
python -m pip install -r requirements-baseline-win-py310.txt
python -m pip check
python -m pytest
```

The baseline snapshot contains no local paths, editable installs, URLs, or
credentials. It is an environment record, not a cross-platform universal lock.

## 13. Safety boundaries

- Tests must not initialize MT5, use real account state, or reach real order APIs.
- Tests must not start the bot, Streamlit, shell commands, child processes, or HTTP.
- Test credentials are dummy values and are never passed to subprocesses.
- Runtime databases, JSON, journals and caches are redirected to temporary paths.
- CI has read-only repository permissions, no secrets, no deployment and no
  optimization job.

## 14. Deferred work

- Phase 2: causal candle alignment, historical visibility and timestamp-based DXY
  alignment (completed; see `docs/PHASE2_CAUSAL_DATA.md`).
- Phase 3: same-candle fills, market/limit execution modeling, partial closes and
  trailing parity (completed; see `docs/PHASE3_EXECUTION_PARITY.md`).
- Phase 4: risk cap, floating drawdown, circuit-breaker outcome wiring and atomic
  risk restart state (completed; see `docs/PHASE4_RISK_PROTECTION.md`).
- Phase 5: completed broker execution safety, ownership, reconciliation and invalid-stop handling; see `PHASE5_BROKER_SAFETY.md`.
- Phase 6: regime/ATR, DXY, order-block, news, session, and confluence semantics;
  repaired in `docs/PHASE6_STRATEGY_SEMANTICS.md`.
- Later phase: symbol/global configuration isolation and operational hardening.

## 15. Interpretation warning

The baseline and its synthetic smoke test establish reproducibility and safety
boundaries only. Existing or future baseline backtest results are **not evidence
of profitability, strategy validity, or suitability for live trading**.
