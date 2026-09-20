from __future__ import annotations

import json
from dataclasses import replace

import pytest

from bot.backtesting.models import FidelityClass
from bot.validation.datasets import validate_dataset_package
from bot.validation.models import AcceptanceOutcome, DataStreamKind, ValidationError
from bot.validation.synthetic import END

from .helpers import package, rewrite_jsonl, stream_by_kind, without_stream


def reasons(report) -> set[str]:
    return {issue.reason_code for issue in report.issues}


def test_high_fidelity_synthetic_package_is_accepted_for_development(tmp_path):
    root, manifest = package(tmp_path)
    report = validate_dataset_package(manifest, root, checked_at=END)
    assert report.outcome is AcceptanceOutcome.ACCEPTED_FOR_DEVELOPMENT_ONLY
    assert report.synthetic_label == "SYNTHETIC TEST FIXTURE - NOT MARKET EVIDENCE"
    assert len(report.accepted_stream_hashes) == len(manifest.streams)


def test_assumed_cost_fidelity_is_diagnostic_only(tmp_path):
    root, manifest = package(tmp_path, fidelity=FidelityClass.MID_BAR_WITH_ASSUMED_COSTS)
    report = validate_dataset_package(manifest, root, checked_at=END)
    assert report.outcome is AcceptanceOutcome.DIAGNOSTIC_ONLY
    assert "FIDELITY_NOT_VALIDATION_ELIGIBLE" in reasons(report)


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        (DataStreamKind.NEWS_EVENTS, "NEWS_HISTORY_MISSING"),
        (DataStreamKind.BROKER_METADATA, "BROKER_METADATA_MISSING"),
        (DataStreamKind.SLIPPAGE_OBSERVATIONS, "SLIPPAGE_PROVENANCE_MISSING"),
    ],
)
def test_required_stream_omissions_reject(tmp_path, kind, reason):
    root, manifest = package(tmp_path)
    manifest = without_stream(manifest, lambda item: item.kind is kind)
    report = validate_dataset_package(manifest, root, checked_at=END)
    assert report.outcome is AcceptanceOutcome.REJECTED
    assert reason in reasons(report)


def test_missing_dxy_constituent_rejects(tmp_path):
    root, manifest = package(tmp_path)
    manifest = without_stream(
        manifest,
        lambda item: item.kind is DataStreamKind.DXY_CONSTITUENT and item.symbol == "USDSEK",
    )
    report = validate_dataset_package(manifest, root, checked_at=END)
    assert "DXY_COVERAGE_INCOMPLETE" in reasons(report)


def test_direct_dxy_stream_is_valid_alternative_to_six_constituents(tmp_path):
    root, manifest = package(tmp_path)
    dxy_streams = [item for item in manifest.streams if item.kind is DataStreamKind.DXY_CONSTITUENT]
    direct = replace(dxy_streams[0], kind=DataStreamKind.DIRECT_DXY, symbol="DXY", name="direct_dxy")
    manifest = replace(
        manifest,
        streams=tuple(item for item in manifest.streams if item.kind is not DataStreamKind.DXY_CONSTITUENT) + (direct,),
    )
    report = validate_dataset_package(manifest, root, checked_at=END)
    assert report.outcome is AcceptanceOutcome.ACCEPTED_FOR_DEVELOPMENT_ONLY


def test_missing_analysis_timeframe_and_restricted_license_reject(tmp_path):
    root, manifest = package(tmp_path)
    manifest = without_stream(
        manifest,
        lambda item: item.kind is DataStreamKind.ANALYSIS_CANDLES and item.timeframe == "H4",
    )
    report = validate_dataset_package(manifest, root, checked_at=END)
    assert "ANALYSIS_TIMEFRAME_MISSING" in reasons(report)

    root2, manifest2 = package(tmp_path / "licensed")
    first = replace(manifest2.streams[0], license_or_restrictions="NO_VALIDATION")
    manifest2 = replace(manifest2, streams=(first, *manifest2.streams[1:]))
    assert "LICENSE_RESTRICTS_VALIDATION" in reasons(validate_dataset_package(manifest2, root2, checked_at=END))


