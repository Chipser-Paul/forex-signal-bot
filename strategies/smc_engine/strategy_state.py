# strategies/smc_engine/strategy_state.py
# Persistent SMC strategy state per symbol

from datetime import datetime, timedelta
from utils.log import log

STATE_EXPIRY_MINUTES = 120
LIQUIDITY_TIMEOUT_BARS = 6   # max candles to wait after liquidity
MAX_LIQUIDITY_CANDLES = 12
CASCADE_BLOCK_HOURS = 12      # hours to block re-entry after 2 same-direction losses
STATES = [
    "MAPPING_STRUCTURE",
    "SCANNING_FOR_SETUP",
    "SETUP_FOUND_PENDING_CONFIRMATION",
    "TRADE_ACTIVE",
    "DAILY_LIMIT_HIT",
    "NEWS_BLACKOUT",
]


class StrategyState:
    def __init__(self):
        self.reset()

    # -------------------------------------------------
    # Reset
    # -------------------------------------------------
    def reset(self):
        self.state_name = "MAPPING_STRUCTURE"

        # Core SMC state
        self.structure_dir = None          # 'bullish' | 'bearish'

        # Liquidity tracking
        self.liquidity_swept = False
        self.liquidity_side = None         # 'buy' | 'sell'
        self.liquidity_type = None         # 'equal_highs', 'equal_lows', 'internal_continuation', 'trend_continuation'
        self.liquidity_index = None        # candle index when detected
        self.liquidity_time = None

        # Displacement / imbalance
        self.displacement_seen = False
        self.fvg_zone = None               # (low, high) or None

        # Partial entry tracking
        self.entry_started = False         # first entry executed
        self.remaining_entries = []        # queued partial entries

        # Context & setup candidate tracking
        self.setup_candidate = None
        self.setup_score = 0
        self.setup_grade = None
        self.trade_direction = None
        self.entry_mode = None
        self.ob_zone = None
        self.asian_sweep_detected = False
        self.bias_snapshot = None
        self.session_context = None
        self.news_status = None
        self.daily_limits_hit = False
        self.last_rejection_reason = None

        self.last_update = datetime.utcnow()

        # Cascade circuit breaker tracking
        self._consecutive_same_dir_losses = 0
        self._last_trade_direction = None       # last trade direction (bullish/bearish)
        self._last_trade_result = None          # "win" or "loss"
        self._direction_blocked_until = None    # datetime or None

        # Tracks missing conditions for entry diagnostics
        self.missing_conditions = []
        self.structure_state = None

    # -------------------------------------------------
    # Expiry & timeout checks
    # -------------------------------------------------
    def is_expired(self) -> bool:
        return datetime.utcnow() - self.last_update > timedelta(minutes=STATE_EXPIRY_MINUTES)

    def liquidity_timed_out(self, current_index: int) -> bool:
        """
        Returns True if liquidity was swept but no displacement
        occurred within allowed bars.
        """
        if not self.liquidity_swept or self.liquidity_index is None:
            return False
        return (current_index - self.liquidity_index) > LIQUIDITY_TIMEOUT_BARS

    # -------------------------------------------------
    # Update methods
    # -------------------------------------------------
    def update_structure(self, direction: str, state: str):
        # If structure direction flips -> FULL RESET
        if self.structure_dir and self.structure_dir != direction:
            self.reset()

        self.structure_dir = direction
        self.structure_state = state
        if state == "confirmed":
            self.state_name = "SCANNING_FOR_SETUP"
        self.last_update = datetime.utcnow()

    def update_liquidity(self, side: str, index: int, liquidity_type: str | None = None):
        """
        Update liquidity sweep info in the state.

        side: 'buy' or 'sell'
        index: candle index
        liquidity_type: 'equal_highs', 'equal_lows', 'internal_continuation', 'trend_continuation'
        """
        # sanitize side
        if side not in ("buy", "sell"):
            log(f"[ERROR] Invalid liquidity side received: {side} -> forcing None", "red")
            self.liquidity_side = None
        else:
            self.liquidity_side = side

        self.liquidity_swept = True
        self.liquidity_type = liquidity_type
        self.liquidity_index = index
        self.liquidity_time = datetime.utcnow()
        self.state_name = "SETUP_FOUND_PENDING_CONFIRMATION"
        self.last_update = datetime.utcnow()

    def update_displacement(self, fvg: tuple | None = None):
        self.displacement_seen = True
        self.fvg_zone = fvg
        self.last_update = datetime.utcnow()

    def update_bias(self, bias_snapshot: dict | None):
        self.bias_snapshot = bias_snapshot
        self.last_update = datetime.utcnow()

    def update_session(self, session_context: dict | None):
        self.session_context = session_context
        self.last_update = datetime.utcnow()

    def update_news(self, news_status: dict | None):
        self.news_status = news_status
        if news_status and not news_status.get("news_clear", True):
            self.state_name = "NEWS_BLACKOUT"
        self.last_update = datetime.utcnow()

    def set_daily_limit_hit(self, hit: bool, reason: str | None = None):
        self.daily_limits_hit = bool(hit)
        if self.daily_limits_hit:
            self.state_name = "DAILY_LIMIT_HIT"
            self.last_rejection_reason = reason or "daily_limit_hit"
        elif self.state_name == "DAILY_LIMIT_HIT":
            self.state_name = "SCANNING_FOR_SETUP"
        self.last_update = datetime.utcnow()

    def register_setup_candidate(
        self,
        *,
        trade_direction: str,
        score: int = 0,
        grade: str | None = None,
        entry_mode: str | None = None,
        ob_zone=None,
        fvg_zone=None,
        asian_sweep: bool = False,
        metadata: dict | None = None,
    ):
        self.setup_candidate = {
            "trade_direction": trade_direction,
            "score": score,
            "grade": grade,
            "entry_mode": entry_mode,
            "ob_zone": ob_zone,
            "fvg_zone": fvg_zone,
            "asian_sweep": asian_sweep,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
        }
        self.setup_score = score
        self.setup_grade = grade
        self.trade_direction = trade_direction
        self.entry_mode = entry_mode
        self.ob_zone = ob_zone
        self.fvg_zone = fvg_zone
        self.asian_sweep_detected = asian_sweep
        self.state_name = "SETUP_FOUND_PENDING_CONFIRMATION"
        self.last_update = datetime.utcnow()

    def register_entry_plan(self, entries: list):
        """
        Store partial entry plan from entry_model.
        """
        self.entry_started = False
        self.remaining_entries = entries.copy()
        self.last_update = datetime.utcnow()

    def mark_entry_filled(self):
        self.entry_started = True
        self.state_name = "TRADE_ACTIVE"
        self.last_update = datetime.utcnow()

    def reject_setup(self, reason: str):
        self.setup_candidate = None
        self.setup_score = 0
        self.setup_grade = None
        self.entry_mode = None
        self.trade_direction = None
        self.last_rejection_reason = reason
        self.state_name = "SCANNING_FOR_SETUP"
        self.last_update = datetime.utcnow()

    # -------------------------------------------------
    # Cascade circuit breaker
    # -------------------------------------------------
    def record_trade_result(self, direction: str, result: str, now: datetime | None = None):
        """
        Track consecutive same-direction losses.
        After 2 same-direction losses in a row, block that direction for CASCADE_BLOCK_HOURS.
        A win in either direction resets the counter.
        """
        now = now or datetime.utcnow()
        if result == "loss" and direction == self._last_trade_direction:
            self._consecutive_same_dir_losses += 1
            if self._consecutive_same_dir_losses >= 2:
                self._direction_blocked_until = now + timedelta(hours=CASCADE_BLOCK_HOURS)
                log(f"[CASCADE] {direction} blocked until {self._direction_blocked_until.isoformat()} "
                    f"after {self._consecutive_same_dir_losses} consecutive losses", "yellow")
        elif result == "win":
            # Any win resets cascade tracking
            self._consecutive_same_dir_losses = 0
            self._direction_blocked_until = None
        else:
            # Opposite direction loss or unknown result
            self._consecutive_same_dir_losses = 0 if result == "loss" else self._consecutive_same_dir_losses

        self._last_trade_direction = direction if result == "loss" else None
        self._last_trade_result = result

    def is_direction_blocked(self, direction: str, now: datetime | None = None) -> bool:
        """
        Returns True if the given direction is currently blocked by the cascade breaker.
        """
        now = now or datetime.utcnow()
        if self._direction_blocked_until is None:
            return False
        if self._last_trade_direction is None:
            return False
        if direction != self._last_trade_direction:
            return False
        if now >= self._direction_blocked_until:
            # Cooldown expired — auto-clear
            self._direction_blocked_until = None
            self._consecutive_same_dir_losses = 0
            return False
        return True

    # -------------------------------------------------
    # State checks
    # -------------------------------------------------
    def ready_for_entry(self) -> bool:
        """
        Entry allowed only when:
        - Structure is defined
        - Liquidity is swept
        - Displacement is seen
        Also populates missing_conditions for diagnostics.
        """
        self.missing_conditions = []

        if self.structure_state != "confirmed":
            self.missing_conditions.append("Confirmed structure")
        if not self.liquidity_swept:
            self.missing_conditions.append("Liquidity sweep")
        if not self.displacement_seen:
            self.missing_conditions.append("Displacement / FVG")
        if self.daily_limits_hit:
            self.missing_conditions.append("Daily limit clear")
        if self.news_status and not self.news_status.get("news_clear", True):
            self.missing_conditions.append("News clear")
        return len(self.missing_conditions) == 0

    def invalidate_structure_if_needed(self):
        if self.structure_state in ("transition", "range"):
            self.structure_dir = None
            self.displacement_seen = False
            self.fvg_zone = None
            self.setup_candidate = None
            self.entry_mode = None
            self.setup_score = 0

    # -------------------------------------------------
    # Debug snapshot
    # -------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "state_name": self.state_name,
            "structure_dir": self.structure_dir,
            "liquidity_swept": self.liquidity_swept,
            "liquidity_side": self.liquidity_side,
            "liquidity_type": self.liquidity_type,
            "liquidity_index": self.liquidity_index,
            "displacement_seen": self.displacement_seen,
            "fvg_zone": self.fvg_zone,
            "entry_started": self.entry_started,
            "remaining_entries": len(self.remaining_entries),
            "last_update": self.last_update.isoformat(),
            "missing_conditions": self.missing_conditions.copy(),
            "structure_state": self.structure_state,
            "setup_score": self.setup_score,
            "setup_grade": self.setup_grade,
            "trade_direction": self.trade_direction,
            "entry_mode": self.entry_mode,
            "asian_sweep_detected": self.asian_sweep_detected,
            "daily_limits_hit": self.daily_limits_hit,
            "last_rejection_reason": self.last_rejection_reason,
        }
