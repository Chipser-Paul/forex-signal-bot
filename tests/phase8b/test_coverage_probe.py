from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backtests import empirical_data_control
from backtests.empirical_data_control import _shutdown_gateway
from bot.acquisition.benchmark import AcquisitionBenchmark
from bot.acquisition.coverage_probe import (
    COARSE_STARTS,
    DEVELOPMENT_END,
    RECENT_CONTROL,
    TARGET_CONTROL,
    TickCoverageProbe,
    verify_coverage_probe,
)
from bot.acquisition.gateway import ReadOnlyMT5Gateway
from bot.acquisition.journal import BenchmarkJournal

from .helpers import FakeReadOnlyMT5


UTC = timezone.utc


class ProbeMT5(FakeReadOnlyMT5):
    def __init__(self) -> None:
        super().__init__()
        self.tick_counts: dict[datetime, int] = {}
        self.bar_counts: dict[datetime, int] = {}
        self.none_starts: set[datetime] = set()
        self.error_by_start: dict[datetime, tuple[int, str]] = {}

    def copy_ticks_range(self, symbol, start, end, flags):
        self._call("copy_ticks_range", symbol, start, end, flags)
        self.last_error_value = self.error_by_start.get(start, (1, "Success"))
        if start in self.none_starts:
            return None
        return [object()] * self.tick_counts.get(start, 0)

    def copy_rates_range(self, symbol, timeframe, start, end):
        self._call("copy_rates_range", symbol, timeframe, start, end)
        self.last_error_value = self.error_by_start.get(start, (1, "Success"))
        if start in self.none_starts:
            return None
        return [object()] * self.bar_counts.get(start, 0)


def _run_probe(tmp_path, mt5: ProbeMT5, **kwargs):
    gateway = ReadOnlyMT5Gateway(mt5)
    gateway.initialize(confirmed_read_only_demo_export=True)
    journal = BenchmarkJournal.create(tmp_path, "coverage")
    result = TickCoverageProbe(
        gateway, tmp_path, journal, m5_timeframe=mt5.TIMEFRAME_M5, **kwargs
    ).run()
    journal.append("MT5_SHUTDOWN_STARTED", status="RUNNING")
    gateway.shutdown()
    journal.append("MT5_SHUTDOWN_COMPLETED", status="SUCCEEDED")
    journal.append("RUN_COMPLETED", status="PASSED", exit_status=0)
    return result, journal


def _complete_october_hour(mt5: ProbeMT5) -> datetime:
    october = datetime(2024, 10, 1, 12, tzinfo=UTC)
    mt5.tick_counts.update({
        RECENT_CONTROL: 3136,
        COARSE_STARTS[0]: 500,
        october: 500,
        october + timedelta(minutes=15): 500,
        october + timedelta(minutes=30): 500,
        october + timedelta(minutes=45): 500,
    })
    mt5.bar_counts[TARGET_CONTROL] = 3
    return october


@pytest.mark.unit
def test_probe_brackets_retention_and_authorizes_only_complete_pre2025_hour(tmp_path):
    mt5 = ProbeMT5()
    october = _complete_october_hour(mt5)
    result, journal = _run_probe(tmp_path, mt5)

    assert result["conclusion"] == "TICK_RETENTION_LIMITATION"
    assert result["recent_positive_control_rows"] == 3136
    assert result["target_tick_rows"] == 0 and result["target_bar_rows"] == 3
    assert result["complete_development_hour_start"] == october.isoformat().replace("+00:00", "Z")
    assert result["conditional_benchmark_authorized"] is True
    assert result["tick_request_count"] <= 30 and result["bar_request_count"] <= 10
    assert result["availability_monotonic"] is True
    assert verify_coverage_probe(journal.run_dir) == result
    assert not any(path.suffix in {".gz", ".parquet"} for path in journal.run_dir.rglob("*"))


@pytest.mark.unit
def test_probe_distinguishes_none_api_error_from_successful_empty_array(tmp_path):
    mt5 = ProbeMT5()
    mt5.none_starts.add(RECENT_CONTROL)
    mt5.error_by_start[RECENT_CONTROL] = (-4, "terminal path C:\\private\\terminal 12345678")
    result, _journal = _run_probe(tmp_path, mt5)
    observations = {item["interval_id"]: item for item in result["observations"]}

    assert result["conclusion"] == "GATEWAY_SESSION_DEFECT"
    assert observations["recent-positive-control"]["response_kind"] == "NONE"
    assert observations["recent-positive-control"]["classification"] == "API_ERROR"
    assert observations["target-2024-control"]["response_kind"] == "EMPTY_ARRAY"
    assert observations["target-2024-control"]["classification"] == "EMPTY_SUCCESS_RESPONSE"
    assert "private" not in repr(result).lower()


@pytest.mark.unit
def test_probe_captures_last_error_immediately_after_every_history_request(tmp_path):
    mt5 = ProbeMT5()
    mt5.tick_counts[RECENT_CONTROL] = 1
    _result, _journal = _run_probe(tmp_path, mt5)
    history_indexes = [
        index for index, (name, _args, _kwargs) in enumerate(mt5.calls)
        if name in {"copy_ticks_range", "copy_rates_range"}
    ]
    assert history_indexes
    assert all(mt5.calls[index + 1][0] == "last_error" for index in history_indexes)


@pytest.mark.unit
def test_non_monotonic_or_incomplete_hour_blocks_conditional_benchmark(tmp_path):
    mt5 = ProbeMT5()
    october = _complete_october_hour(mt5)
    mt5.tick_counts.pop(october + timedelta(minutes=15))
    result, _journal = _run_probe(tmp_path, mt5)
    assert result["availability_monotonic"] is False
    assert result["conclusion"] == "INTERMITTENT_OR_AMBIGUOUS"
    assert result["conditional_benchmark_authorized"] is False


