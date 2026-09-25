"""D004 — expired order-block structural fate decomposition tooling.

Synthetic fixtures only — the empirical store ``fold-01-a8b406884ab3525a``
is NEVER opened in this suite, and no observed D003 empirical count appears
as an expected output (preregistration §2/§3).

Covered (preregistration §20):
* expired + untouched / touched / invalidating close / first retest on the
  final decision candle (LONG and SHORT);
* expired + final same-direction overlapping FVG / non-overlapping FVG;
* causal exclusion of post-decision candles;
* the EXPIRED consumption invariant (asserted; violation fails closed);
* block-identity reconciliation (tampered identity/zone fails closed);
* malformed/data-unsafe inputs fail closed;
* age tests: exact post-confirmation age, frozen expiry threshold stays 30,
  age reporting does not alter canonical state, no alternate-expiry key;
* banned-output guard (exact keys + semantic families, honest keys pass);
* loop-level accounting, prior-state discipline, provenance binding.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtests import phase8_v2_diagnostic_d001 as d001  # noqa: E402
from backtests import phase8_v2_diagnostic_d003 as d003  # noqa: E402
from backtests import phase8_v2_diagnostic_d004 as d004  # noqa: E402
from bot.strategy.config import StrategyConfig  # noqa: E402
from bot.strategy.models import BlockState, StrategySide  # noqa: E402
from bot.strategy.order_blocks import evaluate_order_block  # noqa: E402
from bot.strategy.setup_state import (  # noqa: E402
    StrategyState,
    record_from_state,
)
from tests.test_phase8_v2_d001_tooling import (  # noqa: E402
    AT,
    FOLD01_START_MS,
    _Snapshot,
    _mocked_ok_snapshot,
    _ok_snapshot,
    _patch_engines,
    _seed_record,
)
from tests.test_phase8_v2_d003_tooling import (  # noqa: E402
    _d003_boundary_store,
    _real_adapter_row,
    _store_with_rows,
)

FOLD01_END_MS = int(datetime(2024, 6, 8, tzinfo=timezone.utc).timestamp() * 1000)


# ---------------------------------------------------------------------------
# Synthetic fate fixtures (no empirical data)
# ---------------------------------------------------------------------------

_QUIET = {
    "bullish": (102.0, 102.2, 101.8, 102.0),   # above the LONG zone (99, 101)
    "bearish": (97.8, 98.0, 97.6, 97.8),       # below the SHORT zone (99, 101)
}
_TOUCH = {
    "bullish": (101.0, 101.5, 100.5, 101.2),   # low <= zone_high, high >= zone_low
    "bearish": (98.4, 99.5, 98.2, 99.2),
}
_INVALIDATING = {
    "bullish": (98.8, 99.0, 97.8, 98.5),       # close < zone_low (LONG)
    "bearish": (101.2, 101.8, 100.8, 101.6),   # close > zone_high (SHORT)
}


def _fate_frame(
    *,
    side: str = "bullish",
    scenario: str = "untouched",
    quiet_bars: int = 31,
    trailing: int = 0,
) -> pd.DataFrame:
    """Synthetic frame with a confirmed block and a preregistered fate.

    ``scenario``: untouched | touched | invalidated | first_retest_final |
    causality (quiet bars, then a touch, then more quiet bars).  All
    scenarios place more than 30 post-confirmation bars, so the frozen
    canonical evaluation classifies EXPIRED by construction.
    """
    start = pd.Timestamp("2024-04-01T00:00:00Z")
    rows: list[tuple[float, float, float, float]] = []
    for index in range(14):
        price = 100.0 + index * 0.01
        rows.append((price, price + 0.2, price - 0.2, price + 0.01))
    if side == "bullish":
        rows.extend([(100.5, 101.0, 99.0, 99.5), (99.5, 103.5, 99.4, 103.0)])
    else:
        rows.extend([(100.0, 101.0, 99.0, 100.5), (100.5, 100.6, 96.5, 97.0)])
    quiet = _QUIET[side]
    after: list[tuple[float, float, float, float]] = [quiet] * quiet_bars
    if scenario == "touched":
        after = [quiet] * quiet_bars + [_TOUCH[side]] + [quiet] * 3
    elif scenario == "invalidated":
        after = [quiet] * quiet_bars + [_INVALIDATING[side]] + [quiet] * 3
    elif scenario == "first_retest_final":
        after = [quiet] * quiet_bars + [_TOUCH[side]]
    elif scenario == "causality":
        after = [quiet] * quiet_bars + [_TOUCH[side]] + [quiet] * trailing
    rows.extend(after)
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    frame["open_time"] = pd.date_range(start, periods=len(frame), freq="5min")
    frame["available_at"] = frame["open_time"] + pd.Timedelta(minutes=5)
    return frame


def _fate_snapshot(
    monkeypatch,
    *,
    side: str = "bullish",
    scenario: str = "untouched",
    quiet_bars: int = 31,
    trailing: int = 0,
):
    """A REAL gate-input snapshot over a fate frame (engines mocked like
    the proven D003 fixture); returns ``(snapshot, frame, decision_at)``."""
    from bot.state import gate_inputs as gi
    from config.symbol_profiles import get_symbol_profile

    frame = _fate_frame(
        side=side, scenario=scenario, quiet_bars=quiet_bars, trailing=trailing,
    )
    decision_at = frame["available_at"].iloc[-1].to_pydatetime()
    _patch_engines(monkeypatch)
    inputs = gi.build_gate_inputs(
        symbol="XAUUSDm", event_at=decision_at,
        frames={"H1": frame, "M5": frame, "M15": frame},
        profile=get_symbol_profile("XAUUSDm"), htf_bias=side,
        bias_snapshot={"htf_bias": {"direction": side}},
        bias_resolution={"direction": side},
        liquidity_context={
            "structure_context": {
                "structure": side, "state": "confirmed",
                "discount_zone": (95.0, 99.0),
                "premium_zone": (101.0, 105.0),
            },
            "liquidity_pools": [],
        },
        dxy_context={"available": True, "dxy_bias": side},
        news_context={"news_clear": True},
        session_context={"session_allowed": True, "active_session": "london"},
        config=StrategyConfig(),
    )
    snapshot = _Snapshot(
        available_at_ms=int(decision_at.timestamp() * 1000),
        gate_status="ok",
        gate_payload=inputs.payload,
        gate_event_id=gi.gate_event_id(
            symbol="XAUUSDm", event_at=decision_at,
            sources=inputs.source_identities, side=side,
            payload=inputs.payload, config_fingerprint=inputs.config_fingerprint,
        ),
        gate_sources=inputs.source_identities,
        config_fingerprint=inputs.config_fingerprint,
        bias_snapshot={"htf_bias": {"direction": side}},
        bias_resolution={"direction": side},
        dxy_context={"available": True, "dxy_bias": side},
        frames_sufficient=True,
    )
    return snapshot, frame, decision_at


def _fate_lifecycle(snapshot, *, side="bullish"):
    """The frozen canonical lifecycle for a fate snapshot (D003 observer)."""
    return d004.canonical_ob_lifecycle(
        snapshot, htf_bias=side, prior_state_record=_seed_record(),
        config=StrategyConfig(),
    )


def _fate_observation(monkeypatch, **kwargs):
    """Full real-adapter observation for a fate snapshot."""
    snapshot, frame, decision_at = _fate_snapshot(monkeypatch, **kwargs)
    row, next_record = d001.evaluate_orchestration_decision(snapshot, _seed_record())
    observation = d004.observe_decision(
        row, _seed_record(), snapshot=snapshot, config=StrategyConfig(),
        decision_result_record=next_record,
    )
    return observation, row, snapshot, frame, decision_at


# ---------------------------------------------------------------------------
# §29 (1-4, 7, 8) — fate scenarios across both sides; canonical EXPIRED
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "side,scenario,untouched,touched,invalidated,first_retest",
    [
        ("bullish", "untouched", True, False, False, False),
        ("bullish", "touched", False, True, False, False),
        ("bullish", "invalidated", False, True, True, False),
        ("bullish", "first_retest_final", False, True, False, True),
        ("bearish", "untouched", True, False, False, False),
        ("bearish", "touched", False, True, False, False),
        ("bearish", "invalidated", False, True, True, False),
        ("bearish", "first_retest_final", False, True, False, True),
    ],
)
def test_fate_predicates_by_scenario(
    monkeypatch, side, scenario, untouched, touched, invalidated, first_retest,
):
    snapshot, _frame, decision_at = _fate_snapshot(
        monkeypatch, side=side, scenario=scenario,
    )
    lifecycle = _fate_lifecycle(snapshot, side=side)
    assert lifecycle["state"] == "EXPIRED"
    assert lifecycle["reason"] == "block_expired"
    assert lifecycle["side"] == ("LONG" if side == "bullish" else "SHORT")
    fate = d004.decompose_expired_block(
        snapshot, decision_at=decision_at, lifecycle=lifecycle,
        config=StrategyConfig(),
    )
    assert fate["untouched_through_decision"] is untouched
    assert fate["zone_overlap_before_decision"] is touched
    assert fate["invalidating_close"] is invalidated
    assert fate["first_retest_on_final_candle"] is first_retest
    assert fate["block_side"] == ("LONG" if side == "bullish" else "SHORT")
    assert fate["block_zone"]["zone_low"] == pytest.approx(99.0)
    assert fate["block_zone"]["zone_high"] == pytest.approx(101.0)
    categories = d004.expired_fate_categories(fate)
    assert categories["EXPIRED_UNTOUCHED"] is untouched
    assert categories["EXPIRED_TOUCHED"] is touched
    assert categories["EXPIRED_INVALIDATED"] is invalidated
    assert categories["EXPIRED_FIRST_RETEST_AT_DECISION"] is first_retest


def test_expired_first_retest_index_is_final_candle(monkeypatch):
    snapshot, _frame, decision_at = _fate_snapshot(
        monkeypatch, scenario="first_retest_final", quiet_bars=31,
    )
    lifecycle = _fate_lifecycle(snapshot)
    fate = d004.decompose_expired_block(
        snapshot, decision_at=decision_at, lifecycle=lifecycle,
        config=StrategyConfig(),
    )
    assert fate["first_zone_overlap_index"] == fate["post_confirmation_bars"] - 1
    assert fate["first_retest_on_final_candle"] is True


def test_expired_touched_first_overlap_index(monkeypatch):
    snapshot, _frame, decision_at = _fate_snapshot(
        monkeypatch, scenario="touched", quiet_bars=31,
    )
    fate = d004.decompose_expired_block(
        snapshot, decision_at=decision_at, lifecycle=_fate_lifecycle(snapshot),
        config=StrategyConfig(),
    )
    assert fate["first_zone_overlap_index"] == 31
    assert fate["first_invalidating_close_index"] is None


def test_expired_invalidated_first_index_and_overlap_coexist(monkeypatch):
    """Raw predicates are independent: the invalidating bar also overlaps
    the zone, and both raw counts are reported (no forced single bucket)."""
    snapshot, _frame, decision_at = _fate_snapshot(
        monkeypatch, scenario="invalidated", quiet_bars=31,
    )
    fate = d004.decompose_expired_block(
        snapshot, decision_at=decision_at, lifecycle=_fate_lifecycle(snapshot),
        config=StrategyConfig(),
    )
    assert fate["first_invalidating_close_index"] == 31
    assert fate["first_zone_overlap_index"] == 31
    categories = d004.expired_fate_categories(fate)
    assert categories["EXPIRED_TOUCHED"] and categories["EXPIRED_INVALIDATED"]
    assert categories["EXPIRED_UNTOUCHED"] is False


# ---------------------------------------------------------------------------
# §29 (9) — causal exclusion of post-decision candles
# ---------------------------------------------------------------------------


def test_post_decision_candles_are_excluded(monkeypatch):
    """A zone touch occurring AFTER the decision timestamp is invisible at
    the earlier decision: same frame, two decision instants."""
    snapshot, _frame, late_decision = _fate_snapshot(
        monkeypatch, scenario="causality", quiet_bars=31, trailing=4,
    )
    lifecycle = _fate_lifecycle(snapshot)
    frame = _fate_frame(scenario="causality", quiet_bars=31, trailing=4)
    early_bars = 31
    # Decision at the availability of the EARLIER post-confirmation bar
    # (open index lead+conf+30) so the post-decision touch is excluded.
    early_decision = frame["available_at"].iloc[15 + 1 + 30].to_pydatetime()

    early_fate = d004.decompose_expired_block(
        snapshot, decision_at=early_decision, lifecycle=lifecycle,
        config=StrategyConfig(),
    )
    late_fate = d004.decompose_expired_block(
        snapshot, decision_at=late_decision, lifecycle=lifecycle,
        config=StrategyConfig(),
    )
    assert early_fate["post_confirmation_bars"] == early_bars
    assert early_fate["zone_overlap_before_decision"] is False
    assert early_fate["untouched_through_decision"] is True
    assert early_fate["bars_beyond_expiry_boundary"] == early_bars - 30
    assert late_fate["post_confirmation_bars"] == early_bars + 1 + 4
    assert late_fate["first_zone_overlap_index"] == early_bars


def test_causal_exclusion_through_the_full_observer(monkeypatch):
    """The loop-level decision timestamp (snapshot available_at_ms) drives
    the canonical lifecycle: a frame whose post-decision bars would touch
    the zone still evaluates causally at the earlier decision."""
    snapshot, _frame, _decision_at = _fate_snapshot(
        monkeypatch, scenario="causality", quiet_bars=31, trailing=4,
    )
    frame = _fate_frame(scenario="causality", quiet_bars=31, trailing=4)
    early_decision = frame["available_at"].iloc[15 + 1 + 30].to_pydatetime()
    config = StrategyConfig()
    early = evaluate_order_block(
        _snapshot_frame(snapshot), StrategySide.LONG, early_decision, config,
    )
    assert early.state is BlockState.EXPIRED  # 31 > 30 bars, quiet so far
    late = evaluate_order_block(
        _snapshot_frame(snapshot), StrategySide.LONG,
        frame["available_at"].iloc[-1].to_pydatetime(), config,
    )
    assert late.state is BlockState.EXPIRED
    assert late.block_id == early.block_id


def _snapshot_frame(snapshot):
    return d003.canonical_ob_frame(
        list(json.loads(snapshot.gate_payload).get("entry_rows") or [])
    )


# ---------------------------------------------------------------------------
# §29 (5, 6) — final FVG context: overlapping vs non-overlapping
# ---------------------------------------------------------------------------


def test_expired_with_same_direction_overlapping_fvg(monkeypatch):
    observation, _row, _snapshot, _frame, _at = _fate_observation(
        monkeypatch, scenario="untouched",
    )
    assert observation["gate_11_entered"] is True
    assert observation["canonical_state"] == "EXPIRED"
    fvg = observation["fvg_context"]
    assert fvg["final_fvg_present"] is True
    assert fvg["raw_canonical_fvg_count"] == 1
    assert fvg["direction_agreement"] == "agree"
    assert fvg["canonical_overlap"] is True
    assert fvg["separation_geometry"]["intersection"] is True


def test_expired_with_non_overlapping_fvg(monkeypatch):
    from bot.state import gate_inputs as gi

    _patch_engines(monkeypatch)
    monkeypatch.setattr(gi, "get_unfilled_fvgs", lambda *a, **kw: [{
        "bottom": 120.0, "top": 121.0, "direction": "bullish",
        "type": "bullish_fvg", "filled": False,
    }])
    from config.symbol_profiles import get_symbol_profile

    frame = _fate_frame(scenario="untouched")
    decision_at = frame["available_at"].iloc[-1].to_pydatetime()
    inputs = gi.build_gate_inputs(
        symbol="XAUUSDm", event_at=decision_at,
        frames={"H1": frame, "M5": frame, "M15": frame},
        profile=get_symbol_profile("XAUUSDm"), htf_bias="bullish",
        bias_snapshot={"htf_bias": {"direction": "bullish"}},
        bias_resolution={"direction": "bullish"},
        liquidity_context={
            "structure_context": {
                "structure": "bullish", "state": "confirmed",
                "discount_zone": (95.0, 99.0), "premium_zone": (101.0, 105.0),
            },
            "liquidity_pools": [],
        },
        dxy_context={"available": True, "dxy_bias": "bullish"},
        news_context={"news_clear": True},
        session_context={"session_allowed": True, "active_session": "london"},
        config=StrategyConfig(),
    )
    snapshot = _Snapshot(
        available_at_ms=int(decision_at.timestamp() * 1000),
        gate_status="ok", gate_payload=inputs.payload,
        gate_event_id=gi.gate_event_id(
            symbol="XAUUSDm", event_at=decision_at,
            sources=inputs.source_identities, side="bullish",
            payload=inputs.payload, config_fingerprint=inputs.config_fingerprint,
        ),
        gate_sources=inputs.source_identities,
        config_fingerprint=inputs.config_fingerprint, frames_sufficient=True,
    )
    row, next_record = d001.evaluate_orchestration_decision(snapshot, _seed_record())
    observation = d004.observe_decision(
        row, _seed_record(), snapshot=snapshot, config=StrategyConfig(),
        decision_result_record=next_record,
    )
    assert observation["canonical_state"] == "EXPIRED"
    fvg = observation["fvg_context"]
    assert fvg["final_fvg_present"] is True
    assert fvg["direction_agreement"] == "agree"
    assert fvg["canonical_overlap"] is False
    assert fvg["separation_geometry"]["intersection"] is False
    assert fvg["separation_geometry"]["signed_separation"] > 0.0


def test_expired_without_final_fvg_is_not_available(monkeypatch):
    from bot.state import gate_inputs as gi

    _patch_engines(monkeypatch)
    monkeypatch.setattr(gi, "get_unfilled_fvgs", lambda *a, **kw: [])
    from config.symbol_profiles import get_symbol_profile

    frame = _fate_frame(scenario="untouched")
    decision_at = frame["available_at"].iloc[-1].to_pydatetime()
    inputs = gi.build_gate_inputs(
        symbol="XAUUSDm", event_at=decision_at,
        frames={"H1": frame, "M5": frame, "M15": frame},
        profile=get_symbol_profile("XAUUSDm"), htf_bias="bullish",
        bias_snapshot={"htf_bias": {"direction": "bullish"}},
        bias_resolution={"direction": "bullish"},
        liquidity_context={
            "structure_context": {
                "structure": "bullish", "state": "confirmed",
                "discount_zone": (95.0, 99.0), "premium_zone": (101.0, 105.0),
            },
            "liquidity_pools": [],
        },
        dxy_context={"available": True, "dxy_bias": "bullish"},
        news_context={"news_clear": True},
        session_context={"session_allowed": True, "active_session": "london"},
        config=StrategyConfig(),
    )
    snapshot = _Snapshot(
        available_at_ms=int(decision_at.timestamp() * 1000),
        gate_status="ok", gate_payload=inputs.payload,
        gate_event_id=gi.gate_event_id(
            symbol="XAUUSDm", event_at=decision_at,
            sources=inputs.source_identities, side="bullish",
            payload=inputs.payload, config_fingerprint=inputs.config_fingerprint,
        ),
        gate_sources=inputs.source_identities,
        config_fingerprint=inputs.config_fingerprint, frames_sufficient=True,
    )
    row, next_record = d001.evaluate_orchestration_decision(snapshot, _seed_record())
    observation = d004.observe_decision(
        row, _seed_record(), snapshot=snapshot, config=StrategyConfig(),
        decision_result_record=next_record,
    )
    assert observation["canonical_state"] == "EXPIRED"
    fvg = observation["fvg_context"]
    assert fvg["final_fvg_present"] is False
    assert fvg["direction_agreement"] == "not_available"
    assert fvg["raw_canonical_fvg_count"] == 0


# ---------------------------------------------------------------------------
# §29 (10) — consumption invariant (asserted; violation fails closed)
# ---------------------------------------------------------------------------


def test_expired_consumption_invariant_holds_on_real_path(monkeypatch):
    snapshot, _frame, decision_at = _fate_snapshot(monkeypatch)
    lifecycle = _fate_lifecycle(snapshot)
    assert lifecycle["state"] == "EXPIRED"
    fate = d004.decompose_expired_block(
        snapshot, decision_at=decision_at, lifecycle=lifecycle,
        config=StrategyConfig(),
    )
    assert fate["consumed_invariant_holds"] is True
    assert fate["block_already_consumed"] is False
    assert fate["block_id"] not in set(lifecycle["consumed_ids_derived"])


def test_expired_consumed_invariant_violation_fails_closed(monkeypatch):
    snapshot, _frame, decision_at = _fate_snapshot(monkeypatch)
    lifecycle = _fate_lifecycle(snapshot)
    assert lifecycle["state"] == "EXPIRED"
    tampered = {
        **lifecycle,
        "consumed_ids_derived": sorted(
            set(lifecycle["consumed_ids_derived"]) | {lifecycle["block_id"]}
        ),
    }
    with pytest.raises(d004.D004Error, match="consumption invariant violated"):
        d004.decompose_expired_block(
            snapshot, decision_at=decision_at, lifecycle=tampered,
            config=StrategyConfig(),
        )


def test_consumed_block_is_never_classified_expired_by_frozen_evaluator(monkeypatch):
    """The invariant's premise: the frozen evaluator checks consumed ids
    before its expiry short-circuit, so a consumed block cannot return
    EXPIRED under frozen semantics."""
    snapshot, _frame, decision_at = _fate_snapshot(monkeypatch)
    frame = _snapshot_frame(snapshot)
    config = StrategyConfig()
    block_id = evaluate_order_block(
        frame, StrategySide.LONG, decision_at, config,
    ).block_id
    blocked = evaluate_order_block(
        frame, StrategySide.LONG, decision_at, config,
        consumed_ids=frozenset({block_id}),
    )
    assert blocked.state is BlockState.CONSUMED
    assert blocked.reason == "block_already_consumed"


# ---------------------------------------------------------------------------
# §29 (11) — block-identity reconciliation (fail closed)
# ---------------------------------------------------------------------------


def test_block_identity_reconciles_with_frozen_evaluation(monkeypatch):
    snapshot, _frame, decision_at = _fate_snapshot(monkeypatch)
    lifecycle = _fate_lifecycle(snapshot)
    frozen = evaluate_order_block(
        _snapshot_frame(snapshot), StrategySide.LONG, decision_at,
        StrategyConfig(),
    )
    assert lifecycle["block_id"] == frozen.block_id
    fate = d004.decompose_expired_block(
        snapshot, decision_at=decision_at, lifecycle=lifecycle,
        config=StrategyConfig(),
    )
    assert fate["block_id"] == frozen.block_id
    assert fate["block_zone"]["zone_low"] == pytest.approx(frozen.zone_low)
    assert fate["block_zone"]["zone_high"] == pytest.approx(frozen.zone_high)
    assert fate["block_confirmed_at"] == frozen.confirmed_at.astimezone(timezone.utc).isoformat()


def test_block_identity_mismatch_fails_closed(monkeypatch):
    snapshot, _frame, decision_at = _fate_snapshot(monkeypatch)
    lifecycle = _fate_lifecycle(snapshot)
    with pytest.raises(d004.D004Error, match="block identity reconciliation failed"):
        d004.decompose_expired_block(
            snapshot, decision_at=decision_at,
            lifecycle={**lifecycle, "block_id": "deadbeef" * 3},
            config=StrategyConfig(),
        )
    with pytest.raises(d004.D004Error, match="block zone reconciliation failed"):
        d004.decompose_expired_block(
            snapshot, decision_at=decision_at,
            lifecycle={**lifecycle, "zone_low": 12.0, "zone_high": 13.0},
            config=StrategyConfig(),
        )


def test_nondirectional_block_fails_closed(monkeypatch):
    snapshot, _frame, decision_at = _fate_snapshot(monkeypatch)
    lifecycle = _fate_lifecycle(snapshot)
    with pytest.raises(d004.D004Error, match="directional block"):
        d004.decompose_expired_block(
            snapshot, decision_at=decision_at,
            lifecycle={**lifecycle, "side": "FLAT"},
            config=StrategyConfig(),
        )


# ---------------------------------------------------------------------------
# §29 (12) — malformed / data-unsafe inputs fail closed
# ---------------------------------------------------------------------------


def test_malformed_payload_fails_closed(monkeypatch):
    snapshot, _frame, decision_at = _fate_snapshot(monkeypatch)
    payload = json.loads(snapshot.gate_payload)
    rows = payload["entry_rows"]
    for row in rows:
        row.pop("close", None)
    broken = _Snapshot(
        available_at_ms=snapshot.available_at_ms, gate_status="ok",
        gate_payload=json.dumps(payload), gate_event_id=snapshot.gate_event_id,
        gate_sources=snapshot.gate_sources,
        config_fingerprint=snapshot.config_fingerprint, frames_sufficient=True,
    )
    with pytest.raises(d004.D004Error, match="no same-side detected block"):
        d004.decompose_expired_block(
            broken, decision_at=decision_at,
            lifecycle=_fate_lifecycle(snapshot), config=StrategyConfig(),
        )


def test_data_unsafe_lifecycle_is_count_only(monkeypatch):
    """A DATA_UNSAFE canonical evaluation is counted (no geometry), never
    decomposed, and never silently dropped."""
    snapshot, _frame, _decision_at = _fate_snapshot(monkeypatch)
    observation = {
        "decision_id": "data-unsafe",
        "gate_11_entered": True,
        "canonical_state": "DATA_UNSAFE",
        "fate": None,
        "fvg_context": None,
    }
    aggregate = d004.aggregate_d004([observation])
    assert aggregate["gate11_entrants"] == 1
    assert aggregate["count_only_states"] == {"DATA_UNSAFE": 1}
    assert aggregate["expired_population"]["count"] == 0
    d004.assert_expected_surfaces(_minimal_document(aggregate))


def test_run_d004_rejects_wrong_fold_and_coverage(monkeypatch):
    store = _d003_boundary_store(monkeypatch)
    store.identity = {**store.identity, "fold_id": "fold-02"}
    with pytest.raises(d001.BoundaryError):
        d004.run_d004(
            store, canonical_commit="c" * 40,
            tooling_commit=_d004_tooling_commit(),
            blob_source=_d004_tooling_blob_source(),
        )
    store2 = _d003_boundary_store(monkeypatch)
    store2.identity = {**store2.identity, "coverage": "stride-4"}
    with pytest.raises(d001.BoundaryError):
        d004.run_d004(
            store2, canonical_commit="c" * 40,
            tooling_commit=_d004_tooling_commit(),
            blob_source=_d004_tooling_blob_source(),
        )


def test_write_result_refuses_overwrite(tmp_path, monkeypatch):
    doc, rendered = d004.run_d004(
        _d003_boundary_store(monkeypatch), canonical_commit="c" * 40,
        tooling_commit=_d004_tooling_commit(),
        blob_source=_d004_tooling_blob_source(),
    )
    target, digest = d004.write_result(doc, rendered, tmp_path)
    assert Path(target).exists()
    assert hashlib.sha256(Path(target).read_bytes()).hexdigest() == digest
    with pytest.raises(d004.D004Error, match="refusing overwrite"):
        d004.write_result(doc, rendered, tmp_path)


# ---------------------------------------------------------------------------
# §30 — age tests
# ---------------------------------------------------------------------------


def test_age_is_exact_post_confirmation_bar_count(monkeypatch):
    snapshot, _frame, decision_at = _fate_snapshot(
        monkeypatch, scenario="untouched", quiet_bars=33,
    )
    fate = d004.decompose_expired_block(
        snapshot, decision_at=decision_at, lifecycle=_fate_lifecycle(snapshot),
        config=StrategyConfig(),
    )
    assert fate["post_confirmation_bars"] == 33
    assert fate["bars_beyond_expiry_boundary"] == 3
    aggregate = d004.aggregate_d004([_expired_observation(fate)])
    surface = aggregate["expired_population"]["age_surface"]
    assert surface["histogram"] == {"33": 1}
    assert surface["count"] == 1 and surface["min"] == 33 and surface["max"] == 33
    assert surface["median"] == 33.0


def test_age_histogram_covers_mixed_ages_exactly(monkeypatch):
    fates = []
    for quiet in (31, 32, 35):
        snapshot, _frame, decision_at = _fate_snapshot(
            monkeypatch, scenario="untouched", quiet_bars=quiet,
        )
        fates.append(d004.decompose_expired_block(
            snapshot, decision_at=decision_at,
            lifecycle=_fate_lifecycle(snapshot), config=StrategyConfig(),
        ))
    aggregate = d004.aggregate_d004([_expired_observation(fate) for fate in fates])
    surface = aggregate["expired_population"]["age_surface"]
    assert surface["histogram"] == {"31": 1, "32": 1, "35": 1}
    assert surface["min"] == 31 and surface["max"] == 35
    assert surface["median"] == 32.0
    assert surface["quantiles"]["p25"] == pytest.approx(31.5)
    assert surface["quantiles"]["p75"] == pytest.approx(33.5)


def test_frozen_expiry_threshold_stays_30(monkeypatch):
    snapshot, _frame, decision_at = _fate_snapshot(monkeypatch)
    fate = d004.decompose_expired_block(
        snapshot, decision_at=decision_at, lifecycle=_fate_lifecycle(snapshot),
        config=StrategyConfig(),
    )
    assert fate["frozen_expiry_bars"] == 30
    assert StrategyConfig().order_block_expiry_bars == 30
    store = _store_with_rows(monkeypatch, [snapshot])
    doc, _rendered = d004.run_d004(
        store, canonical_commit="c" * 40, tooling_commit=_d004_tooling_commit(),
        blob_source=_d004_tooling_blob_source(),
    )
    assert doc["frozen_configuration"] == {
        "order_block_expiry_bars": 30,
        "evaluation_performed_only_at_frozen_threshold": True,
    }


def test_age_reporting_does_not_alter_state(monkeypatch):
    snapshot, _frame, decision_at = _fate_snapshot(monkeypatch)
    config = StrategyConfig()
    frame = _snapshot_frame(snapshot)
    before = evaluate_order_block(frame, StrategySide.LONG, decision_at, config)
    lifecycle_before = _fate_lifecycle(snapshot)
    d004.decompose_expired_block(
        snapshot, decision_at=decision_at, lifecycle=lifecycle_before, config=config,
    )
    after = evaluate_order_block(frame, StrategySide.LONG, decision_at, config)
    assert (after.state, after.reason, after.block_id) == (
        before.state, before.reason, before.block_id
    )
    lifecycle_after = _fate_lifecycle(snapshot)
    assert lifecycle_after == lifecycle_before


def test_no_alternate_expiry_output_key_exists(monkeypatch):
    store = _d003_boundary_store(monkeypatch)
    doc, _rendered = d004.run_d004(
        store, canonical_commit="c" * 40, tooling_commit=_d004_tooling_commit(),
        blob_source=_d004_tooling_blob_source(),
    )
    allowed = {
        "frozen_expiry_bars", "bars_beyond_expiry_boundary",
        "order_block_expiry_bars",
    }
    found: list[str] = []

    def _scan(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if "expiry" in str(key).lower():
                    found.append(str(key))
                _scan(value)
        elif isinstance(node, list):
            for value in node:
                _scan(value)

    _scan(doc)
    assert set(found) <= allowed, found
    d004._reject_banned_metrics(doc)  # guard passes over the real document


# ---------------------------------------------------------------------------
# §31 — banned-output guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["pnl", "profit", "profit_factor", "win_rate", "expectancy", "drawdown",
     "sharpe", "returns", "fills", "closed_trades", "candidate_if_expiry_removed",
     "eligible_without_expiry", "alternate_expiry", "alternative_expiry",
     "expiry_45", "expiry_60", "expiry_90", "counterfactual_candidate",
     "temporal_fvg_lag", "candidate_count_at_expiry_60", "would_pass_at_expiry_45"],
)
def test_banned_keys_fail_closed(key):
    with pytest.raises(d004.D004Error, match=d004.REJECTED_D004_METRIC_KEY):
        d004._reject_banned_metrics({key: 1})


@pytest.mark.parametrize(
    "key",
    ["no_profitability_metrics", "no_alternate_configuration_scored",
     "fate_categories", "untouched_through_decision", "h002_not_reopened",
     "expired_population", "first_retest_on_final_candle"],
)
def test_honest_keys_pass(key):
    d004._reject_banned_metrics({key: 1})


def test_guard_is_recursive_over_nested_output():
    with pytest.raises(d004.D004Error, match=d004.REJECTED_D004_METRIC_KEY):
        d004._reject_banned_metrics({"surfaces": {"deep": [{"expiry_60": 1}]}})


# ---------------------------------------------------------------------------
# §14/§20 — D003-semantics reconciliation + reference populations
# ---------------------------------------------------------------------------


def test_observer_agrees_with_d003_semantics(monkeypatch):
    observation, row, snapshot, _frame, _at = _fate_observation(monkeypatch)
    _row2, next_record = d001.evaluate_orchestration_decision(snapshot, _seed_record())
    base = d003.observe_decision(
        row, _seed_record(), snapshot=snapshot, config=StrategyConfig(),
        decision_result_record=next_record,
    )
    lifecycle = base["canonical_lifecycle"]
    assert observation["canonical_state"] == lifecycle["state"] == "EXPIRED"
    assert observation["fate"]["block_id"] == lifecycle["block_id"]
    assert observation["fate"]["block_side"] == lifecycle["side"]
    assert observation["fate"]["reason"] == lifecycle["reason"]
    assert observation["final_fvg_present"] == base["final_fvg_present"]


def test_reference_populations_carry_predicates(monkeypatch):
    """A canonically ELIGIBLE entrant carries the same descriptive
    predicates under its own BlockState label; states are never merged."""
    observation, _row, _snapshot, _frame, _at = _fate_observation(
        monkeypatch, scenario="untouched", quiet_bars=2,
    )
    # quiet_bars=2 keeps the block canonically ELIGIBLE at the decision.
    assert observation["canonical_state"] == "ELIGIBLE"
    assert observation["fate"] is not None
    assert observation["fate_categories"] is None  # categories are EXPIRED-only
    aggregate = d004.aggregate_d004([observation])
    eligible = aggregate["reference_populations"]["ELIGIBLE"]
    assert eligible["blocks"] == 1
    assert eligible["fate_predicates"]["untouched_through_decision"] == 1
    assert aggregate["expired_population"]["count"] == 0


# ---------------------------------------------------------------------------
# Loop-level: accounting, prior-state discipline, determinism
# ---------------------------------------------------------------------------


def _expired_observation(fate):
    return {
        "decision_id": f"expired-{fate['post_confirmation_bars']}",
        "gate_11_entered": True,
        "canonical_state": "EXPIRED",
        "fate": fate,
        "fate_categories": d004.expired_fate_categories(fate),
        "fvg_context": {
            "final_fvg_present": False, "raw_canonical_fvg_count": 0,
            "direction_agreement": "not_available", "canonical_overlap": False,
            "separation_geometry": {},
        },
    }


def _minimal_document(aggregate):
    return {
        "decision_accounting": {
            "scheduled": 1, "reducer_classified": 1, "missing_history": 0,
            "unavailable_input": 0, "evaluation_error": 0,
        },
        "gate_funnel": {},
        **aggregate,
    }


def test_run_d004_loop_mixed_population(monkeypatch):
    """Default-fixture entrants (flat frames -> UNAVAILABLE) plus one
    custom EXPIRED entrant partition the Gate-11 population exactly.  The
    D001 store-row iteration is causal order-preserving, so rows must be
    supplied in nondecreasing available_at_ms order."""
    expired_snapshot, _frame, _at = _fate_snapshot(monkeypatch)
    # Chronological store order (D001 iteration is order-preserving):
    # early_exit (Apr 1 00:00), dxy_blocked (Apr 1 00:00:09), the expired
    # fate entrant (Apr 1 01:15), the default fixture (Apr 8).
    rows = [
        _Snapshot(available_at_ms=FOLD01_START_MS, gate_status="early_exit"),
        _Snapshot(available_at_ms=FOLD01_START_MS + 9, gate_status="dxy_blocked"),
        expired_snapshot,
        _mocked_ok_snapshot(monkeypatch, at=datetime(2024, 4, 8, tzinfo=timezone.utc)),
    ]
    store = _store_with_rows(monkeypatch, rows)
    doc, rendered = d004.run_d004(
        store, canonical_commit="c" * 40, tooling_commit=_d004_tooling_commit(),
        blob_source=_d004_tooling_blob_source(),
    )
    accounting = doc["decision_accounting"]
    assert accounting["scheduled"] == 4
    assert accounting["missing_history"] == 1
    assert accounting["unavailable_input"] == 1
    assert accounting["reducer_classified"] == 2
    assert accounting["reducer_classified"] + accounting["missing_history"] + \
        accounting["unavailable_input"] + accounting["evaluation_error"] == accounting["scheduled"]
    assert doc["gate11_entrants"] == 2
    assert doc["expired_population"]["count"] == 1
    assert doc["count_only_states"].get("UNAVAILABLE") == 1
    d004.assert_expected_surfaces(doc)
    assert len(rendered) > 0
    # Determinism: identical inputs reproduce identical aggregates.
    doc2, _rendered2 = d004.run_d004(
        _store_with_rows(monkeypatch, rows), canonical_commit="c" * 40,
        tooling_commit=_d004_tooling_commit(),
        blob_source=_d004_tooling_blob_source(),
    )
    assert doc2["expired_population"] == doc["expired_population"]
    assert doc2["fate_x_fvg_contingency"] == doc["fate_x_fvg_contingency"]


def test_run_d004_expired_loop_surfaces(monkeypatch):
    snapshot, _frame, _at = _fate_snapshot(monkeypatch, scenario="touched")
    store = _store_with_rows(monkeypatch, [snapshot])
    doc, _rendered = d004.run_d004(
        store, canonical_commit="c" * 40, tooling_commit=_d004_tooling_commit(),
        blob_source=_d004_tooling_blob_source(),
    )
    expired = doc["expired_population"]
    assert expired["count"] == 1
    assert expired["fate_predicate_counts"]["zone_overlap_before_decision"] == 1
    assert expired["fate_categories"]["EXPIRED_TOUCHED"] == 1
    assert expired["age_surface"]["histogram"] == {str(31 + 4): 1}
    fvg = doc["fvg_context_summary"]
    assert fvg["expired_with_final_fvg"] == 1
    assert fvg["direction_agreement"]["agree"] == 1
    assert fvg["canonical_overlap_true"] == 1
    assert doc["fate_x_fvg_contingency"]
    cell = next(iter(doc["fate_x_fvg_contingency"]))
    assert "untouched=False/touched=True" in cell
    assert "fvg_present=True" in cell


def test_run_d004_short_side_loop(monkeypatch):
    snapshot, _frame, _at = _fate_snapshot(
        monkeypatch, side="bearish", scenario="first_retest_final",
    )
    store = _store_with_rows(monkeypatch, [snapshot])
    doc, _rendered = d004.run_d004(
        store, canonical_commit="c" * 40, tooling_commit=_d004_tooling_commit(),
        blob_source=_d004_tooling_blob_source(),
    )
    expired = doc["expired_population"]
    assert expired["count"] == 1
    assert expired["fate_categories"]["EXPIRED_FIRST_RETEST_AT_DECISION"] == 1
    assert expired["fate_predicate_counts"]["first_retest_on_final_candle"] == 1


def test_run_d004_observer_receives_causal_prior_record(monkeypatch):
    """TC001 discipline carried into the D004 loop: the observer receives
    the identical prior record the adapter consumed (never next_record)."""
    store = _d003_boundary_store(monkeypatch)
    import backtests.phase8_v2_diagnostic_d004 as d004_mod

    adapter_records: list = []
    real_adapter = d004_mod.evaluate_orchestration_decision

    def adapter_spy(snapshot, record):
        adapter_records.append(record)
        return real_adapter(snapshot, record)

    monkeypatch.setattr(d004_mod, "evaluate_orchestration_decision", adapter_spy)

    observer_records: list = []
    real_observer = d004_mod.observe_decision

    def observer_spy(row, prior_state_record, *, snapshot, config, decision_result_record):
        observer_records.append(prior_state_record)
        return real_observer(
            row, prior_state_record, snapshot=snapshot, config=config,
            decision_result_record=decision_result_record,
        )

    monkeypatch.setattr(d004_mod, "observe_decision", observer_spy)
    d004.run_d004(
        store, canonical_commit="c" * 40, tooling_commit=_d004_tooling_commit(),
        blob_source=_d004_tooling_blob_source(),
    )
    assert observer_records, "observer must run for successful decisions"
    assert len(adapter_records) == len(observer_records)
    for adapter_record, observer_record in zip(adapter_records, observer_records):
        assert observer_record is adapter_record


# ---------------------------------------------------------------------------
# Provenance — canonical_git_blob_v1 tooling fingerprint (TC002 discipline)
# ---------------------------------------------------------------------------

_D004_TOOLING_IDENTITY: tuple[str, object] | None = None


def _d004_tooling_identity():
    """Synthetic committed-blob fixture for the D004 tooling file (pure
    Python Git object store; tests never launch processes)."""
    global _D004_TOOLING_IDENTITY
    if _D004_TOOLING_IDENTITY is None:
        from tests.test_canonical_byte_contract import GitObjectStore

        source = Path(d004.__file__).read_bytes()
        store = GitObjectStore(Path(tempfile.mkdtemp(prefix="d004-tooling-")))
        commit = store.commit_files(
            {"backtests/phase8_v2_diagnostic_d004.py": source},
            "D004 tooling fixture commit",
        )
        _D004_TOOLING_IDENTITY = (commit, store.blob_bytes)
    return _D004_TOOLING_IDENTITY


def _d004_tooling_commit():
    return _d004_tooling_identity()[0]


def _d004_tooling_blob_source():
    return _d004_tooling_identity()[1]


def test_provenance_fingerprint_is_committed_blob():
    import hashlib

    commit, blob_source = _d004_tooling_identity()
    doc = d004.provenance(
        canonical_commit="c" * 40, tooling_commit=commit,
        store_identity={}, blob_source=blob_source,
    )
    assert doc["fingerprint_contract"] == "canonical_git_blob_v1"
    assert doc["tooling_fingerprint"] == hashlib.sha256(
        blob_source(commit, "backtests/phase8_v2_diagnostic_d004.py")
    ).hexdigest()


def test_provenance_fails_closed_on_unresolvable_identity():
    commit, blob_source = _d004_tooling_identity()
    for bad_commit in ("short", "g" * 40, "f" * 40):
        with pytest.raises(d004.D004Error, match="invalid|unresolvable"):
            d004.provenance(
                canonical_commit="c" * 40, tooling_commit=bad_commit,
                store_identity={}, blob_source=blob_source,
            )
    with pytest.raises(d004.D004Error, match="invalid"):
        d004.provenance(
            canonical_commit="tooshort", tooling_commit=commit,
            store_identity={}, blob_source=blob_source,
        )


def test_run_d004_provenance_binds_spec_and_diagnostic(monkeypatch):
    store = _d003_boundary_store(monkeypatch)
    doc, _rendered = d004.run_d004(
        store, canonical_commit="c" * 40, tooling_commit=_d004_tooling_commit(),
        blob_source=_d004_tooling_blob_source(),
    )
    provenance = doc["provenance"]
    assert provenance["diagnostic_id"] == "phase8-v2-D004"
    assert provenance["linked_hypothesis"] == "phase8-v2-H006"
    assert provenance["contextual_prior"] == "phase8-v2-H002 = SUPPORTED_BY_D003"
    assert provenance["specification_sha256"] == d004.SPECIFICATION_SHA256
    assert provenance["not_reopened_hypotheses"] == [
        "phase8-v2-H001", "phase8-v2-H002", "phase8-v2-H003", "phase8-v2-H005",
    ]
    assert provenance["tooling_commit"] == _d004_tooling_commit()
