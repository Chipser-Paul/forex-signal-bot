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
    filter_candidates_by_window,
    pre_release_evidence_preflight,
    reconcile_completed_trades,
    validate_canonical_candidate,
    verify_fold01_parity_against_sealed_v005,
    verify_frozen_candidate_execution_integrity,
    verify_plan_tc002,
    verify_tooling_integrity,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


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
    doc = {
        "classification": "DEVELOPMENT_VARIANT_EVIDENCE — V005 — FOLD01 — NOT PROFITABILITY EVIDENCE",
        "candidate_surface": {
            "candidates": candidates,
            "total_candidates": len(candidates),
        },
    }
    return json.dumps(doc, indent=2, sort_keys=True).encode("utf-8")


def test_fold01_parity_missing_candidate_surface_fails(tmp_path: Path) -> None:
    """Sealed artifact without candidate_surface fails closed."""
    bad_doc = {"candidates": [_make_valid_candidate() for _ in range(102)]}
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
    )

    assert reader.empirical_first_read_utc is None
    assert reader.read_call_count == 0

    # Open store (with preflight_already_run=True for fast synthetic test)
    stream = list(reader.open_store(preflight_already_run=True))
    assert stream == ["row1", "row2"]
    assert mock_raw_stream_called == 1
    assert reader.read_call_count == 1
    assert reader.empirical_first_read_utc is not None
    assert reader.exposure_state["status"] == LABEL_FIRST_EMPIRICAL_BYTE_READ


def test_release_guard_output_not_fresh_fails_before_store_read(tmp_path: Path) -> None:
    """If target output path already exists, guard halts before calling store opener."""
    out_target = tmp_path / "stale_result.json"
    out_target.write_text("existing", encoding="utf-8")

    auth = ReleaseAuthorizationRecord(
        authorization_id="auth_test_002",
        target_partition="fold-01-rehearsal",
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
        governing_plan_id=PLAN_ID, tooling_id=TOOLING_CORRECTION_ID,
        frozen_candidate_identity=FREEZE_IDENTITY, supervisory_approval_reference="REF",
        output_path="out.json", created_utc="2026-10-15T10:00:00Z",
        prior_sealed_pass_reference=None,
    )
    with pytest.raises(TierBAuthorizationError) as exc:
        auth_f3_bad.validate("fold-03")
    assert "requires sealed Fold-02 PASS" in str(exc.value)

    # Fold 03 with prior pass reference passes
    auth_f3_good = ReleaseAuthorizationRecord(
        authorization_id="auth_f3", target_partition="fold-03",
        governing_plan_id=PLAN_ID, tooling_id=TOOLING_CORRECTION_ID,
        frozen_candidate_identity=FREEZE_IDENTITY, supervisory_approval_reference="REF",
        output_path="out.json", created_utc="2026-10-15T10:00:00Z",
        prior_sealed_pass_reference="phase8-v2-tierb-feasibility-fold02-PASS.json",
    )
    auth_f3_good.validate("fold-03")  # passes cleanly


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
    # Conftest prohibits subprocess inside pytest; inject pure working-tree blob source
    monkeypatch.setattr(cp, "make_git_blob_source", lambda repo: (lambda commit, rel: (Path(repo) / rel).read_bytes()))
    from backtests.phase8_v2_tierb_feasibility import main
    rc = main(["preflight"])
    assert rc == 0


def test_cli_run_fold_unauthorized_fails() -> None:
    """CLI run-fold without authorization fails closed with code 4."""
    from backtests.phase8_v2_tierb_feasibility import main
    rc = main(["run-fold", "--fold-id", "fold-02"])
    assert rc == 4
