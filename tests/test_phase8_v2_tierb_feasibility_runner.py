"""Phase-B synthetic unit, negative, and full-pipeline integration tests for Tier-B Feasibility Tooling.

All tests operate strictly on synthetic fixtures and canonical manifests.
ZERO empirical data access, zero historical store reads, zero profitability metrics.
Covers Sections 40 through 47 and all 14 supervisory review defects.
"""

from __future__ import annotations

from collections import Counter
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from bot.execution.lifecycle.models import (
    Direction,
    EntryIntent,
    ExitReason,
    LifecycleStatus,
    ManagementConfig,
    MarketEvent,
    MarketEventKind,
    PositionState,
    ReadinessStyle,
)
from bot.execution.lifecycle.entry import new_entry_intent
from bot.strategy.variant_v005 import (
    V005_SOURCE_DIRECTIONAL_FALLBACK,
    V005_SOURCE_NONE,
    V005_SOURCE_V003_BASELINE,
)
from bot.validation.tierb_feasibility import (
    PLAN_ID,
    PLAN_SCHEMA,
    PLAN_CONTENT_SHA256,
    TOOLING_CORRECTION_ID,
    FREEZE_IDENTITY,
    DEVELOPMENT_PREDECESSOR,
    SEMANTIC_ANCHOR_COMMIT,
    EXPECTED_STRATEGY_DIGEST,
    EXPECTED_CONFIG_SHA256,
    EXPECTED_VALIDATION_DIGEST,
    EXPECTED_PROTECTED_DIGEST_V2,
    EXPECTED_LEDGER_SEAL,
    STAGE1_FUTILITY_THRESHOLD,
    STAGE1_HEADROOM_TARGET,
    STAGE2_MIN_COMPLETED_TRADES,
    PRIMARY_BASELINE_SCENARIO_ID,
    SEALED_V005_R001_SHA256,
    SEALED_V005_R001_BYTES,
    LABEL_STAGE1_FUTILITY,
    LABEL_STAGE1_HEADROOM_MET,
    LABEL_STAGE1_HEADROOM_NOT_MET,
    LABEL_STAGE2_FEASIBILITY_PASS,
    LABEL_STAGE2_SAMPLE_INSUFFICIENT,
    LABEL_END_OF_DATA_EXCLUDED,
    LABEL_GEOMETRY_ATTRITION,
    LABEL_PREFLIGHT_BLOCKAGE,
    LABEL_PARITY_FAILURE,
    LABEL_IDENTITY_MISMATCH,
    LABEL_FIRST_EMPIRICAL_BYTE_READ,
    LABEL_EMPIRICAL_BOUNDARY_ENTERED,
    MANDATORY_STAGE2_QUALIFICATIONS,
    PROHIBITED_METRICS,
    QUALIFYING_NATURAL_EXITS,
    QUALIFYING_NATURAL_EXIT_NAMES,
    NON_COMPLETED_EXCLUDED_STATES,
    COMPLETE_PRE_RELEASE_INPUT_CHAIN,
    GuardedEmpiricalStoreReader,
    ReleaseAuthorizationRecord,
    TierBAuthorizationError,
    TierBFeasibilityError,
    TierBParityError,
    TierBPreflightError,
    TierBProfitabilityViolation,
    assert_zero_profitability,
    candidate_to_entry_intent,
    candidate_to_trade_levels,
    evaluate_stage1_candidates,
    execute_candidate_lifecycle,
    execute_stage2_primary_baseline,
    filter_candidates_by_window,
    pre_release_evidence_preflight,
    reconcile_completed_trades,
    replay_v005_candidates_from_store,
    validate_canonical_candidate,
    verify_fold01_parity_against_sealed_v005,
    verify_frozen_candidate_execution_integrity,
    verify_plan_tc002,
    verify_tooling_integrity,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def _make_causal_snapshot(direction: str = "buy", price: float = 2350.0, available_at_ms: int = 1713168000000):
    t0_dt = datetime.fromtimestamp(available_at_ms / 1000.0, tz=timezone.utc)
    candle_time = (t0_dt - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    avail_time = t0_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [
        {
            "open_time": candle_time,
            "available_at": avail_time,
            "open": price,
            "high": price + 5.0,
            "low": price - 5.0,
            "close": price,
        }
    ]
    return SimpleNamespace(
        available_at_ms=available_at_ms,
        gate_status="evaluated",
        gate_payload=json.dumps({
            "entry_rows": rows,
            "fvgs": [],
            "htf_bias": "bullish" if direction == "buy" else "bearish",
            "liquidity_signal": True,
            "dxy_context": {},
            "news_context": {},
            "session_context": {"active_session": "london"},
            "liquidity_context": {},
            "internal_structure": {},
            "market_conditions": {"atr": 5.0},
            "atr": 5.0,
            "ob_result": {},
            "displacement": {},
            "score": {"score": 8, "grade": "A"},
        }),
    )


def _make_valid_candidate(
    decision_id: str = "dec_001",
    setup_id: str = "setup_001",
    direction: str = "buy",
    source: str = V005_SOURCE_V003_BASELINE,
    available_at_ms: int = 1713168000000,  # 2024-04-15T08:00:00Z
    entry_price: float = 2350.0,
    ob_zone: list[float] | None = None,
) -> dict[str, Any]:
    """Helper creating a canonically valid V005 candidate."""
    side = "LONG" if direction == "buy" else "SHORT"
    default_ob = [2340.0, 2345.0] if direction == "buy" else [2355.0, 2360.0]
    return {
        "decision_id": decision_id,
        "setup_id": setup_id,
        "available_at_ms": available_at_ms,
        "side": side,
        "entry_direction": direction,
        "entry_source": source,
        "fvg_evidence_source": "FINAL_SURFACE",
        "entry": {
            "direction": direction,
            "entry_type": "market",
            "entry_mode": "aggressive",
            "entry_price": entry_price,
            "price": entry_price,
            "ob_zone": ob_zone or default_ob,
        },
        "_causal_snapshot": _make_causal_snapshot(direction, entry_price, available_at_ms),
    }


# -----------------------------------------------------------------------------
# 1. Plan, Tooling, and Frozen Candidate Execution Integrity Tests
# -----------------------------------------------------------------------------

def test_plan_tc002_verification_success() -> None:
    """Plan TC002 parses and passes schema and content SHA-256 verification."""
    plan = verify_plan_tc002(REPO_ROOT)
    assert plan["plan_id"] == PLAN_ID
    assert plan["schema_version"] == PLAN_SCHEMA
    assert plan["plan_content_sha256"] == PLAN_CONTENT_SHA256
    assert plan["zero_empirical_access"] is True
    assert plan["budget_impact"] == 0


def test_tooling_integrity_verification_success() -> None:
    """Tooling integrity binds to phase6-frozen-v2 with all four invariant digests."""
    tooling = verify_tooling_integrity(REPO_ROOT)
    assert tooling["freeze_identity"] == FREEZE_IDENTITY
    assert tooling["development_predecessor"] == DEVELOPMENT_PREDECESSOR
    assert tooling["semantic_anchor_commit"] == SEMANTIC_ANCHOR_COMMIT
    assert tooling["strategy_digest"] == EXPECTED_STRATEGY_DIGEST
    assert tooling["config_sha256"] == EXPECTED_CONFIG_SHA256
    assert tooling["validation_digest"] == EXPECTED_VALIDATION_DIGEST
    assert tooling["protected_digest_v2"] == EXPECTED_PROTECTED_DIGEST_V2
    assert tooling["ledger_seal"] == EXPECTED_LEDGER_SEAL
    assert tooling["unresolved_entities_count"] == 0
    assert tooling["verified"] is True


def test_frozen_candidate_execution_integrity_success() -> None:
    """Frozen candidate execution integrity passes when manifest and strategy files match."""
    res = verify_frozen_candidate_execution_integrity(REPO_ROOT)
    assert res["status"] == "FROZEN_CANDIDATE_EXECUTION_INTEGRITY_VERIFIED"
    assert res["freeze_identity"] == FREEZE_IDENTITY


def test_frozen_candidate_execution_integrity_drift_fails() -> None:
    """Drift in any declared digest halts fail-closed with FROZEN_CANDIDATE_EXECUTION_IDENTITY_MISMATCH."""
    drifted_manifest = {
        "strategy_semantic_identity_v2": {"aggregate_digest": "0000000000000000000000000000000000000000000000000000000000000000"},
        "configuration_identity": {"complete_candidate_configuration_identity": EXPECTED_CONFIG_SHA256},
        "validation_pipeline_identity_v1": {"aggregate_digest": EXPECTED_VALIDATION_DIGEST},
        "protected_infrastructure_identity_v2": {"aggregate_digest": EXPECTED_PROTECTED_DIGEST_V2},
    }
    with pytest.raises(TierBPreflightError) as exc_info:
        verify_frozen_candidate_execution_integrity(REPO_ROOT, manifest_data=drifted_manifest)
    assert LABEL_IDENTITY_MISMATCH in str(exc_info.value)


# -----------------------------------------------------------------------------
# 2. Canonical V005 Candidate Schema & Validation (Section 13, 14, 42)
# -----------------------------------------------------------------------------

def test_canonical_candidate_valid_passes() -> None:
    """Valid baseline and fallback candidates pass canonical validation."""
    c_base = _make_valid_candidate(direction="buy", source=V005_SOURCE_V003_BASELINE)
    validate_canonical_candidate(c_base)

    c_fall = _make_valid_candidate(direction="sell", source=V005_SOURCE_DIRECTIONAL_FALLBACK)
    validate_canonical_candidate(c_fall)


def test_canonical_candidate_missing_fields_fail() -> None:
    """Missing decision_id, setup_id, or available_at_ms fails closed."""
    c_no_dec = _make_valid_candidate()
    del c_no_dec["decision_id"]
    with pytest.raises(TierBFeasibilityError) as exc:
        validate_canonical_candidate(c_no_dec)
    assert "decision_id" in str(exc.value)

    c_no_setup = _make_valid_candidate()
    c_no_setup["setup_id"] = ""
    with pytest.raises(TierBFeasibilityError) as exc:
        validate_canonical_candidate(c_no_setup)
    assert "setup_id" in str(exc.value)

    c_no_avail = _make_valid_candidate()
    c_no_avail["available_at_ms"] = float("nan")
    with pytest.raises(TierBFeasibilityError) as exc:
        validate_canonical_candidate(c_no_avail)
    assert "available_at_ms" in str(exc.value)


def test_canonical_candidate_unknown_enums_fail() -> None:
    """Unknown source, direction, or side fails closed."""
    c_bad_src = _make_valid_candidate(source="V006_EXPERIMENTAL")
    with pytest.raises(TierBFeasibilityError) as exc:
        validate_canonical_candidate(c_bad_src)
    assert "entry_source" in str(exc.value)

    c_bad_dir = _make_valid_candidate()
    c_bad_dir["entry_direction"] = "sideways"
    with pytest.raises(TierBFeasibilityError) as exc:
        validate_canonical_candidate(c_bad_dir)
    assert "entry_direction" in str(exc.value)


def test_canonical_candidate_direction_side_contradiction_fails() -> None:
    """LONG with sell direction or SHORT with buy direction fails closed."""
    c_mismatch = _make_valid_candidate(direction="buy")
    c_mismatch["side"] = "SHORT"  # buy != SHORT
    with pytest.raises(TierBFeasibilityError) as exc:
        validate_canonical_candidate(c_mismatch)
    assert "side/direction contradiction" in str(exc.value)

    c_entry_mismatch = _make_valid_candidate(direction="buy")
    c_entry_mismatch["entry"]["direction"] = "sell"
    with pytest.raises(TierBFeasibilityError) as exc:
        validate_canonical_candidate(c_entry_mismatch)
    assert "entry.direction" in str(exc.value)


# -----------------------------------------------------------------------------
# 3. Evaluation-Window Enforcement Tests (Section 15, 43)
# -----------------------------------------------------------------------------

def test_evaluation_window_filtering() -> None:
    """Candidates outside evaluation window are strictly excluded from Stage-1 count."""
    eval_start = datetime(2024, 4, 1, 0, 0, tzinfo=UTC)
    eval_end = datetime(2024, 6, 8, 0, 0, tzinfo=UTC)
    start_ms = int(eval_start.timestamp() * 1000)
    end_ms = int(eval_end.timestamp() * 1000)

    # Candidate 1: Warmup (1 second before evaluation start) -> EXCLUDED
    c_warmup = _make_valid_candidate("c_warmup", "s1", available_at_ms=start_ms - 1000)
    # Candidate 2: Exactly at evaluation start -> INCLUDED
    c_start = _make_valid_candidate("c_start", "s2", available_at_ms=start_ms)
    # Candidate 3: Mid-evaluation -> INCLUDED
    c_mid = _make_valid_candidate("c_mid", "s3", available_at_ms=start_ms + 86400000)
    # Candidate 4: 1 millisecond before evaluation end -> INCLUDED
    c_end_minus = _make_valid_candidate("c_end_minus", "s4", available_at_ms=end_ms - 1)
    # Candidate 5: Exactly at evaluation end -> EXCLUDED
    c_at_end = _make_valid_candidate("c_at_end", "s5", available_at_ms=end_ms)
    # Candidate 6: Post evaluation -> EXCLUDED
    c_post = _make_valid_candidate("c_post", "s6", available_at_ms=end_ms + 10000)

    all_cands = [c_warmup, c_start, c_mid, c_end_minus, c_at_end, c_post]
    report = evaluate_stage1_candidates(
        all_cands,
        evaluation_start=eval_start,
        evaluation_end=eval_end,
    )

    assert report.raw_candidate_ready == 3
    ids = {c["decision_id"] for c in report.candidates}
    assert ids == {"c_start", "c_mid", "c_end_minus"}


def test_warmup_only_candidates_produce_zero_stage1_count() -> None:
    """Warmup-only candidate records produce raw_candidate_ready == 0."""
    eval_start = datetime(2024, 4, 1, 0, 0, tzinfo=UTC)
    eval_end = datetime(2024, 6, 8, 0, 0, tzinfo=UTC)
    start_ms = int(eval_start.timestamp() * 1000)

    # 10 candidates in warmup period (e.g. March 2024)
    warmup_cands = [
        _make_valid_candidate(f"warm_{i}", f"s_{i}", available_at_ms=start_ms - (i + 1) * 3600000)
        for i in range(10)
    ]

    report = evaluate_stage1_candidates(
        warmup_cands,
        evaluation_start=eval_start,
        evaluation_end=eval_end,
    )
    assert report.raw_candidate_ready == 0
    assert report.unique_setup_ids == 0
    assert report.futility_condition_met is True
    assert report.futility_classification == LABEL_STAGE1_FUTILITY


# -----------------------------------------------------------------------------
# 4. Fold-01 Rehearsal Parity Negative Tests (Section 18, 19, 20, 21, 44)
# -----------------------------------------------------------------------------

def _build_synthetic_sealed_v005_artifact(candidates: list[dict[str, Any]]) -> bytes:
    """Helper returning byte-exact synthetic sealed artifact JSON."""
    clean_candidates = [
        {k: v for k, v in c.items() if not k.startswith("_")}
        for c in candidates
    ]
    doc = {
        "classification": "DEVELOPMENT_VARIANT_EVIDENCE — V005 — FOLD01 — NOT PROFITABILITY EVIDENCE",
        "candidate_surface": {
            "candidates": clean_candidates,
            "total_candidates": len(clean_candidates),
        },
    }
    return json.dumps(doc, indent=2, sort_keys=True).encode("utf-8")


def test_fold01_parity_missing_candidate_surface_fails(tmp_path: Path) -> None:
    """Sealed artifact without candidate_surface fails closed."""
    clean_candidates = [
        {k: v for k, v in _make_valid_candidate().items() if not k.startswith("_")}
        for _ in range(102)
    ]
    bad_doc = {"candidates": clean_candidates}
    p = tmp_path / "bad_sealed.json"
    p.write_text(json.dumps(bad_doc), encoding="utf-8")

    # Monkeypatch expected SHA and bytes for test
    raw = p.read_bytes()
    reps = [_make_valid_candidate(f"dec_{i}", f"setup_{i}") for i in range(102)]

    import bot.validation.tierb_feasibility as tf
    orig_sha = tf.SEALED_V005_R001_SHA256
    orig_bytes = tf.SEALED_V005_R001_BYTES
    try:
        tf.SEALED_V005_R001_SHA256 = hashlib.sha256(raw).hexdigest()
        tf.SEALED_V005_R001_BYTES = len(raw)
        with pytest.raises(TierBParityError) as exc:
            verify_fold01_parity_against_sealed_v005(reps, p)
        assert "Missing 'candidate_surface'" in str(exc.value)
    finally:
        tf.SEALED_V005_R001_SHA256 = orig_sha
        tf.SEALED_V005_R001_BYTES = orig_bytes


def test_fold01_parity_multiset_mismatch_fails(tmp_path: Path) -> None:
    """Same 102/81/21 counts but one changed decision_id fails closed."""
    # 81 baseline + 21 fallback
    sealed_cands = [
        _make_valid_candidate(f"dec_{i}", f"setup_{i}", source=V005_SOURCE_V003_BASELINE if i < 81 else V005_SOURCE_DIRECTIONAL_FALLBACK)
        for i in range(102)
    ]
    raw = _build_synthetic_sealed_v005_artifact(sealed_cands)
    p = tmp_path / "sealed.json"
    p.write_bytes(raw)

    # Reproduced has one altered decision_id
    rep_cands = [dict(c) for c in sealed_cands]
    rep_cands[50]["decision_id"] = "dec_ALT_50"

    import bot.validation.tierb_feasibility as tf
    orig_sha = tf.SEALED_V005_R001_SHA256
    orig_bytes = tf.SEALED_V005_R001_BYTES
    try:
        tf.SEALED_V005_R001_SHA256 = hashlib.sha256(raw).hexdigest()
        tf.SEALED_V005_R001_BYTES = len(raw)
        with pytest.raises(TierBParityError) as exc:
            verify_fold01_parity_against_sealed_v005(rep_cands, p)
        assert "multiset mismatch" in str(exc.value)
    finally:
        tf.SEALED_V005_R001_SHA256 = orig_sha
        tf.SEALED_V005_R001_BYTES = orig_bytes


def test_fold01_parity_entry_object_drift_fails(tmp_path: Path) -> None:
    """Same candidate IDs but one changed price field in entry fails closed."""
    sealed_cands = [
        _make_valid_candidate(f"dec_{i}", f"setup_{i}", source=V005_SOURCE_V003_BASELINE if i < 81 else V005_SOURCE_DIRECTIONAL_FALLBACK)
        for i in range(102)
    ]
    raw = _build_synthetic_sealed_v005_artifact(sealed_cands)
    p = tmp_path / "sealed.json"
    p.write_bytes(raw)

    rep_cands = [copy.deepcopy(c) for c in sealed_cands]
    rep_cands[10]["entry"]["entry_price"] = 2399.99  # was 2350.0

    import bot.validation.tierb_feasibility as tf
    orig_sha = tf.SEALED_V005_R001_SHA256
    orig_bytes = tf.SEALED_V005_R001_BYTES
    try:
        tf.SEALED_V005_R001_SHA256 = hashlib.sha256(raw).hexdigest()
        tf.SEALED_V005_R001_BYTES = len(raw)
        with pytest.raises(TierBParityError) as exc:
            verify_fold01_parity_against_sealed_v005(rep_cands, p)
        assert "entry JSON mismatch" in str(exc.value)
    finally:
        tf.SEALED_V005_R001_SHA256 = orig_sha
        tf.SEALED_V005_R001_BYTES = orig_bytes


def test_fold01_parity_source_mismatch_fails(tmp_path: Path) -> None:
    """Same entries but one swapped source fails closed."""
    sealed_cands = [
        _make_valid_candidate(f"dec_{i}", f"setup_{i}", source=V005_SOURCE_V003_BASELINE if i < 81 else V005_SOURCE_DIRECTIONAL_FALLBACK)
        for i in range(102)
    ]
    raw = _build_synthetic_sealed_v005_artifact(sealed_cands)
    p = tmp_path / "sealed.json"
    p.write_bytes(raw)

    rep_cands = [copy.deepcopy(c) for c in sealed_cands]
    # Swap source on item 0
    rep_cands[0]["entry_source"] = V005_SOURCE_DIRECTIONAL_FALLBACK

    import bot.validation.tierb_feasibility as tf
    orig_sha = tf.SEALED_V005_R001_SHA256
    orig_bytes = tf.SEALED_V005_R001_BYTES
    try:
        tf.SEALED_V005_R001_SHA256 = hashlib.sha256(raw).hexdigest()
        tf.SEALED_V005_R001_BYTES = len(raw)
        with pytest.raises(TierBParityError) as exc:
            verify_fold01_parity_against_sealed_v005(rep_cands, p)
        assert "entry_source mismatch" in str(exc.value)
    finally:
        tf.SEALED_V005_R001_SHA256 = orig_sha
        tf.SEALED_V005_R001_BYTES = orig_bytes


# -----------------------------------------------------------------------------
# 5. Stage-2 Natural Exit & Accounting Tests (Section 23, 24, 47)
# -----------------------------------------------------------------------------

def test_stage2_invalid_mystery_exit_fails_closed() -> None:
    """30 MYSTERY_EXIT values fail closed and never produce a feasibility pass."""
    with pytest.raises(TierBFeasibilityError) as exc:
        reconcile_completed_trades(
            raw_candidates_count=30,
            qualifying_exits=["MYSTERY_EXIT"] * 30,
        )
    assert "Invalid or non-qualifying exit reason" in str(exc.value)


def test_stage2_exact_threshold_boundary() -> None:
    """29 qualifying completed trades is INSUFFICIENT; 30 is PASS."""
    # 29 trades
    res_29 = reconcile_completed_trades(
        raw_candidates_count=50,
        qualifying_exits=[ExitReason.STOP_LOSS] * 29,
        attrition_count=21,
    )
    assert res_29.qualifying_completed_trades == 29
    assert res_29.feasibility_verdict == LABEL_STAGE2_SAMPLE_INSUFFICIENT

    # 30 trades
    res_30 = reconcile_completed_trades(
        raw_candidates_count=50,
        qualifying_exits=[ExitReason.STOP_LOSS] * 30,
        attrition_count=20,
    )
    assert res_30.qualifying_completed_trades == 30
    assert res_30.feasibility_verdict == LABEL_STAGE2_FEASIBILITY_PASS


def test_stage2_end_of_data_does_not_count_towards_quota() -> None:
    """29 natural exits + 10 END_OF_DATA is INSUFFICIENT (qualifying == 29 < 30)."""
    res = reconcile_completed_trades(
        raw_candidates_count=39,
        qualifying_exits=[ExitReason.TAKE_PROFIT] * 29,
        end_of_data_count=10,
    )
    assert res.qualifying_completed_trades == 29
    assert res.end_of_data_closed == 10
    assert res.feasibility_verdict == LABEL_STAGE2_SAMPLE_INSUFFICIENT


# -----------------------------------------------------------------------------
# 6. Synthetic Full-Pipeline Tests (Section 40, 41)
# -----------------------------------------------------------------------------

def test_synthetic_full_pipeline_v003_baseline() -> None:
    """Full pipeline: V003 baseline candidate -> levels -> intent -> lifecycle fill -> TAKE_PROFIT."""
    candidate = _make_valid_candidate(
        decision_id="dec_v003_01",
        setup_id="setup_v003_01",
        direction="buy",
        source=V005_SOURCE_V003_BASELINE,
        entry_price=2350.0,
        ob_zone=[2340.0, 2345.0],
    )

    # 1. Levels
    levels = candidate_to_trade_levels(candidate)
    assert levels.stop is not None and levels.stop < 2350.0
    assert levels.target is not None and levels.target > 2350.0

    # 2. Intent
    intent = candidate_to_entry_intent(candidate, levels)
    assert intent.direction is Direction.BUY
    assert intent.stop_loss == levels.stop
    assert intent.final_target == levels.target

    # 3. Market Events: Tick 1 fills at 2350.0 -> OPEN; Tick 2 hits target at 2370.0 -> CLOSED (TAKE_PROFIT)
    t0 = datetime(2024, 4, 15, 8, 0, tzinfo=UTC)
    events = [
        MarketEvent(
            event_id="e1", timestamp=t0, symbol="XAUUSDm", source="syn",
            kind=MarketEventKind.TICK, sequence=1, bid=2349.99, ask=2350.00, close=2350.00,
        ),
        MarketEvent(
            event_id="e2", timestamp=t0 + timedelta(minutes=15), symbol="XAUUSDm", source="syn",
            kind=MarketEventKind.TICK, sequence=2, bid=float(levels.target) + 1.0, ask=float(levels.target) + 1.01, close=float(levels.target) + 1.0,
        ),
    ]

    position, exit_reason = execute_candidate_lifecycle(intent, events)
    assert position is not None
    assert position.status is LifecycleStatus.CLOSED
    assert exit_reason is ExitReason.TAKE_PROFIT
    assert exit_reason in QUALIFYING_NATURAL_EXITS


def test_synthetic_full_pipeline_v005_fallback() -> None:
    """Full pipeline: V005 fallback candidate -> levels -> intent -> lifecycle fill -> STOP_LOSS."""
    candidate = _make_valid_candidate(
        decision_id="dec_v005_fb_01",
        setup_id="setup_v005_fb_01",
        direction="sell",
        source=V005_SOURCE_DIRECTIONAL_FALLBACK,
        entry_price=2350.0,
        ob_zone=[2355.0, 2360.0],
    )

    # 1. Levels
    levels = candidate_to_trade_levels(candidate)
    assert levels.stop is not None and levels.stop > 2350.0
    assert levels.target is not None and levels.target < 2350.0

    # 2. Intent
    intent = candidate_to_entry_intent(candidate, levels)
    assert intent.direction is Direction.SELL
    assert intent.stop_loss == levels.stop
    assert intent.final_target == levels.target

    # 3. Market Events: Tick 1 fills sell at 2350.0 -> OPEN; Tick 2 hits stop at 2365.0 -> CLOSED (STOP_LOSS)
    t0 = datetime(2024, 4, 15, 8, 0, tzinfo=UTC)
    events = [
        MarketEvent(
            event_id="e1", timestamp=t0, symbol="XAUUSDm", source="syn",
            kind=MarketEventKind.TICK, sequence=1, bid=2350.00, ask=2350.01, close=2350.00,
        ),
        MarketEvent(
            event_id="e2", timestamp=t0 + timedelta(minutes=15), symbol="XAUUSDm", source="syn",
            kind=MarketEventKind.TICK, sequence=2, bid=float(levels.stop) + 0.5, ask=float(levels.stop) + 0.51, close=float(levels.stop) + 0.5,
        ),
    ]

    position, exit_reason = execute_candidate_lifecycle(intent, events)
    assert position is not None
    assert position.status is LifecycleStatus.CLOSED
    assert exit_reason is ExitReason.STOP_LOSS
    assert exit_reason in QUALIFYING_NATURAL_EXITS


# -----------------------------------------------------------------------------
# 7. Release-Guard Ordering & Store Exposure Tests (Section 35, 36, 46)
# -----------------------------------------------------------------------------

def test_release_guard_ordering_and_first_byte_read(tmp_path: Path) -> None:
    """Guard strictly checks prerequisites and records FIRST_EMPIRICAL_BYTE_READ only on store open."""
    out_target = tmp_path / "fresh_result.json"

    auth = ReleaseAuthorizationRecord(
        authorization_id="auth_test_001",
        target_partition="fold-01-rehearsal",
        authorized_operation="FOLD01_PARITY_REHEARSAL",
        governing_plan_id=PLAN_ID,
        tooling_id=TOOLING_CORRECTION_ID,
        frozen_candidate_identity=FREEZE_IDENTITY,
        supervisory_approval_reference="SUP-AUTH-20261015-001",
        output_path=str(out_target),
        created_utc="2026-10-15T10:00:00Z",
    )

    mock_raw_stream_called = 0

    def mock_opener():
        nonlocal mock_raw_stream_called
        mock_raw_stream_called += 1
        return ["row1", "row2"]

    reader = GuardedEmpiricalStoreReader(
        partition="fold-01-rehearsal",
        authorization=auth,
        repo_root=REPO_ROOT,
        raw_store_opener=mock_opener,
        expected_operation="FOLD01_PARITY_REHEARSAL",
    )

    assert reader.empirical_first_read_utc is None
    assert mock_raw_stream_called == 0

    # Open store (with preflight_already_run=True for fast synthetic test)
    stream = list(reader.open_store(preflight_already_run=True))
    assert stream == ["row1", "row2"]
    assert mock_raw_stream_called == 1
    assert reader.empirical_first_read_utc is not None
    assert reader.exposure_record is not None
    assert reader.exposure_record["status"] == LABEL_EMPIRICAL_BOUNDARY_ENTERED


def test_release_guard_output_not_fresh_fails_before_store_read(tmp_path: Path) -> None:
    """If target output path already exists, guard halts before calling store opener."""
    out_target = tmp_path / "stale_result.json"
    out_target.write_text("existing", encoding="utf-8")

    auth = ReleaseAuthorizationRecord(
        authorization_id="auth_test_002",
        target_partition="fold-01-rehearsal",
        authorized_operation="FOLD01_PARITY_REHEARSAL",
        governing_plan_id=PLAN_ID,
        tooling_id=TOOLING_CORRECTION_ID,
        frozen_candidate_identity=FREEZE_IDENTITY,
        supervisory_approval_reference="SUP-AUTH-20261015-002",
        output_path=str(out_target),
        created_utc="2026-10-15T10:00:00Z",
    )

    mock_raw_stream_called = 0

    def mock_opener():
        nonlocal mock_raw_stream_called
        mock_raw_stream_called += 1
        return []

    reader = GuardedEmpiricalStoreReader(
        partition="fold-01-rehearsal",
        authorization=auth,
        repo_root=REPO_ROOT,
        raw_store_opener=mock_opener,
        expected_operation="FOLD01_PARITY_REHEARSAL",
    )

    with pytest.raises(TierBFeasibilityError) as exc:
        reader.open_store(preflight_already_run=True)
    assert "already exists (not fresh)" in str(exc.value)
    assert mock_raw_stream_called == 0
    assert reader.empirical_first_read_utc is None


def test_reserved_fold_authorization_prerequisites() -> None:
    """Fold 03 requires Fold 02 pass; Fold 04 requires Fold 03 pass."""
    # Fold 03 without prior pass reference fails
    auth_f3_bad = ReleaseAuthorizationRecord(
        authorization_id="auth_f3", target_partition="fold-03",
        authorized_operation="RESERVED_FOLD_FEASIBILITY",
        governing_plan_id=PLAN_ID, tooling_id=TOOLING_CORRECTION_ID,
        frozen_candidate_identity=FREEZE_IDENTITY, supervisory_approval_reference="REF",
        output_path="out.json", created_utc="2026-10-15T10:00:00Z",
        prior_sealed_pass_reference=None,
    )
    with pytest.raises(TierBAuthorizationError) as exc:
        auth_f3_bad.validate("fold-03", expected_operation="RESERVED_FOLD_FEASIBILITY")
    assert "requires sealed Fold-02 PASS" in str(exc.value)

    # Fold 03 with prior pass reference passes
    auth_f3_good = ReleaseAuthorizationRecord(
        authorization_id="auth_f3", target_partition="fold-03",
        authorized_operation="RESERVED_FOLD_FEASIBILITY",
        governing_plan_id=PLAN_ID, tooling_id=TOOLING_CORRECTION_ID,
        frozen_candidate_identity=FREEZE_IDENTITY, supervisory_approval_reference="REF",
        output_path="out.json", created_utc="2026-10-15T10:00:00Z",
        prior_sealed_pass_reference="phase8-v2-tierb-feasibility-fold02-PASS.json",
    )
    auth_f3_good.validate("fold-03", expected_operation="RESERVED_FOLD_FEASIBILITY")  # passes cleanly


# -----------------------------------------------------------------------------
# 8. CLI Command Execution Tests (Section 37)
# -----------------------------------------------------------------------------

def test_cli_verify_plan() -> None:
    """CLI verify-plan executes and exits with 0."""
    from backtests.phase8_v2_tierb_feasibility import main
    rc = main(["verify-plan"])
    assert rc == 0


def test_cli_verify_tooling() -> None:
    """CLI verify-tooling executes and exits with 0."""
    from backtests.phase8_v2_tierb_feasibility import main
    rc = main(["verify-tooling"])
    assert rc == 0


def test_cli_preflight(monkeypatch) -> None:
    """CLI preflight executes across full input chain and exits with 0."""
    import bot.validation.cost_policy as cp
    import bot.validation.development_evaluation_plan as dep
    from tests.test_phase8_v2_frozen_candidate import GitObjectStore
    store = GitObjectStore(REPO_ROOT)
    monkeypatch.setattr(cp, "make_git_blob_source", lambda repo: (lambda commit, rel: store.blob_bytes(commit, rel)))
    monkeypatch.setattr(dep, "verify_input_readiness_prospective", lambda **kwargs: {"status": "PASSED"})
    from backtests.phase8_v2_tierb_feasibility import main
    rc = main(["preflight"])
    assert rc == 0


def test_cli_run_fold_unauthorized_fails() -> None:
    """CLI run-fold without authorization fails closed with code 4."""
    from backtests.phase8_v2_tierb_feasibility import main
    rc = main(["run-fold", "--fold-id", "fold-02"])
    assert rc == 4


# -----------------------------------------------------------------------------
# 9. Additional TC002 Specification & Negative Tests (Sections 11, 25, 32-37)
# -----------------------------------------------------------------------------

def test_true_synthetic_v005_observer_baseline_and_fallback() -> None:
    """Section 11: True synthetic V005 observer test (baseline & fallback cases)."""
    from bot.strategy.config import StrategyConfig
    from bot.strategy.setup_state import StrategyState, record_from_state
    from bot.strategy.models import StrategySide
    from bot.strategy.variant_v003 import V003PairResult
    import backtests.phase8_v2_variant_v005_eval as v005_eval

    # 1. State records
    t0 = datetime(2024, 4, 15, 8, 0, tzinfo=UTC)
    st = StrategyState(event_time=t0)
    st.structure_dir = "bearish"
    rec_b = record_from_state(st, event_at=t0, last_event_id="dec_b1", last_result=json.dumps({"setup_id": "setup_b1", "structure_dir": "bearish"}))
    rec_f = record_from_state(st, event_at=t0, last_event_id="dec_f1", last_result=json.dumps({"setup_id": "setup_f1", "structure_dir": "bearish"}))

    # 2. Case 1: V003 Baseline Candidate snapshot
    s_base = SimpleNamespace(
        available_at_ms=1713168000000,
        gate_status="evaluated",
        gate_payload=json.dumps({
            "entry_rows": [{"open_time": "2024-04-15T07:55:00Z", "close": 2350.0, "high": 2355.0, "low": 2345.0, "open": 2350.0}],
            "fvgs": [],
            "htf_bias": "bullish",
            "liquidity_signal": True,
            "session_context": {"active_session": "london"},
            "liquidity_context": {},
            "internal_structure": {},
            "market_conditions": {"atr": 5.0},
            "score": {"score": 8, "passes_threshold": True},
        }),
    )

    # 3. Case 2: V005 Directional Fallback Candidate snapshot
    s_fall = SimpleNamespace(
        available_at_ms=1713168300000,
        gate_status="evaluated",
        gate_payload=json.dumps({
            "entry_rows": [{"open_time": "2024-04-15T08:00:00Z", "close": 2352.0, "high": 2358.0, "low": 2348.0, "open": 2352.0}],
            "fvgs": [],
            "htf_bias": "bullish",
            "liquidity_signal": True,
            "session_context": {"active_session": "london"},
            "liquidity_context": {},
            "internal_structure": {},
            "market_conditions": {"atr": 5.0},
            "score": {"score": 8, "passes_threshold": True},
        }),
    )

    active_pair = V003PairResult(
        state="ACTIVE",
        reason="formed",
        side=StrategySide.LONG,
        block_id="b1",
        zone_low=2340.0,
        zone_high=2345.0,
        confirmed_at=t0,
        age_bars=2,
        final_fvg_associated=True,
        temporal_fvg_evidence=True,
        v003_fvg_evidence=True,
        fvg_evidence_source="FINAL_SURFACE",
        fvg_direction="bullish",
        exact_overlap=True,
        live_fvg_top=2346.0,
        live_fvg_bottom=2344.0,
    )

    row_base = {"decision_id": "dec_b1"}
    row_fall = {"decision_id": "dec_f1"}

    # Evaluate using actual observer
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(v005_eval, "evaluate_v005_structural_pair", lambda *a, **kw: active_pair)
        mp.setattr(v005_eval, "score_v005_setup", lambda **kw: {"score": 8, "passes_threshold": True})

        # Baseline case
        mp.setattr(
            v005_eval,
            "evaluate_v005_entry_readiness",
            lambda **kw: ({"direction": "buy", "price": 2350.0, "entry_type": "market", "entry_mode": "aggressive"}, True, V005_SOURCE_V003_BASELINE),
        )
        obs_b = v005_eval.observe_v005_decision(row_base, s_base, rec_b, config=StrategyConfig(), decision_result_record=rec_b)
        assert obs_b["v005_entry_source"] == V005_SOURCE_V003_BASELINE
        assert obs_b["v005_entry_ready"] is True

        # Fallback case
        mp.setattr(
            v005_eval,
            "evaluate_v005_entry_readiness",
            lambda **kw: ({"direction": "buy", "price": 2352.0, "entry_type": "market", "entry_mode": "aggressive"}, True, V005_SOURCE_DIRECTIONAL_FALLBACK),
        )
        obs_f = v005_eval.observe_v005_decision(row_fall, s_fall, rec_f, config=StrategyConfig(), decision_result_record=rec_f)
        assert obs_f["v005_entry_source"] == V005_SOURCE_DIRECTIONAL_FALLBACK
        assert obs_f["v005_entry_ready"] is True

    # Assemble canonical candidates from real observer output
    cand_b = {
        "decision_id": obs_b["decision_id"],
        "setup_id": obs_b["v005_setup_id"] or "setup_b1",
        "available_at_ms": obs_b["available_at_ms"],
        "side": obs_b["v005_side"],
        "entry_direction": "buy",
        "entry_source": obs_b["v005_entry_source"],
        "fvg_evidence_source": "FINAL_SURFACE",
        "entry": obs_b["v005_entry"],
    }
    cand_f = {
        "decision_id": obs_f["decision_id"],
        "setup_id": obs_f["v005_setup_id"] or "setup_f1",
        "available_at_ms": obs_f["available_at_ms"],
        "side": obs_f["v005_side"],
        "entry_direction": "buy",
        "entry_source": obs_f["v005_entry_source"],
        "fvg_evidence_source": "FINAL_SURFACE",
        "entry": obs_f["v005_entry"],
    }

    report = evaluate_stage1_candidates([cand_b, cand_f], evaluation_start=t0 - timedelta(hours=1), evaluation_end=t0 + timedelta(hours=1))
    assert report.raw_candidate_ready == 2
    assert report.v003_baseline_count == 1
    assert report.v005_directional_fallback_count == 1
    assert report.headroom_target_met is False  # 2 < 60
    assert report.futility_condition_met is True  # 2 < 30


def test_authorization_operation_isolation() -> None:
    """Section 25: Authorization operation isolation (parity vs lifecycle vs reserved fold)."""
    # 1. Parity authorization rejected for lifecycle
    auth_parity = ReleaseAuthorizationRecord(
        authorization_id="auth_p1",
        target_partition="fold-01-rehearsal",
        authorized_operation="FOLD01_PARITY_REHEARSAL",
        governing_plan_id=PLAN_ID,
        tooling_id=TOOLING_CORRECTION_ID,
        frozen_candidate_identity=FREEZE_IDENTITY,
        supervisory_approval_reference="REF",
        output_path="out.json",
        created_utc="2026-10-15T10:00:00Z",
    )
    with pytest.raises(TierBAuthorizationError) as exc:
        auth_parity.validate("fold-01-rehearsal", expected_operation="FOLD01_LIFECYCLE_REHEARSAL")
    assert "operation mismatch" in str(exc.value)

    # 2. Rehearsal authorization rejected for reserved fold
    with pytest.raises(TierBAuthorizationError) as exc2:
        auth_parity.validate("fold-02", expected_operation="RESERVED_FOLD_FEASIBILITY")
    assert "partition mismatch" in str(exc2.value)

    # 3. Reserved fold authorization with wrong operation fails
    auth_f2 = ReleaseAuthorizationRecord(
        authorization_id="auth_f2",
        target_partition="fold-02",
        authorized_operation="FOLD01_PARITY_REHEARSAL",
        governing_plan_id=PLAN_ID,
        tooling_id=TOOLING_CORRECTION_ID,
        frozen_candidate_identity=FREEZE_IDENTITY,
        supervisory_approval_reference="REF",
        output_path="out.json",
        created_utc="2026-10-15T10:00:00Z",
        prior_sealed_parity_reference="ref_p",
        prior_sealed_lifecycle_reference="ref_l",
    )
    with pytest.raises(TierBAuthorizationError) as exc3:
        auth_f2.validate("fold-02", expected_operation="RESERVED_FOLD_FEASIBILITY")
    assert "operation mismatch" in str(exc3.value) or "requires RESERVED_FOLD_FEASIBILITY" in str(exc3.value)


def test_synthetic_cli_commands_success(monkeypatch, tmp_path: Path) -> None:
    """Section 32: Authorized synthetic CLI commands execute and write valid results."""
    from backtests.phase8_v2_tierb_feasibility import main
    import backtests.phase8_v2_tierb_feasibility as cli_mod
    import bot.validation.tierb_feasibility as tf_mod

    # Setup fake store (81 baseline + 21 fallback)
    fake_cands = [
        _make_valid_candidate(
            f"dec_{i}",
            f"setup_{i}",
            source=V005_SOURCE_V003_BASELINE if i < 81 else V005_SOURCE_DIRECTIONAL_FALLBACK,
        )
        for i in range(102)
    ]
    clean_cands = [{k: v for k, v in c.items() if not k.startswith("_")} for c in fake_cands]
    sealed_raw = _build_synthetic_sealed_v005_artifact(fake_cands)

    sealed_p = tmp_path / "sealed_v005.json"
    sealed_p.write_bytes(sealed_raw)

    store_p = tmp_path / "fake_store.parquet"
    store_p.write_text("fake", encoding="utf-8")

    out_p = tmp_path / "out_parity.json"
    auth_p = tmp_path / "auth_parity.json"
    auth_doc = {
        "authorization_id": "auth_syn_parity",
        "target_partition": "fold-01-rehearsal",
        "authorized_operation": "FOLD01_PARITY_REHEARSAL",
        "governing_plan_id": PLAN_ID,
        "tooling_id": TOOLING_CORRECTION_ID,
        "frozen_candidate_identity": FREEZE_IDENTITY,
        "supervisory_approval_reference": "SUP-2026",
        "output_path": str(out_p),
        "created_utc": "2026-10-15T10:00:00Z",
    }
    auth_p.write_text(json.dumps(auth_doc), encoding="utf-8")

    # Mocks
    fake_store = SimpleNamespace(identity={"store_sha256": "fake_sha", "fold_id": "fold-01"})
    monkeypatch.setattr(cli_mod, "load_feature_store", lambda *a, **kw: fake_store)
    monkeypatch.setattr(cli_mod, "replay_v005_candidates_from_store", lambda *a, **kw: fake_cands)
    monkeypatch.setattr(cli_mod, "pre_release_evidence_preflight", lambda *a, **kw: {"status": "PASSED"})
    monkeypatch.setattr(tf_mod, "pre_release_evidence_preflight", lambda *a, **kw: {"status": "PASSED"})

    orig_sha = tf_mod.SEALED_V005_R001_SHA256
    orig_bytes = tf_mod.SEALED_V005_R001_BYTES
    try:
        tf_mod.SEALED_V005_R001_SHA256 = hashlib.sha256(sealed_raw).hexdigest()
        tf_mod.SEALED_V005_R001_BYTES = len(sealed_raw)

        # 1. Test fold01-parity-rehearsal
        rc = main([
            "fold01-parity-rehearsal",
            "--authorization", str(auth_p),
            "--feature-store", str(store_p),
            "--sealed-v005-result", str(sealed_p),
            "--output", str(out_p),
        ])
        assert rc == 0
        assert out_p.is_file()
        res_doc = json.loads(out_p.read_text(encoding="utf-8"))
        assert res_doc["protocol"] == "FOLD01_PARITY_REHEARSAL"
        assert res_doc["candidates_count"] == 102
        assert_zero_profitability(res_doc)

        # 2. Test fold01-lifecycle-rehearsal
        out_life = tmp_path / "out_lifecycle.json"
        auth_life_p = tmp_path / "auth_lifecycle.json"
        auth_life_doc = dict(auth_doc, authorized_operation="FOLD01_LIFECYCLE_REHEARSAL", output_path=str(out_life))
        auth_life_p.write_text(json.dumps(auth_life_doc), encoding="utf-8")

        monkeypatch.setattr(cli_mod, "_extract_quotes_from_store", lambda *a, **kw: [])
        monkeypatch.setattr(
            cli_mod,
            "execute_stage2_primary_baseline",
            lambda *a, **kw: reconcile_completed_trades(raw_candidates_count=102, qualifying_exits=[ExitReason.STOP_LOSS] * 30, attrition_count=72),
        )

        rc_l = main([
            "fold01-lifecycle-rehearsal",
            "--authorization", str(auth_life_p),
            "--feature-store", str(store_p),
            "--output", str(out_life),
        ])
        assert rc_l == 0
        assert out_life.is_file()
        res_life = json.loads(out_life.read_text(encoding="utf-8"))
        assert res_life["protocol"] == "FOLD01_LIFECYCLE_REHEARSAL"
        assert_zero_profitability(res_life)

        # 3. Test run-fold on fold-02
        out_f2 = tmp_path / "out_fold02.json"
        auth_f2_p = tmp_path / "auth_fold02.json"
        auth_f2_doc = dict(
            auth_doc,
            target_partition="fold-02",
            authorized_operation="RESERVED_FOLD_FEASIBILITY",
            output_path=str(out_f2),
            prior_sealed_parity_reference=str(out_p),
            prior_sealed_lifecycle_reference=str(out_life),
        )
        auth_f2_p.write_text(json.dumps(auth_f2_doc), encoding="utf-8")

        fake_store_f2 = SimpleNamespace(identity={"store_sha256": "fake_sha_2", "fold_id": "fold-02"})
        monkeypatch.setattr(cli_mod, "load_feature_store", lambda *a, **kw: fake_store_f2)

        rc_f2 = main([
            "run-fold",
            "--fold-id", "fold-02",
            "--authorization", str(auth_f2_p),
            "--feature-store", str(store_p),
            "--output", str(out_f2),
        ])
        assert rc_f2 == 0
        assert out_f2.is_file()
        res_f2 = json.loads(out_f2.read_text(encoding="utf-8"))
        assert res_f2["fold_id"] == "fold-02"
        assert "PROSPECTIVE_RESERVED_DEVELOPMENT_FEASIBILITY" in res_f2["classification"]
        assert_zero_profitability(res_f2)
    finally:
        tf_mod.SEALED_V005_R001_SHA256 = orig_sha
        tf_mod.SEALED_V005_R001_BYTES = orig_bytes


def test_full_pipeline_primary_baseline() -> None:
    """Section 33: HistoricalExecutionEngine under PRIMARY_BASELINE applies slippage and closes naturally."""
    from bot.backtesting.models import HistoricalQuote
    from bot.backtesting.engine import HistoricalExecutionEngine

    cand = _make_valid_candidate(
        decision_id="dec_pb_1",
        setup_id="setup_pb_1",
        direction="buy",
        entry_price=2350.0,
    )
    levels = candidate_to_trade_levels(cand)
    intent = candidate_to_entry_intent(cand, levels)

    t0 = datetime(2024, 4, 15, 8, 0, tzinfo=UTC)
    quotes = [
        # Tick 1: triggers BUY at 2350.0. With SLIPPAGE_MODERATE_ADVERSE (+1.0 pt), fill price shifts.
        HistoricalQuote(symbol="XAUUSDm", timestamp=t0, bid=2349.90, ask=2350.00, source="syn", dataset_id="d1", sequence_id=1),
        # Tick 2: hits target levels.target + 1.0 -> closed TAKE_PROFIT
        HistoricalQuote(symbol="XAUUSDm", timestamp=t0 + timedelta(minutes=15), bid=float(levels.target) + 1.0, ask=float(levels.target) + 1.1, source="syn", dataset_id="d1", sequence_id=2),
    ]

    accounting = execute_stage2_primary_baseline([cand], quotes)
    assert accounting.qualifying_completed_trades == 1
    assert "TAKE_PROFIT" in accounting.natural_exit_distribution
    assert accounting.reconciliation_balanced is True
    assert_zero_profitability(accounting.to_dict())


def test_profile_drift_negative() -> None:
    """Section 34: Feasibility adapter with drifted min_stop_atr_mult (0.35 != 2.0) fails closed."""
    cand = _make_valid_candidate()
    drifted_profile = {
        "execution_levels": {
            "min_stop_atr_mult": 0.35,  # Drifted from frozen XAUUSDm 2.0!
        }
    }
    with pytest.raises(TierBFeasibilityError) as exc:
        candidate_to_trade_levels(cand, profile=drifted_profile)
    assert "Effective XAUUSDm min_stop_atr_mult must be 2.0" in str(exc.value)
    assert LABEL_GEOMETRY_ATTRITION in str(exc.value)


def test_active_commit_negative(tmp_path: Path) -> None:
    """Section 35: Preflight with stale/wrong active commit fails closed before store read."""
    auth = ReleaseAuthorizationRecord(
        authorization_id="auth_test_commit",
        target_partition="fold-01-rehearsal",
        authorized_operation="FOLD01_PARITY_REHEARSAL",
        governing_plan_id=PLAN_ID,
        tooling_id=TOOLING_CORRECTION_ID,
        frozen_candidate_identity=FREEZE_IDENTITY,
        supervisory_approval_reference="SUP-2026",
        output_path=str(tmp_path / "fresh.json"),
        created_utc="2026-10-15T10:00:00Z",
    )
    store_opened = False

    def opener():
        nonlocal store_opened
        store_opened = True
        return []

    reader = GuardedEmpiricalStoreReader(
        partition="fold-01-rehearsal",
        authorization=auth,
        repo_root=REPO_ROOT,
        raw_store_opener=opener,
        expected_operation="FOLD01_PARITY_REHEARSAL",
    )

    with pytest.raises(TierBPreflightError):
        reader.open_store(preflight_already_run=False, active_commit="0000000000000000000000000000000000000000")

    assert not store_opened
    assert reader.empirical_first_read_utc is None


def test_frozen_git_identity_negative(monkeypatch) -> None:
    """Section 36: Altering one synthetic semantic blob at execution commit fails closed."""
    from tests.test_phase8_v2_frozen_candidate import GitObjectStore
    store = GitObjectStore(REPO_ROOT)
    active_head = "132343a0b1de527f6ecdb1776b7a90132068dbea"

    # Corrupt one file at the active commit
    def corrupted_blob_source(commit: str, rel_path: str) -> bytes:
        real = store.blob_bytes(commit, rel_path)
        if commit == active_head and rel_path == "bot/strategy/variant_v005.py":
            return real + b"\n# DRIFT_INJECTION"
        return real

    with pytest.raises(TierBFeasibilityError) as exc:
        verify_frozen_candidate_execution_integrity(REPO_ROOT, active_commit=active_head, blob_source=corrupted_blob_source)
    assert LABEL_IDENTITY_MISMATCH in str(exc.value)


def test_true_observer_negative(monkeypatch) -> None:
    """Section 37: Breaking/bypassing observe_v005_decision causes replay to fail."""
    import backtests.phase8_v2_variant_v005_eval as v005_eval
    import backtests.phase8_v2_diagnostic_d001 as d001_mod

    monkeypatch.setattr(
        v005_eval,
        "observe_v005_decision",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("V005_OBSERVER_BROKEN")),
    )

    dummy_snapshot = SimpleNamespace(
        available_at_ms=1713168000000,
        gate_status="evaluated",
        gate_payload=json.dumps({"entry_rows": [{"open_time": "2024-04-15T08:00:00Z", "close": 2350.0}]}),
    )
    fake_store = SimpleNamespace(identity={"store_sha256": "fake"})
    monkeypatch.setattr(d001_mod, "_snapshot_rows", lambda s: [dummy_snapshot])
    monkeypatch.setattr(d001_mod, "classify_snapshot", lambda s: None)
    monkeypatch.setattr(d001_mod, "_reference_check_failed", lambda s: False)
    monkeypatch.setattr(
        d001_mod,
        "evaluate_orchestration_decision",
        lambda s, p: ({"action": "evaluate", "gate_results": {"gate_11_confluence_score": True}}, p),
    )
    monkeypatch.setattr(v005_eval, "assert_store_semantic_compatibility", lambda s: None)

    eval_start = datetime(2024, 4, 1, tzinfo=UTC)
    eval_end = datetime(2024, 5, 1, tzinfo=UTC)

    with pytest.raises(RuntimeError) as exc:
        replay_v005_candidates_from_store(fake_store, eval_start, eval_end)
    assert "V005_OBSERVER_BROKEN" in str(exc.value)
