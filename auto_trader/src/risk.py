"""Trading-hours, kill-switch, and daily-loss guardrails."""

import logging
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# All trading_start/trading_end/eod_square_off_time config values are IST
# wall-clock times (NSE's timezone). Callers must pass an `now` built with
# this tzinfo (datetime.now(IST)) — GitHub Actions runners and most VPS
# hosts default to UTC, and a naive datetime.now() compared against these
# IST times silently checks the wrong 5.5-hour window instead of raising.
IST = ZoneInfo("Asia/Kolkata")


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
        """Realized-only breach (legacy) — total check is total_loss_breached()."""
        row = self.state.today_state()
        breached = row["realized_pnl"] <= -abs(self.max_daily_loss)
        if breached:
            logger.error("Daily loss limit breached (realized): realized_pnl=%.2f", row["realized_pnl"])
        return breached

    def total_loss_breached(self, overall_pnl: float = None, kite=None, state=None, pe_ltp=None, ce_ltp=None) -> bool:
        """
        Total daily loss breach — realized + unrealized of open legs.

        If `overall_pnl` is provided directly (computed via Strategy._get_overall_pnl_today),
        it is used verbatim. Otherwise, if kite/state/pe/ce are provided, we compute
        total on the fly. This implements your ask: 'how will you determine based on
        todays loss or entire loss of the position because i will be closing few of the
        profitable position' — now both closed (realized) and open (unrealized) are counted,
        so MAXLOSS truly caps the day's net, not just closed legs.

        Returns True if overall_pnl <= -max_daily_loss.
        """
        if overall_pnl is None:
            # Compute via state + kite if possible
            try:
                from .strategy import NiftyOptionSellerStrategy  # avoid circular at import time
                # Fallback: compute here if caller didn't provide overall
                # Use state directly if available
                s = state or self.state
                row = s.today_state()
                realized = row["realized_pnl"] or 0.0
                unreal = 0.0
                if kite and s:
                    # Try to estimate unrealized if legs exist
                    for leg_name in ("PE", "CE"):
                        leg = s.get_leg(leg_name)
                        if not leg:
                            continue
                        ltp = pe_ltp if leg_name == "PE" else ce_ltp
                        if ltp is None and kite:
                            try:
                                key = f"{leg['exchange']}:{leg['tradingsymbol']}"
                                ltp = kite.ltp([key])[key]["last_price"]
                            except Exception:
                                ltp = None
                        if ltp is not None:
                            unreal += (leg["entry_price"] - ltp) * leg["quantity"]
                overall_pnl = realized + unreal
            except Exception:
                # Fallback to realized-only if computation fails
                row = self.state.today_state()
                overall_pnl = row["realized_pnl"]

        breached = overall_pnl <= -abs(self.max_daily_loss)
        if breached:
            logger.error("Daily loss limit breached (total): overall=%.2f (realized+unreal) vs limit -%s", overall_pnl, self.max_daily_loss)
        return breached

    def trading_allowed(self, now: datetime) -> bool:
        if self.kill_switch_active():
            logger.warning("Kill switch file present (%s) — new entries/rolls are paused", self.kill_switch_path)
            return False
        if self.daily_loss_breached():
            return False
        return self.is_market_open(now)
