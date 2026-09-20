"""Offline control surface for the immutable Phase 8B package registry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from bot.acquisition.models import AcquisitionError
from bot.acquisition.package_registry import PackageRegistryStore, PackageStatus, _json_hash
from bot.validation.models import canonical_data


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline package registry control; no acquisition is performed")
    parser.add_argument("command", choices=("validate", "show", "bootstrap-dry-run", "bootstrap-apply", "allocate-recovery", "register-candidate", "record-verification", "activate", "quarantine"))
    parser.add_argument("--registry-root", type=Path, required=True)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--package-id")
    parser.add_argument("--operation-id")
    parser.add_argument("--reason")
    parser.add_argument("--writer-fingerprint")
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--plan-hash")
    parser.add_argument("--confirm", action="store_true")
    return parser


def _load_spec(path: Path | None) -> dict[str, object]:
    if path is None: raise AcquisitionError("PACKAGE_REGISTRY_SPEC_REQUIRED")
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise AcquisitionError("PACKAGE_REGISTRY_SPEC_INVALID") from exc
    if not isinstance(value, dict): raise AcquisitionError("PACKAGE_REGISTRY_SPEC_INVALID")
    return value


def _emit(status: str, **details: object) -> int:
    print(json.dumps(canonical_data({"status": status, **details}), sort_keys=True, separators=(",", ":")))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv); store = PackageRegistryStore(args.registry_root)
    try:
        if args.command in {"validate", "show"}:
            registry = store.load()
            return _emit("PACKAGE_REGISTRY_VALID" if args.command == "validate" else "PACKAGE_REGISTRY_STATUS", registry=registry)
        if args.command == "bootstrap-dry-run":
            spec = _load_spec(args.spec)
            return _emit("PACKAGE_REGISTRY_BOOTSTRAP_PLAN", plan=canonical_data(spec), plan_hash=_json_hash(canonical_data(spec)), mutation_performed=False)
        if not args.confirm: raise AcquisitionError("PACKAGE_REGISTRY_CONFIRMATION_REQUIRED")
        if args.command == "bootstrap-apply":
            registry = store.bootstrap(_load_spec(args.spec), reviewed_plan_hash=str(args.plan_hash or ""), owner_confirmed=True)
            return _emit("PACKAGE_REGISTRY_BOOTSTRAPPED", revision=registry["revision"])
        if args.command == "allocate-recovery":
            result = store.allocate_recovery(operation_id=str(args.operation_id or ""), reason=str(args.reason or ""), writer_fingerprint=str(args.writer_fingerprint or ""), package_root=args.package_root)
            return _emit("PACKAGE_REGISTRY_RECOVERY_ALLOCATED", allocation=result["allocation"], idempotent=result["idempotent"])
        if args.command == "register-candidate":
            spec = _load_spec(args.spec)
            record = store.register_candidate(**spec)
            return _emit("PACKAGE_REGISTRY_CANDIDATE_REGISTERED", package_id=record["package_id"])
        if args.command == "record-verification":
            record = store.transition(str(args.package_id or ""), PackageStatus.VERIFYING, reason=str(args.reason or ""), operation_id=str(args.operation_id or ""))
            record = store.transition(record["package_id"], PackageStatus.VERIFIED_INACTIVE, reason="VERIFICATION_RECORDED", operation_id=str(args.operation_id or ""))
            return _emit("PACKAGE_REGISTRY_VERIFIED", package_id=record["package_id"])
        if args.command == "activate":
            registry = store.activate(str(args.package_id or ""), operation_id=str(args.operation_id or ""), reason=str(args.reason or ""))
            return _emit("PACKAGE_REGISTRY_ACTIVATED", package_id=registry["active_package_id"])
        record = store.transition(str(args.package_id or ""), PackageStatus.QUARANTINED, reason=str(args.reason or ""), operation_id=str(args.operation_id or ""))
        return _emit("PACKAGE_REGISTRY_QUARANTINED", package_id=record["package_id"])
    except (AcquisitionError, FileNotFoundError, OSError, ValueError, TypeError) as exc:
        return _emit("PACKAGE_REGISTRY_BLOCKED", reason_code=str(exc)) or 2


if __name__ == "__main__":
    raise SystemExit(main())
