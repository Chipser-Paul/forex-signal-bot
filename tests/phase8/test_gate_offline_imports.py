from pathlib import Path
import sys

from tests.conftest import REAL_POPEN


def test_offline_orchestration_imports_without_terminal_or_network():
    root = Path(__file__).resolve().parents[2]
    script = f"""
import importlib.abc
import socket
import sys
sys.path.insert(0, {str(root)!r})
class NoTerminal(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'MetaTrader5' or fullname.startswith('MetaTrader5.'):
            raise AssertionError('offline orchestration imported MT5')
sys.meta_path.insert(0, NoTerminal())
def forbidden(*args, **kwargs):
    raise AssertionError('offline import contacted a network')
socket.create_connection = forbidden
socket.socket.connect = forbidden
from bot.state.gate_inputs import StrategyEvaluationInputs
from bot.state.gate_reducer import evaluate_strategy_gates
from bot.state.orchestrator import StrategyOrchestrator, OrchestratorAcquisition
from bot.strategy.setup_state import SetupStateRecord
from bot.strategy.setup_intent import intent_from_setup_levels
from bot.strategy.setup_consumption import SetupConsumptionEvent
from bot.strategy.setup_recovery import SetupRecoveryCoordinator
from bot.strategy.setup_store import SetupReplayStore
from bot.backtesting.fill_journal import HistoricalFillJournal
from bot.validation.development_plan_revision import build_revision
from bot.validation.recovery_plan_correction import build_corrected_revision
from bot.validation.empirical_strategy_adapter import evaluate_historical_orchestration
assert 'MetaTrader5' not in sys.modules
print('offline imports verified')
"""
    process = REAL_POPEN(
        [sys.executable, "-I", "-c", script], cwd=root,
        stdout=-1, stderr=-1, text=True,
    )
    stdout, stderr = process.communicate(timeout=30)
    assert process.returncode == 0, stderr
    assert stdout.strip() == "offline imports verified"
