"""
Nifty option-selling strategy:

- PE leg: short one ITM PE on the monthly expiry, entered near a target
  premium. Held; squared off automatically on its expiry day.
- CE leg: short one ATM CE on the weekly expiry, entered near a target
  premium. Continuously rolled: whenever its premium decays below a
  threshold AND the strike has drifted OTM relative to spot, it is bought
  back and a fresh ATM CE is sold immediately.

Both legs are tracked in StateStore so a restart doesn't lose track of
what's open, and reconcile_from_broker() adopts any matching short option
position already open at the broker (e.g. after a crash-restart with a
lost/replaced state file) instead of blindly opening a duplicate.
"""

import logging
from datetime import date, datetime

from .instruments import InstrumentStore, find_strike_by_target_premium, is_otm

logger = logging.getLogger(__name__)


class NiftyOptionSellerStrategy:
    def __init__(self, kite, store: InstrumentStore, orders, state, risk, notifier, config: dict):
        self.kite = kite
        self.store = store
        self.orders = orders
        self.state = state
        self.risk = risk
        self.notifier = notifier
        self.config = config
        self.underlying_cfg = config["underlying"]
        self.pe_cfg = config["pe_leg"]
        self.ce_cfg = config["ce_leg"]

    def get_spot(self) -> float:
        symbol = self.underlying_cfg["spot_symbol"]
        return self.kite.ltp([symbol])[symbol]["last_price"]

    def _quote_ltp(self, exchange: str, tradingsymbol: str) -> float:
        key = f"{exchange}:{tradingsymbol}"
        return self.kite.ltp([key])[key]["last_price"]

    def reconcile_from_broker(self):
        """Adopt any already-open short NIFTY option position at the broker into state."""
        try:
            positions = self.kite.positions().get("net", [])
        except Exception as e:
            logger.warning("Could not fetch broker positions for reconciliation: %s", e)
            return

        name = self.underlying_cfg["name"]
        for pos in positions:
            if pos.get("exchange") != "NFO" or pos.get("quantity", 0) >= 0:
                continue
            tradingsymbol = pos["tradingsymbol"]
            if name not in tradingsymbol:
                continue
            if tradingsymbol.endswith("CE"):
                option_type, leg_name = "CE", "CE"
            elif tradingsymbol.endswith("PE"):
                option_type, leg_name = "PE", "PE"
            else:
                continue

            if self.state.get_leg(leg_name):
                continue

            strike = self.store.strike_for_tradingsymbol(name, tradingsymbol) or 0.0
            quantity = abs(pos["quantity"])
            entry_price = abs(pos["average_price"])
            self.state.set_leg(leg_name, tradingsymbol, pos["instrument_token"], pos["exchange"],
                                strike, option_type, quantity, entry_price)
            logger.info("Reconciled existing broker position into state: %s", tradingsymbol)
            self.notifier.send(f"Adopted existing broker position on startup: {tradingsymbol} x{quantity}")

    def ensure_pe_leg(self):
        if not self.pe_cfg.get("enabled", True) or self.state.get_leg("PE"):
            return

        spot = self.get_spot()
        expiry = self.store.monthly_expiry(self.underlying_cfg["name"], date.today())
        info = find_strike_by_target_premium(
            self.kite, self.store, self.underlying_cfg["name"], expiry, "PE", spot,
            self.underlying_cfg["strike_step"], self.pe_cfg["target_premium"],
            self.pe_cfg["premium_tolerance"], self.pe_cfg["strike_search_range"], "ITM",
        )
        quantity = self.pe_cfg["quantity_lots"] * info["lot_size"]
        fill = self.orders.sell_to_open(info["tradingsymbol"], info["exchange"], quantity,
                                         info["premium"], self.pe_cfg["product"])
        self.state.set_leg("PE", info["tradingsymbol"], info["instrument_token"], info["exchange"],
                            info["strike"], "PE", quantity, fill)
        self.state.log_roll("PE", "ENTER", info["tradingsymbol"], fill, quantity)
        self.notifier.send(f"PE leg opened: SELL {info['tradingsymbol']} x{quantity} @ {fill:.2f}")

    def ensure_ce_leg(self):
        if not self.ce_cfg.get("enabled", True) or self.state.get_leg("CE"):
            return
        self._open_ce_leg()

    def _open_ce_leg(self):
        spot = self.get_spot()
        expiry = self.store.weekly_expiry(self.underlying_cfg["name"], date.today())
        info = find_strike_by_target_premium(
            self.kite, self.store, self.underlying_cfg["name"], expiry, "CE", spot,
            self.underlying_cfg["strike_step"], self.ce_cfg["target_premium"],
            self.ce_cfg["premium_tolerance"], self.ce_cfg["strike_search_range"],
            self.ce_cfg["reentry_moneyness"],
        )
        quantity = self.ce_cfg["quantity_lots"] * info["lot_size"]
        fill = self.orders.sell_to_open(info["tradingsymbol"], info["exchange"], quantity,
                                         info["premium"], self.ce_cfg["product"])
        self.state.set_leg("CE", info["tradingsymbol"], info["instrument_token"], info["exchange"],
                            info["strike"], "CE", quantity, fill)
        self.state.log_roll("CE", "ENTER", info["tradingsymbol"], fill, quantity)
        self.notifier.send(f"CE leg opened: SELL {info['tradingsymbol']} x{quantity} @ {fill:.2f}")
        return info

    def _can_roll_now(self) -> bool:
        row = self.state.today_state()
        if row["roll_count"] >= self.ce_cfg["max_rolls_per_day"]:
            logger.warning("Max CE rolls/day reached (%s) — not rolling further today", row["roll_count"])
            return False
        if row["last_roll_time"]:
            elapsed = (datetime.now() - datetime.fromisoformat(row["last_roll_time"])).total_seconds()
            if elapsed < self.ce_cfg["min_seconds_between_rolls"]:
                return False
        return True

    def check_ce_roll(self, ce_ltp: float, spot: float):
        """Call on every fresh CE tick/quote: exit + re-enter ATM if the roll condition is met."""
        leg = self.state.get_leg("CE")
        if not leg:
            return

        threshold = self.ce_cfg["exit_premium_threshold"]
        requires_otm = self.ce_cfg.get("exit_requires_otm", True)
        strike_is_otm = is_otm("CE", leg["strike"], spot)

        should_exit = ce_ltp < threshold and (strike_is_otm or not requires_otm)
        if not should_exit or not self._can_roll_now():
            return

        pnl = (leg["entry_price"] - ce_ltp) * leg["quantity"]
        fill = self.orders.buy_to_close(leg["tradingsymbol"], leg["exchange"], leg["quantity"],
                                         ce_ltp, self.ce_cfg["product"])
        realized = (leg["entry_price"] - fill) * leg["quantity"]
        self.state.log_roll("CE", "EXIT", leg["tradingsymbol"], fill, leg["quantity"], note=f"pnl={realized:.2f}")
        self.state.add_realized_pnl(realized)
        self.state.clear_leg("CE")
        self.notifier.send(
            f"CE leg rolled: BUY {leg['tradingsymbol']} x{leg['quantity']} @ {fill:.2f} "
            f"(pnl {realized:.2f}) — opening fresh ATM CE"
        )

        self._open_ce_leg()

    def square_off_leg_if_near_expiry(self, leg_name: str, cfg: dict, now: datetime):
        leg = self.state.get_leg(leg_name)
        if not leg:
            return
        close_cfg = cfg.get("close_before_expiry", {})
        if not close_cfg.get("enabled", True):
            return

        name = self.underlying_cfg["name"]
        expiry = (self.store.weekly_expiry(name, now.date()) if leg_name == "CE"
                  else self.store.monthly_expiry(name, now.date()))
        if now.date() != expiry:
            return

        h, m = close_cfg.get("time", "15:15").split(":")
        cutoff = now.time().replace(hour=int(h), minute=int(m), second=0, microsecond=0)
        if now.time() < cutoff:
            return

        ltp = self._quote_ltp(leg["exchange"], leg["tradingsymbol"])
        fill = self.orders.buy_to_close(leg["tradingsymbol"], leg["exchange"], leg["quantity"], ltp, cfg["product"])
        pnl = (leg["entry_price"] - fill) * leg["quantity"]
        self.state.log_roll(leg_name, "EXPIRY_SQUAREOFF", leg["tradingsymbol"], fill, leg["quantity"],
                             note=f"pnl={pnl:.2f}")
        self.state.add_realized_pnl(pnl)
        self.state.clear_leg(leg_name)
        self.notifier.send(f"{leg_name} leg squared off before expiry: {leg['tradingsymbol']} @ {fill:.2f} (pnl {pnl:.2f})")

    def square_off_all(self, reason: str):
        for leg_name, cfg in (("PE", self.pe_cfg), ("CE", self.ce_cfg)):
            leg = self.state.get_leg(leg_name)
            if not leg:
                continue
            ltp = self._quote_ltp(leg["exchange"], leg["tradingsymbol"])
            fill = self.orders.buy_to_close(leg["tradingsymbol"], leg["exchange"], leg["quantity"], ltp, cfg["product"])
            pnl = (leg["entry_price"] - fill) * leg["quantity"]
            self.state.log_roll(leg_name, "SQUAREOFF", leg["tradingsymbol"], fill, leg["quantity"], note=reason)
            self.state.add_realized_pnl(pnl)
            self.state.clear_leg(leg_name)
            self.notifier.send(f"{leg_name} leg squared off ({reason}): {leg['tradingsymbol']} @ {fill:.2f} (pnl {pnl:.2f})")
