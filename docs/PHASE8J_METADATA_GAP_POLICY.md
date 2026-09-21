# Phase 8J: Historical Broker Metadata Gap Policy

Phase 8J is an append-only decision overlay on the Phase 8I dataset-acceptance
review. It does not modify the Phase 8I package, activate a strategy run, or
upgrade current Exness support material to historical 2024 fact.

## Owner Decision

Effective-dated 2024 XAUUSDm broker metadata is unavailable while an official
Exness request remains pending. The decision is to examine a development-only,
assumption-only metadata-gap policy. It is not a statement that Exness cannot
provide the material later.

## Evidence Binding

The policy is content-addressed and binds the exact Phase 8I acceptance review,
Phase 8H cost-policy fingerprint, active Phase 8I swap-policy activation, all
published broker-support revisions, the selected current metadata evidence, and
the accepted tick, causal-candle, observed-spread, news, and DXY identities.
Publication uses the Phase 8E atomic evidence store. Re-publication of identical
content is idempotent; a different Phase 8J decision under this schema fails
closed instead of silently superseding it.

## Classification Vocabulary

- `HISTORICALLY_VERIFIED`: effective-dated evidence proves the field for 2024.
- `EMPIRICALLY_DERIVED_FROM_2024_DATA`: directly observed property of accepted
  2024 artifacts, not an asserted broker rule.
- `CURRENT_ONLY`: present-day support or platform evidence only.
- `ASSUMPTION_ONLY`: an explicit development model, never historical fact.
- `UNAVAILABLE`: no usable evidence.

## Field Decision

Observed quote representation and observed-tick availability are derived from
accepted 2024 artifacts. They can constrain replay parsing and availability,
but do not prove historical broker order-normalization or published sessions.

Contract size, point/tick size, tick value, minimum/maximum lot, volume step,
margin/leverage, filling modes, stop level, freeze level, and other
symbol-specific restrictions remain either `CURRENT_ONLY` or `UNAVAILABLE`.
Their historical ranges are not bounded by the current evidence. The policy
therefore uses `FAIL_CLOSED_NO_*_ASSUMPTION` treatments rather than inventing
favorable numeric inputs. Current execution mode can only be represented by
the existing adverse, assumption-only `MARKET_ON_TRIGGER` model.

## Outcome

Because material broker metadata remains unbounded, the policy record must set:

- `development_metadata_gap_acceptable=false`
- `development_evaluation_sufficient=false`
- `strategy_evaluation_authorized=false`
- `accepted_for_final_validation=false`

The readiness overlay preserves these gates and lists every unresolved blocker.
No strategy or backtest is run in this checkpoint.

Published records:

- `evidence-broker_metadata_gap_policy-v1-c1aea67b764d323f`
- `evidence-metadata_gap_readiness-v1-1c4504f33bed24ea`

The eleven unresolved material blockers are contract size, point/tick size,
tick value, minimum/maximum lot, volume step, margin/leverage, filling modes,
stop level, freeze level, and symbol-specific execution/P&L restrictions.

## Future Official Evidence

If effective-dated 2024 metadata arrives, it must be ingested as a new immutable
revision. The future process compares every official value with each provisional
assumption, reports mismatches, reruns acceptance, and invalidates or reruns any
materially affected development result. This policy is retained unchanged.
