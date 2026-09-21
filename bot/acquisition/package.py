from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from bot.backtesting.models import FidelityClass
from bot.data.candles import TIMEFRAMES
from bot.validation.models import (
    DataStreamKind,
    DataStreamManifest,
    EmpiricalPackageManifest,
    StudyPeriod,
    canonical_data,
    canonical_hash,
)

from .models import AcquisitionError, DXY_BASE_SYMBOLS, EXECUTABLE_SYMBOL, ExportConfig
from .storage import atomic_json, file_sha256


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AcquisitionError(f"{path.name} is missing or malformed") from exc
    if not isinstance(value, dict):
        raise AcquisitionError(f"{path.name} must contain an object")
    return value


def build_partial_package(
    config: ExportConfig,
    *,
    created_at: datetime,
    license_or_restrictions: str,
) -> Path:
    export_manifest = _load_json(config.output_root / "manifests" / "export_manifest.json")
    mapping_values = export_manifest.get("symbol_mappings")
    if not isinstance(mapping_values, dict):
        raise AcquisitionError("export manifest lacks symbol mappings")
    reverse_mapping = {
        str(details["broker_symbol"]): base
        for base, details in mapping_values.items()
        if base in DXY_BASE_SYMBOLS and isinstance(details, dict) and details.get("broker_symbol")
    }
    streams: list[DataStreamManifest] = []
    marker_paths = sorted(config.output_root.rglob("*.complete.json"))
    for marker_path in marker_paths:
        marker = _load_json(marker_path)
        relative_path = str(marker.get("relative_path") or "")
        data_path = config.output_root / relative_path
        parts = Path(relative_path).parts
        if not data_path.is_file() or len(parts) < 3:
            raise AcquisitionError("chunk marker references an invalid data file")
        timeframe: str | None = None
        if parts[0] == "ticks" and parts[1] == EXECUTABLE_SYMBOL:
            kind = DataStreamKind.EXECUTION_QUOTES
            symbol = EXECUTABLE_SYMBOL
            maximum_gap = 15 * 60
        elif parts[0] == "bars":
            broker_symbol, timeframe = parts[1], parts[2]
            if timeframe not in TIMEFRAMES:
                raise AcquisitionError("chunk marker references an unsupported timeframe")
            if broker_symbol == EXECUTABLE_SYMBOL:
                kind = DataStreamKind.ANALYSIS_CANDLES
                symbol = EXECUTABLE_SYMBOL
            elif broker_symbol in reverse_mapping:
                kind = DataStreamKind.DXY_CONSTITUENT
                symbol = reverse_mapping[broker_symbol]
            else:
                raise AcquisitionError("bar chunk has no verified symbol mapping")
            maximum_gap = int(TIMEFRAMES[timeframe].duration.total_seconds() * 4)
        else:
            continue
        chunk_id = str(marker["chunk_id"])
        if int(marker.get("record_count", 0)) == 0:
            continue
        streams.append(DataStreamManifest(
            name=chunk_id,
            kind=kind,
            relative_path=relative_path.replace("\\", "/"),
            sha256=str(marker["sha256"]),
            symbol=symbol,
            start=datetime.fromisoformat(str(marker["start"]).replace("Z", "+00:00")),
            end=datetime.fromisoformat(str(marker["end"]).replace("Z", "+00:00")),
            record_count=int(marker["record_count"]),
            provenance="already-authenticated-demo-terminal-read-only-export",
            license_or_restrictions=license_or_restrictions,
            timeframe=timeframe,
            maximum_expected_gap_seconds=maximum_gap,
        ))

    metadata_path = config.output_root / "metadata" / "XAUUSDm.current-symbol-snapshot.json"
    if metadata_path.is_file():
        metadata = _load_json(metadata_path)
        effective_from = datetime.fromisoformat(str(metadata["effective_from"]).replace("Z", "+00:00"))
        streams.append(DataStreamManifest(
            name="XAUUSDm-current-symbol-metadata",
            kind=DataStreamKind.BROKER_METADATA,
            relative_path=metadata_path.relative_to(config.output_root).as_posix(),
            sha256=file_sha256(metadata_path),
            symbol=EXECUTABLE_SYMBOL,
            start=effective_from,
            end=effective_from,
            record_count=1,
            provenance="current-demo-terminal-symbol-metadata-snapshot",
            license_or_restrictions=license_or_restrictions,
        ))
    if not streams:
        raise AcquisitionError("no verified completed chunks are available to package")
    package_seed = {
        "tool_version": export_manifest.get("tool_version"),
        "config": export_manifest.get("configuration_fingerprint"),
        "streams": [(stream.name, stream.sha256) for stream in streams],
    }
    manifest = EmpiricalPackageManifest(
        schema_version=1,
        package_id=f"phase8b-{canonical_hash(package_seed)[:20]}",
        broker_source="already-authenticated-demo-terminal-redacted",
        fidelity=FidelityClass.TICK_BID_ASK,
        evaluation_period=StudyPeriod(config.start, config.end, "requested-empirical-coverage"),
        streams=tuple(sorted(streams, key=lambda item: item.name)),
        synthetic=False,
        collection_method="phase8b-stage1-guarded-read-only-mt5-export",
        created_at=created_at,
        raw_data_outside_git=True,
    )
    path = config.output_root / "package" / "empirical_data_package.json"
    atomic_json(path, canonical_data(manifest))
    return path