@pytest.mark.unit
def test_probe_timeout_is_bounded_before_request(tmp_path):
    class Clock:
        value = 0.0

        def __call__(self):
            self.value += 2.0
            return self.value

    mt5 = ProbeMT5()
    gateway = ReadOnlyMT5Gateway(mt5)
    gateway.initialize(confirmed_read_only_demo_export=True)
    journal = BenchmarkJournal.create(tmp_path, "coverage")
    with pytest.raises(TimeoutError, match="wall limit"):
        TickCoverageProbe(
            gateway,
            tmp_path,
            journal,
            m5_timeframe=mt5.TIMEFRAME_M5,
            monotonic=Clock(),
            maximum_wall_seconds=1,
        ).run()
    assert not any(name == "copy_ticks_range" for name, _args, _kwargs in mt5.calls)


@pytest.mark.unit
def test_probe_schedule_avoids_weekends_and_never_enters_strategy(tmp_path):
    mt5 = ProbeMT5()
    mt5.tick_counts[RECENT_CONTROL] = 1
    result, _journal = _run_probe(tmp_path, mt5)
    assert all(datetime.fromisoformat(item["requested_start"].replace("Z", "+00:00")).weekday() < 5
               for item in result["observations"])
    assert result["strategy_evaluated"] is False
    assert result["profitability_evaluated"] is False
    assert result["raw_ticks_persisted"] is False


@pytest.mark.unit
def test_shutdown_status_is_independent_of_run_failure(tmp_path):
    mt5 = ProbeMT5()
    gateway = ReadOnlyMT5Gateway(mt5)
    journal = BenchmarkJournal.create(tmp_path, "coverage")
    assert _shutdown_gateway(journal, gateway) is None
    assert journal.records()[-1]["status"] == "ALREADY_DISCONNECTED"

    gateway.initialize(confirmed_read_only_demo_export=True)
    assert _shutdown_gateway(journal, gateway) is None
    assert journal.records()[-1]["status"] == "SUCCEEDED"


@pytest.mark.unit
def test_shutdown_failure_is_classified_without_hiding_original_failure(tmp_path):
    class FailingGateway:
        is_initialized = True

        @staticmethod
        def shutdown():
            raise RuntimeError("sensitive raw failure")

    journal = BenchmarkJournal.create(tmp_path, "coverage")
    failure = _shutdown_gateway(journal, FailingGateway())
    assert isinstance(failure, RuntimeError)
    final = journal.records()[-1]
    assert final["status"] == "FAILED"
    assert final["error_category"] == "MT5_SHUTDOWN_FAILED"
    assert "sensitive" not in repr(final).lower()


@pytest.mark.unit
def test_probe_constants_remain_bounded_and_development_gate_is_strict():
    assert len(COARSE_STARTS) < 30
    assert all(value.weekday() in {1, 2} and value.hour == 12 for value in COARSE_STARTS)
    assert TARGET_CONTROL < DEVELOPMENT_END < RECENT_CONTROL


@pytest.mark.unit
@pytest.mark.parametrize("benchmark_authorized", [False, True])
def test_coverage_worker_uses_one_session_and_conditionally_runs_one_benchmark(
    tmp_path, monkeypatch, benchmark_authorized
):
    mt5 = ProbeMT5()
    owner = tmp_path / "owner"
    state = owner / "frontend" / "utils"
    state.mkdir(parents=True)
    (state / ".bot_state.json").write_text('{"state":"stopped"}', encoding="utf-8")
    output = tmp_path / "output"
    journal = BenchmarkJournal.create(output, "coverage")
    monkeypatch.setattr(empirical_data_control, "windows_process_snapshot", lambda: ())
    monkeypatch.setattr(empirical_data_control.importlib, "import_module", lambda _name: mt5)
    monkeypatch.setattr(
        TickCoverageProbe,
        "run",
        lambda _self: {
            "conditional_benchmark_authorized": benchmark_authorized,
            "complete_development_hour_start": (
                "2024-10-01T12:00:00Z" if benchmark_authorized else None
            ),
        },
    )
    benchmark_calls: list[tuple[datetime, datetime]] = []

    def run_benchmark(instance, **_kwargs):
        benchmark_calls.append(instance.interval)
        return {"status": "VERIFIED"}

    monkeypatch.setattr(AcquisitionBenchmark, "run", run_benchmark)
    exit_code = empirical_data_control.main([
        "probe-tick-coverage", "--_coverage-worker", "--_benchmark-run-id", journal.run_id,
        "--confirm-read-only-demo-export", "--owner-worktree", str(owner),
        "--output-root", str(output), "--minimum-free-gb", "0", "--maximum-output-gb", "1",
    ])
    assert exit_code == 0
    assert [name for name, _args, _kwargs in mt5.calls].count("initialize") == 1
    assert [name for name, _args, _kwargs in mt5.calls].count("shutdown") == 1
    assert len(benchmark_calls) == int(benchmark_authorized)
    assert BenchmarkJournal.open(journal.run_dir).state()["terminal_event"] == "RUN_COMPLETED"


@pytest.mark.unit
def test_probe_requires_confirmation_before_git_process_or_mt5(monkeypatch):
    monkeypatch.setattr(
        empirical_data_control,
        "_worktree_roots",
        lambda: (_ for _ in ()).throw(AssertionError("git must not run")),
    )
    monkeypatch.setattr(
        empirical_data_control,
        "windows_process_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("process scan must not run")),
    )
    assert empirical_data_control.main(["probe-tick-coverage"]) == 2
