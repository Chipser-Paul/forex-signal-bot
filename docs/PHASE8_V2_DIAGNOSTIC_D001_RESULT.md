# Phase 8 V2 Diagnostic D001 — Result Record (R001)

**Diagnostic:** `phase8-v2-D001` — Frozen OB/FVG Structural Attrition Decomposition
**Classification:** `DEVELOPMENT_DIAGNOSTIC_EVIDENCE — FOLD01 — NOT PROFITABILITY EVIDENCE`
**Research identity:** `phase6-development-v2`
**Charter:** `phase8-v2-research-charter-v1-8527e3a5eec98f53` (SHA-256 `8527e3a5eec98f53795f396ad7cb5baf80aa549144ebaf580f3afe972cf204bc`)
**Preregistration:** commit `8985fb2f8396a999dbddcc8b51342788823dc2c2` (specification unchanged since; see provenance correction `phase8-v2-PC001`)
**Provenance correction:** `phase8-v2-PC001`
**Tooling commit:** `1f2f997c1763f7a6e50f7d02e35d88bcdd568ebf` (parent `403587e0…`; tests 32/32 + regression 25/25 before any data access)
**Executed:** 2026-09-23T00:13:49Z, duration 117.8 s, zero orchestrator errors
**Raw output (external, outside Git):** `evidence/v2_diagnostics/phase8-v2-D001-R001/phase8-v2-D001_result.json` — SHA-256 `af03bfbe688b010deb70261eabe2240336e16bbff07d519ea20a8ccbc3b99c10` (4,901 bytes; deterministic canonical JSON; read-back hash-verified)
**Budget after execution:** `1 / 12` diagnostics · `0 / 8` strategy variants observed · `0 / 4` numeric parameter trials

---

## 1. What D001 can tell us

D001 decomposes, within Fold 01 and under **unchanged V1 frozen semantics**, where OB/FVG structural eligibility disappears before candidate creation. It observes only preregistered structural quantities: decision accounting, the canonical gate funnel, OB and FVG state/reason decompositions, the OB × FVG × overlap contingency, canonical overlap geometry (where defined), and direction consistency. All decisions were evaluated through the production orchestrator path (`evaluate_orchestration_from_features` + the untouched frozen reducer), with cell-local state carry identical to the empirical reference pipeline.

## 2. What D001 cannot tell us

It cannot say whether any alternative overlap rule, proximity threshold, sequential association, or 7/8 confluence architecture *would* produce sufficient candidates — no counterfactual candidate count was computed, by preregistration. It cannot say anything about profitability, fills, or closed trades. It does not test H003 (no temporal-distance analysis). It is not evidence of strategy quality in either direction.

## 3. Empirical provenance

| Item | Value |
|---|---|
| Fold store | `fold-01-1d710826193a6767` (full coverage, 13,269 rows) |
| Store SHA-256 | `1d710826193a67671e99f968160b2f8d586444f749a7f39e94c3ce6c04b0255e` |
| Boundary | `[2024-04-01T00:00:00Z, 2024-06-08T00:00:00Z)`, M5 decisions |
| Row integrity | `verify_rows=True` passed over all 13,269 rows |
| Fingerprint contract | Legacy V1 verification only; evaluation semantics byte-identical across `c38f9dc..1f2f997` |
| Historical build note | The store was built at `42c0956` in the historical build worktree and binds the pre-adapter pipeline fingerprint `765b19d7…`; the canonical-byte adapter publication `94b278a` post-dates the store build. Store resolution used direct identity verification (all nine frozen identity fields independently reproduced). This is the documented V1 `legacy_worktree_bytes_v0` defect that `canonical_git_blob_v1` now prevents prospectively. |

## 4. Decision accounting (reconciles exactly)

13,269 scheduled = 7,316 reducer-classified + 4,815 missing-history (`early_exit`, incl. 169 news-blocked) + 1,138 unavailable-input (`dxy_blocked`) + 0 evaluation errors.

Historical V1 reproduction: wait 5,827 ✓ · skip total 7,273 ✓ · scheduled 13,269 ✓ — the run exactly reproduces the known (already-contaminated) V1 diagnostic evidence.

## 5. Preregistered results

### 5.1 Gate funnel (canonical gate order)

