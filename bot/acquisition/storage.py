from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from filelock import FileLock

from bot.validation.models import canonical_data

from .models import AcquisitionError, ChunkSummary, utc_datetime


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_output_root(path: Path, *, forbidden_roots: Iterable[Path]) -> Path:
    resolved = Path(path).expanduser().resolve(strict=False)
    for root in forbidden_roots:
        candidate = Path(root).resolve(strict=False)
        if _inside(resolved, candidate) or _inside(candidate, resolved):
            raise AcquisitionError("raw-data output must be outside every Git worktree")
    for parent in (resolved, *resolved.parents):
        if (parent / ".git").exists():
            raise AcquisitionError("raw-data output cannot be inside a Git repository")
    return resolved


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object, *, refuse_overwrite: bool = True) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock", timeout=10):
        _atomic_json_locked(path, value, refuse_overwrite=refuse_overwrite)


def _atomic_json_locked(path: Path, value: object, *, refuse_overwrite: bool) -> None:
    if refuse_overwrite and path.exists():
        raise FileExistsError(f"refusing to overwrite {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".partial")
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            json.dump(canonical_data(value), handle, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def output_size(root: Path) -> int:
    if not Path(root).exists():
        return 0
    return sum(path.stat().st_size for path in Path(root).rglob("*") if path.is_file())


class ChunkStore:
    def __init__(self, root: Path, *, maximum_output_bytes: int) -> None:
        self.root = validate_output_root(root, forbidden_roots=())
        self.maximum_output_bytes = int(maximum_output_bytes)
        if self.maximum_output_bytes <= 0:
            raise AcquisitionError("output budget must be positive")
        self.root.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        relative_path: str,
        records: Iterable[Mapping[str, object]],
        *,
        chunk_id: str,
        start: datetime,
        end: datetime,
        diagnostics: Mapping[str, int] | None = None,
        resume: bool = False,
    ) -> ChunkSummary:
        with FileLock(str(self.root / ".chunks.lock"), timeout=10):
            return self._write_locked(relative_path, records, chunk_id=chunk_id, start=start,
                                      end=end, diagnostics=diagnostics, resume=resume)

    def _write_locked(
        self, relative_path: str, records: Iterable[Mapping[str, object]], *,
        chunk_id: str, start: datetime, end: datetime,
        diagnostics: Mapping[str, int] | None, resume: bool,
    ) -> ChunkSummary:
        utc_datetime(start, "chunk start")
        utc_datetime(end, "chunk end")
        final_path = self._safe_path(relative_path)
        marker_path = final_path.with_suffix(final_path.suffix + ".complete.json")
        if final_path.exists() or marker_path.exists():
            if resume and final_path.exists() and marker_path.exists():
                return self.verify(relative_path)
            raise FileExistsError(f"completed chunk already exists: {final_path.name}")
        partial_path = final_path.with_suffix(final_path.suffix + ".partial")
        if partial_path.exists():
            if not resume:
                raise FileExistsError(f"partial chunk requires resume: {partial_path.name}")
            partial_path.unlink()

        final_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        try:
            with partial_path.open("xb") as raw:
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                    for record in records:
                        line = json.dumps(canonical_data(record), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
                        compressed.write(line.encode("utf-8") + b"\n")
                        count += 1
                raw.flush()
                os.fsync(raw.fileno())
            with gzip.open(partial_path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    json.loads(line)
            projected = output_size(self.root)
            if projected > self.maximum_output_bytes:
                raise AcquisitionError("output budget would be exceeded")
            os.replace(partial_path, final_path)
            summary = ChunkSummary(
                chunk_id=chunk_id,
                relative_path=final_path.relative_to(self.root).as_posix(),
                sha256=file_sha256(final_path),
                record_count=count,
                start=utc_datetime(start, "chunk start"),
                end=utc_datetime(end, "chunk end"),
                size_bytes=final_path.stat().st_size,
                duplicate_count=int((diagnostics or {}).get("duplicate_count", 0)),
                crossed_quote_count=int((diagnostics or {}).get("crossed_quote_count", 0)),
                zero_quote_count=int((diagnostics or {}).get("zero_quote_count", 0)),
                gap_count=int((diagnostics or {}).get("gap_count", 0)),
                complete=True,
            )
            atomic_json(marker_path, asdict(summary))
            return summary
        except Exception:
            partial_path.unlink(missing_ok=True)
            if final_path.exists() and not marker_path.exists():
                final_path.unlink()
            raise

    def verify(self, relative_path: str) -> ChunkSummary:
        final_path = self._safe_path(relative_path)
        marker_path = final_path.with_suffix(final_path.suffix + ".complete.json")
        if not final_path.is_file() or not marker_path.is_file():
            raise AcquisitionError("chunk is incomplete")
        try:
            raw = json.loads(marker_path.read_text(encoding="utf-8"))
            summary = ChunkSummary(
                chunk_id=raw["chunk_id"],
                relative_path=raw["relative_path"],
                sha256=raw["sha256"],
                record_count=int(raw["record_count"]),
                start=datetime.fromisoformat(raw["start"].replace("Z", "+00:00")),
                end=datetime.fromisoformat(raw["end"].replace("Z", "+00:00")),
                size_bytes=int(raw["size_bytes"]),
                duplicate_count=int(raw["duplicate_count"]),
                crossed_quote_count=int(raw["crossed_quote_count"]),
                zero_quote_count=int(raw["zero_quote_count"]),
                gap_count=int(raw["gap_count"]),
                complete=raw["complete"] is True,
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AcquisitionError("chunk completion marker is invalid") from exc
        if not summary.complete or summary.relative_path != final_path.relative_to(self.root).as_posix():
            raise AcquisitionError("chunk completion marker does not match the file")
        if file_sha256(final_path) != summary.sha256 or final_path.stat().st_size != summary.size_bytes:
            raise AcquisitionError("chunk hash or size does not match its completion marker")
        try:
            with gzip.open(final_path, "rt", encoding="utf-8") as handle:
                record_count = 0
                for line in handle:
                    json.loads(line)
                    record_count += 1
        except (OSError, EOFError, UnicodeError, json.JSONDecodeError) as exc:
            raise AcquisitionError("chunk stream is malformed") from exc
        if record_count != summary.record_count:
            raise AcquisitionError("chunk record count does not match its completion marker")
        return summary

    def free_bytes(self) -> int:
        return int(shutil.disk_usage(self.root).free)

    def _safe_path(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise AcquisitionError("chunk path must be package-relative")
        path = (self.root / relative).resolve(strict=False)
        if not _inside(path, self.root.resolve(strict=False)):
            raise AcquisitionError("chunk path escapes the output root")
        return path
