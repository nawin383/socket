"""
Instrument master helpers: expiries, strikes, ATM/ITM/OTM calculation, and
finding the strike whose live premium is closest to a target price.
"""

import logging
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class InstrumentStore:
    def __init__(self, kite, cache_dir: Path):
        self.kite = kite
        self.cache_dir = cache_dir
        self._df: Optional[pd.DataFrame] = None

    def load(self) -> pd.DataFrame:
        """Load (and cache-per-day) the NFO instrument dump."""
        cache_file = self.cache_dir / f"nfo_instruments_{date.today().isoformat()}.csv"
        if cache_file.exists():
            self._df = pd.read_csv(cache_file, parse_dates=["expiry"])
            return self._df

        instruments = self.kite.instruments("NFO")
        df = pd.DataFrame(instruments)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache_file, index=False)
        self._df = df
        return df

    def _df_or_load(self) -> pd.DataFrame:
        return self._df if self._df is not None else self.load()

    def options(self, name: str) -> pd.DataFrame:
        df = self._df_or_load()
        return df[(df["name"] == name) & (df["instrument_type"].isin(["CE", "PE"]))]

    def expiries(self, name: str) -> List[date]:
        opts = self.options(name)
        dates = {d.date() if hasattr(d, "date") else d for d in opts["expiry"]}
        return sorted(dates)

    def weekly_expiry(self, name: str, today: date, min_days_out: int = 0) -> date:
        """
        Nearest upcoming weekly expiry. `min_days_out` excludes expiries
        closer than that many days away — e.g. min_days_out=1 skips an
        expiry falling on `today` itself (0DTE), landing on next week's
        contract instead, which carries lower margin/gamma risk than
        holding or entering a same-day-expiry option.
        """
        upcoming = [e for e in self.expiries(name) if (e - today).days >= min_days_out]
        if not upcoming:
            raise RuntimeError(f"No upcoming expiries found for {name} at least {min_days_out} day(s) out")
        return upcoming[0]

    def monthly_expiry(self, name: str, today: date) -> date:
        """The last expiry falling within a given calendar month is that month's monthly expiry."""
        upcoming = [e for e in self.expiries(name) if e >= today]
        by_month = {}
        for e in upcoming:
            key = (e.year, e.month)
            if key not in by_month or e > by_month[key]:
                by_month[key] = e
        this_month_key = (today.year, today.month)
        if this_month_key in by_month:
            return by_month[this_month_key]
        return sorted(by_month.values())[0]

    def lot_size(self, name: str) -> int:
        opts = self.options(name)
        return int(opts.iloc[0]["lot_size"])

    def tradingsymbol(self, name: str, expiry: date, strike: float, option_type: str) -> dict:
        opts = self.options(name)
        rows = opts[
            (opts["expiry"].dt.date == expiry)
            & (opts["instrument_type"] == option_type)
            & (opts["strike"] == strike)
        ]
        if rows.empty:
            raise RuntimeError(f"No instrument for {name} {expiry} {strike} {option_type}")
        row = rows.iloc[0]
        return {
            "tradingsymbol": row["tradingsymbol"],
            "instrument_token": int(row["instrument_token"]),
            "exchange": row["exchange"],
            "lot_size": int(row["lot_size"]),
        }

    def strike_for_tradingsymbol(self, name: str, tradingsymbol: str) -> Optional[float]:
        opts = self.options(name)
        rows = opts[opts["tradingsymbol"] == tradingsymbol]
        return float(rows.iloc[0]["strike"]) if not rows.empty else None


def round_to_strike_step(spot: float, step: int) -> float:
    return round(spot / step) * step


def is_otm(option_type: str, strike: float, spot: float) -> bool:
    if option_type == "CE":
        return strike > spot
    return strike < spot  # PE


def is_itm(option_type: str, strike: float, spot: float) -> bool:
    if option_type == "CE":
        return strike < spot
    return strike > spot  # PE


def find_strike_by_target_premium(kite, store: InstrumentStore, name: str, expiry: date,
                                   option_type: str, spot: float, step: int,
                                   target_premium: float, tolerance: float,
                                   search_range: int, moneyness: str) -> dict:
    """
    Search strikes around ATM (restricted to the requested moneyness) for the
    one whose live premium is closest to `target_premium`. Returns instrument
    info plus the observed premium and strike; logs a warning if nothing was
    found within `tolerance`.
    """
    atm = round_to_strike_step(spot, step)
    candidates = []
    for i in range(-search_range, search_range + 1):
        strike = atm + i * step
        if moneyness == "ATM" and abs(i) > 2:
            continue
        if moneyness == "ITM" and not is_itm(option_type, strike, spot):
            continue
        if moneyness == "OTM" and not is_otm(option_type, strike, spot):
            continue
        candidates.append(strike)

    if not candidates:
        raise RuntimeError(f"No {moneyness} strikes found for {option_type} near spot {spot}")

    strike_map = {}
    for strike in candidates:
        try:
            info = store.tradingsymbol(name, expiry, strike, option_type)
        except RuntimeError:
            continue
        key = f"{info['exchange']}:{info['tradingsymbol']}"
        strike_map[key] = (strike, info)

    if not strike_map:
        raise RuntimeError(f"No tradable instruments found for candidate strikes: {candidates}")

    quotes = kite.quote(list(strike_map.keys()))

    best_key, best_diff, best_price = None, None, None
    for key, (strike, info) in strike_map.items():
        ltp = quotes.get(key, {}).get("last_price")
        if ltp is None:
            continue
        diff = abs(ltp - target_premium)
        if best_diff is None or diff < best_diff:
            best_key, best_diff, best_price = key, diff, ltp

    if best_key is None:
        raise RuntimeError("Could not fetch live quotes for any candidate strike")

    strike, info = strike_map[best_key]
    if best_diff > tolerance:
        logger.warning(
            "No %s %s strike within tolerance of target premium %s; using closest match "
            "%s @ %.2f (diff %.2f)",
            moneyness, option_type, target_premium, info["tradingsymbol"], best_price, best_diff,
        )

    info["premium"] = best_price
    info["strike"] = strike
    return info
