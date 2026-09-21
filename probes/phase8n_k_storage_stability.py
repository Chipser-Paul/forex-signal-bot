"""Phase 8N-K storage-stability probe (engineering diagnosis, not strategy evidence).

Background: on 2026-09-20, two frozen tick partitions (2024-12, then 2024-04)
returned SHA-256 digests that differed from their manifests under heavy
concurrent I/O; the December file re-verified OK, the April file returned a
stable-but-wrong digest, and two file writes were silently lost.  This probe
measures read stability directly: every frozen tick partition is read in fixed
chunks over several passes, each pass digest compared against the manifest.
A memory pattern test runs first to separate RAM faults from storage faults.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

PACKAGES_ROOT = Path(
    "C:/Users/chips/forex-signal-bot-data/phase8/exness-tick-history/processed/packages"
)
CHUNK = 4 << 20  # 4 MiB
PASSES = 3


def memory_pattern_test(rounds: int = 200, size: int = 8 << 20) -> dict:
    buf = bytearray(size)
    pattern = bytes(range(256)) * (size // 256)
    failures = 0
    t0 = time.perf_counter()
    for _ in range(rounds):
        buf[: len(pattern)] = pattern
        if bytes(buf[: len(pattern)]) != pattern:
            failures += 1
    return {
        "rounds": rounds,
        "buffer_mib": size >> 20,
        "failures": failures,
        "seconds": round(time.perf_counter() - t0, 2),
        "status": "ok" if failures == 0 else "RAM_INSTABILITY",
    }


def verify_partition(package: Path, part: dict) -> dict:
    path = package / str(part["relative_path"])
    want = str(part["sha256"])
    res = {"package": package.name, "partition": str(part["relative_path"]), "passes": []}
    with path.open("rb") as fh:
        for pass_no in range(1, PASSES + 1):
            fh.seek(0)
            digest = hashlib.sha256()
            t0 = time.perf_counter()
            while True:
                chunk = fh.read(CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
            res["passes"].append(
                {
                    "pass": pass_no,
                    "match": digest.hexdigest() == want,
                    "digest": digest.hexdigest(),
                    "seconds": round(time.perf_counter() - t0, 2),
                }
            )
    res["status"] = "ok" if all(p["match"] for p in res["passes"]) else "UNSTABLE_READS"
    return res


def main() -> int:
    report = {
        "label": "EMPIRICAL ENGINEERING BENCHMARK - NOT STRATEGY EVIDENCE",
        "purpose": "storage read-stability diagnosis after transient hash mismatches",
        "chunk_bytes": CHUNK,
        "passes": PASSES,
    }
    report["memory_pattern_test"] = memory_pattern_test()
    print("memory:", json.dumps(report["memory_pattern_test"]), flush=True)
    partitions = []
    for pkg in sorted(PACKAGES_ROOT.glob("exness-xauusdm-2024-*")):
        completion = json.loads((pkg / "package.complete.json").read_text())
        manifest = json.loads((pkg / completion["manifest_relative_path"]).read_text())
        for part in manifest.get("partitions", []):
            r = verify_partition(pkg, part)
            partitions.append(r)
            print(f"  {r['package']}/{r['partition']}: {r['status']}", flush=True)
    unstable = [p for p in partitions if p["status"] != "ok"]
    report["partitions"] = partitions
    report["summary"] = {
        "partitions_checked": len(partitions),
        "unstable": len(unstable),
        "unstable_packages": [p["package"] for p in unstable],
    }
    out = Path(__file__).with_name("storage_stability_report.json")
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    mem = report["memory_pattern_test"]
    return 0 if not unstable and mem["failures"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
