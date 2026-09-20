"""Phase 8E offline evidence intake CLI (owner-facing entry point).

Subcommands (all offline; no provider network access, no MT5):

- ``init``                  create an empty owner-input package (refuses overwrite)
- ``validate-news``         validate a historical USD news file (JSON, raw provider rows)
- ``validate-metadata``     validate effective-dated XAUUSDm broker metadata
- ``validate-commission``   validate a commission schedule
- ``validate-swap``         validate swap/rollover/triple-swap evidence
- ``validate-slippage``     validate sanitized fill/slippage evidence
- ``verify-source``         compare a supplied file against a declared SHA-256
- ``register-spread``       register observed XAUUSDm spread evidence from existing manifests
- ``matrix``                build + publish the evidence matrix
- ``readiness``             build + publish the readiness revision
- ``reverify``              hash-verify every published evidence package

Generated packages live outside Git under
``C:\\Users\\chips\\forex-signal-bot-data\\phase8\\evidence``. Source files are
read-only: hashed, never modified, never copied with credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from bot.acquisition.evidence_contracts import (
    DEVELOPMENT_ONLY_CLASSIFICATION,
    DEVELOPMENT_INTERVAL_END,
    DEVELOPMENT_INTERVAL_START,
    STATUS_ACCEPTED_DEVELOPMENT_ONLY,
    STATUS_ACCEPTED_EMPIRICAL,
    STATUS_MISSING,
    build_evidence_matrix,
    canonical_hash,
    sha256_file,
)
from bot.acquisition.evidence_store import (
    EvidenceStoreError,
    load_evidence_package,
    publish_evidence_package,
    run_intake,
)

DEFAULT_DATA_ROOT = Path(r"C:\Users\chips\forex-signal-bot-data\phase8")
DERIVED_CANDLE_PACKAGE = "derived-candles-2024-v1-20260911T195553Z"
ATTESTATION_ID = "derived-candles-attestation-v1-6715e5c64d888215"
OWNER_INPUT_DIRS = ("news", "broker-metadata", "commission", "swap", "slippage")


def _load_records(path: Path) -> list[Mapping[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise EvidenceStoreError("input file must be a JSON array of objects")
    return data


def _evidence_roots(args: argparse.Namespace) -> tuple[Path, Path]:
    data_root = Path(args.data_root)
    return data_root, data_root / "evidence"


# ---------------------------------------------------------------------------
# Observed spread evidence (STEP 8)
# ---------------------------------------------------------------------------


def build_observed_spread_evidence(data_root: Path) -> dict[str, Any]:
    """Bind observed spread evidence to the existing verified manifests.

    Reads only manifests + the small M5 partition; never re-derives ticks.
    """

    derived_dir = data_root / "derived" / DERIVED_CANDLE_PACKAGE
    manifest_path = derived_dir / "manifest.json"
    completion_path = derived_dir / "pipeline.complete.json"
    readiness_path = derived_dir / "readiness_report.json"
    for path in (manifest_path, completion_path, readiness_path):
        if not path.is_file():
            raise EvidenceStoreError(f"derived package file missing: {path.name}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest["timeframe_entries"]
    if isinstance(entries, dict):
        m5 = entries["M5"]
    else:
        m5 = next(item for item in entries if str(item.get("timeframe")) == "M5")
    relative = m5["partition_relative_path"]
    parquet_path = derived_dir / relative
    if not parquet_path.is_file():
        # The manifest records paths relative to the candles root.
        parquet_path = derived_dir / "candles" / relative
    if not parquet_path.is_file():
        raise EvidenceStoreError(f"M5 partition not found for relative path {relative!r}")

    spread_stats: dict[str, float] | None = None
    try:
        import pyarrow.parquet as pq  # type: ignore

        table = pq.read_table(parquet_path, columns=["spread_min", "spread_median", "spread_max"])
        data = table.to_pydict()
        mins = [float(v) for v in data["spread_min"] if v is not None]
        medians = [float(v) for v in data["spread_median"] if v is not None]
        maxs = [float(v) for v in data["spread_max"] if v is not None]
        if medians:
            medians_sorted = sorted(medians)
            mid = len(medians_sorted) // 2
            spread_stats = {
                "observed_min_of_spread_min": min(mins) if mins else 0.0,
                "observed_median_of_spread_median": medians_sorted[mid],
                "observed_max_of_spread_max": max(maxs) if maxs else 0.0,
            }
    except Exception:
        spread_stats = None
    if spread_stats is None:
        raise EvidenceStoreError(
            "observed spread statistics could not be computed from the M5 partition"
        )

    attestation_path = (
        data_root / "derived" / "attestations" / ATTESTATION_ID / "attestation.json"
    )
    if not attestation_path.is_file():
        raise EvidenceStoreError("derived-candle attestation document is missing")

    # Locate the verified tick year package by exact canonical-hash identity
    # with the derived manifest's recorded source — never by filename.
    source_canonical = str(manifest.get("source_canonical_sha256"))
    year_packages_root = data_root / "exness-tick-history" / "processed" / "year-packages"
    tick_manifest = None
    tick_manifest_path = None
    if year_packages_root.is_dir():
        for candidate in sorted(year_packages_root.glob("*/manifest.json")):
            data = json.loads(candidate.read_text(encoding="utf-8"))
            stats = data.get("statistics") or {}
            if str(stats.get("canonical_normalized_sha256")) == source_canonical:
                if tick_manifest is not None:
                    raise EvidenceStoreError(
                        "ambiguous tick year package: two manifests share the canonical hash"
                    )
                tick_manifest = data
                tick_manifest_path = candidate
    if tick_manifest is None or tick_manifest_path is None:
        raise EvidenceStoreError(
            "no tick year package manifest matches the derived source_canonical_sha256"
        )
    tick_stats = tick_manifest["statistics"]
    tick_spread = tick_stats["aggregate_spread_price"]

    content = {
        "schema_version": "phase8e.observed-spread-evidence.v1",
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "status": STATUS_ACCEPTED_DEVELOPMENT_ONLY,
        "source_identities": {
            "derived_candle_package_id": DERIVED_CANDLE_PACKAGE,
            "derived_manifest_sha256": sha256_file(manifest_path),
            "derived_completion_sha256": sha256_file(completion_path),
            "attestation_id": ATTESTATION_ID,
            "attestation_sha256": sha256_file(attestation_path),
            "tick_year_package_id": str(tick_manifest.get("package_id")),
            "tick_year_canonical_sha256": str(
                tick_stats.get("canonical_normalized_sha256")
            ),
            "tick_year_manifest_sha256": sha256_file(tick_manifest_path),
            "source_tick_row_count": manifest.get("source_row_count"),
        },
        "coverage": {
            "interval_utc": [DEVELOPMENT_INTERVAL_START, DEVELOPMENT_INTERVAL_END],
            "first_tick_utc": str(tick_stats.get("first_timestamp", "")),
            "last_tick_utc": str(tick_stats.get("last_timestamp", "")),
            "first_m5_open_ms": m5["first_open_ms"],
            "last_m5_open_ms": m5["last_open_ms"],
            "m5_candle_count": m5["record_count"],
        },
        "units": "USD price units (ask - bid)",
        "tick_level_spread": {
            "minimum": str(tick_spread["minimum"]),
            "mean": str(tick_spread["mean"]),
            "maximum": str(tick_spread["maximum"]),
            "observation_count": tick_spread["observation_count"],
            "provenance": "verified tick year-package manifest statistics (hash-bound above)",
        },
        "candle_level_spread_m5": spread_stats,
        "aggregation_limitations": (
            "Candle-level spread_min/spread_median/spread_max/spread_close aggregate the "
            "verified tick path within each candle; they do NOT reconstruct the exact "
            "executable tick path. Tick-level aggregates (min/mean/max over the full year) "
            "are authoritative for cost-model plausibility but are still not a per-tick "
            "execution path."
        ),
        "gaps": {
            "m5_gap_count": m5["gap_count"],
            "tick_long_gap_count": (tick_stats.get("aggregate_integrity") or {}).get("long_gap_count"),
            "note": "missing windows remain missing; no forward fill",
        },
        "permitted_uses": [
            "development spread-aware stress testing",
            "spread plausibility checks for cost models",
        ],
        "prohibited_uses": [
            "claiming candle-level median/max spread equals the executable tick path",
            "claiming tick-level min/mean/max reconstructs the per-tick execution path",
            "final-validation execution fidelity claims",
        ],
    }
    content["content_canonical_sha256"] = canonical_hash(
        {k: v for k, v in content.items() if k != "content_canonical_sha256"}
    )
    return content


def _spread_matrix_entry(spread_content: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "category": "OBSERVED_SPREAD",
        "status": str(spread_content["status"]),
        "source_identity": str(spread_content["source_identities"]["derived_candle_package_id"]),
        "provider": "Exness (verified tick archive)",
        "coverage_interval": str(spread_content["coverage"]["interval_utc"]),
        "effective_interval": str(spread_content["coverage"]["interval_utc"]),
        "retrieval_or_observation_utc": "",
        "sha256": str(spread_content["content_canonical_sha256"]),
        "schema_version": str(spread_content["schema_version"]),
        "provenance": "verified 2024 XAUUSDm bid/ask ticks (manifest-bound)",
        "licensing": "owner-supplied market data; development-only",
        "completeness": "full 2024 candle coverage with declared gaps",
        "units": str(spread_content["units"]),
        "account_type_dependency": "XAUUSDm standard accounts",
        "validation_errors": [],
        "permitted_uses": list(spread_content["permitted_uses"]),
        "prohibited_uses": list(spread_content["prohibited_uses"]),
        "aggregation_limitations": str(spread_content["aggregation_limitations"]),
    }


# ---------------------------------------------------------------------------
# Matrix + readiness
# ---------------------------------------------------------------------------

EVIDENCE_KIND_TO_CATEGORY = {
    "news": "HISTORICAL_USD_NEWS",
    "broker_metadata": "BROKER_METADATA",
    "commission": "COMMISSION",
    "swap": "SWAP_ROLLOVER",
    "slippage": "SLIPPAGE_FILLS",
    "official_news": "OFFICIAL_USD_NEWS",
    "broker_support": "BROKER_SUPPORT",
    "development_cost_policy": "DEVELOPMENT_COST_POLICY",
    "cost_policy_activation": "COST_POLICY_ACTIVATION",
    "dataset_acceptance_review": "DATASET_ACCEPTANCE_REVIEW",
    "development_evaluation_plan": "DEVELOPMENT_EVALUATION_PLAN",
}

# A broker_support package supersedes an older one only as an honest lineage:
# identical claim sets (re-ingestion) select latest; a proper superset (new
# corroboration added) is succession; partial overlap fails closed.
def _broker_support_claim_id_set(package_dir: Path) -> frozenset[str]:
    content = json.loads(
        (package_dir / "package.json").read_text(encoding="utf-8")
    )["content"]
    return frozenset(str(c.get("claim_id")) for c in content.get("claims", []))


def _official_news_event_id_set(package_dir: Path) -> frozenset[str]:
    """Stable event-identity set of an official-news package (dataset identity)."""

    content = json.loads(
        (package_dir / "package.json").read_text(encoding="utf-8")
    )["content"]
    return frozenset(
        str(e.get("event_id")) for e in content.get("events", [])
    )


def collect_evidence_statuses(evidence_root: Path) -> dict[str, dict[str, Any]]:
    """Scan published evidence packages; map kind -> {status, sha256, ...}."""

    found: dict[str, dict[str, Any]] = {}
    if not evidence_root.is_dir():
        return found
    for child in sorted(evidence_root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        manifest_path = child / "manifest.json"
        if not manifest_path.is_file():
            continue
        package = load_evidence_package(child)
        manifest = package["manifest"]
        kind = str(manifest.get("kind"))
        if kind not in EVIDENCE_KIND_TO_CATEGORY:
            continue
        status = str(package["content"].get("status", STATUS_MISSING))
        record = {
            "package_id": str(manifest["package_id"]),
            "status": status,
            "sha256": str(manifest.get("source_file_sha256", "")),
            "content_canonical_sha256": str(manifest.get("content_canonical_sha256")),
            "schema_version": str(manifest.get("content_schema_version", "")),
        }
        if kind in found and found[kind]["content_canonical_sha256"] != record["content_canonical_sha256"]:
            # Official-news packages are immutable retrieval revisions of one
            # dataset lineage. Succession rules on the stable event-ID set:
            #   equal sets            -> same dataset, latest revision wins;
            #   proper superset       -> coverage growth (e.g. the manual BLS
            #                            completion), supersedes;
            #   proper subset         -> retained older revision, never
            #                            selected, never a failure;
            #   partial overlap       -> two genuinely different datasets
            #                            (loss/replacement/contradiction)
            #                            -> fail closed.
            if kind in {"official_news", "broker_support"}:
                if kind == "official_news":
                    ids_new = _official_news_event_id_set(child)
                    ids_old = _official_news_event_id_set(
                        evidence_root / found[kind]["package_id"]
                    )
                else:
                    ids_new = _broker_support_claim_id_set(child)
                    ids_old = _broker_support_claim_id_set(
                        evidence_root / found[kind]["package_id"]
                    )
                if ids_new != ids_old and not (
                    ids_new < ids_old or ids_old < ids_new
                ):
                    identity_label = (
                        "event sets" if kind == "official_news" else "identity sets"
                    )
                    raise EvidenceStoreError(
                        f"ambiguous evidence: two {kind} packages with "
                        f"different stable {identity_label} are published "
                        f"({found[kind]['package_id']} vs {record['package_id']})"
                    )
                # Succession key: coverage first (superset beats subset),
                # then accepted status (a completed verification of the same
                # dataset supersedes an incomplete classification), then the
                # content-derived package id for full determinism.
                _ACCEPTED = {"ACCEPTED_EMPIRICAL", "ACCEPTED_DEVELOPMENT_ONLY"}
                rank_new = (
                    len(ids_new),
                    1 if record["status"] in _ACCEPTED else 0,
                    record["package_id"],
                )
                rank_old = (
                    len(ids_old),
                    1 if found[kind]["status"] in _ACCEPTED else 0,
                    found[kind]["package_id"],
                )
                if rank_new > rank_old:
                    found[kind] = record
                continue
            raise EvidenceStoreError(
                f"ambiguous evidence: two conflicting {kind} packages are published"
            )
        found[kind] = record
    return found


def build_matrix_package(evidence_root: Path, data_root: Path) -> dict[str, Any]:
    found = collect_evidence_statuses(evidence_root)
    spread_content = build_observed_spread_evidence(data_root)
    statuses = {
        "news": STATUS_MISSING,
        "broker_metadata": STATUS_MISSING,
        "commission": STATUS_MISSING,
        "swap": STATUS_MISSING,
        "slippage": STATUS_MISSING,
        "official_news": STATUS_MISSING,
        "broker_support": STATUS_MISSING,
        "development_cost_policy": STATUS_MISSING,
        "cost_policy_activation": STATUS_MISSING,
        "dataset_acceptance_review": STATUS_MISSING,
        "development_evaluation_plan": STATUS_MISSING,
    }
    for kind, record in found.items():
        statuses[kind] = record["status"]
    # The official-government feed satisfies the news requirement once it is
    # accepted; while DEVELOPMENT_INCOMPLETE it maps to PRESENT_UNVERIFIED
    # for the 8E news category (evidence exists, acceptance not earned).
    official_status = statuses["official_news"]
    news_status = statuses["news"]
    if news_status == STATUS_MISSING and official_status == "ACCEPTED_DEVELOPMENT_ONLY":
        news_status = "ACCEPTED_DEVELOPMENT_ONLY"
    matrix = build_evidence_matrix(
        news_status=news_status,
        broker_metadata_status=statuses["broker_metadata"],
        commission_status=statuses["commission"],
        swap_status=statuses["swap"],
        slippage_status=statuses["slippage"],
        observed_spread_entry=_spread_matrix_entry(spread_content),
        notes={
            "HISTORICAL_USD_NEWS": (
                "official-government feed tracked separately; see OFFICIAL_USD_NEWS entry"
            )
        },
    )
    # Phase 8F: append the distinct official-news category entry (the 8E
    # category tuple is frozen for backwards compatibility). Status is taken
    # verbatim from the published official-news package, including the
    # honest DEVELOPMENT_INCOMPLETE state.
    if "OFFICIAL_USD_NEWS" not in matrix["statuses"]:
        matrix["statuses"]["OFFICIAL_USD_NEWS"] = official_status
        matrix["entries"].append(
            {
                "category": "OFFICIAL_USD_NEWS",
                "status": official_status,
                "schema_version": str(found.get("official_news", {}).get("schema_version", "")),
                "sha256": str(found.get("official_news", {}).get("content_canonical_sha256", "")),
                "permitted_uses": [
                    "development news-window filtering once accepted"
                    if official_status == "ACCEPTED_DEVELOPMENT_ONLY"
                    else "no permitted use until coverage is complete"
                ],
                "prohibited_uses": ["holdout evaluation", "profitability evidence"],
                "note": "zero-cost official government sources (Fed/BEA/Census/BLS)",
            }
        )
        matrix["all_categories_accepted"] = all(
            status in {STATUS_ACCEPTED_EMPIRICAL, STATUS_ACCEPTED_DEVELOPMENT_ONLY}
            for status in matrix["statuses"].values()
        )
    # Phase 8G: broker-support conditions evidence is a distinct, honest
    # category — broker-asserted statements plus current-only observations;
    # it never promotes BROKER_METADATA/COMMISSION/SWAP_ROLLOVER to accepted
    # historical evidence by itself.
    if "BROKER_SUPPORT" not in matrix["statuses"]:
        support_record = found.get("broker_support")
        matrix["statuses"]["BROKER_SUPPORT"] = (
            str(support_record["status"]) if support_record else STATUS_MISSING
        )
        matrix["entries"].append(
            {
                "category": "BROKER_SUPPORT",
                "status": str(support_record["status"]) if support_record else STATUS_MISSING,
                "schema_version": str(
                    support_record.get("schema_version", "") if support_record else ""
                ),
                "sha256": str(
                    support_record.get("content_canonical_sha256", "") if support_record else ""
                ),
                "permitted_uses": (
                    [
                        "development-only commission-NONE representation",
                        "proposed (inactive) swap stress-policy derivation",
                        "spread-cost linkage context",
                    ]
                    if support_record
                    else []
                ),
                "prohibited_uses": [
                    "claiming historical 2024 swap values",
                    "treating current screenshot values as historical",
                    "final-validation execution fidelity claims",
                    "profitability evidence",
                ],
                "note": (
                    "Exness support transcript + sanitized MT5 screenshots; "
                    "claim-level classification"
                    if support_record
                    else "no broker support evidence ingested"
                ),
            }
        )
        matrix["all_categories_accepted"] = all(
            status in {STATUS_ACCEPTED_EMPIRICAL, STATUS_ACCEPTED_DEVELOPMENT_ONLY}
            for status in matrix["statuses"].values()
        )
    matrix["evidence_packages"] = {kind: rec for kind, rec in found.items()}
    matrix["observed_spread"] = spread_content
    # Phase 8H: the frozen development-cost-policy is a distinct honest
    # category.  PREREGISTERED_INACTIVE is an informational state — it never
    # flips all_categories_accepted, never authorizes evaluation, and never
    # promotes commission/swap/slippage to accepted historical evidence.
    if "DEVELOPMENT_COST_POLICY" not in matrix["statuses"]:
        policy_record = found.get("development_cost_policy")
        policy_status = (
            str(policy_record["status"]) if policy_record else STATUS_MISSING
        )
        matrix["statuses"]["DEVELOPMENT_COST_POLICY"] = policy_status
        matrix["entries"].append(
            {
                "category": "DEVELOPMENT_COST_POLICY",
                "status": policy_status,
                "schema_version": str(
                    policy_record.get("schema_version", "") if policy_record else ""
                ),
                "sha256": str(
                    policy_record.get("content_canonical_sha256", "")
                    if policy_record
                    else ""
                ),
                "permitted_uses": (
                    [
                        "frozen disclosure baseline for development cost accounting"
                        if policy_status == "PREREGISTERED_INACTIVE"
                        else "no permitted use in this state"
                    ]
                    if policy_record
                    else []
                ),
                "prohibited_uses": [
                    "strategy evaluation authorization",
                    "cheapest-scenario cherry-picking",
                    "presenting current swap references as historical",
                    "final-validation or holdout evidence",
                ],
                "note": (
                    "preregistered inactive; activation requires its own "
                    "owner-authorized checkpoint"
                    if policy_record
                    else "no development-cost policy preregistered"
                ),
            }
        )
    matrix["all_categories_accepted"] = all(
        status in {STATUS_ACCEPTED_EMPIRICAL, STATUS_ACCEPTED_DEVELOPMENT_ONLY}
        for status in matrix["statuses"].values()
    )
    # Phase 8I: the swap-policy activation record and the dataset-acceptance
    # review are distinct honest categories.  Both never flip
    # all_categories_accepted, never authorize evaluation, and never promote
    # any evidence to final-validation strength.
    for kind, category in (
        ("cost_policy_activation", "COST_POLICY_ACTIVATION"),
        ("dataset_acceptance_review", "DATASET_ACCEPTANCE_REVIEW"),
    ):
        if category not in matrix["statuses"]:
            record = found.get(kind)
            record_status = str(record["status"]) if record else STATUS_MISSING
            matrix["statuses"][category] = record_status
            if kind == "cost_policy_activation":
                permitted = (
                    [
                        "scenario-based development swap/slippage accounting "
                        "under the frozen Phase 8H governance rules"
                    ]
                    if record_status == "ACTIVE_FOR_DEVELOPMENT_VALIDATION"
                    else []
                )
                prohibited = [
                    "strategy evaluation authorization",
                    "parameter tuning from scenario results",
                    "cheapest-scenario selection",
                    "reinterpreting historical 2024 swap evidence",
                    "final-validation or holdout evidence",
                ]
                note = (
                    "owner-activated assumption-only swap stress policy; "
                    "HISTORICAL_SWAP_UNCERTAIN labelling required"
                    if record_status == "ACTIVE_FOR_DEVELOPMENT_VALIDATION"
                    else "swap stress policy not activated"
                )
            else:
                permitted = (
                    ["development-evaluation input-completion review"]
                    if record_status == "ACCEPTED_DEVELOPMENT_ONLY"
                    else []
                )
                prohibited = [
                    "upgrading development-strength evidence to final-validation strength",
                    "strategy evaluation authorization",
                    "holdout access",
                ]
                note = (
                    "per-category dataset acceptance review; insufficient "
                    "categories block final validation"
                    if record
                    else "no dataset-acceptance review published"
                )
            matrix["entries"].append(
                {
                    "category": category,
                    "status": record_status,
                    "schema_version": str(
                        record.get("schema_version", "") if record else ""
                    ),
                    "sha256": str(
                        record.get("content_canonical_sha256", "") if record else ""
                    ),
                    "permitted_uses": permitted,
                    "prohibited_uses": prohibited,
                    "note": note,
                }
            )
    # Phase 8M: the frozen development-evaluation plan is an orchestration
    # contract, not accepted evidence.  FROZEN_AWAITING_AUTHORIZED_RUN is
    # informational; it never flips all_categories_accepted, never
    # authorizes evaluation, holdout access, or final validation.
    if "DEVELOPMENT_EVALUATION_PLAN" not in matrix["statuses"]:
        plan_record = found.get("development_evaluation_plan")
        plan_status = str(plan_record["status"]) if plan_record else STATUS_MISSING
        matrix["statuses"]["DEVELOPMENT_EVALUATION_PLAN"] = plan_status
        matrix["entries"].append(
            {
                "category": "DEVELOPMENT_EVALUATION_PLAN",
                "status": plan_status,
                "schema_version": str(
                    plan_record.get("schema_version", "") if plan_record else ""
                ),
                "sha256": str(
                    plan_record.get("content_canonical_sha256", "") if plan_record else ""
                ),
                "permitted_uses": (
                    ["deterministic all-scenario development-evaluation execution once separately authorized"]
                    if plan_status == "FROZEN_AWAITING_AUTHORIZED_RUN"
                    else []
                ),
                "prohibited_uses": [
                    "strategy evaluation authorization",
                    "holdout access",
                    "final-validation evidence",
                    "automatic tuning or cheapest-scenario selection",
                ],
                "note": (
                    "immutable run plan frozen; execution requires a separate "
                    "owner-authorized checkpoint"
                    if plan_record
                    else "no development-evaluation plan frozen"
                ),
            }
        )
    matrix["all_categories_accepted"] = all(
        status in {STATUS_ACCEPTED_EMPIRICAL, STATUS_ACCEPTED_DEVELOPMENT_ONLY}
        for status in matrix["statuses"].values()
    )
    return matrix


def build_readiness_package(matrix: Mapping[str, Any]) -> dict[str, Any]:
    statuses = matrix["statuses"]
    return {
        "schema_version": "phase8e.evidence-readiness.v1",
        "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
        "inputs": {
            "xauusdm_ticks_2024": "AVAILABLE",
            "xauusdm_causal_candles": "AVAILABLE",
            "observed_spread_evidence": str(statuses.get("OBSERVED_SPREAD", STATUS_MISSING)),
            "dxy_development_input": "AVAILABLE",
            "official_usd_news": str(statuses.get("OFFICIAL_USD_NEWS", STATUS_MISSING)),
            "historical_news": str(statuses.get("HISTORICAL_USD_NEWS", STATUS_MISSING)),
            "broker_metadata": str(statuses.get("BROKER_METADATA", STATUS_MISSING)),
            "commission": str(statuses.get("COMMISSION", STATUS_MISSING)),
            "swap_rollover": str(statuses.get("SWAP_ROLLOVER", STATUS_MISSING)),
            "slippage_fills": str(statuses.get("SLIPPAGE_FILLS", STATUS_MISSING)),
            "broker_support_conditions": str(statuses.get("BROKER_SUPPORT", STATUS_MISSING)),
            "development_cost_policy": str(
                statuses.get("DEVELOPMENT_COST_POLICY", STATUS_MISSING)
            ),
            "cost_policy_activation": str(
                statuses.get("COST_POLICY_ACTIVATION", STATUS_MISSING)
            ),
            "dataset_acceptance_review": str(
                statuses.get("DATASET_ACCEPTANCE_REVIEW", STATUS_MISSING)
            ),
            "development_evaluation_plan": str(
                statuses.get("DEVELOPMENT_EVALUATION_PLAN", STATUS_MISSING)
            ),
            "holdout": "UNAVAILABLE_AND_UNTOUCHED",
        },
        "accepted_for_final_validation": False,
        "strategy_evaluation_authorized": False,
        "holdout_access_authorized": False,
        "notes": (
            "Evidence intake software passing tests never authorizes a baseline "
            "strategy run; every mandatory category must be genuinely accepted first."
        ),
        "evidence_matrix_canonical_sha256": canonical_hash(dict(matrix)),
    }


def _publish_doc(content: Mapping[str, Any], kind: str, evidence_root: Path) -> tuple[Path, str]:
    package = {
        "manifest": {
            "schema_version": "phase8e.evidence-package.v1",
            "package_id": f"{kind}-v1-{canonical_hash(dict(content))[:16]}",
            "kind": kind,
            "classification": DEVELOPMENT_ONLY_CLASSIFICATION,
            "content_canonical_sha256": canonical_hash(dict(content)),
        },
        "content": dict(content),
    }
    return publish_evidence_package(package, evidence_root=evidence_root)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    _, evidence_root = _evidence_roots(args)
    owner_input = evidence_root / "owner-input"
    if owner_input.exists() and any(owner_input.iterdir()):
        print(f"REFUSED: owner-input package already exists at {owner_input}", file=sys.stderr)
        return 2
    owner_input.mkdir(parents=True, exist_ok=True)
    for sub in OWNER_INPUT_DIRS:
        (owner_input / sub).mkdir(exist_ok=True)
    readme = owner_input / "README.txt"
    readme.write_text(
        "Phase 8E owner evidence intake area (offline).\n\n"
        "Place owner-supplied files here; then run the matching validate-* subcommand.\n"
        "Files are hashed and validated; they are never modified.\n"
        "Never place credentials, account numbers, or API tokens here.\n"
        "All accepted evidence remains DEVELOPMENT_ONLY - NOT HOLDOUT - NOT PROFITABILITY EVIDENCE.\n",
        encoding="utf-8",
    )
    print(f"initialized empty owner-input package at {owner_input}")
    return 0


def _validate_command(kind: str, args: argparse.Namespace) -> int:
    _, evidence_root = _evidence_roots(args)
    source = Path(args.file)
    if not source.is_file():
        print(f"input file not found: {source}", file=sys.stderr)
        return 2
    payload: dict[str, Any] = {"records": _load_records(source)}
    if kind == "news":
        payload.update(
            {
                "provider": args.provider,
                "retrieval_utc": args.retrieved_at,
                "licensing_declaration": args.license_declaration,
                "declared_coverage_start": getattr(args, "coverage_start", None),
                "declared_coverage_end": getattr(args, "coverage_end", None),
            }
        )
    try:
        target, package_id, content = run_intake(
            kind, payload, source_path=source, evidence_root=evidence_root
        )
    except (EvidenceStoreError, ValueError) as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1
    print(f"published {kind} evidence package {package_id} at {target}")
    print(f"status: {content.get('status')}")
    return 0


def cmd_verify_source(args: argparse.Namespace) -> int:
    actual = sha256_file(Path(args.file))
    if actual.lower() != args.sha256.lower():
        print(f"FAIL-CLOSED: source hash mismatch: {actual} != {args.sha256}", file=sys.stderr)
        return 1
    print(f"source verified: {actual}")
    return 0


def cmd_register_spread(args: argparse.Namespace) -> int:
    data_root, evidence_root = _evidence_roots(args)
    try:
        content = build_observed_spread_evidence(data_root)
        target, package_id = _publish_doc(content, "observed_spread", evidence_root)
    except EvidenceStoreError as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1
    print(f"published observed-spread evidence package {package_id} at {target}")
    return 0


def cmd_matrix(args: argparse.Namespace) -> int:
    data_root, evidence_root = _evidence_roots(args)
    try:
        matrix = build_matrix_package(evidence_root, data_root)
        target, package_id = _publish_doc(matrix, "evidence_matrix", evidence_root)
    except (EvidenceStoreError, ValueError) as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1
    print(f"published evidence matrix {package_id} at {target}")
    print(json.dumps(matrix["statuses"], indent=2, sort_keys=True))
    return 0


def cmd_readiness(args: argparse.Namespace) -> int:
    data_root, evidence_root = _evidence_roots(args)
    try:
        matrix = build_matrix_package(evidence_root, data_root)
        readiness = build_readiness_package(matrix)
        target, package_id = _publish_doc(readiness, "evidence_readiness", evidence_root)
    except (EvidenceStoreError, ValueError) as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1
    print(f"published readiness revision {package_id} at {target}")
    print(json.dumps(readiness["inputs"], indent=2, sort_keys=True))
    print(
        "accepted_for_final_validation="
        f"{readiness['accepted_for_final_validation']} "
        f"strategy_evaluation_authorized={readiness['strategy_evaluation_authorized']}"
    )
    return 0


def cmd_reverify(args: argparse.Namespace) -> int:
    _, evidence_root = _evidence_roots(args)
    failures = 0
    count = 0
    if evidence_root.is_dir():
        for child in sorted(evidence_root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if not (child / "manifest.json").is_file():
                continue
            count += 1
            try:
                package = load_evidence_package(child)
                print(f"verified {package['manifest']['package_id']}")
            except EvidenceStoreError as exc:
                failures += 1
                print(f"TAMPER/FAIL: {child.name}: {exc}", file=sys.stderr)
    print(f"reverified {count} packages, {failures} failures")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 8E offline evidence intake")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    news = sub.add_parser("validate-news")
    news.add_argument("--file", required=True)
    news.add_argument("--provider", required=True, choices=["TRADING_ECONOMICS", "EODHD"])
    news.add_argument("--retrieved-at", required=True)
    news.add_argument("--license-declaration", required=True)
    news.add_argument(
        "--coverage-start",
        help="UTC instant the export is declared to start covering (optional)",
    )
    news.add_argument(
        "--coverage-end",
        help="UTC instant the export is declared to cover through (optional)",
    )
    news.set_defaults(func=lambda a: _validate_command("news", a))

    for kind, label in (
        ("broker_metadata", "validate-metadata"),
        ("commission", "validate-commission"),
        ("swap", "validate-swap"),
        ("slippage", "validate-slippage"),
    ):
        p = sub.add_parser(label)
        p.add_argument("--file", required=True)
        p.set_defaults(func=lambda a, k=kind: _validate_command(k, a))

    verify = sub.add_parser("verify-source")
    verify.add_argument("--file", required=True)
    verify.add_argument("--sha256", required=True)
    verify.set_defaults(func=cmd_verify_source)

    sub.add_parser("register-spread").set_defaults(func=cmd_register_spread)
    sub.add_parser("matrix").set_defaults(func=cmd_matrix)
    sub.add_parser("readiness").set_defaults(func=cmd_readiness)
    sub.add_parser("reverify").set_defaults(func=cmd_reverify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
