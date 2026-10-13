# Phase 8 V2 — Variant V004 Attempt 1 Implementation Blockage Record

## 1. Executive Summary & Formal Disposition

- **Variant ID:** `phase6-development-v2-V004`
- **Variant Title:** `Unified Requested-Side Entry Direction Authority`
- **Attempt ID:** `phase6-development-v2-V004-ATTEMPT1`
- **Linked Effective Hypothesis:** `phase8-v2-H009-TC001` (*Entry Direction Authority Coherence*)
- **Historical Hypothesis:** `phase8-v2-H009`
- **Target Domain:** `TIER_A_FOLD01` (`fold-01-a8b406884ab3525a`)
- **Execution Timestamp (Exposure Event):** `2026-10-13T12:22:49Z` (Execution start: `2026-10-13T12:22:10Z`)
- **Formal Supervisory Disposition:** `IMPLEMENTATION_BLOCKED_POST_EXPOSURE`
- **Status of V004:** CLOSED. V004 MUST NOT be patched and rerun.
- **Variant Slot 4:** PERMANENTLY CONSUMED (`4 / 8` variants observed; non-refundable per Charter §11 and §38).
- **H009 / H009-TC001 Status:** Remains `REGISTERED` (result `null`, disposition `null`). V004 completed zero Gate-11 observations, so H009 remains scientifically unresolved.

---

## 2. Canonical Git Baseline

- **Repository:** `https://github.com/Chipser-Paul/forex-signal-bot.git`
- **Branch:** `integration/phase8-checkpoint-20260921`
- **Active Commit:** `5ffa8608370e19d5049e96da50dafa9d3d7aef54`
- **Tree:** `c07d6bbd50d7e8cc6f00b572c023b0de5db36375`
- **Parent:** `c604a7763c09a960d676fa8f152ac249cd041eed`
- **Subject:** `fix: align V004 specification and sealed baseline contract`
- **Tracked Working Tree:** Verified clean and identical to remote integration branch before store access and after failure.

---

## 3. Tooling, Implementation, and Specification Identities

- **Implementation Module:** `bot/strategy/variant_v004.py`
  - Committed Git Blob SHA: `a6aa1d9e68dd5d9d29cb6cc5399dc3a773fbfd47`
  - Canonical Fingerprint (`canonical_git_blob_v1`): `650c84b6ead13b33476888047e6e24673392f65e61fd175a0270bd6ac86b60a3`
- **Tooling Module:** `backtests/phase8_v2_variant_v004_eval.py`
  - Committed Git Blob SHA: `fda5f879bd199ea974d0ec27a544fe202307b3cb`
  - Canonical Fingerprint (`canonical_git_blob_v1`): `66912f82e29cca4dcc9a3bacda131359c941b9cd49ac47cd7bc2432f119e53f3`
- **Specification Document:** `docs/PHASE8_V2_VARIANT_V004.md`
  - Corrected TC001 SHA-256: `fe226ca5f2bb8e3336ad0ce5d6430f57eb88bc9427f343d1716fd161352fd801` (19,201 bytes)
  - Historical Phase-A SHA-256: `9ad9b5660bcb2d6d209c430958c3d88e47b83122c6c9816b6f5ee40d61b11b7f` (12,523 bytes)

---

## 4. Input Store & Sealed V003 Prior Integrities

- **Store Path:** `C:/Users/chips/forex-signal-bot-data/phase8/evidence/market-feature-store/fold-01-a8b406884ab3525a`
  - Store Identity SHA: `a8b406884ab3525ab8750958d700db32fddaa444d5beac0fc64de395505d8fe4`
  - Rows Content SHA: `96c522e062087cb452e1667dc4f50b5b2e81c876265d1bce159cff5a866e5e22`
  - Total Snapshots: 13,269 (`verify_rows=True` passed prior to replay loop)
- **Sealed V003 R001 Prior Artifact:**
  - Path: `C:/Users/chips/forex-signal-bot-data/phase8/v2_variants/phase6-development-v2-V003/fold01/phase6-development-v2-V003_result.json`
  - SHA-256: `50117c399481a2e31b8da6260da4e05c8719a522efb524f80bb2063319c41ff8`
  - Size: 45,221 bytes (verified read-only)

---

## 5. Exact Failure Mechanism & Root Cause

### 5.1 Verbatim Error
```python
bot.strategy.variant_v004.V004VariantError: V004 directional consistency violation: requested_side 'bullish' contradicts structural pair side <StrategySide.FLAT: 'FLAT'> (expected 'LONG')
```

