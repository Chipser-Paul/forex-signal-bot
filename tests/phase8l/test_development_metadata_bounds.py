"""Synthetic, MT5-free tests for Phase 8L's preregistered proxy policy."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bot.acquisition.evidence_contracts import canonical_hash  # noqa: E402
from bot.validation import development_metadata_bounds as bounds  # noqa: E402


def _sources(tmp_path: Path) -> tuple[Path, Path]:
    eml = tmp_path / "support.eml"
    eml.write_text(
        "From: Support <reply@mail.exness.com>\n"
        "Date: Mon, 15 Sep 2026 12:00:00 +0000\n"
        "Subject: Private owner name\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        "We don't maintain an archived contract specification document or a historical trading terms page for XAUUSDm from 2024. "
        "We cannot provide retroactively dated contract specifications such as historical margin rules, stop distances, or execution modes for 2024.\n",
        encoding="utf-8",
    )
    pdf = tmp_path / "rendition.pdf"
    pdf.write_bytes(b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF")
    return eml, pdf


def _evidence(tmp_path: Path) -> dict:
    eml, pdf = _sources(tmp_path)
    return bounds.build_unavailability_evidence(eml_path=eml, pdf_path=pdf)


@pytest.fixture(autouse=True)
def _recovery_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bounds.metadata_recovery, "verify_metadata_recovery", lambda value: {"verified": True})
    monkeypatch.setattr(bounds.metadata_recovery, "verify_metadata_recovery_readiness", lambda value: {"verified": True})


def _policy(tmp_path: Path) -> dict:
    evidence = _evidence(tmp_path)
    return bounds.build_development_metadata_bounds(
        unavailability_evidence=evidence, unavailability_package_id="evidence-broker_metadata_unavailability-v1-test",
        unavailability_content_sha256=canonical_hash(evidence), recovery={}, recovery_package_id="evidence-broker_metadata_recovery-v1-test",
        recovery_content_sha256=canonical_hash({}), recovery_readiness={}, recovery_readiness_package_id="evidence-metadata_recovery_readiness-v1-test",
        recovery_readiness_content_sha256=canonical_hash({}),
        cost_policy_report={"package_id": "evidence-development_cost_policy-v1-test", "policy_fingerprint": "c" * 64},
        bindings={"strategy_fingerprint": "s" * 64, "risk_policy_fingerprint": "r" * 64, "execution_model_fingerprint": "x" * 64,
                  "development_dataset": {"year_package_id": "year", "source_canonical_sha256": "y" * 64}},
        decision_utc="2026-09-15T00:00:00Z",
    )


def test_primary_eml_is_sanitized_and_pdf_is_secondary(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    assert bounds.verify_unavailability_evidence(evidence)["verified"] is True
    assert evidence["primary_source"]["parsed_as_primary"] is True
    assert evidence["rendition"]["parsed_as_primary"] is False
    assert set(evidence["statements"]) == set(bounds.REQUIRED_NEGATIVE_STATEMENTS)
    assert "@" not in json.dumps(evidence)
    assert "Private owner name" not in json.dumps(evidence)


def test_malformed_or_incomplete_email_fails_closed(tmp_path: Path) -> None:
    eml, pdf = _sources(tmp_path)
    eml.write_text("From: spoof@example.com\n\narchived contract specification document", encoding="utf-8")
    with pytest.raises(bounds.DevelopmentMetadataBoundsError, match="sender domain"):
        bounds.build_unavailability_evidence(eml_path=eml, pdf_path=pdf)


def test_policy_is_deterministic_and_keeps_historical_facts_separate(tmp_path: Path) -> None:
    first = _policy(tmp_path)
    second = _policy(tmp_path)
    assert first == second
    assert bounds.verify_development_metadata_bounds(first)["verified"] is True
    assert first["baseline_proxy"]["point_tick_size"]["not_historical_fact"] is True
    assert first["derived_tick_value_proxy"]["usd_per_tick_per_lot"] == 0.1
    assert first["derived_tick_value_proxy"]["classification"] == "DERIVED_FROM_ASSUMED_CONTRACT_SIZE"
    assert first["development_metadata_gap_acceptable"] is True
    assert first["development_evaluation_sufficient"] is True
    for gate in ("strategy_evaluation_authorized", "accepted_for_final_validation", "holdout_access_authorized", "phase9_authorized"):
        assert first[gate] is False


def test_all_adverse_scenarios_are_mandatory_and_no_selection_is_allowed(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    assert tuple(item["scenario_id"] for item in policy["mandatory_scenarios"]) == bounds.SCENARIO_ORDER
    assert all(item["selection_by_profit_prohibited"] for item in policy["mandatory_scenarios"])
    assert policy["restrictions"]["cheapest_scenario_selection"] == "PROHIBITED"
    ids = {item["scenario_id"] for item in policy["mandatory_scenarios"]}
    assert {"STALE_METADATA_REJECTION", "MINIMUM_VOLUME_RISK_BUDGET_FAILURE", "STOP_FREEZE_RESTRICTION_GUARD", "COMBINED_ADVERSE_BROKER_CONDITIONS"} <= ids


def test_policy_rejects_missing_scenario_and_promoted_gate(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    missing = json.loads(json.dumps(policy))
    missing["mandatory_scenarios"] = missing["mandatory_scenarios"][:-1]
    missing["policy_fingerprint"] = bounds.policy_fingerprint(missing)
    with pytest.raises(bounds.DevelopmentMetadataBoundsError, match="scenarios"):
        bounds.verify_development_metadata_bounds(missing)
    promoted = json.loads(json.dumps(policy))
    promoted["strategy_evaluation_authorized"] = True
    promoted["policy_fingerprint"] = bounds.policy_fingerprint(promoted)
    with pytest.raises(bounds.DevelopmentMetadataBoundsError, match="strategy_evaluation_authorized"):
        bounds.verify_development_metadata_bounds(promoted)


def test_policy_rejects_mismatched_bound_evidence_hash(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    with pytest.raises(bounds.DevelopmentMetadataBoundsError, match="unavailability evidence hash mismatch"):
        bounds.build_development_metadata_bounds(
            unavailability_evidence=evidence, unavailability_package_id="evidence-broker_metadata_unavailability-v1-test",
            unavailability_content_sha256="0" * 64, recovery={}, recovery_package_id="recovery",
            recovery_content_sha256=canonical_hash({}), recovery_readiness={}, recovery_readiness_package_id="readiness",
            recovery_readiness_content_sha256=canonical_hash({}),
            cost_policy_report={"package_id": "cost", "policy_fingerprint": "c" * 64}, bindings={},
            decision_utc="2026-09-15T00:00:00Z",
        )


def test_tick_value_derivation_is_dimensional_and_rejects_invalid_values() -> None:
    assert bounds.derive_tick_value_proxy(contract_size_oz=100.0, tick_size_price=0.001) == 0.1
    with pytest.raises(bounds.DevelopmentMetadataBoundsError, match="positive"):
        bounds.derive_tick_value_proxy(contract_size_oz=0.0, tick_size_price=0.001)


def test_preregistered_proxy_guards_cover_volume_margin_stop_fill_and_staleness(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    scenarios = {item["scenario_id"]: item for item in policy["mandatory_scenarios"]}
    assert bounds.normalize_volume_down(0.109999999, 0.01) == 0.1
    assert bounds.evaluate_scenario_guard(scenarios["MINIMUM_VOLUME_RISK_BUDGET_FAILURE"], requested_volume=0.10, risk_budget_volume=0.05, metadata_fresh=True, free_margin_fraction=1.0, stop_distance_price=10.0) == "REJECT_MINIMUM_VOLUME_EXCEEDS_RISK_BUDGET"
    assert bounds.evaluate_scenario_guard(scenarios["STRICTER_MARGIN_REQUIREMENT"], requested_volume=0.10, risk_budget_volume=1.0, metadata_fresh=True, free_margin_fraction=0.01, stop_distance_price=10.0) == "REJECT_FREE_MARGIN"
    assert bounds.evaluate_scenario_guard(scenarios["STOP_FREEZE_RESTRICTION_GUARD"], requested_volume=0.10, risk_budget_volume=1.0, metadata_fresh=True, free_margin_fraction=1.0, stop_distance_price=1.0) == "REJECT_STOP_FREEZE_GUARD"
    assert bounds.evaluate_scenario_guard(scenarios["FOK_MISSED_FILL_STRESS"], requested_volume=0.10, risk_budget_volume=1.0, metadata_fresh=True, free_margin_fraction=1.0, stop_distance_price=10.0, fok_fill_available=False) == "REJECT_FOK_MISSED_FILL"
    assert bounds.evaluate_scenario_guard(scenarios["PARTIAL_FILL_REDUCED_LIQUIDITY"], requested_volume=0.10, risk_budget_volume=1.0, metadata_fresh=True, free_margin_fraction=1.0, stop_distance_price=10.0) == "PARTIAL_FILL_STRESS"
    assert bounds.evaluate_scenario_guard(scenarios["BASELINE_CURRENT_REFERENCE_PROXY"], requested_volume=0.10, risk_budget_volume=1.0, metadata_fresh=False, free_margin_fraction=1.0, stop_distance_price=10.0) == "REJECT_METADATA_STALE"


def test_readiness_is_hash_bound_and_cannot_authorize_execution(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    readiness = bounds.build_readiness(policy, policy_package_id="evidence-development_metadata_bounds-v1-test", policy_content_sha256="p" * 64)
    assert bounds.verify_readiness(readiness)["verified"] is True
    tampered = json.loads(json.dumps(readiness))
    tampered["phase9_authorized"] = True
    tampered["readiness_canonical_sha256"] = canonical_hash({key: value for key, value in tampered.items() if key != "readiness_canonical_sha256"})
    with pytest.raises(bounds.DevelopmentMetadataBoundsError, match="phase9_authorized"):
        bounds.verify_readiness(tampered)


def test_phase8l_imports_are_mt5_and_network_free() -> None:
    before = sys.modules.get("MetaTrader5")
    import bot.validation.development_metadata_bounds as module  # noqa: F401
    import backtests.development_metadata_bounds_control as cli  # noqa: F401
    assert sys.modules.get("MetaTrader5") is before
    for relative in ("bot/validation/development_metadata_bounds.py", "backtests/development_metadata_bounds_control.py"):
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        for forbidden in ("MetaTrader5", "import requests", "import socket", "order_send", "account_info"):
            assert forbidden not in source
