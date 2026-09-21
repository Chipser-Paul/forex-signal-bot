# Phase 8N-B — Empirical Strategy Adapter Checkpoint

Status: **PARTIAL EXTRACTION; AMENDMENT BLOCKED**. No empirical strategy run,
entry intent, superseding plan or commit exists.

## Supported production path

`main.py` calls the live `bot.state.orchestrator` gates. The orchestrator
fetches closed M5/M15/H1/H4/D1/W1 candles, builds W1/D1/H4 bias through
`bot.analysis.bias_engine`, gathers liquidity and setup evidence, checks DXY,
news and session, scores confluence, calls the Phase 6 canonical compatibility
reducer, then calls the stateful `determine_entry`. The live boundary builds
absolute stop/target with `main._build_orchestrator_trade_levels`, creates a
Phase 3 intent, and passes it to Phase 4 risk and Phase 5 broker authorities.
The legacy shadow backtester is diagnostic, not the supported live path or a
Phase 7 cost-aware empirical runner. These paths must not be blended.

`baseline/phase8n_production_mapping.json` is the machine-readable field,
source timeframe, function, availability, failure and identity audit.

## Semantics-preserving extraction

`bias_snapshot_from_frames` and `build_liquidity_map_from_frames` now accept
injected causal frames. Their live wrappers fetch broker frames and delegate
to the same functions. The bias computation still calls the existing market
structure analyzer, uses unchanged W1/D1/H4 weights and the unchanged
`resolve_trade_bias` fallback rules. The liquidity map still calls the same
analyzer and previous-day/week/Asian-range functions. An unused MT5 import
was removed from `utils.indicators`; market-data imports in these modules are
lazy, so offline imports do not load MetaTrader5.

The partial `bot.validation.empirical_strategy_adapter` selects the production
XAUUSDm M5 decision timeframe and required causal M5/M15/H1/H4/D1/W1
snapshots with Phase 2 `causal_snapshot`. Exact `available_at` equality is
included; the instant before close excludes the candle. It rejects missing or
insufficient input history and derives requested side solely from the existing
bias snapshot and resolver. Its name and docstring explicitly prohibit using
the prepared bias as an entry approval. It cannot emit a `StrategyDecision` or
`EntryIntent` while required fields are unmapped.

## Exact unresolved fields

| Field | Consumer and production source | Why unavailable | Smallest safe repair |
| --- | --- | --- | --- |
| `SetupEvidence` flags and setup ID | orchestrator gates 8–11; H1 sweep, M5 displacement/OB/FVG, M15 confirmation and mutable `StrategyState` | no injected, deterministic gate/state transition reducer exists | extract existing gate calculations with causal-frame and event-clock injection, preserve gate order, prove live/offline results equal |
| news snapshot `retrieved_at` | `bot.strategy.news.evaluate_news`; accepted official USD timeline | package records retrospective retrieval, not a provable fresh provider snapshot as of each 2024 decision | obtain as-of provenance or a separately reviewed, versioned historical-news interpretation; do not invent a 2024 retrieval time or alter the frozen Phase 6 gate |
| `entry_type`, trigger, setup candidate | `determine_entry`; mutable `StrategyState` | state expiry, update and candidate timestamps call `datetime.utcnow`; no causal clock/restart transition contract | inject an event clock and deterministic state snapshot into the *same* entry model, preserving defaults and proving equivalence |
| absolute stop and target | `main._build_orchestrator_trade_levels`; broker metadata, OB and liquidity anchors | no offline final-gate injection or dated effective symbol specification is bound | extract the existing level builder to a shared injected pure call, reject missing anchors/metadata, prove equality |
| Phase 3 intent and invalidation | `intent_from_strategy_entry`; entry dictionary, source candle, levels | blocked by all upstream fields | call the existing intent constructor only after all upstream gates pass; retain source-candle barrier |

The accepted development metadata scenarios are development proxies, not
historically verified broker specifications. No substitute strategy rule,
news retrieval time, entry price, stop or target has been inserted.

## Synthetic proof and safety

Synthetic tests compare live-wrapper and injected-frame W1/D1/H4 bias and
liquidity-map serialization. Long and short bias agree; an H1/H4/D1/W1 row
whose availability equals the decision boundary is visible, while one
microsecond before it is not. Insufficient history fails closed. These are
**partial parity proofs**, not full strategy-decision or entry-intent parity.
No profitability, final-validation or holdout claim follows. The parent Phase
8M plan remains unchanged and awaiting separate, reviewed supersession.

## Phase 8N-C follow-up (still blocked)

Event-time injection now covers legacy `StrategyState` timestamps and expiry;
the supported orchestrator still generates process-time setup IDs and mutates
state inline. Absolute stop/target construction has been extracted to
`bot.strategy.trade_levels.build_trade_levels`, called by the existing live
wrapper with unchanged profile and risk-facade inputs. The accepted official
news timeline can be evaluated **development-only** through
`bot.validation.historical_news_replay` with
`RETROSPECTIVE_OFFICIAL_SCHEDULE` provenance and actual retrospective
retrieval timestamps. That is not an as-of-2024 live provider snapshot; the
live freshness gate remains unchanged.

The exact remaining mapping blocker is the stable setup state/evidence/ID
transition from orchestrator gates 8–13. The partial adapter still emits no
decision, stop/target or intent. See `docs/PHASE8N_CAUSAL_STRATEGY_ORCHESTRATION.md`.

## Phase 8N-D retained Stage 2 implementation

The earlier paragraphs describe the checkpoint, not the current uncommitted
implementation. The offline adapter now supplies read-only causal acquisition
to the supported `StrategyOrchestrator` itself. Both paths call the same frozen
gate aggregate and pure reducer. Existing bias, liquidity and DXY functions
are shared with exact production lookbacks and explicit event time.
`evaluate_setup_inputs` can create synthetic levels and Phase 3 intents through
the existing builders, with effective-dated injected metadata and no broker
call. Non-candidates and invalid levels cannot become intents.

Sixteen symmetric synthetic wrapper cases pass, including real canonical
long/short decisions and complete approved-case level/intent payload equality.
The canonical engine is not mocked in those cases; acquired evidence is
synthetic. This is not full required lifecycle/restart/per-cell parity. Final
fill consumption is not yet linked to the serialized setup event history.
No empirical evaluation or plan amendment is authorized. Mapping version
remains explicitly incomplete pending that acceptance gap.
# Phase 8N-E completion reference

Synthetic Stage 2 acceptance and append-only supersession passed. The
successor is `evidence-development_evaluation_plan-v1-ba2745f96fda3939`,
fingerprint `d69bbed4542d9517dc46d043d12324f6a921a846bca39c30e57fdc3774779c72`.
Its implementation/cell bindings are also recorded in the production mapping
manifest. Evaluation still requires separate authorization and an approved
streaming runner; no empirical input or holdout was read for these proofs.

The prior blocked checkpoints below are historical. The shared setup adapter
now has a versioned fill-authoritative consumption/restart path; see
`docs/PHASE8N_CAUSAL_STRATEGY_ORCHESTRATION.md` for the exact ordering.
Live and offline evaluation share immutable acquired inputs, the timed gate
reducer, restored state, levels and existing Phase 3 intent serialization.
Confirmed entry consumption is separate from evaluation: Phase 7 must publish
its actual positive entry fill before the shared coordinator can consume.
The historical-news input remains retrospective official event-time veto
evidence, not evidence of a fresh provider retrieval in 2024. Live freshness
policy is unchanged. Synthetic parity does not authorize empirical evaluation.