| Gate | Entered | Passed | Failed | Pass rate |
|---|---|---|---|---|
| `gate_8_liquidity` | 7,316 | 3,607 | 3,709 | 0.4930 |
| `gate_9_displacement` | 3,607 | 1,489 | 2,118 | 0.4128 |
| `gate_10_internal_structure` | 1,489 | 526 | 963 | 0.3533 |
| `gate_11_confluence_score` | 526 | 0 | 526 | 0.0000 |

(`canonical_strategy` and `gate_12_13_rr_entry`: 0 entered — nothing passes gate 11.)

### 5.2 OB decomposition (7,316 reducer decisions)

OB present: 526 (7.2%). Reasons: absent 6,790; `ob_mitigated` 307 (58.4% of present); `ob_outside_pd_zone` 79 (15.0%); `ob_invalidated` 75 (14.3%); `ob_no_displacement` 61 (11.6%); `ob_aligned` 4 (0.8%). Direction (of the OB search, = resolved HTF bias): bullish 4,740 / bearish 2,576. Among present OBs: `mitigated=True` 382 of 526; `in_pd_zone=True` 4 of 526.

### 5.3 FVG decomposition

FVG present: **0 of 7,316** — the canonical `fvgs` list was empty in every reducer decision. (FVG detection is downstream of the displacement gate, and no decision in this fold produced an FVG at decision time under frozen semantics.)

### 5.4 OB × FVG × overlap contingency (raw counts)

| valid_ob | fvg_present | overlap | Count |
|---|---|---|---|
| False | False | False | 7,312 |
| True | False | False | 4 |

`overlap_true_decisions`: 0. Geometry observations (both regions existing): 0 — the overlap geometry is **vacuously unmeetable** in this fold (never co-defined), so no separation distribution exists to report.

### 5.5 Confluence decomposition (526 scored decisions)

Score distribution: 5 → 522; 7 → 4; 8 → 0. Check pass counts: HTF-bias alignment 526/526; premium/discount placement 526/526; valid order block 4/526; **FVG overlaps order block 0/526**; liquidity sweep 526/526.

### 5.6 Direction consistency

`same` 526 · `opposite` 0 · `undefined_no_ob` 6,790.

## 6. Hypothesis dispositions (preregistered classifications only)

### H001 — `SUPPORTED_BY_D001`

The frozen exact contemporaneous OB/FVG geometric overlap is stricter than the underlying economic idea *in a stronger sense than hypothesized*: the two structures' availabilities fail at materially different rates — OB present in 526 decisions, FVG present in **zero** — and the exact-overlap condition is therefore never even evaluable (0/526). The preregistered diagnostic implication (materially different failure rates) is confirmed. This is diagnosis, not a rule proposal; no alternative-overlap candidate count was computed.

### H002 — `SUPPORTED_BY_D001`

The valid-OB predicate is conjunctively restrictive with **concentrated** subpredicate failures: mitigation (58.4%), premium/discount placement (15.0%), invalidation (14.3%), displacement (11.6%); only 0.8% of OB-present decisions reach `ob_aligned`. Individual lifecycle/structural subconditions occur at materially different rates while their conjunction is rare — exactly the preregistered implication. No OB condition was removed or weakened.

### H003 — `NOT_TESTED_BY_D001`

Registered later direction; no OB→FVG temporal-distance metric was computed, per preregistration.

### Unplanned observations

`UNPLANNED_OBSERVATION — REQUIRES FUTURE PREREGISTRATION`: premium/discount placement failed for 522/526 OB-present decisions (`in_pd_zone_true` = 4 across the entire fold). Recorded without analysis into any strategy rule.

## 7. Boundaries honored

No strategy variant was executed; no numeric parameter trial occurred; no performance metric (P&L, win rate, expectancy, profit factor, drawdown, Sharpe, return distributions) was emitted; no counterfactual candidate count exists; no threshold search was performed. Folds 02–04 were not touched and remain reserved (sequential fail-fast release). Holdout and 2025+ data were not accessed. No MT5/Streamlit/trading-API/demo/live activity occurred. The strategy-variant budget result-lock has **not** triggered (no variant result exists).

## 8. Next step

Requires supervisory review before any D002 preregistration or Variant 1 authorization. The next diagnostic, if approved, must receive a new ID and preregistration before execution (budget remaining: 11 of 12).
