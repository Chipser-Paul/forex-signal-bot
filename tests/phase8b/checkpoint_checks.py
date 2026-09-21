"""Offline checkpoint verification. Never imports the real MT5 package."""
from __future__ import annotations

import argparse
import ast
import importlib
import importlib.abc
import json
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from bot.acquisition.safety import strip_sensitive_environment

ROOT = Path(__file__).resolve().parents[2]


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], env=strip_sensitive_environment())


class NoMT5(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "MetaTrader5":
            raise AssertionError("real MT5 import prohibited")
        return None


def blocked_network(*args, **kwargs):
    raise AssertionError("network prohibited during verification")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--base", default="c84fb39", help="acquisition checkpoint to compare")
    args = parser.parse_args()
    sys.meta_path.insert(0, NoMT5())
    socket.socket.connect = blocked_network
    socket.create_connection = blocked_network
    from detect_secrets.core.secrets_collection import SecretsCollection
    from detect_secrets.settings import default_settings
    import jsonschema
    import yaml

    paths = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z") if args.staged else git("ls-files", "-z")
    names = [name for name in paths.decode().split("\0") if name]
    scan_names = set(names) if args.staged else set(
        git("diff", args.base, "--name-only", "--diff-filter=ACMR").decode().splitlines()
    )
    if not args.staged:
        names += [str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "tests/phase8b").glob("*.py")]
        names += [str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "bot/acquisition").glob("*.py")]
        scan_names.update(name for name in names if name.startswith(("tests/phase8b/", "bot/acquisition/")))
    counts = {"python": 0, "json": 0, "yaml": 0, "schemas": 0, "scanned_files": 0}
    findings = []
    order_paths = []
    prohibited = {"login", "account_info", "positions_get", "orders_get", "history_orders_get",
                  "history_deals_get", "order_check", "order_send", "order_calc_margin", "order_calc_profit"}
    with tempfile.TemporaryDirectory(prefix="acquisition-scan-") as temporary, default_settings():
        for name in sorted(set(names)):
            data = git("show", ":" + name) if args.staged else (ROOT / name).read_bytes()
            suffix = Path(name).suffix.lower()
            if suffix == ".py":
                compile(data, name, "exec")
                counts["python"] += 1
                tree = ast.parse(data, filename=name)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                        if node.func.attr == "order_send" and not name.startswith("tests/"):
                            order_paths.append(name)
                        if (name.startswith("bot/acquisition/") or name == "backtests/empirical_data_control.py") and node.func.attr in prohibited:
                            raise AssertionError("forbidden acquisition API: " + name)
            elif suffix == ".json":
                value = json.loads(data)
                counts["json"] += 1
                if name.endswith(".schema.json"):
                    jsonschema.validators.validator_for(value).check_schema(value)
                    counts["schemas"] += 1
            elif suffix in {".yml", ".yaml"}:
                yaml.safe_load(data)
                counts["yaml"] += 1
            if name not in scan_names or b"\0" in data:
                continue
            try:
                data.decode("utf-8-sig")
            except UnicodeDecodeError:
                continue
            target = Path(temporary) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            secrets = SecretsCollection()
            secrets.scan_file(str(target))
            counts["scanned_files"] += 1
            if secrets:
                findings.append(name)
    for name in ("bot.acquisition.gateway", "bot.acquisition.preflight", "bot.acquisition.exporter",
                 "bot.acquisition.storage", "bot.acquisition.safety", "backtests.empirical_data_control"):
        module = importlib.import_module(name)
        assert Path(module.__file__).is_relative_to(ROOT)
    assert "MetaTrader5" not in sys.modules
    assert set(order_paths) <= {"bot/execution/broker/adapter.py"}, order_paths
    print(json.dumps({"staged": args.staged, "counts": counts, "secret_findings": findings,
                      "safe_imports": 6, "real_mt5_imported": False, "order_send_paths": sorted(set(order_paths))}, sort_keys=True))
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
