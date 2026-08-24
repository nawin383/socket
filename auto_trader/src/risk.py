"""Trading-hours, kill-switch, and daily-loss guardrails."""

import logging
from datetime import datetime, time as dtime
from pathlib import Path

logger = logging.getLogger(__name__)


def _parse_time(value: str) -> dtime:
    h, m = value.split(":")
    return dtime(int(h), int(m))


class RiskGuard:
    def __init__(self, config: dict, state, kill_switch_path: Path):
        self.config = config
        self.state = state
        self.kill_switch_path = kill_switch_path
        self.trading_start = _parse_time(config["trading_start"])
        self.trading_end = _parse_time(config["trading_end"])
        self.eod_square_off_time = _parse_time(config["eod_square_off_time"])
        self.max_daily_loss = config["max_daily_loss"]
        self.holidays = set(config.get("holidays", []))

    def is_trading_day(self, now: datetime) -> bool:
        if now.weekday() >= 5:
            return False
        return now.date().isoformat() not in self.holidays

    def is_market_open(self, now: datetime) -> bool:
        if not self.is_trading_day(now):
            return False
        return self.trading_start <= now.time() <= self.trading_end

    def is_eod_square_off_time(self, now: datetime) -> bool:
        return now.time() >= self.eod_square_off_time

    def kill_switch_active(self) -> bool:
        return self.kill_switch_path.exists()

    def daily_loss_breached(self) -> bool:
        row = self.state.today_state()
        breached = row["realized_pnl"] <= -abs(self.max_daily_loss)
        if breached:
            logger.error("Daily loss limit breached: realized_pnl=%.2f", row["realized_pnl"])
        return breached

    def trading_allowed(self, now: datetime) -> bool:
        if self.kill_switch_active():
            logger.warning("Kill switch file present (%s) — new entries/rolls are paused", self.kill_switch_path)
            return False
        if self.daily_loss_breached():
            return False
        return self.is_market_open(now)
