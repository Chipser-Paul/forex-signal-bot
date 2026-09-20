"""Publish the Phase 8N-K runner-compatibility record (engineering step).

Binds the CURRENT runner source fingerprint to the accepted Phase 8N-I plan,
records the Stage-2 commit, and publishes through the append-only Phase 8E
store. Refuses to run if the plan binding changed or the commit is missing.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.validation.runner_compatibility import (  # noqa: E402
    load_compatibility_record,
    publish_compatibility_record,
)

EVIDENCE_ROOT = Path("C:/Users/chips/forex-signal-bot-data/phase8/evidence")
WORKTREE = Path(__file__).resolve().parents[1]


def main() -> int:
    prev = load_compatibility_record(EVIDENCE_ROOT)
    plan_id = prev["plan_binding"]["package_id"]
    plan_fp = prev["plan_binding"]["plan_fingerprint"]
    invalid = prev["invalidated_plan_never_accepted"]
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=WORKTREE, capture_output=True, text=True, check=True
    ).stdout.strip()
    if len(commit) != 40:
        raise SystemExit("no 40-char HEAD commit; commit first")
    content_out, content_id = publish_compatibility_record(
        evidence_root=EVIDENCE_ROOT,
        content={
            "__build__": {
                "plan_package_id": plan_id,
                "plan_fingerprint": plan_fp,
                "invalidated_plan_package_id": invalid["package_id"],
                "invalidated_plan_fingerprint": invalid["fingerprint"],
                "worktree": WORKTREE,
                "code_commit": commit,
                "runner_schema": "phase8n.development-evaluation-runner.v1",
                "runner_version": "phase8n-runner-v1",
                "test_node_ids": [
                    "backtests/development_evaluation_control.py",
                    "tests/phase8n_g/test_development_evaluation_runner.py",
                    "tests/phase8n_i/test_empirical_input_pipeline.py",
                    "tests/phase8n_j/test_replay_input_index.py",
                    "tests/phase8n_k/test_market_feature_store.py",
                ],
            }
        },
    )
    print("published:", content_id)
    print("path:", content_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
