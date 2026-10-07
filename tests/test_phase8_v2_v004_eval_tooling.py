# -*- coding: utf-8 -*-
"""Phase-B synthetic tests for the frozen V004 Fold-01 measurement tooling.

Synthetic fixtures only — no Fold-01 empirical data, no historical store,
no external evidence. Proves, before any empirical access:

* store boundary + authorized-store validation + holdout/2025+ path rejection;
* store-compatibility assertion fails closed on payload gaps and accepts
  complete causal inputs;
* banned metric keys (P&L, win rate, drawdown, Sharpe, counterfactuals) fail closed;
* aggregate + surface verification + funnel consistency + setup ID reconciliation;
* strict V003 baseline candidate preservation (zero lost candidates);
* candidate source breakdown (V003_BASELINE vs V004_DIRECTIONAL_FALLBACK);
* bound specification SHA-256 matches Phase-A preregistration;
* zero hardcoded candidate numbers encoded as test oracle predictions.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from backtests import phase8_v2_variant_v004_eval as v004_eval
from bot.strategy.variant_v004 import (
    SPEC_SHA256 as V004_SPEC_SHA256,
    V004_ID,
    H009_ID,
    V004_SOURCE_V003_BASELINE,
    V004_SOURCE_DIRECTIONAL_FALLBACK,
    V004_SOURCE_NONE,
)

UTC = timezone.utc
REPO_ROOT = Path(__file__).resolve().parents[1]


def _store_identity() -> dict[str, Any]:
    return {
        "fold_id": "fold-01",
        "decision_timeframe": "M5",
        "evaluation_start_ms": v004_eval.FOLD01_START_MS,
        "evaluation_end_ms": v004_eval.FOLD01_END_MS,
        "coverage": "full",
    }


# ===========================================================================
# 1. Store Boundary and Path Validation Tests
# ===========================================================================


def test_v004_spec_sha256_binding() -> None:
    """Tooling SPEC_SHA256 must match the SHA-256 of docs/PHASE8_V2_VARIANT_V004.md."""
    spec_path = REPO_ROOT / "docs" / "PHASE8_V2_VARIANT_V004.md"
    assert spec_path.is_file(), f"{spec_path} must exist"
    actual_sha = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    assert v004_eval.SPEC_SHA256 == actual_sha
    assert V004_SPEC_SHA256 == actual_sha


def test_store_boundary_refuses_wrong_fold_and_coverage() -> None:
    """Store boundary check must fail closed on wrong fold or incomplete coverage."""
    v004_eval.check_store_boundary(_store_identity())
    bad_fold = dict(_store_identity(), fold_id="fold-02")
    with pytest.raises(Exception):
        v004_eval.check_store_boundary(bad_fold)
    bad_cov = dict(_store_identity(), coverage="partial")
    with pytest.raises(Exception):
        v004_eval.check_store_boundary(bad_cov)
    bad_start = dict(_store_identity(), evaluation_start_ms=0)
    with pytest.raises(Exception):
        v004_eval.check_store_boundary(bad_start)


def test_validate_authorized_store_path_accepts_canonical_fold01() -> None:
    """Canonical authorized Fold-01 store basename must pass path validation."""
    v004_eval.validate_authorized_store_path("C:/data/stores/fold-01-a8b406884ab3525a")
    v004_eval.validate_authorized_store_path(Path("C:/data/stores/fold-01-a8b406884ab3525a"))


def test_validate_authorized_store_path_refuses_holdout() -> None:
    """Holdout and final-validation paths must fail closed."""
    with pytest.raises(v004_eval.BoundaryError, match="holdout"):
        v004_eval.validate_authorized_store_path("C:/data/holdout/store")
    with pytest.raises(v004_eval.BoundaryError, match="holdout"):
        v004_eval.validate_authorized_store_path("C:/data/final_validation/store")


def test_validate_authorized_store_path_refuses_post_2024() -> None:
    """Paths containing 2025+ markers must fail closed."""
    with pytest.raises(v004_eval.BoundaryError, match="post-2024"):
        v004_eval.validate_authorized_store_path("C:/data/stores/2025/fold-01-a8b406884ab3525a")
    with pytest.raises(v004_eval.BoundaryError, match="post-2024"):
        v004_eval.validate_authorized_store_path("C:/data/stores/2025-01-01/store")
    with pytest.raises(v004_eval.BoundaryError, match="post-2024"):
        v004_eval.validate_authorized_store_path("C:/data/stores/year=2025/store")


def test_validate_authorized_store_path_refuses_unauthorized_folds() -> None:
    """Unauthorized fold numbers must fail closed."""
    with pytest.raises(v004_eval.BoundaryError, match="unauthorized store basename refused"):
        v004_eval.validate_authorized_store_path("C:/data/stores/fold-02-abc123")
    with pytest.raises(v004_eval.BoundaryError, match="unauthorized store basename refused"):
        v004_eval.validate_authorized_store_path("C:/data/stores/fold-03-def456")


# ===========================================================================
# 2. Store Compatibility Tests
# ===========================================================================


def test_store_compatibility_fails_closed() -> None:
    """Missing gate payload or required fields must raise StoreCompatibilityError."""
    # Missing payload
    s1 = SimpleNamespace(gate_payload=None)
    with pytest.raises(v004_eval.StoreCompatibilityError):
        v004_eval.assert_store_semantic_compatibility(s1)

    # Undecodable payload
    s2 = SimpleNamespace(gate_payload="invalid json {")
    with pytest.raises(v004_eval.StoreCompatibilityError):
        v004_eval.assert_store_semantic_compatibility(s2)

    # Missing required field
    s3 = SimpleNamespace(gate_payload='{"htf_bias": "bullish"}')
    with pytest.raises(v004_eval.StoreCompatibilityError, match="lacks V004-required"):
        v004_eval.assert_store_semantic_compatibility(s3)


# ===========================================================================
# 3. Metric Sanitization Tests
# ===========================================================================


def test_banned_metrics_rejected() -> None:
    """Prohibited profitability and counterfactual keys must raise RuntimeError."""
    banned_keys = ["pnl", "profit", "win_rate", "expectancy", "drawdown", "sharpe", "returns", "closed_trades"]
    for key in banned_keys:
        bad_doc = {"clean_field": 123, key: 456}
        with pytest.raises(RuntimeError):
            v004_eval._reject_banned_metrics(bad_doc)

    # Clean doc passes
    clean_doc = {
        "candidate_ready": 85,
        "candidate_rate": 0.16,
        "v003_baseline_reconciliation": {"all_v003_candidates_preserved": True},
    }
    v004_eval._reject_banned_metrics(clean_doc)


# ===========================================================================
# 4. Aggregation and Baseline Preservation Tests
# ===========================================================================


def make_mock_observation(
    decision_id: str,
    *,
    gate11_passed: bool = True,
    strategy_eligible: bool = True,
    v003_ready: bool = False,
    v004_ready: bool = False,
    v004_source: str = V004_SOURCE_NONE,
    side: str = "LONG",
    direction: str | None = None,
) -> dict[str, Any]:
    return {
        "decision_id": decision_id,
        "available_at_ms": 1714557600000,
        "v004_pair_state": "ACTIVE" if gate11_passed else "MITIGATED",
        "v004_pair_reason": "canonical_confirmed",
        "v004_structurally_active": gate11_passed,
        "v004_side": side,
        "v004_block_id": f"ob_{decision_id}",
        "v004_age_bars": 5,
        "v004_final_fvg_associated": True,
        "v004_temporal_fvg_evidence": False,
        "v004_fvg_evidence": True,
        "v004_fvg_evidence_source": "FINAL_SURFACE",
        "v004_gate11_score": {"score": 8 if gate11_passed else 6, "passes_threshold": gate11_passed},
        "v004_gate11_passed": gate11_passed,
        "v004_strategy_eligible": strategy_eligible,
        "v003_setup_id": f"s8n1_{decision_id}" if v003_ready else None,
        "v003_entry": {"direction": direction or "buy"} if v003_ready else None,
        "v003_entry_ready": v003_ready,
        "v004_setup_id": f"s8n1_{decision_id}" if v004_ready else None,
        "v004_entry": {"direction": direction or "buy"} if v004_ready else None,
        "v004_entry_ready": v004_ready,
        "v004_entry_source": v004_source,
        "v004_entry_direction": direction or ("buy" if v004_ready else None),
    }


def test_synthetic_aggregation_and_funnel_consistency() -> None:
    """Synthetic observations must aggregate with exact funnel and baseline preservation."""
    observations = [
        # 2 failing gate 11
        make_mock_observation("d01", gate11_passed=False, strategy_eligible=False),
        make_mock_observation("d02", gate11_passed=False, strategy_eligible=False),
        # 2 passing gate 11, failing strategy
        make_mock_observation("d03", gate11_passed=True, strategy_eligible=False),
        make_mock_observation("d04", gate11_passed=True, strategy_eligible=False),
        # 3 V003 baseline ready candidates
        make_mock_observation("d05", v003_ready=True, v004_ready=True, v004_source=V004_SOURCE_V003_BASELINE, direction="buy"),
        make_mock_observation("d06", v003_ready=True, v004_ready=True, v004_source=V004_SOURCE_V003_BASELINE, direction="buy"),
        make_mock_observation("d07", v003_ready=True, v004_ready=True, v004_source=V004_SOURCE_V003_BASELINE, direction="sell", side="SHORT"),
        # 2 V004 directional fallback candidates
        make_mock_observation("d08", v003_ready=False, v004_ready=True, v004_source=V004_SOURCE_DIRECTIONAL_FALLBACK, direction="buy"),
        make_mock_observation("d09", v003_ready=False, v004_ready=True, v004_source=V004_SOURCE_DIRECTIONAL_FALLBACK, direction="sell", side="SHORT"),
        # 1 passing strategy, not ready under either
        make_mock_observation("d10", v003_ready=False, v004_ready=False, v004_source=V004_SOURCE_NONE),
    ]

    agg = v004_eval.aggregate_v004(observations)

    # 1. Structural pair surface
    surf = agg["V004_structural_pair_surface"]
    assert surf["gate11_entrants_observed"] == 10
    assert surf["v004_structurally_active_count"] == 8

    # 2. Funnel
    funnel = agg["V004_variant_funnel"]
    assert funnel["gate_11_v004"]["entered"] == 10
    assert funnel["gate_11_v004"]["passed"] == 8
    assert funnel["canonical_strategy_v004"]["entered"] == 8
    assert funnel["canonical_strategy_v004"]["passed"] == 6  # d05, d06, d07, d08, d09, d10
    assert funnel["gate_12_13_rr_entry_v004"]["entered"] == 6
    assert funnel["gate_12_13_rr_entry_v004"]["passed"] == 5  # d05, d06, d07, d08, d09

    # 3. Candidates
    cand = agg["candidate_surface"]
    assert cand["candidate_ready"] == 5
    assert cand["candidate_v003_baseline_count"] == 3
    assert cand["candidate_v004_directional_fallback_count"] == 2
    assert cand["candidate_long_count"] == 3
    assert cand["candidate_short_count"] == 2
    assert cand["unique_candidate_setup_ids"] == 5
    assert cand["duplicate_candidate_setup_id_occurrences"] == 0

    # 4. Baseline reconciliation
    rec = agg["v003_baseline_reconciliation"]
    assert rec["v003_baseline_candidate_count"] == 3
    assert rec["all_v003_candidates_preserved"] is True
    assert rec["v003_fallback_recovery_count"] == 2

    # 5. Classification
    assert agg["success_classification"]["classification"] == "OPPORTUNITY_INSUFFICIENT"


def test_v003_baseline_candidate_loss_raises_error() -> None:
    """If any V003 candidate is lost in V004, aggregate_v004 must fail closed."""
    observations = [
        # d01 was ready in V003, but not ready in V004
        make_mock_observation("d01", v003_ready=True, v004_ready=False, v004_source=V004_SOURCE_NONE),
    ]
    with pytest.raises(v004_eval.V004EvalError, match="lost in V004"):
        v004_eval.aggregate_v004(observations)


def test_opportunity_classification_thresholds() -> None:
    """Classification must follow preregistered rules: >=90 SUFFICIENT, >0 INSUFFICIENT, 0 NO_CANDIDATES."""
    # 90 candidates -> SUFFICIENT
    obs_90 = [
        make_mock_observation(f"d{i}", v003_ready=True, v004_ready=True, v004_source=V004_SOURCE_V003_BASELINE)
        for i in range(90)
    ]
    agg_90 = v004_eval.aggregate_v004(obs_90)
    assert agg_90["success_classification"]["classification"] == "OPPORTUNITY_SUFFICIENT"

    # 0 candidates -> NO_CANDIDATES
    obs_0 = [make_mock_observation("d01", v003_ready=False, v004_ready=False)]
    agg_0 = v004_eval.aggregate_v004(obs_0)
    assert agg_0["success_classification"]["classification"] == "NO_CANDIDATES"


# ===========================================================================
# 5. Output Document Surface Validation Tests
# ===========================================================================


def test_assert_expected_surfaces_validates_required_structure() -> None:
    """Document must satisfy all root keys and invariant checks."""
    doc = {
        "variant_id": V004_ID,
        "hypothesis_id": H009_ID,
        "charter_id": v004_eval.CHARTER_ID,
        "specification_document": v004_eval.SPECIFICATION_DOCUMENT,
        "specification_sha256": v004_eval.SPEC_SHA256,
        "classification": v004_eval.CLASSIFICATION,
        "provenance": {},
        "fold01_boundary": ["2024-04-01T00:00:00Z", "2024-06-08T00:00:00Z"],
        "decision_accounting": {},
        "gate_funnel": {},
        "V004_structural_pair_surface": {"gate11_entrants_observed": 10},
        "V004_variant_funnel": {
            "gate_11_v004": {"entered": 10, "passed": 8, "failed": 2},
            "canonical_strategy_v004": {"entered": 8, "passed": 6, "failed": 2},
            "gate_12_13_rr_entry_v004": {"entered": 6, "passed": 5, "failed": 1},
        },
        "candidate_surface": {
            "candidate_ready": 5,
            "setup_id_reconciliation": {"unique_plus_duplicates_equals_candidate_ready": True},
        },
        "v003_baseline_reconciliation": {"all_v003_candidates_preserved": True},
        "success_classification": {"classification": "OPPORTUNITY_INSUFFICIENT"},
        "one_concept_rule": "directional authority unification",
        "canonical_state_invariance_verified": True,
        "liquidity_rules_invariance_verified": True,
    }

    # Clean document passes
    v004_eval.assert_expected_surfaces(doc)

    # Broken funnel chain fails
    broken_funnel = copy.deepcopy(doc)
    broken_funnel["V004_variant_funnel"]["canonical_strategy_v004"]["passed"] = 9  # > gate_11 passed (8)
    with pytest.raises(v004_eval.V004EvalError, match="funnel chain violated"):
        v004_eval.assert_expected_surfaces(broken_funnel)

    # Missing root key fails
    missing_key = copy.deepcopy(doc)
    del missing_key["v003_baseline_reconciliation"]
    with pytest.raises(v004_eval.V004EvalError, match="missing required root key"):
        v004_eval.assert_expected_surfaces(missing_key)

# ===========================================================================
# TC001 Additional Sealed-Baseline and Execution-Safety Tests
# ===========================================================================


def make_synthetic_sealed_v003_doc(
    *,
    entrants: int = 526,
    gate11_pass: int = 138,
    strat_pass: int = 110,
    cand_ready: int = 81,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a synthetic sealed V003 R001 document matching exact prior schema."""
    if candidates is None:
        candidates = [
            {
                "decision_id": f"d_{i:03d}",
                "setup_id": f"s8n1_{i:03d}",
                "side": "LONG",
                "age_bars": 5,
                "fvg_evidence_source": "FINAL_SURFACE",
                "exact_overlap_descriptive": True,
                "temporal_fvg_offset_bars": None,
                "entry": {
                    "direction": "buy",
                    "entry_mode": "conservative",
                    "entry_type": "conservative",
                    "market_entry": 2400.0,
                    "pullback_entry": 2395.0,
                    "score": 8,
                },
            }
            for i in range(cand_ready)
        ]

    return {
        "variant_id": "phase6-development-v2-V003",
        "V003_variant_funnel": {
            "gate_11_v003": {
                "entered": entrants,
                "passed": gate11_pass,
                "failed": entrants - gate11_pass,
            },
            "canonical_strategy_v003": {
                "entered": gate11_pass,
                "passed": strat_pass,
                "failed": gate11_pass - strat_pass,
            },
            "gate_12_13_rr_entry_v003": {
                "entered": strat_pass,
                "passed": cand_ready,
                "failed": strat_pass - cand_ready,
            },
        },
        "candidate_surface": {
            "candidate_ready": cand_ready,
            "unique_candidate_setup_ids": len(set(c["setup_id"] for c in candidates)),
            "duplicate_candidate_setup_id_occurrences": len(candidates) - len(set(c["setup_id"] for c in candidates)),
            "candidates": candidates,
        },
    }


