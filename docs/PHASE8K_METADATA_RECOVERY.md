# Phase 8K: Historical Broker Metadata Recovery

Phase 8K is an append-only, read-only evidence recovery attempt from the
Phase 8J metadata-gap decision. It does not modify Phase 8J, start a strategy
run, inspect an account, or treat current broker support material as proof of
2024 terms.

## Local Evidence Audit

The audit searched repository source and diagnostic filenames, the immutable
Phase 8 evidence packages, accepted 2024 tick/candle/spread manifests, the
owner-preserved 2024 XAUUSDm quote archive names and members, and safe filename
inventories under the owner Documents, Desktop, and Downloads roots. It found
the accepted quote-only annual source and current-only broker-support material.
It did not find an effective-dated 2024 specification export, order/fill report,
account statement, terminal/Experts journal, or `symbol_info` dump.

The accepted archive schema contains provider, symbol, UTC timestamp, bid, and
ask. It establishes quote representation, not accepted lot sizes, broker
economics, margin treatment, filling modes, or server restrictions. Source code
defaults and synthetic tests are expressly excluded as broker evidence.

## Recovery Result

The record classifies observed three-decimal quote serialization as
`EMPIRICALLY_DERIVED_FROM_2024_DATA`. This is a parsing fact only: it is not a
broker `point` or trade-tick-size rule. Contract size, tick value, lot bounds,
volume step, margin/leverage, filling modes, stop/freeze levels, and
symbol-specific restrictions remain unbounded because no independent historical
execution or economic evidence was found. Current support material remains
`CURRENT_ONLY`.

No numeric scenario was invented to clear a gate. In particular, a stop or
freeze level cannot be bounded by picking a larger number without proof that it
is more restrictive than every historical broker constraint.

## Governance

The recovery package binds the exact Phase 8J policy/readiness and Phase 8I
acceptance review hashes. It remains development-only and must keep:

- `all_material_metadata_bounded=false`
- `development_metadata_gap_acceptable=false`
- `development_evaluation_sufficient=false`
- `strategy_evaluation_authorized=false`
- `accepted_for_final_validation=false`

Even a future fully bounded recovery would require a separate explicit strategy
execution checkpoint. When official effective-dated material arrives, it must
be published as a new immutable revision, compared with every Phase 8K finding,
and followed by a new acceptance review.

Published immutable overlays:

- `evidence-broker_metadata_recovery-v1-712deee4c757709f`
- `evidence-metadata_recovery_readiness-v1-f3301b9715937ad0`