### 5.2 Call Stack
1. `backtests/phase8_v2_variant_v004_eval.py:976` in `run_v004`: `observe_v004_decision(...)`
2. `backtests/phase8_v2_variant_v004_eval.py:606` in `observe_v004_decision`: `evaluate_v004_entry_readiness(...)`
3. `bot/strategy/variant_v004.py:163` in `evaluate_v004_entry_readiness`: `raise V004VariantError(...)`

### 5.3 Root Cause Analysis
In TC001, an executable fail-closed directional consistency check was added to `evaluate_v004_entry_readiness` (lines 157–166 of `bot/strategy/variant_v004.py`):
```python
req_side = str(requested_side).lower() if requested_side is not None else ""
if req_side in ("bullish", "bearish") and pair is not None and hasattr(pair, "side"):
    pair_side_val = getattr(pair.side, "value", pair.side)
    pair_side_str = str(pair_side_val).upper()
    expected_pair_side = "LONG" if req_side == "bullish" else "SHORT"
    if pair_side_str != expected_pair_side:
        raise V004VariantError(...)
```
In `backtests/phase8_v2_variant_v004_eval.py`, `observe_v004_decision` is invoked across all 526 Gate-11 entrants in Fold 01. For decisions where no active structural order block or FVG pair has formed, `pair.side` is `StrategySide.FLAT`.
Because this consistency check was placed unconditionally at the very top of `evaluate_v004_entry_readiness`—prior to checking whether `v003_entry_ready == True`, prior to checking `v003_gate11_passed`, and prior to entering the fallback evaluation—and because it treated `StrategySide.FLAT` as an opposing directional contradiction rather than an unformed structural state, the function failed closed immediately on the first Gate-11 entrant decision where `pair.side == StrategySide.FLAT`.

---

## 6. What V004 Did NOT Test

- **Gate-11 V004 Observations Completed:** `0`
- **Sealed-V003 Baseline Reconciliation:** `NOT COMPLETED`
- **Valid V004 R001:** `DOES NOT EXIST`
- **Scientific Evidence Provided:** None. V004 provides no empirical evidence regarding H009 support or refutation, candidate-ready count, candidate frequency, or Tier-A opportunity density.
- **Classification Precaution:** This blockage must NOT be interpreted as `OPPORTUNITY_INSUFFICIENT` or candidate absence.

---

## 7. Status of Hypothesis H009

- `phase8-v2-H009` and effective `phase8-v2-H009-TC001` remain:
  - `status: "REGISTERED"`
  - `result: null`
  - `disposition: null`
- H009 remains an open, unresolved market/architecture hypothesis. No new hypothesis H010 is registered because the failure was purely implementation scoping.

---

## 8. Post-Failure Forensics Classification

A technical post-failure inspection script was executed to extract snapshot metadata from the already-exposed Fold-01 store to ascertain the exact point of failure.
- **Classification:** `TECHNICAL_POST_FAILURE_FORENSICS_ONLY`
- **Properties:**
  - Did NOT evaluate V004 strategy behavior.
  - Did NOT consume an additional variant budget slot.
  - Is NOT a preregistered diagnostic (NOT D007).
  - Must NOT be used for candidate-density inference or H009 evaluation.
  - Consumed zero additional budget.

---

## 9. Blockage Artifact & Log Evidence

- **Blockage Artifact:** `C:/Users/chips/forex-signal-bot-data/phase8/v2_variants/phase6-development-v2-V004/fold01/phase6-development-v2-V004_ATTEMPT1_BLOCKAGE.json`
  - SHA-256: `2900dac5d095322839ba28d3b2c2e09bdce28d83bb1c7934bf6d81d8a03ba5f1`
  - Bytes: `6,129`
  - Verified read-only.
- **Execution Log:** `C:/Users/chips/forex-signal-bot-data/phase8/v2_variants/phase6-development-v2-V004/fold01/phase6-development-v2-V004_attempt1.log`
  - SHA-256: `32a12357e3cc24285201744d1b369297bfe5ee44e7c7ef31795eed432d8d0a44`
  - Bytes: `1,314`
  - Verified read-only.

---

## 10. Budget and Governance Transition

- **Diagnostics Executed:** `5 / 12` (unchanged)
- **Strategy Variants Observed:** `4 / 8` (PERMANENTLY CONSUMED at `2026-10-13T12:22:49Z`; non-refundable)
- **Numeric Parameter Trials:** `0 / 4` (unchanged)
- **Upward Revision Lock:** `ACTIVE`
- **Tier B:** Strictly `SEALED` (Folds 02–04, holdout, 2025+ data untouched)
- **Production Files:** 0 bytes diff; completely untouched.
- **Strict Scientific Stop:** V004 is closed without patch or rerun. Variant V005 is authorized for preregistration and synthetic freeze under separate governance.
