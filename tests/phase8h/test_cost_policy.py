"""Phase 8H focused tests: frozen development transaction-cost policy.

Synthetic fixtures only — no network, no MT5, no strategy evaluation, no
holdout access.  The frozen policy under test is inactive by construction;
``ACTIVE`` is not a representable state.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.acquisition.evidence_store import (  # noqa: E402
    EvidenceStoreError,
    build_evidence_package,
    load_evidence_package,
    publish_evidence_package,
)
from bot.validation import cost_policy as cp  # noqa: E402

# A synthetic SHA-256 binding value (fixture constant; matches nothing real).
SYNTH_SUPPORT_HASH = "3" * 64


@pytest.fixture()
def temp_data_root(tmp_path: Path) -> Path:
    """Minimal synthetic data root satisfying build_cost_policy bindings."""
    derived = tmp_path / "derived" / "derived-candles-2024-v1-20260911T195553Z"
    derived.mkdir(parents=True)
    (derived / "manifest.json").write_text(
        json.dumps(
            {
                "year_package_id": "synthetic-year-package",
                "source_canonical_sha256": "a" * 64,
                "source_row_count": 12345,
            }
        ),
        encoding="utf-8",
    )
    dxy = tmp_path / "dxy" / "dxy-development-2024-v1-20260912T091410.712364Z"
    dxy.mkdir(parents=True)
    (dxy / "manifest.json").write_text(
        json.dumps(
            {
                "package_id": "dxy-development-2024-v1-synthetic",
                "causal_dxy": {
                    "canonical_content_sha256": "b" * 64,
                    "record_count": 100,
                },
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def policy(temp_data_root: Path) -> dict:
    return cp.build_cost_policy(
        data_root=temp_data_root,
        broker_support_content_sha256=SYNTH_SUPPORT_HASH,
    )


# ---------------------------------------------------------------------------
# Determinism and fingerprint
# ---------------------------------------------------------------------------


def test_policy_build_is_deterministic(temp_data_root: Path) -> None:
    first = cp.build_cost_policy(
        data_root=temp_data_root, broker_support_content_sha256=SYNTH_SUPPORT_HASH
    )
    second = cp.build_cost_policy(
        data_root=temp_data_root, broker_support_content_sha256=SYNTH_SUPPORT_HASH
    )
    assert first == second
    assert first["policy_fingerprint"] == second["policy_fingerprint"]


def test_policy_fingerprint_excludes_itself(policy: dict) -> None:
    assert cp.policy_fingerprint(policy) == policy["policy_fingerprint"]
    altered = json.loads(json.dumps(policy))
    altered["policy_fingerprint"] = "0" * 64
    assert cp.policy_fingerprint(altered) == policy["policy_fingerprint"]


def test_fingerprint_binds_content_not_env(policy: dict, temp_data_root: Path) -> None:
    tampered = json.loads(json.dumps(policy))
    tampered["cost_components"]["commission"]["amount"] = 5
    assert cp.policy_fingerprint(tampered) != policy["policy_fingerprint"]


# ---------------------------------------------------------------------------
# Frozen components
# ---------------------------------------------------------------------------


def test_commission_zero_is_evidence_bound(policy: dict) -> None:
    commission = policy["cost_components"]["commission"]
    assert commission["mode"] == "NONE"
    assert commission["amount"] == 0
    assert commission["currency"] == "USD"
    assert commission["per_side_charge"] == 0
    assert commission["round_turn_charge"] == 0
    assert commission["minimum_charge"] == 0
    assert commission["effective_interval_established"] is False
    assert commission["final_validation_eligible"] is False


def test_spread_requires_observed_bid_ask(policy: dict) -> None:
    spread = policy["cost_components"]["spread"]
    assert spread["basis"] == "OBSERVED_EMPIRICAL_BID_ASK_ONLY"
    assert spread["fixed_spread_substitution_prohibited"] is True
    assert spread["forward_fill_prohibited"] is True


def test_fixed_spread_substitution_is_rejected(policy: dict) -> None:
    tampered = json.loads(json.dumps(policy))
    tampered["cost_components"]["spread"]["basis"] = "FIXED_SPREAD"
    tampered["policy_fingerprint"] = cp.policy_fingerprint(tampered)  # re-signed
    with pytest.raises(cp.CostPolicyError, match="observed bid/ask"):
        cp.verify_cost_policy(tampered)


def test_swap_unit_conflict_preserved_and_conversion_prohibited(policy: dict) -> None:
    swap = policy["cost_components"]["swap"]
    assert swap["email_reference"]["long_usd_per_lot_per_day"] == -3.85
    assert swap["email_reference"]["short_usd_per_lot_per_day"] == -0.25
    assert swap["screenshot_reference"]["long_points_per_lot"] == -534.9
    assert swap["screenshot_reference"]["short_points_per_lot"] is None
    assert swap["unit_conflict_preserved"] is True
    assert swap["conversion_prohibited"] is True
    assert swap["averaging_prohibited"] is True
    assert swap["single_source_selection_prohibited"] is True
    assert swap["historical_2024_values"] is None


def test_no_historical_swap_value_may_appear(policy: dict) -> None:
    tampered = json.loads(json.dumps(policy))
    tampered["cost_components"]["swap"]["historical_2024_values"] = {"long": -3.85}
    tampered["policy_fingerprint"] = cp.policy_fingerprint(tampered)  # re-signed
    with pytest.raises(cp.CostPolicyError, match="historical 2024"):
        cp.verify_cost_policy(tampered)


def test_unit_arithmetic_is_recorded_not_converted(policy: dict) -> None:
    # The policy stores the conflict verbatim; the documented arithmetic
    # (1 pip = 10 points; 1 point per lot = 0.10 USD) is conversion context,
    # never an equivalence claim between the two sources.
    swap = policy["cost_components"]["swap"]
    assert "equivalence" not in json.dumps(swap).lower().replace(
        "no official rule was provided", ""
    )
    assert swap["email_reference"]["classification"] == "CURRENT_SUPPORT_REFERENCE"
    assert (
        swap["screenshot_reference"]["classification"] == "CURRENT_ONLY_NOT_HISTORICAL"
    )


# ---------------------------------------------------------------------------
# Scenario ladders
# ---------------------------------------------------------------------------


def test_swap_scenario_order_and_values(policy: dict) -> None:
    scenarios = policy["swap_scenarios"]
    assert [s["scenario_id"] for s in scenarios] == list(cp.SWAP_SCENARIO_ORDER)
    by_id = {s["scenario_id"]: s for s in scenarios}
    assert by_id["SWAP_NO_OVERNIGHT_EXPOSURE_DIAGNOSTIC"][
        "long_usd_per_lot_per_day"
    ] == 0.0
    assert by_id["SWAP_EMAIL_REFERENCE"]["long_usd_per_lot_per_day"] == -3.85
    assert by_id["SWAP_EMAIL_REFERENCE"]["short_usd_per_lot_per_day"] == -0.25
    assert by_id["SWAP_EMAIL_2X_ADVERSE"]["long_usd_per_lot_per_day"] == -7.7
    assert by_id["SWAP_EMAIL_3X_ADVERSE"]["long_usd_per_lot_per_day"] == -11.55
    assert by_id["SWAP_EMAIL_3X_ADVERSE"]["short_usd_per_lot_per_day"] == -0.75


def test_wednesday_triple_swap_in_every_scenario(policy: dict) -> None:
    for scenario in policy["swap_scenarios"]:
        assert scenario["triple_swap_weekday"] == "WEDNESDAY"
        assert scenario["triple_swap_multiplier"] == 3


def test_no_positive_swap_credit_anywhere(policy: dict) -> None:
    for scenario in policy["swap_scenarios"]:
        assert scenario["no_favorable_positive_swap_credit"] is True
        assert scenario["long_usd_per_lot_per_day"] <= 0
        assert scenario["short_usd_per_lot_per_day"] <= 0


def test_partial_volume_and_side_applicability(policy: dict) -> None:
    scenario = policy["swap_scenarios"][1]
    assert scenario["applicability"]["partial_volume"] == (
        "charged pro rata on open volume per day"
    )
    assert scenario["applicability"]["long_positions"] is True
    assert scenario["applicability"]["short_positions"] is True
    assert scenario["applicability"]["rollover_crossing_required"] is True


def test_missing_slippage_calibration_is_assumption_only(policy: dict) -> None:
    slippage = policy["cost_components"]["slippage"]
    assert slippage["classification"] == "ASSUMPTION_ONLY"
    assert slippage["basis"] == "NO_CALIBRATED_HISTORICAL_EVIDENCE"
    assert slippage["silent_zero_for_acceptance_prohibited"] is True


def test_slippage_scenario_values_are_frozen(policy: dict) -> None:
    points = [s["points"] for s in policy["slippage_scenarios"]]
    assert points == [0.0, 1.0, 3.0]
    for scenario in policy["slippage_scenarios"]:
        assert scenario["classification"] == "ASSUMPTION_ONLY"
        assert scenario["usd_per_point_per_lot"] == 0.10


# ---------------------------------------------------------------------------
# Acceptance restrictions
# ---------------------------------------------------------------------------


def test_cheapest_scenario_cherry_picking_prohibited(policy: dict) -> None:
    restrictions = policy["acceptance_restrictions"]
    assert restrictions["cheapest_scenario_pass_rule"] == "PROHIBITED"
    assert restrictions["required_adverse_boundary"] == "SWAP_EMAIL_3X_ADVERSE"
    assert restrictions["disclose_all_scenarios"] is True
    assert restrictions["automatic_parameter_selection"] == "PROHIBITED"


def test_uncertainty_label_required(policy: dict) -> None:
    restrictions = policy["acceptance_restrictions"]
    assert restrictions["uncertainty_label"] == "HISTORICAL_SWAP_UNCERTAIN"
    assert "every relevant result" in restrictions["uncertainty_labeling"]


def test_gates_remain_false(policy: dict) -> None:
    restrictions = policy["acceptance_restrictions"]
    assert restrictions["strategy_evaluation_authorized"] is False
    assert restrictions["final_validation_authorized"] is False
    assert restrictions["holdout_access_authorized"] is False
    assert policy["activation_authorized"] is False
    assert policy["policy_state"] == "PREREGISTERED_INACTIVE"


def test_active_state_is_unrepresentable(policy: dict) -> None:
    tampered = json.loads(json.dumps(policy))
    tampered["policy_state"] = "ACTIVE"
    tampered["activation_authorized"] = True
    with pytest.raises(cp.CostPolicyError, match="PREREGISTERED_INACTIVE"):
        cp.verify_cost_policy(tampered)


# ---------------------------------------------------------------------------
# Bindings
# ---------------------------------------------------------------------------


def test_binding_fingerprints_are_sha256(policy: dict) -> None:
    bindings = policy["bindings"]
    for field in (
        "strategy_fingerprint",
        "execution_model_fingerprint",
        "risk_policy_fingerprint",
    ):
        assert len(bindings[field]) == 64
        int(bindings[field], 16)


def test_binding_hash_mismatch_fails_closed(
    temp_data_root: Path, policy: dict
) -> None:
    # Module level: a malformed digest is rejected outright.
    tampered = json.loads(json.dumps(policy))
    tampered["bindings"]["broker_support_revision"]["content_canonical_sha256"] = "nothash"
    tampered["policy_fingerprint"] = cp.policy_fingerprint(tampered)  # re-signed
    with pytest.raises(cp.CostPolicyError):
        cp.verify_cost_policy(tampered)
    # End to end: a well-formed but wrong on-disk revision hash must fail
    # closed in the control CLI's binding cross-check.
    evidence_root = temp_data_root / "evidence"
    support_dir = evidence_root / "evidence-broker_support-v1-3b68b4203a9109b9"
    support_dir.mkdir(parents=True)
    (support_dir / "manifest.json").write_text(
        json.dumps({"content_canonical_sha256": "e" * 64}), encoding="utf-8"
    )
    package, _ = build_evidence_package(
        kind="development_cost_policy", content=policy, source_path=None
    )
    policy_dir = evidence_root / package["manifest"]["package_id"]
    policy_dir.mkdir(parents=True)
    (policy_dir / "package.json").write_text(
        json.dumps(package, indent=2, sort_keys=True), encoding="utf-8"
    )
    (policy_dir / "manifest.json").write_text(
        json.dumps(package["manifest"], indent=2, sort_keys=True), encoding="utf-8"
    )
    from backtests import cost_policy_control as cpc

    with pytest.raises(EvidenceStoreError, match="broker-support binding"):
        cpc.cmd_verify(type("Args", (), {"data_root": str(temp_data_root)})())


def test_no_absolute_paths_in_bindings(policy: dict) -> None:
    assert "C:\\" not in json.dumps(policy["bindings"])


def test_execution_model_drift_detected(policy: dict) -> None:
    tampered = json.loads(json.dumps(policy))
    tampered["bindings"]["execution_model_fingerprint"] = "f" * 64
    tampered["policy_fingerprint"] = cp.policy_fingerprint(tampered)  # re-signed
    with pytest.raises(cp.CostPolicyError, match="execution-model"):
        cp.verify_cost_policy(tampered)


# ---------------------------------------------------------------------------
# Evidence-store publication
# ---------------------------------------------------------------------------


def _package(policy_content: dict) -> dict:
    package, _ = build_evidence_package(
        kind="development_cost_policy", content=policy_content, source_path=None
    )
    return package


def test_publication_is_idempotent(policy: dict, tmp_path: Path) -> None:
    evidence_root = tmp_path / "evidence"
    package = _package(policy)
    first_target, first_id = publish_evidence_package(
        package, evidence_root=evidence_root
    )
    second_target, second_id = publish_evidence_package(
        package, evidence_root=evidence_root
    )
    assert first_id == second_id
    assert first_target == second_target


def test_conflicting_publication_fails_closed(policy: dict, tmp_path: Path) -> None:
    evidence_root = tmp_path / "evidence"
    original_package, original_id = build_evidence_package(
        kind="development_cost_policy", content=policy, source_path=None
    )
    publish_evidence_package(original_package, evidence_root=evidence_root)
    # A forged package reusing the published id with altered content must
    # fail closed (the honest altered content would simply get a new id).
    conflicting = json.loads(json.dumps(policy))
    conflicting["cost_components"]["commission"]["amount"] = 1
    forged, _ = build_evidence_package(
        kind="development_cost_policy", content=conflicting, source_path=None
    )
    forged["manifest"]["package_id"] = original_id
    with pytest.raises(EvidenceStoreError):
        publish_evidence_package(forged, evidence_root=evidence_root)


def test_tampered_package_rejected_on_readback(policy: dict, tmp_path: Path) -> None:
    evidence_root = tmp_path / "evidence"
    target, _ = publish_evidence_package(_package(policy), evidence_root=evidence_root)
    loaded = load_evidence_package(target)
    assert loaded["content"]["policy_fingerprint"] == policy["policy_fingerprint"]
    package_path = target / "package.json"
    stored = json.loads(package_path.read_text(encoding="utf-8"))
    stored["content"]["swap_scenarios"][1]["long_usd_per_lot_per_day"] = -0.0
    package_path.write_text(json.dumps(stored, indent=2, sort_keys=True), encoding="utf-8")
    with pytest.raises(EvidenceStoreError):
        load_evidence_package(target)


def test_unknown_kind_rejected(tmp_path: Path) -> None:
    with pytest.raises(EvidenceStoreError):
        build_evidence_package(kind="swap_policy_ACTIVE", content={}, source_path=None)


# ---------------------------------------------------------------------------
# Import safety
# ---------------------------------------------------------------------------


def test_no_mt5_or_network_imports() -> None:
    """Process-level MT5-freedom plus source-level network/exec prohibition."""
    mt5_before = sys.modules.get("MetaTrader5")
    import bot.validation.cost_policy  # noqa: F401
    import backtests.cost_policy_control  # noqa: F401
    import bot.strategy.config  # noqa: F401
    import backtests.evidence_intake_control  # noqa: F401

    # Pure validation modules must not transitively require the terminal
    # library (Phase 8H import-safety regression).
    assert sys.modules.get("MetaTrader5") is mt5_before

    # Source-level prohibition on network and execution surfaces.
    for module_name in (
        "bot/validation/cost_policy.py",
        "backtests/cost_policy_control.py",
    ):
        source = (REPO_ROOT / module_name).read_text(encoding="utf-8")
        for forbidden in (
            "MetaTrader5",
            "import requests",
            "import socket",
            "urllib",
            "httpx",
            "order_send",
            "account_info",
        ):
            assert forbidden not in source, forbidden
