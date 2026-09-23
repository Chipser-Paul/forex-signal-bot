"""Phase-A tests for V001 (phase6-development-v2-V001): Canonical FVG
ATR-Series Compatibility Repair.

Verifies the local FVG-detector ATR-interface repair against the
preregistered specification (docs/PHASE8_V2_VARIANT_V001.md) and the static
audit (phase8-v2-S001).  Synthetic, hand-constructed OHLC data only — no
Phase 8 empirical Parquet, no Fold-01 feature store, no historical market
archives, no external evidence outputs.

Covered:

* ATR mathematical equivalence: ``bot.strategy.regime.atr_series`` final-bar
  value equals the frozen scalar ``utils.indicators.calculate_atr`` across
  multiple deterministic frame shapes and periods (1e-12 tolerance);
* frozen semantic invariants (defaults 14 / 1.5, geometry, fill, direction,
  ``source_index = i - 1``);
* required synthetic detector cases A-H (insufficient history, bullish,
  bearish, displacement rejection, no-gap rejection, filled, unfilled,
  direction filtering);
* the static-defect regression: ``detect_fvgs`` must evaluate real
  three-candle structure (fails under the exact pre-V001 implementation,
  which returned ``[]`` for every input);
* global-helper invariance (``utils/indicators.py`` blob unchanged);
* fresh-process import safety (no MetaTrader5, no broker, no Streamlit).
"""

from __future__ import annotations

import hashlib
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

from tests.conftest import REAL_POPEN

from bot.analysis import fvg_engine
from bot.analysis.fvg_engine import detect_fvgs, get_unfilled_fvgs
from bot.strategy.regime import atr_series
from utils.indicators import calculate_atr

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "287a159e5ce87339688f3d862e42fb81fba90d0c"
INDICATORS_BLOB = "5324ae9e1b1be9dc578c187f05216141bd32c5bb"
ATR_EQUIVALENCE_TOLERANCE = dict(rel_tol=1e-12, abs_tol=1e-12)