def make_matching_reproduced_observations(
    sealed_doc: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate matching reproduced observations for all 526 entrants."""
    candidates = sealed_doc["candidate_surface"]["candidates"]
    observations = []

    # 81 ready candidate observations
    for c in candidates:
        d_id = c["decision_id"]
        s_id = c["setup_id"]
        entry_copy = dict(c["entry"])
        observations.append(
            {
                "decision_id": d_id,
                "available_at_ms": 1714557600000,
                "v004_pair_state": "ACTIVE",
                "v004_pair_reason": "canonical_confirmed",
                "v004_structurally_active": True,
                "v004_side": "LONG",
                "v004_block_id": f"ob_{d_id}",
                "v004_age_bars": 5,
                "v004_final_fvg_associated": True,
                "v004_temporal_fvg_evidence": False,
                "v004_fvg_evidence": True,
                "v004_fvg_evidence_source": "FINAL_SURFACE",
                "v004_gate11_score": {"score": 8, "passes_threshold": True},
                "v004_gate11_passed": True,
                "v004_strategy_eligible": True,
                "v003_setup_id": s_id,
                "v003_entry": entry_copy,
                "v003_entry_ready": True,
                "v004_setup_id": s_id,
                "v004_entry": entry_copy,
                "v004_entry_ready": True,
                "v004_entry_source": V004_SOURCE_V003_BASELINE,
                "v004_entry_direction": "buy",
            }
        )

    # 29 passing strategy, not ready
    for i in range(29):
        observations.append(
            make_mock_observation(f"d_strat_pass_{i:02d}", gate11_passed=True, strategy_eligible=True, v003_ready=False, v004_ready=False)
        )

    # 28 passing gate 11, failing strategy
    for i in range(28):
        observations.append(
            make_mock_observation(f"d_g11_pass_{i:02d}", gate11_passed=True, strategy_eligible=False, v003_ready=False, v004_ready=False)
        )

    # 388 failing gate 11
    for i in range(388):
        observations.append(
            make_mock_observation(f"d_fail_g11_{i:03d}", gate11_passed=False, strategy_eligible=False, v003_ready=False, v004_ready=False)
        )

    return observations


def test_sealed_v003_exact_candidate_pairs_success() -> None:
    """Section 15-18 & 32: When reproduced multiset matches sealed V003, reconciliation succeeds."""
    sealed = make_synthetic_sealed_v003_doc()
    obs = make_matching_reproduced_observations(sealed)

    rec = v004_eval.reconcile_sealed_v003_baseline(
        sealed,
        obs,
        sealed_artifact_path="synthetic/path/v003_result.json",
        sealed_sha256="abc123sha",
        sealed_byte_count=45221,
    )

    assert rec["status"] == v004_eval.STATUS_SEALED_V003_RECONCILED
    assert rec["upstream_count_reconciliation"]["all_counts_reconciled"] is True
    assert rec["candidate_identity_reconciliation"]["multiset_identity_equal"] is True
    assert rec["candidate_entry_object_reconciliation"]["all_entry_objects_identical"] is True


def test_sealed_v003_candidate_pairs_failure_cases() -> None:
    """Section 32: Five independent failure cases for candidate multiset reconciliation."""
    sealed = make_synthetic_sealed_v003_doc()

    # 1. Changed decision ID
    obs1 = make_matching_reproduced_observations(sealed)
    obs1[0]["decision_id"] = "d_altered"
    with pytest.raises(v004_eval.V004BaselineReproductionError, match="multiset mismatch"):
        v004_eval.reconcile_sealed_v003_baseline(sealed, obs1)

    # 2. Changed setup ID
    obs2 = make_matching_reproduced_observations(sealed)
    obs2[0]["v003_setup_id"] = "s8n1_altered"
    with pytest.raises(v004_eval.V004BaselineReproductionError, match="multiset mismatch"):
        v004_eval.reconcile_sealed_v003_baseline(sealed, obs2)

    # 3. Missing candidate (80 candidates instead of 81)
    obs3 = make_matching_reproduced_observations(sealed)
    obs3[0]["v003_entry_ready"] = False
    with pytest.raises(v004_eval.V004BaselineReproductionError, match="counts mismatch"):
        v004_eval.reconcile_sealed_v003_baseline(sealed, obs3)

    # 4. Extra candidate (82 candidates instead of 81)
    obs4 = make_matching_reproduced_observations(sealed)
    # Turn one of the non-ready ones into ready
    obs4[81]["v003_entry_ready"] = True
    obs4[81]["v003_setup_id"] = "s8n1_extra"
    obs4[81]["v003_entry"] = {"direction": "buy"}
    with pytest.raises(v004_eval.V004BaselineReproductionError, match="counts mismatch"):
        v004_eval.reconcile_sealed_v003_baseline(sealed, obs4)

    # 5. Duplicate setup ID in reproduced candidates
    obs5 = make_matching_reproduced_observations(sealed)
    obs5[1]["v003_setup_id"] = obs5[0]["v003_setup_id"]
    with pytest.raises(v004_eval.V004BaselineReproductionError, match="Duplicate setup_id"):
        v004_eval.reconcile_sealed_v003_baseline(sealed, obs5)


def test_sealed_v003_entry_object_reconciliation_failures() -> None:
    """Section 33: Single-field entry object modifications fail closed."""
    sealed = make_synthetic_sealed_v003_doc()

    field_modifications = [
        ("direction", "sell"),
        ("entry_type", "market"),
        ("market_entry", 2405.0),
        ("pullback_entry", 2390.0),
        ("score", 10),
    ]

    for field_name, bad_value in field_modifications:
        obs = make_matching_reproduced_observations(sealed)
        obs[0]["v003_entry"][field_name] = bad_value
        with pytest.raises(v004_eval.V004BaselineReproductionError, match="entry-object mismatch"):
            v004_eval.reconcile_sealed_v003_baseline(sealed, obs)


def test_same_count_different_identities_fails() -> None:
    """Section 34: Exactly 81 candidates with different identities must fail (preventing 81 == 81 false positive)."""
    sealed = make_synthetic_sealed_v003_doc()
    obs = make_matching_reproduced_observations(sealed)

    # Change all candidate IDs to a different 81-set
    for i in range(81):
        obs[i]["decision_id"] = f"d_alt_{i:03d}"
        obs[i]["v003_setup_id"] = f"s8n1_alt_{i:03d}"

    with pytest.raises(v004_eval.V004BaselineReproductionError, match="multiset mismatch"):
        v004_eval.reconcile_sealed_v003_baseline(sealed, obs)


def test_sealed_prior_artifact_loader_failures(tmp_path: Path) -> None:
    """Section 35: Prior artifact loader fails independently on wrong SHA, wrong bytes, or malformed JSON."""
    good_doc = {"test": 123}
    good_json = json.dumps(good_doc)
    good_bytes = good_json.encode("utf-8")
    good_len = len(good_bytes)
    good_sha = hashlib.sha256(good_bytes).hexdigest()

    good_file = tmp_path / "good.json"
    good_file.write_bytes(good_bytes)

    # 1. Successful load with matching params
    doc, length, sha = v004_eval.load_and_verify_sealed_v003_result(
        good_file, expected_sha256=good_sha, expected_bytes=good_len
    )
    assert doc == good_doc
    assert length == good_len
    assert sha == good_sha

    # 2. Byte count mismatch
    with pytest.raises(v004_eval.V004BaselineReproductionError, match="byte count mismatch"):
        v004_eval.load_and_verify_sealed_v003_result(
            good_file, expected_sha256=good_sha, expected_bytes=good_len + 1
        )

    # 3. SHA-256 mismatch
    with pytest.raises(v004_eval.V004BaselineReproductionError, match="SHA-256 mismatch"):
        v004_eval.load_and_verify_sealed_v003_result(
            good_file, expected_sha256="0" * 64, expected_bytes=good_len
        )

    # 4. Malformed JSON
    bad_json_file = tmp_path / "bad.json"
    bad_bytes = b"{ invalid json"
    bad_json_file.write_bytes(bad_bytes)
    with pytest.raises(v004_eval.V004BaselineReproductionError, match="malformed JSON"):
        v004_eval.load_and_verify_sealed_v003_result(
            bad_json_file,
            expected_sha256=hashlib.sha256(bad_bytes).hexdigest(),
            expected_bytes=len(bad_bytes),
        )


def test_existing_result_or_temp_refused_before_store_load(tmp_path: Path) -> None:
    """Section 23 & 36: If output or temp target exists, CLI fails before loading store."""
    from unittest.mock import patch

    out_file = tmp_path / "output.json"
    temp_file = out_file.with_suffix(".tmp")
    store_dir = tmp_path / "fold-01-a8b406884ab3525a"
    store_dir.mkdir()
    v003_file = tmp_path / "v003.json"
    v003_file.write_bytes(b"dummy")

    with patch("bot.validation.market_feature_store.load_feature_store") as mock_load:
        # Case A: output target exists
        out_file.write_text("existing")
        with pytest.raises(v004_eval.V004ResultAlreadyExistsError, match="Output target already exists"):
            v004_eval.main([
                "--store", str(store_dir),
                "--output", str(out_file),
                "--v003-result", str(v003_file),
                "--implementation-commit", "0" * 40,
                "--tooling-commit", "1" * 40,
            ])
        mock_load.assert_not_called()

        # Case B: temp target exists
        out_file.unlink()
        temp_file.write_text("existing temp")
        with pytest.raises(v004_eval.V004ResultAlreadyExistsError, match="Stale temporary target already exists"):
            v004_eval.main([
                "--store", str(store_dir),
                "--output", str(out_file),
                "--v003-result", str(v003_file),
                "--implementation-commit", "0" * 40,
                "--tooling-commit", "1" * 40,
            ])
        mock_load.assert_not_called()


def test_strict_store_basename_refusal() -> None:
    """Section 24 & 37: Basename must be strictly fold-01-a8b406884ab3525a."""
    # Canonical basename passes
    v004_eval.validate_authorized_store_path("C:/data/stores/fold-01-a8b406884ab3525a")

    # Arbitrary basename fails closed
    with pytest.raises(v004_eval.BoundaryError, match="unauthorized store basename refused"):
        v004_eval.validate_authorized_store_path("C:/data/stores/copied-authorized-store")

    # Other folds fail closed
    with pytest.raises(v004_eval.BoundaryError, match="unauthorized store basename refused"):
        v004_eval.validate_authorized_store_path("C:/data/stores/fold-02-a8b406884ab3525a")


def test_cli_execution_order_with_mocks(tmp_path: Path) -> None:
    """Section 38: Using mocks only, prove future CLI main execution order."""
    from unittest.mock import MagicMock, call, patch

    call_order = []

    out_file = tmp_path / "fresh_output.json"
    store_dir = tmp_path / "fold-01-a8b406884ab3525a"
    store_dir.mkdir()
    v003_file = tmp_path / "v003_result.json"
    v003_file.write_bytes(b"dummy_v003")

    def mock_validate_path(path):
        call_order.append("validate_path")

    def mock_load_v003(path, **kwargs):
        call_order.append("load_v003")
        return {"synthetic": True}, 45221, "dummy_sha"

    def mock_load_store(path, verify_rows=True):
        call_order.append("load_store")
        mock_s = MagicMock()
        mock_s.identity = _store_identity()
        return mock_s

    def mock_run_v004(store, **kwargs):
        call_order.append("run_v004")
        return {"result": True}, b'{"result": true}\n'

    with patch.object(v004_eval, "validate_authorized_store_path", side_effect=mock_validate_path), \
         patch.object(v004_eval, "load_and_verify_sealed_v003_result", side_effect=mock_load_v003), \
         patch("bot.validation.market_feature_store.load_feature_store", side_effect=mock_load_store), \
         patch.object(v004_eval, "run_v004", side_effect=mock_run_v004):

        res = v004_eval.main([
            "--store", str(store_dir),
            "--output", str(out_file),
            "--v003-result", str(v003_file),
            "--implementation-commit", "a" * 40,
            "--tooling-commit", "b" * 40,
        ])
        assert res == 0
        call_order.append("atomic_write")

    assert call_order == [
        "validate_path",
        "load_v003",
        "load_store",
        "run_v004",
        "atomic_write",
    ]
    assert out_file.is_file()
