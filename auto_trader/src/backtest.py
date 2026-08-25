"""
Backtest the PE stop-loss/re-entry and CE roll DECISION RULES against a
premium time series you supply.

Scope, read this before trusting the output: this is NOT a full
option-chain replay with automatic strike/expiry selection across time —
building that needs a historical option-chain database this repo doesn't
have, and Kite Connect's historical API has real limits on how far back
expired-contract data goes. What this DOES validate: "if premium had
followed this exact path, what would trigger_pct / exit_premium_threshold
/ discount_points have triggered, and what's the resulting PnL" — the same
trigger math as strategy.check_pe_stop_loss() / _place_pe_reentry() /
check_ce_roll(), reimplemented here as pure functions (no kite/state/order
objects) so it can run against a CSV instead of a live connection. Useful
for answering "is a 40% PE stop too tight/loose" or "how often would CE
have rolled at a 90 exit threshold" against real historical premium
levels — not for simulating the bot's full day-to-day strike selection.

Getting the input data: this session has no live market-data access —
run `kite.historical_data(instrument_token, from_date, to_date, "day")`
yourself (e.g. in a Python shell with your own Kite credentials) for the
specific contract(s) you want to test, then write it to CSV in the schema
below.

CSV schema:
  PE: date,premium                       one row per trading day for ONE
                                          held contract, from entry to
                                          expiry (or however far you have
                                          data), premiums only — no gaps.
  CE: date,premium,strike,spot           one row per trading day. Because
                                          a CE roll opens a NEW contract at
                                          a new strike, and this harness
                                          doesn't have live option-chain
                                          data to pick that new contract's
                                          premium path automatically, this
                                          only counts how many times the
                                          roll condition would have fired
                                          (a roll-frequency count), not a
                                          full re-entered-leg PnL chain
                                          like the PE side does.

Run: python -m src.backtest pe entry_premium quantity trigger_pct pe.csv
     python -m src.backtest ce exit_threshold ce.csv [--no-otm-required]
"""

import csv
import sys
from dataclasses import dataclass, field
from typing import List, Optional

from .instruments import is_otm


@dataclass
class PeBacktestRow:
    date: str
    premium: float


@dataclass
class PeTrade:
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    pnl_points: float
    action: str  # "STOP_LOSS" | "STOP_LOSS_REENTRY" | "HELD_TO_END"


def load_pe_csv(path: str) -> List[PeBacktestRow]:
    with open(path, newline="") as f:
        return [PeBacktestRow(row["date"], float(row["premium"])) for row in csv.DictReader(f)]


def backtest_pe_leg(
    rows: List[PeBacktestRow], entry_price: float, quantity: int, trigger_pct: float,
    reentry_enabled: bool = False, discount_points: float = 20.0,
) -> dict:
    """
    Pure reimplementation of check_pe_stop_loss()/_place_pe_reentry()'s
    trigger math against a premium time series for ONE contract. `rows`
    must be sorted by date ascending, starting the day after entry.
    """
    trigger_price = round(entry_price * (1 + trigger_pct / 100.0), 2)
    trades: List[PeTrade] = []
    state = "ORIGINAL"  # ORIGINAL -> WAITING_REENTRY -> REENTERED -> DONE
    reentry_trigger: Optional[float] = None
    current_entry_date = rows[0].date if rows else None
    current_entry_price = entry_price
    last_row: Optional[PeBacktestRow] = None

    for row in rows:
        last_row = row
        if state == "DONE":
            break
        if state == "ORIGINAL":
            if row.premium >= trigger_price:
                trades.append(PeTrade(
                    current_entry_date, current_entry_price, row.date, row.premium,
                    (current_entry_price - row.premium) * quantity, "STOP_LOSS",
                ))
                if reentry_enabled:
                    state = "WAITING_REENTRY"
                    reentry_trigger = trigger_price - discount_points
                else:
                    state = "DONE"
        elif state == "WAITING_REENTRY":
            if row.premium <= reentry_trigger:
                current_entry_date, current_entry_price = row.date, reentry_trigger
                state = "REENTERED"
        elif state == "REENTERED":
            # Flat stop at the ORIGINAL trigger price, not a fresh percentage —
            # matches check_pe_stop_loss()'s sl_reference_price behaviour.
            if row.premium >= trigger_price:
                trades.append(PeTrade(
                    current_entry_date, current_entry_price, row.date, row.premium,
                    (current_entry_price - row.premium) * quantity, "STOP_LOSS_REENTRY",
                ))
                state = "DONE"

    if state in ("ORIGINAL", "REENTERED") and last_row is not None:
        trades.append(PeTrade(
            current_entry_date, current_entry_price, last_row.date, last_row.premium,
            (current_entry_price - last_row.premium) * quantity, "HELD_TO_END",
        ))

    return {
        "trigger_price": trigger_price,
        "trades": trades,
        "total_pnl_points": sum(t.pnl_points for t in trades),
    }


