# Phase 8 V2 Variant V001 — Fold-01 Structural Result (R001)

**Variant:** `phase6-development-v2-V001` — Canonical FVG ATR-Series Compatibility Repair
**Hypothesis:** `phase8-v2-H005` — FVG ATR-Series Interface Repair
**Research identity:** `phase6-development-v2`
**Charter:** `phase8-v2-research-charter-v1-8527e3a5eec98f53` (SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
**Result classification:** `DEVELOPMENT_VARIANT_EVIDENCE — V001 — FOLD01 — NOT PROFITABILITY EVIDENCE`

## Identity / lineage

* Charter: `phase8-v2-research-charter-v1-8527e3a5eec98f53` (SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`).
* V001 specification: `docs/PHASE8_V2_VARIANT_V001.md`, SHA-256 `0b1d5ec57c68746f7c346c4b576220460d0dad54d218a2add34dbe6e2adbf8fb`.
* Strategy implementation commit: `b4a1b0e6ab353f513a0df554840344f322e0964c` (canonical source used).
* Measurement tooling actually producing this result (MR003): `1a8e4b278dad1741c056ab0d44b8e61dbe36f497`; evaluator blob verified equal to HEAD before invocation; evaluator schema `phase8_v2_v001_result_v1`; fingerprint contract `canonical_git_blob_v1`.
* Complete tooling lineage: original frozen tooling `d87b71491203249e6ab3dd95bca4b9ee89cf3e9e` -> prospective readiness `d621aebcaae89b99d3727fb2fff02a3ada53b0ae` -> MR001 `a193702c4d26cbae7e5121950fa66574b860a69d` -> MR002 `6e253dd81b41b1c95d085463673a7e8e11dfa16e` -> MR003 `1a8e4b278dad1741c056ab0d44b8e61dbe36f497`.
* Governance lineage: `phase6-development-v2-V001-MR001`, `phase6-development-v2-V001-MR002`, `phase6-development-v2-V001-MR003` (append-only; none superseded).
* Measurement window: `2026-09-24T10:55:06.956274+00:00` -> `2026-09-24T11:01:50.317442+00:00`.

## Exposure history

* V001 empirical exposure occurred `2026-09-23T15:23:28.661013+00:00` via the fresh causal Fold-01 rebuild; strategy-variant budget became `1 / 8 observed` and `UPWARD STRATEGY-VARIANT / PARAMETER-TRIAL BUDGET REVISION PROHIBITED = ACTIVE` permanently.
* Store published by that rebuild: `fold-01-a8b406884ab3525a` (store identity SHA-256 `a8b406884ab3525ab8750958d700db32fddaa444d5beac0fc64de395505d8fe4`; rows-content SHA-256 `96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22`; 13,269 decision snapshots; fold-01/full). The historical store `fold-01-1d710826193a6767` is prohibited as V001 input and was never opened.

## Original measurement blocker

* The frozen evaluator (`d87b7149...`) refused the conforming store with `BoundaryError: 2025+ evidence path refused` before any strategy-semantic processing: whole provenance mappings were stringified into the filesystem-path scanner, so hash-hex fragments of real SHA-256 digests were misread as future-year path components. Zero metrics emitted. External immutable blockage artifact: `phase6-development-v2-V001_fold01_EXECUTION_BLOCKAGE.json`, SHA-256 `55a382dce5f00752e70ed03cb244db5f1277a471b78b43055819b3f118a03432`.

## MR001

* `phase6-development-v2-V001-MR001` — provenance/path-validation wiring repaired (structured validator `_assert_source_dates_within_development`; field-scoped `_reject_holdout_identity_paths`; genuine holdout/2025+ references still fail closed; hash-digit false positives eliminated). Commit `a193702c4d26cbae7e5121950fa66574b860a69d`.

## Second blocker

* The post-MR001 rerun failed closed at the tool's own reconciliation gate: zero decisions carried an FVG observer reconciliation. Root cause (proven read-only): `run_v001_evaluation` seeded the sequential setup-state chain with `None`; the production orchestrator's `restore_setup_for_evaluation -> state_from_record(None)` raised, which the canonical adapter classified as `action=error / orchestrator_input_unsafe` for all 7,316 ok-path rows. Zero metrics emitted. External immutable artifact: `phase6-development-v2-V001_fold01_R001_ATTEMPT_BLOCKAGE.json`, SHA-256 `a02b59cb227fbc1d41f6036bb1d3fd2e9a6601af143ae447139ce44d202fda74`.

## MR002

* `phase6-development-v2-V001-MR002` — decision-loop seed omission repaired: canonical seed `record_from_state(StrategyState(event_time=2024-01-01 UTC), event_at=seed)` and D001-exact error-carry semantics (advance only on success; preserve prior valid state on error). Commit `6e253dd81b41b1c95d085463673a7e8e11dfa16e`.

## Third blocker

* The post-MR002 rerun crashed deterministically on `D001Error: state record event mismatch at row-1711987200000` at the first canonical `dxy_blocked` snapshot (2024-04-01T16:00Z). Root cause (proven read-only): the loop omitted D001's canonical pre-orchestration classification stage, so 4,815 `early_exit` and 1,138 `dxy_blocked` rows (empty `gate_event_id`) reached the orchestrator. Zero metrics emitted. External immutable artifact: `phase6-development-v2-V001_fold01_R001_ATTEMPT2_BLOCKAGE.json`, SHA-256 `7a472a509c9bddd2a0100791a04e207a2ef7c33769b2d0f9e6da3184e31d89db`.

## MR003

* `phase6-development-v2-V001-MR003` — snapshot-classification omission repaired: the V001 loop now reuses D001's `classify_snapshot`, `_reference_check_failed` and `reconcile_accounting` verbatim by import (scheduled -> classify -> reference-check -> observe -> error-preserving carry -> accounting reconciliation). Commit `1a8e4b278dad1741c056ab0d44b8e61dbe36f497`. MR003 passed supervisory review; this measurement ran under that authorization.

Three measurement-tooling failures occurred before this result; each was repaired append-only and none is erased from the scientific record.

## Final structural result

All structural metrics below are produced by the frozen MR003 evaluator against the preserved store; the evaluator's own deterministic payload is the primary record (path, SHA-256 and size under "External R001").

## Snapshot accounting

* Scheduled snapshots: 13,269.
* Successfully measured structural decisions: 7,316.
* Pre-evaluation buckets: missing_history 4,815; unavailable_input 1,138; evaluation_error 0.
* Reconciliation: 13,269 = 7,316 + 4,815 + 1,138 + 0 (canonical `reconcile_accounting` passed; the naturally produced accounting is consistent with the pre-MR003 read-only diagnostics, which were not used as targets).

## Detector eligibility

* Detector-eligible decisions: 1,489 (eligibility source `displacement_valid_tier_ok`); stage-A fail decisions 0; observer reconciliation 1,489 / 1,489 exact.

## ATR/FVG attrition

* Windows total 220,372; ATR-valid 202,504; ATR warm-up 17,868; displacement-body threshold passes 5,355.
* Geometric gaps: bullish 2,275; bearish 2,212; none 868.
* Zones: same-direction (all) 2,788; opposite-direction 1,699; filled 3,782; unfilled 705.

## Canonical FVG availability

* Decisions with final canonical FVG present: 455; total final FVG count 579 (bullish 322, bearish 257); unique canonical FVG identities 65.
* Descriptive (preregistered): FVG width median 1.651 (q1 0.773, q3 2.439); ATR at entry-tail median 1.874; body/ATR min 1.5008 — i.e. the frozen 1.5x displacement threshold is exercised by real windows.

## Gate-11

* Gate-8 liquidity: entered 7,316; passed 3,607; failed 3,709.
* Gate-9 displacement: entered 3,607; passed 1,489; failed 2,118.
* Gate-10 internal structure: entered 1,489; passed 526; failed 963.
* Gate-11 confluence: entered 526; passed 1; failed 525.
* Final canonical strategy gate: entered 1; failed 1.
* Action/reason accounting: skip 1,489; wait 5,827; reasons liquidity_sweep_missing 3,709; displacement_missing 2,118; internal_structure_missing 963; score_below_threshold 525; dxy_direction_conflict 1.

## OB/FVG coexistence

* Decisions with a valid OB and an FVG coexisting: 1; OB/FVG zone pairs: 1.

## Canonical overlap

* Canonical overlap true: 1; canonical overlap false: 0 (evaluated only where a real canonical pair exists).

## candidate_ready density

* Raw `candidate_ready`: 0 against the preregistered research-density target of 90 (`research_density.zero = true`).

## V001 classification

* `FUNCTIONAL_REPAIR_NO_CANDIDATES` — the repaired detector demonstrably evaluates valid empirical FVG windows (455 decisions with final canonical FVGs; 579 FVG evaluations; 65 unique identities; Gate-10/11 and overlap paths exercised) while raw `candidate_ready == 0`.

## H005 disposition

* `SUPPORTED_BY_V001` — supplying the equivalent rolling ATR series restores actual execution/evaluation of the frozen canonical FVG semantics under unchanged thresholds. Per the preregistration, H005 support does not require candidates, the 90-density target, or profitability.

## What V001 establishes

* The S001 interface defect is repaired without changing any strategy rule: the frozen detector now evaluates real Fold-01 windows end-to-end (ATR validity, displacement, geometric gaps, direction/fill filters, Gate-10/11, OB/FVG coexistence, canonical overlap).
* Real structural density exists upstream (2,275 bullish / 2,212 bearish geometric gaps; 705 unfilled zones; 65 unique final FVG identities) and the full frozen gate funnel is now empirically observable.
* H005 is supported; the measurement tooling lineage MR001-MR003 is validated by a fully reconciled run.

## What V001 does not establish

* Nothing about profitability, fills, closed trades, win rate, expectancy, drawdown, returns or account growth — none were computed.
* Nothing about alternative parameters (no ATR-period, multiplier, overlap, confluence or timing counterfactuals were evaluated).
* Nothing that auto-promotes H001, H002, H003 or H004, and nothing that selects or freezes a candidate.
* Nothing on reserved evidence: Fold 02, Fold 03, Fold 04, 2025+ data and holdout were not accessed, and completing R001 does not authorize Tier B or release any reserved fold.

## Reserved-evidence status

* Fold 02 / Fold 03 / Fold 04: untouched. 2025+: untouched. Holdout: untouched (`holdout_untouched = true`, `reserved_folds_untouched = true` in the evaluator payload).
* Budget after result: diagnostics `1 / 12`; strategy variants `1 / 8` (completed, not re-consumed); numeric parameter trials `0 / 4`; upward budget-revision lock `ACTIVE`.
* External result payload: `phase8_data::/v2_variants/phase6-development-v2-V001/fold01/phase6-development-v2-V001_result.json` — SHA-256 `63e3be0a73960a1189670afd17feb67061c5c75e351438dbd1afb7343f0d8d11`, 7,104 bytes, read-back verified, never mutated after sealing.
