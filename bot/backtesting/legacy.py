from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import FidelityClass


def classify_phase1_legacy_inventory(manifest_path: Path) -> dict[str, Any]:
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    data = payload["backtest_data"]
    results = payload["backtest_results"]
    return {
        "fidelity_class": FidelityClass.INSUFFICIENT_FOR_VALIDATION.value,
        "result_label": "DIAGNOSTIC \u2014 NOT VALIDATED",
        "result_set_count": int(results["result_set_count"]),
        "cache_pickle_count": int(data["tracked_pickle_count"]),
        "result_tree_sha1": results["git_tree_sha1_at_phase0_parent"],
        "cache_tree_sha1": data["git_tree_sha1"],
        "reason_codes": [
            "MISSING_BID_ASK_PROVENANCE",
            "MISSING_SLIPPAGE_PROVENANCE",
            "MISSING_COMMISSION_PROVENANCE",
            "MISSING_SWAP_PROVENANCE",
            "MISSING_INTRABAR_PATH",
            "MISSING_REPRODUCIBLE_RUN_MANIFEST",
        ],
        "preserved_read_only": True,
        "profitability_evidence": False,
    }
