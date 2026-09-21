"""Append-only setup/restart amendment; never runs an empirical evaluation."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any, Mapping

from bot.acquisition.evidence_contracts import canonical_hash
from bot.acquisition.evidence_store import build_evidence_package, load_evidence_package, publish_evidence_package
from bot.strategy.setup_consumption import CONSUMPTION_SCHEMA, RESTART_CONTRACT
from bot.strategy.setup_state import STATE_SCHEMA, SETUP_ID_SCHEMA
from bot.validation.development_evaluation_plan import verify_development_evaluation_plan
from bot.validation.development_scenario_matrix import build_cell_contract, compose_scenarios, verify_cell_contract


REVISION_SCHEMA = "phase8n.superseding-development-plan.v1"
CODE_COMPONENTS = {
    "empirical_adapter": ("bot/validation/empirical_strategy_adapter.py", "bot/state/orchestrator.py", "main.py", "bot/backtesting/adapters.py"),
    "gate_reducer": ("bot/state/gate_reducer.py", "bot/state/gate_inputs.py", "bot/strategy/legacy_adapter.py"),
    "levels_builder": ("bot/strategy/trade_levels.py", "bot/strategy/setup_intent.py", "strategies/smc_engine/entry_model.py"),
    "consumption": ("bot/strategy/setup_consumption.py", "bot/execution/lifecycle/serialization.py"),
    "restart": ("bot/strategy/setup_recovery.py", "bot/strategy/setup_store.py", "bot/backtesting/fill_journal.py", "bot/validation/development_scenario_matrix.py"),
    "state_migration": ("bot/strategy/setup_state.py",),
    "lifecycle_parity": ("tests/phase8/test_setup_consumption.py", "tests/phase8/test_setup_lifecycle_restart_parity.py", "tests/phase8/test_full_orchestration_parity.py", "tests/phase8/test_consumption_scenario_parity.py", "tests/phase8/test_scenario_cell_contract.py"),
}


def component_fingerprints(worktree: Path) -> dict[str, str]:
    """Hash reviewed Python text with LF newlines across Git checkout modes."""
    return {name: canonical_hash({relative: hashlib.sha256((Path(worktree) / relative).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                                 for relative in paths}) for name, paths in CODE_COMPONENTS.items()}


def build_revision(parent: Mapping[str, Any], parent_package_id: str, fingerprints: Mapping[str, str], *, proof: Mapping[str, Any]) -> dict[str, Any]:
    verify_development_evaluation_plan(parent)
    if set(fingerprints) != set(CODE_COMPONENTS):
        raise ValueError("all replay implementation fingerprints required")
    if (proof.get("consumption_restart_passed") is not True or proof.get("live_offline_parity_passed") is not True
            or proof.get("scenario_cells_verified") != 64 or proof.get("unexpected_failures") != 0
            or proof.get("unexpected_xpasses") != 0 or proof.get("empirical_execution") is not False):
        raise ValueError("synthetic acceptance proof is incomplete")
    matrix = compose_scenarios(
        parent["cost_scenarios"]["swap"], parent["cost_scenarios"]["slippage"],
        parent["metadata_scenarios"]["scenario_ids"], tuple(fold["fold_id"] for fold in parent["folds"]),
    )
    bindings = {
        **dict(fingerprints), "parent_plan": parent["plan_fingerprint"],
        "candidate": canonical_hash(parent["candidate"]), "inputs": canonical_hash(parent["input_readiness"]),
    }
    cell_contract = build_cell_contract(matrix, parent["folds"], bindings)
    revision = deepcopy(dict(parent))
    revision.pop("plan_fingerprint")
    revision.update({
        "schema_version": REVISION_SCHEMA, "plan_id": "phase8n.development-evaluation-plan.v2",
        "status": "FROZEN_AWAITING_AUTHORIZED_RUN",
        "supersedes": {"package_id": parent_package_id, "fingerprint": parent["plan_fingerprint"],
                       "parent_status": "SUPERSEDED_BEFORE_EXECUTION", "original_package_mutated": False},
        "orchestration_contract": {
            "implementation_hash_encoding": "UTF8_TEXT_CANONICAL_LF_SHA256",
            "fingerprints": dict(fingerprints), "setup_id_schema": SETUP_ID_SCHEMA,
            "consumption_schema": CONSUMPTION_SCHEMA, "restart_contract": RESTART_CONTRACT,
            "state_migration_schema": STATE_SCHEMA,
            "consumption_boundary": "FIRST_DURABLE_POSITIVE_CONFIRMED_ENTRY_FILL",
            "uncertain_outcomes": "BLOCK_UNTIL_AUTHORITATIVE_RECONCILIATION",
            "retrospective_news": "DEVELOPMENT_EVENT_TIME_VETO_ONLY_NOT_HISTORICAL_RETRIEVAL_FRESHNESS",
        },
        "scenario_matrix": matrix, "scenario_cell_contract": cell_contract,
        "synthetic_acceptance_proof": deepcopy(dict(proof)),
    })
    revision["plan_fingerprint"] = canonical_hash(revision)
    verify_revision(revision, parent)
    return revision


def verify_revision(revision: Mapping[str, Any], parent: Mapping[str, Any]) -> None:
    verify_development_evaluation_plan(parent)
    if revision.get("schema_version") != REVISION_SCHEMA or revision.get("status") != "FROZEN_AWAITING_AUTHORIZED_RUN":
        raise ValueError("superseding plan schema or status mismatch")
    if revision["supersedes"]["fingerprint"] != parent["plan_fingerprint"]:
        raise ValueError("parent plan fingerprint mismatch")
    if (revision["supersedes"].get("parent_status") != "SUPERSEDED_BEFORE_EXECUTION"
            or revision["supersedes"].get("original_package_mutated") is not False):
        raise ValueError("parent revision must remain append-only")
    changed_keys = {"schema_version", "plan_id", "status", "plan_fingerprint"}
    for key in set(parent) - changed_keys:
        if revision[key] != parent[key]:
            raise ValueError("frozen parent policy/input contract changed")
    if revision["plan_fingerprint"] != canonical_hash({key: value for key, value in revision.items() if key != "plan_fingerprint"}):
        raise ValueError("superseding plan fingerprint mismatch")
    verify_cell_contract(revision["scenario_cell_contract"], revision["scenario_matrix"], revision["folds"])
    fingerprints = revision["orchestration_contract"]["fingerprints"]
    expected_bindings = {
        **fingerprints, "parent_plan": parent["plan_fingerprint"],
        "candidate": canonical_hash(parent["candidate"]), "inputs": canonical_hash(parent["input_readiness"]),
    }
    if revision["scenario_cell_contract"]["bindings"] != expected_bindings:
        raise ValueError("cell and orchestration component bindings differ")
    contract = revision["orchestration_contract"]
    if (contract.get("setup_id_schema"), contract.get("consumption_schema"), contract.get("restart_contract"), contract.get("state_migration_schema")) != (
            SETUP_ID_SCHEMA, CONSUMPTION_SCHEMA, RESTART_CONTRACT, STATE_SCHEMA):
        raise ValueError("replay schema/version contract mismatch")
    proof = revision["synthetic_acceptance_proof"]
    if (proof.get("consumption_restart_passed") is not True or proof.get("live_offline_parity_passed") is not True
            or proof.get("scenario_cells_verified") != 64 or proof.get("unexpected_failures") != 0
            or proof.get("unexpected_xpasses") != 0 or proof.get("empirical_execution") is not False):
        raise ValueError("synthetic acceptance proof is incomplete")


def publish_revision(evidence_root: Path, parent_package_id: str, revision: Mapping[str, Any]) -> dict[str, str]:
    parent_package = load_evidence_package(Path(evidence_root) / parent_package_id)
    parent = parent_package["content"]
    if revision["supersedes"]["package_id"] != parent_package_id:
        raise ValueError("superseding package parent identity mismatch")
    verify_revision(revision, parent)
    package, package_id = build_evidence_package(kind="development_evaluation_plan", content=revision, source_path=None)
    publish_evidence_package(package, evidence_root=Path(evidence_root))
    stored = load_evidence_package(Path(evidence_root) / package_id)
    if stored["content"] != dict(revision):
        raise ValueError("published superseding plan differs from frozen content")
    return {"package_id": package_id, "plan_fingerprint": revision["plan_fingerprint"]}
