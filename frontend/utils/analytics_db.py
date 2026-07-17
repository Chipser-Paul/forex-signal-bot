from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


_ROOT_ANALYTICS_DB = Path(__file__).resolve().parents[2] / "utils" / "analytics_db.py"


def _load_root_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("root_analytics_db", _ROOT_ANALYTICS_DB)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load analytics DB module from {_ROOT_ANALYTICS_DB}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ROOT_MODULE = _load_root_module()

fetch_analytics_details = _ROOT_MODULE.fetch_analytics_details
fetch_analytics_overview = _ROOT_MODULE.fetch_analytics_overview
fetch_recent_loop_snapshots = _ROOT_MODULE.fetch_recent_loop_snapshots
fetch_recent_no_trade_snapshots = _ROOT_MODULE.fetch_recent_no_trade_snapshots
fetch_recent_trade_reviews = _ROOT_MODULE.fetch_recent_trade_reviews