def test_hash_mismatch_rejects(tmp_path):
    root, manifest = package(tmp_path)
    stream = stream_by_kind(manifest, DataStreamKind.EXECUTION_QUOTES)
    (root / stream.relative_path).write_text("tampered\n", encoding="utf-8")
    report = validate_dataset_package(manifest, root, checked_at=END)
    assert "HASH_MISMATCH" in reasons(report)


def test_crossed_quote_rejects(tmp_path):
    root, manifest = package(tmp_path)
    manifest = rewrite_jsonl(root, manifest, "xau_ticks", lambda rows: [{**rows[0], "ask": rows[0]["bid"] - 0.1}, rows[1]])
    report = validate_dataset_package(manifest, root, checked_at=END)
    assert "STREAM_CONTENT_INVALID" in reasons(report)


def test_unsorted_and_duplicate_timestamps_reject(tmp_path):
    root, manifest = package(tmp_path)
    manifest = rewrite_jsonl(root, manifest, "xau_ticks", lambda rows: list(reversed(rows)))
    assert "TIMESTAMPS_UNSORTED" in reasons(validate_dataset_package(manifest, root, checked_at=END))

    root2, manifest2 = package(tmp_path / "second")
    manifest2 = rewrite_jsonl(root2, manifest2, "xau_ticks", lambda rows: [rows[0], {**rows[1], "timestamp": rows[0]["timestamp"]}])
    assert "DUPLICATE_TIMESTAMP" in reasons(validate_dataset_package(manifest2, root2, checked_at=END))


def test_naive_timestamp_and_truncated_json_reject(tmp_path):
    root, manifest = package(tmp_path)
    manifest = rewrite_jsonl(root, manifest, "xau_ticks", lambda rows: [{**rows[0], "timestamp": "2024-01-10T00:00:00"}, rows[1]])
    assert "STREAM_CONTENT_INVALID" in reasons(validate_dataset_package(manifest, root, checked_at=END))

    root2, manifest2 = package(tmp_path / "truncated")
    stream = stream_by_kind(manifest2, DataStreamKind.EXECUTION_QUOTES)
    path = root2 / stream.relative_path
    path.write_text('{"timestamp":', encoding="utf-8")
    stream = replace(stream, sha256=__import__("hashlib").sha256(path.read_bytes()).hexdigest(), record_count=1)
    manifest2 = replace(manifest2, streams=tuple(stream if item.name == stream.name else item for item in manifest2.streams))
    assert "STREAM_CORRUPT" in reasons(validate_dataset_package(manifest2, root2, checked_at=END))


def test_timestamp_contamination_and_unexplained_gap_reject(tmp_path):
    root, manifest = package(tmp_path)
    manifest = rewrite_jsonl(root, manifest, "xau_ticks", lambda rows: [rows[0], {**rows[1], "timestamp": "2024-01-10T00:20:00+00:00"}])
    report = validate_dataset_package(manifest, root, checked_at=END)
    assert {"TIMESTAMP_OUTSIDE_MANIFEST", "COVERAGE_MISMATCH"} & reasons(report)


def test_synthetic_provenance_cannot_be_relabelled_empirical(tmp_path):
    root, manifest = package(tmp_path)
    manifest = replace(manifest, synthetic=False)
    report = validate_dataset_package(manifest, root, checked_at=END)
    assert report.outcome is AcceptanceOutcome.REJECTED
    assert "SYNTHETIC_PACKAGE_MISLABELED" in reasons(report)


def test_manifest_rejects_unsafe_paths(tmp_path):
    _, manifest = package(tmp_path)
    stream = manifest.streams[0]
    with pytest.raises(ValidationError, match="package-relative"):
        replace(stream, relative_path="../outside.jsonl")


def test_acceptance_report_serializes_without_credentials(tmp_path):
    root, manifest = package(tmp_path)
    report = validate_dataset_package(manifest, root, checked_at=END)
    rendered = json.dumps(report, default=lambda value: getattr(value, "__dict__", str(value)))
    assert "password" not in rendered.lower()