@dataclass
class CeBacktestRow:
    date: str
    premium: float
    strike: float
    spot: float


@dataclass
class CeRollEvent:
    date: str
    strike: float
    premium: float
    spot: float


def load_ce_csv(path: str) -> List[CeBacktestRow]:
    with open(path, newline="") as f:
        return [
            CeBacktestRow(row["date"], float(row["premium"]), float(row["strike"]), float(row["spot"]))
            for row in csv.DictReader(f)
        ]


def backtest_ce_leg(rows: List[CeBacktestRow], exit_threshold: float, requires_otm: bool = True) -> dict:
    """
    Pure reimplementation of check_ce_roll()'s trigger condition. Counts how
    often premium < exit_threshold AND (OTM or not required) fires across
    the series — a roll-FREQUENCY estimate, not a full PnL chain (see
    module docstring for why the re-entered leg's own path isn't modeled).
    """
    events = [
        CeRollEvent(row.date, row.strike, row.premium, row.spot)
        for row in rows
        if row.premium < exit_threshold and (not requires_otm or is_otm("CE", row.strike, row.spot))
    ]
    return {"roll_events": events, "roll_count": len(events)}


def _print_pe_report(result: dict):
    print(f"Stop-loss trigger price: {result['trigger_price']:.2f}")
    for t in result["trades"]:
        print(f"  {t.action:18} {t.entry_date} @ {t.entry_price:.2f}  ->  {t.exit_date} @ {t.exit_price:.2f}"
              f"   pnl {t.pnl_points:+.2f}")
    print(f"Total PnL (points x qty): {result['total_pnl_points']:+.2f}")


def _print_ce_report(result: dict):
    print(f"Roll condition fired {result['roll_count']} time(s):")
    for e in result["roll_events"]:
        print(f"  {e.date}  strike {e.strike:.0f}  premium {e.premium:.2f}  spot {e.spot:.2f}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("pe", "ce"):
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "pe":
        if len(sys.argv) < 6:
            print("Usage: python -m src.backtest pe entry_premium quantity trigger_pct pe.csv "
                  "[--reentry discount_points]")
            sys.exit(1)
        entry_price, quantity, trigger_pct, path = float(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
        reentry_enabled = "--reentry" in sys.argv
        discount_points = float(sys.argv[sys.argv.index("--reentry") + 1]) if reentry_enabled else 20.0
        result = backtest_pe_leg(load_pe_csv(path), entry_price, quantity, trigger_pct,
                                  reentry_enabled=reentry_enabled, discount_points=discount_points)
        _print_pe_report(result)
    else:
        if len(sys.argv) < 4:
            print("Usage: python -m src.backtest ce exit_threshold ce.csv [--no-otm-required]")
            sys.exit(1)
        exit_threshold, path = float(sys.argv[2]), sys.argv[3]
        requires_otm = "--no-otm-required" not in sys.argv
        result = backtest_ce_leg(load_ce_csv(path), exit_threshold, requires_otm=requires_otm)
        _print_ce_report(result)


if __name__ == "__main__":
    main()