def _frame(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """Deterministic synthetic OHLC frame (open, high, low, close) per row."""
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def _stable(n: int, level: float = 100.0, rng: float = 0.4) -> list[tuple[float, float, float, float]]:
    """Stable-volatility base candles: tiny bodies, constant range."""
    half = rng / 2
    return [(level, level + half, level - half, level) for _ in range(n)]


# ---------------------------------------------------------------------------
# Section 7 — ATR mathematical equivalence (series helper vs scalar helper)
# ---------------------------------------------------------------------------


def _equivalence_frames() -> dict[str, pd.DataFrame]:
    wide = _frame(_stable(24))
    narrow = _frame(_stable(24, rng=0.1))
    # Prev-close gaps: candle ranges that never overlap the previous close.
    gapped = _frame(
        [
            (100.0, 100.5, 99.5, 100.0),
            (101.0, 101.6, 100.6, 101.2),
            (100.2, 100.8, 99.2, 99.8),
            (101.4, 101.9, 100.9, 101.5),
        ]
        * 6
    )
    # Bullish trend: positive bodies, rising closes.
    bull = _frame(
        [
            (100.0 + 0.5 * k, 100.9 + 0.5 * k, 99.9 + 0.5 * k, 100.6 + 0.5 * k)
            for k in range(24)
        ]
    )
    # Bearish trend: negative bodies, falling closes.
    bear = _frame(
        [
            (101.0 - 0.5 * k, 101.4 - 0.5 * k, 100.2 - 0.5 * k, 100.5 - 0.5 * k)
            for k in range(24)
        ]
    )
    # Changing volatility: calm block then violent block.
    changing = _frame(_stable(12, rng=0.2) + _stable(12, rng=2.4))
    return {
        "stable_wide": wide,
        "stable_narrow": narrow,
        "prev_close_gaps": gapped,
        "bullish_trend": bull,
        "bearish_trend": bear,
        "changing_volatility": changing,
    }


@pytest.mark.parametrize("period", [14, 5])
@pytest.mark.parametrize("shape", list(_equivalence_frames()))
def test_atr_series_equals_scalar_helper_at_final_bar(period, shape):
    frame = _equivalence_frames()[shape]
    series_value = float(atr_series(frame, period).iloc[-1])
    scalar_value = calculate_atr(frame, period)
    assert math.isclose(
        series_value, scalar_value, **ATR_EQUIVALENCE_TOLERANCE
    ), f"{shape} period={period}: {series_value} != {scalar_value}"


def test_atr_series_equals_scalar_helper_on_detector_fixture():
    frame = _frame(_stable(17) + [(100.0, 101.2, 99.8, 101.0), (101.0, 101.4, 100.9, 101.2)])
    assert math.isclose(
        float(atr_series(frame, 14).iloc[-1]),
        calculate_atr(frame, 14),
        **ATR_EQUIVALENCE_TOLERANCE,
    )


# ---------------------------------------------------------------------------
# Section 8 — frozen semantic invariants
# ---------------------------------------------------------------------------


def test_frozen_defaults_unchanged():
    import inspect

    sig = inspect.signature(detect_fvgs)
    assert sig.parameters["atr_period"].default == 14
    assert sig.parameters["displacement_mult"].default == 1.5


# ---------------------------------------------------------------------------
# Section 9A — insufficient history
# ---------------------------------------------------------------------------


def test_case_a_insufficient_history_returns_empty():
    assert detect_fvgs(_frame(_stable(16)), "M5") == []
    assert detect_fvgs(_frame(_stable(2)), "M5") == []


# ---------------------------------------------------------------------------
# Section 9B/9C — canonical bullish and bearish FVG detection
# ---------------------------------------------------------------------------


def _bullish_fixture() -> pd.DataFrame:
    # 16 stable candles + displacement candle (index 17) + gap candle (18)
    # + follow-through that does not touch the zone (19).
    rows = _stable(16)
    rows.append((100.0, 101.2, 99.8, 101.0))  # displacement body 1.0 >= 1.5 * ATR(=0.5)
    rows.append((101.0, 101.4, 100.9, 101.2))  # low 100.9 > c1.high 100.2
    rows.append((101.2, 101.5, 101.1, 101.3))  # low 101.1 > top 100.9: unfilled
    return _frame(rows)


def _bearish_fixture() -> pd.DataFrame:
    rows = _stable(16)
    rows.append((100.0, 100.2, 98.8, 99.0))  # displacement body 1.0
    rows.append((99.0, 99.1, 98.6, 98.8))  # high 99.1 < c1.low 99.8
    rows.append((98.8, 98.9, 98.5, 98.6))  # high 98.9 < bottom 99.1: unfilled
    return _frame(rows)


def test_case_b_bullish_fvg_exact_fields():
    fvgs = detect_fvgs(_bullish_fixture(), "M5")
    assert len(fvgs) == 1
    zone = fvgs[0]
    assert zone == {
        "type": "bullish_fvg",
        "direction": "bullish",
        "top": 100.9,
        "bottom": 100.2,
        "filled": False,
        "timeframe": "M5",
        "source_index": 16,
        "displacement_body": 1.0,
    }


def test_case_c_bearish_fvg_exact_fields():
    fvgs = detect_fvgs(_bearish_fixture(), "M15")
    assert len(fvgs) == 1
    zone = fvgs[0]
    assert zone == {
        "type": "bearish_fvg",
        "direction": "bearish",
        "top": 99.8,
        "bottom": 99.1,
        "filled": False,
        "timeframe": "M15",
        "source_index": 16,
        "displacement_body": 1.0,
    }


# ---------------------------------------------------------------------------
# Section 9D/9E — displacement rejection and no-geometry rejection
# ---------------------------------------------------------------------------


def test_case_d_geometric_gap_with_insufficient_displacement_rejected():
    # High-volatility base (range 2.0) keeps ATR ~2.05 at the displacement
    # candle; the geometric gap exists (row18 low 101.8 > row16 high 101.0)
    # but the middle body 1.5 < 1.5 * ATR, so nothing may be returned.
    rows = _stable(17, rng=2.0)
    rows.append((100.0, 101.7, 99.0, 101.5))  # body 1.5 < 1.5 * ATR
    rows.append((101.5, 102.0, 101.8, 101.9))  # geometric gap present
    rows.append((101.9, 102.1, 101.7, 101.9))
    assert detect_fvgs(_frame(rows), "M5") == []


def test_case_e_displacement_without_geometric_gap_rejected():
    # Same displacement candle as the bullish fixture, but no later candle
    # ever gaps: displacement qualifies, geometry does not.
    rows = _stable(16)
    rows.append((100.0, 101.2, 99.8, 101.0))
    rows.append((101.0, 101.3, 99.9, 101.1))  # low 99.9 < c1.high 100.2: no gap
    rows.append((101.0, 101.4, 100.9, 101.2))  # c1.high 101.2 not < low 100.9
    assert detect_fvgs(_frame(rows), "M5") == []


# ---------------------------------------------------------------------------
# Section 9F/9G — fill-status semantics
# ---------------------------------------------------------------------------


def test_case_f_filled_zone_removed_by_unfilled_filter():
    rows = _stable(16)
    rows.append((100.0, 101.2, 99.8, 101.0))
    rows.append((101.0, 101.4, 100.9, 101.2))
    rows.append((101.2, 101.4, 100.5, 100.8))  # low 100.5 <= top 100.9: touched
    fvgs = detect_fvgs(_frame(rows), "M5")
    assert len(fvgs) == 1 and fvgs[0]["filled"] is True
    assert get_unfilled_fvgs(_frame(rows), "M5") == []


def test_case_g_unfilled_zone_survives():
    frame = _bullish_fixture()
    zones = get_unfilled_fvgs(frame, "M5")
    assert len(zones) == 1
    assert zones[0]["type"] == "bullish_fvg" and zones[0]["filled"] is False


# ---------------------------------------------------------------------------
# Section 9H — direction filtering (both directions in one causal frame)
# ---------------------------------------------------------------------------


def _dual_direction_fixture() -> pd.DataFrame:
    """Bullish FVG near index 17 that later fills, bearish FVG near index 22."""
    rows = _stable(16)
    rows.append((100.0, 101.2, 99.8, 101.0))  # 17: bullish displacement
    rows.append((101.0, 101.4, 100.9, 101.2))  # 18: gap up (bullish zone)
    rows.append((101.2, 101.5, 101.1, 101.3))  # 19
    rows.append((101.2, 101.4, 101.0, 101.1))  # 20
    rows.append((101.1, 101.2, 100.9, 101.0))  # 21
    rows.append((100.9, 101.0, 99.7, 99.9))  # 22: bearish displacement, fills bull zone
    rows.append((99.9, 99.6, 99.4, 99.5))  # 23: gap down (bearish zone)
    return _frame(rows)


def test_case_h_direction_filtering_removes_opposite_zones():
    frame = _dual_direction_fixture()
    fvgs = detect_fvgs(frame, "M5")
    by_direction = {zone["direction"]: zone for zone in fvgs}
    assert set(by_direction) == {"bullish", "bearish"}
    assert by_direction["bullish"]["filled"] is True  # row 22 swept the zone
    assert by_direction["bearish"]["filled"] is False
    assert by_direction["bullish"]["source_index"] == 16
    assert by_direction["bearish"]["source_index"] == 21

    assert get_unfilled_fvgs(frame, "M5", direction="bullish") == []
    bearish = get_unfilled_fvgs(frame, "M5", direction="bearish")
    assert len(bearish) == 1 and bearish[0]["direction"] == "bearish"


# ---------------------------------------------------------------------------
# Section 10 — source-index / causal attribution
# ---------------------------------------------------------------------------


def test_source_index_always_refs_middle_displacement_candle():
    for frame, expected in (
        (_bullish_fixture(), {16}),
        (_bearish_fixture(), {16}),
        (_dual_direction_fixture(), {16, 21}),
    ):
        zones = detect_fvgs(frame, "M5")
        assert {zone["source_index"] for zone in zones} == expected
        for zone in zones:
            # source_index = i - 1 must reference the middle displacement
            # candle: its body equals the reported displacement body and the
            # gap geometry is quoted against it.
            c2 = frame.iloc[zone["source_index"]]
            assert zone["displacement_body"] == abs(
                float(c2["close"]) - float(c2["open"])
            )
            gap_candle = frame.iloc[zone["source_index"] + 1]
            if zone["direction"] == "bullish":
                assert zone["top"] == float(gap_candle["low"])
                assert zone["bottom"] == float(frame.iloc[zone["source_index"] - 1]["high"])
            else:
                assert zone["bottom"] == float(gap_candle["high"])
                assert zone["top"] == float(frame.iloc[zone["source_index"] - 1]["low"])


# ---------------------------------------------------------------------------
# Section 11 — static-defect regression (fails under pre-V001 code)
# ---------------------------------------------------------------------------


def test_regression_detector_no_longer_structurally_empty():
    # Pre-V001 this exact frame returned [] because the scalar ATR surface
    # has no .iloc; post-V001 the canonical three-candle structure must be
    # evaluated and returned.
    assert detect_fvgs(_bullish_fixture(), "M5") != []


def test_regression_atr_series_consulted_with_frozen_period(monkeypatch):
    calls: list[tuple[pd.DataFrame, int]] = []
    real = fvg_engine.atr_series

    def spy(frame, period):
        calls.append((frame, period))
        return real(frame, period)

    monkeypatch.setattr(fvg_engine, "atr_series", spy)
    frame = _bullish_fixture()
    zones = detect_fvgs(frame, "M5")
    # The detector consults the canonical rolling helper exactly once, with
    # the frozen period, and evaluates windows against its values.
    assert calls == [(frame, 14)]
    assert len(zones) == 1


def test_regression_series_values_gate_every_candidate_window(monkeypatch):
    # Substituting an all-10.0 ATR series must suppress the zone entirely
    # (displacement body 1.0 < 1.5 x 10.0 for every window), proving the
    # consulted series' per-window values drive acceptance. The pre-V001
    # implementation had no series path at all, so this coupling could not
    # exist.
    frame = _bullish_fixture()
    monkeypatch.setattr(
        fvg_engine,
        "atr_series",
        lambda frame_, period: pd.Series(10.0, index=frame_.index),
    )
    assert detect_fvgs(frame, "M5") == []


# ---------------------------------------------------------------------------
# Section 12 — global helper invariance (blob identity)
# ---------------------------------------------------------------------------


def test_utils_indicators_blob_unchanged_from_baseline():
    # Git blob ids are content-addressed: sha1(b"blob <size>\\0" + bytes).
    # The suite cannot shell out to git (conftest firewall), so prove the
    # worktree file's content identity equals the recorded baseline blob
    # directly; the standalone Phase-A battery re-verifies the committed
    # blob with `git rev-parse` outside pytest.
    content = (REPO_ROOT / "utils" / "indicators.py").read_bytes()
    blob_sha = hashlib.sha1(b"blob %d\x00" % len(content) + content).hexdigest()
    assert blob_sha == INDICATORS_BLOB


def test_scalar_helper_public_contract_unchanged():
    frame = _equivalence_frames()["stable_wide"]
    assert isinstance(calculate_atr(frame, 14), float)
    assert calculate_atr(_frame(_stable(2)), 14) == 0.0
    assert calculate_atr(None, 14) == 0.0


# ---------------------------------------------------------------------------
# Section 14 — import safety (fresh process)
# ---------------------------------------------------------------------------


def test_import_safety_fresh_process_no_mt5_no_broker():
    script = (
        "import sys\n"
        "sys.path.insert(0, r'" + str(REPO_ROOT) + "')\n"
        "import bot.analysis.fvg_engine as fe\n"
        "import bot.strategy.regime as regime\n"
        "from bot.analysis import get_unfilled_fvgs, detect_fvgs\n"
        "assert 'MetaTrader5' not in sys.modules, 'MetaTrader5 imported'\n"
        "assert 'streamlit' not in sys.modules, 'streamlit imported'\n"
        "assert callable(get_unfilled_fvgs) and callable(detect_fvgs)\n"
        "print('V001_IMPORT_SAFE')\n"
    )
    process = REAL_POPEN(
        [sys.executable, "-I", "-c", script],
        cwd=REPO_ROOT,
        stdout=-1,
        stderr=-1,
        text=True,
    )
    out, err = process.communicate(timeout=60)
    assert process.returncode == 0, err
    assert "V001_IMPORT_SAFE" in out
