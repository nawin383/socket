"""
Telegram Command Bot — remote control for the auto_trader when you're away from laptop.

Runs a background thread that long-polls Telegram getUpdates and executes commands.
Only the configured TELEGRAM_CHAT_ID is authorized; all other chats are ignored.

Commands are grouped for mobile use:
  Monitor  : /ping /status /positions /legs /pnl /spot /quote /config /risk /health /history /help
  Control  : /pause /resume /stop /squareoff /flatten /reconcile
  Mode/Qty : /mode /qty
  Toggles  : /enable_pe /disable_pe /enable_ce /disable_ce
  Tuning   : /set_pe_target /set_ce_target /set_ce_exit /set_sl /set_maxloss /set_maxrolls

All config changes update the in-memory config dict and persist to config/config.yaml
so they survive restarts. pause/resume use the same STOP_TRADING file that
RiskGuard checks (risk.py:39), so they work identically to scripts/stop_trading.sh.

Requires: requests, PyYAML. No extra deps.
"""

import logging
import threading
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import requests
import yaml

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(
        self,
        bot_token: str,
        allowed_chat_id: str,
        state,
        risk,
        strategy,
        orders,
        kite,
        store,
        config: Dict[str, Any],
        config_path: Path,
        kill_switch_path: Path,
        notifier,
        status_ref: Dict[str, Any] = None,
        poll_timeout: int = 20,
    ):
        self.bot_token = bot_token
        self.allowed_chat_id = str(allowed_chat_id) if allowed_chat_id else ""
        self.state = state
        self.risk = risk
        self.strategy = strategy
        self.orders = orders
        self.kite = kite
        self.store = store
        self.config = config
        self.config_path = config_path
        self.kill_switch_path = kill_switch_path
        self.notifier = notifier
        self.status_ref = status_ref or {}
        self.poll_timeout = poll_timeout

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._offset = 0
        # Offset file for GitHub Actions persistence (free, no VPS) — survives via git
        self.offset_file = self.kill_switch_path.parent / "telegram_offset.txt"
        self._load_offset()

        # Map command -> handler
        self.handlers = {
            # Monitor
            "status": self._cmd_status,
            "positions": self._cmd_positions,
            "legs": self._cmd_legs,
            "pnl": self._cmd_pnl,
            "spot": self._cmd_spot,
            "quote": self._cmd_quote,
            "config": self._cmd_config,
            "risk": self._cmd_risk,
            "health": self._cmd_health,
            "history": self._cmd_history,
            "ping": self._cmd_ping,
            "help": self._cmd_help,
            "commands": self._cmd_help,
            "start": self._cmd_help,
            # Control
            "pause": self._cmd_pause,
            "resume": self._cmd_resume,
            "stop": self._cmd_stop,
            "squareoff": self._cmd_squareoff,
            "flatten": self._cmd_stop,  # alias: squareoff ALL + pause
            "reconcile": self._cmd_reconcile,
            # Mode/Qty
            "mode": self._cmd_mode,
            "qty": self._cmd_qty,
            "lots": self._cmd_qty,
            # Toggles
            "enable_pe": self._cmd_enable_pe,
            "disable_pe": self._cmd_disable_pe,
            "enable_ce": self._cmd_enable_ce,
            "disable_ce": self._cmd_disable_ce,
            # Tuning
            "set_pe_target": self._cmd_set_pe_target,
            "set_ce_target": self._cmd_set_ce_target,
            "set_ce_exit": self._cmd_set_ce_exit,
            "set_sl": self._cmd_set_sl,
            "set_maxloss": self._cmd_set_maxloss,
            "set_maxrolls": self._cmd_set_maxrolls,
            "set_tolerance": self._cmd_set_tolerance,
            # PE profit
            "pe_profit": self._cmd_pe_profit,
            "set_pe_profit": self._cmd_set_pe_profit,
            "overall": self._cmd_overall,
            "total": self._cmd_overall,
        }

    # ---------- lifecycle ----------
    def start(self):
        if not self.bot_token or not self.allowed_chat_id:
            logger.info("TelegramBot not started: bot_token or chat_id missing")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="telegram-bot")
        self._thread.start()
        logger.info("TelegramBot started (polling @%s, allowed chat %s)", self.bot_token[:8] + "...", self.allowed_chat_id)
        try:
            self.notifier.send("🤖 Telegram control online. Send /help for commands.")
        except Exception:
            pass

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)

    # ---------- polling ----------
    def _poll_loop(self):
        base_url = f"https://api.telegram.org/bot{self.bot_token}"
        while not self._stop_event.is_set():
            try:
                resp = requests.get(
                    f"{base_url}/getUpdates",
                    params={"offset": self._offset, "timeout": self.poll_timeout, "allowed_updates": json.dumps(["message"])},
                    timeout=self.poll_timeout + 5,
                )
                if resp.status_code != 200:
                    logger.warning("Telegram getUpdates %s: %s", resp.status_code, resp.text[:200])
                    time.sleep(5)
                    continue
                data = resp.json()
                if not data.get("ok"):
                    logger.warning("Telegram getUpdates not ok: %s", data)
                    time.sleep(5)
                    continue
                for upd in data.get("result", []):
                    self._offset = upd["update_id"] + 1
                    msg = upd.get("message") or upd.get("edited_message")
                    if not msg:
                        continue
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    # Authorization — only allowed chat
                    if chat_id != self.allowed_chat_id:
                        logger.warning("Ignoring message from unauthorized chat %s", chat_id)
                        # Optionally tell them they're not authorized
                        continue
                    text = (msg.get("text") or "").strip()
                    if not text.startswith("/"):
                        continue
                    # Strip @botname suffix if present
                    if "@" in text:
                        text = text.split("@")[0] + (" " + " ".join(text.split()[1:]) if len(text.split()) > 1 else "")
                        # Actually above is messy; simpler: split first token at @
                        first, *rest = text.split()
                        first = first.split("@")[0]
                        text = " ".join([first] + rest)
                    self._handle_message(chat_id, text, msg)
            except requests.exceptions.ReadTimeout:
                continue
            except Exception as e:
                logger.error("Telegram poll loop error: %s", e)
                time.sleep(5)

    # ---------- Actions single-shot (free, no VPS) ----------
    def _load_offset(self):
        try:
            if self.offset_file.exists():
                txt = self.offset_file.read_text().strip()
                if txt:
                    self._offset = int(txt)
                    logger.info("Loaded telegram offset %s from %s", self._offset, self.offset_file)
        except Exception as e:
            logger.warning("Failed to load telegram offset: %s", e)
            self._offset = 0

    def _save_offset(self):
        try:
            self.offset_file.parent.mkdir(parents=True, exist_ok=True)
            self.offset_file.write_text(str(self._offset))
        except Exception as e:
            logger.warning("Failed to save telegram offset: %s", e)

    def process_one_batch(self, timeout: int = 0) -> int:
        """Single-shot poll for GitHub Actions (free, no VPS). Fetches one batch, handles, saves offset."""
        if not self.bot_token or not self.allowed_chat_id:
            logger.info("Telegram process_one_batch skipped: bot_token or chat_id missing")
            return 0
        self._load_offset()
        base_url = f"https://api.telegram.org/bot{self.bot_token}"
        try:
            resp = requests.get(
                f"{base_url}/getUpdates",
                params={"offset": self._offset, "timeout": timeout, "allowed_updates": json.dumps(["message"])},
                timeout=timeout + 10,
            )
            if resp.status_code != 200:
                logger.warning("Telegram getUpdates %s: %s", resp.status_code, resp.text[:200])
                return 0
            data = resp.json()
            if not data.get("ok"):
                logger.warning("Telegram getUpdates not ok: %s", data)
                return 0
            results = data.get("result", [])
            if not results:
                logger.info("Telegram: no new messages (offset %s)", self._offset)
                return 0
            handled = 0
            for upd in results:
                self._offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if chat_id != self.allowed_chat_id:
                    logger.warning("Ignoring message from unauthorized chat %s", chat_id)
                    continue
                text = (msg.get("text") or "").strip()
                if not text.startswith("/"):
                    continue
                if "@" in text:
                    first, *rest = text.split()
                    first = first.split("@")[0]
                    text = " ".join([first] + rest)
                logger.info("Actions Telegram handling: %s from %s", text, chat_id)
                self._handle_message(chat_id, text, msg)
                handled += 1
            self._save_offset()
            logger.info("Telegram batch done: %s messages, new offset %s", handled, self._offset)
            return handled
        except Exception as e:
            logger.error("Telegram process_one_batch error: %s", e)
            return 0

    def _handle_message(self, chat_id: str, text: str, raw_msg: dict):
        parts = text.strip().split()
        cmd = parts[0].lstrip("/").lower()
        args = parts[1:]
        handler = self.handlers.get(cmd)
        if not handler:
            self._reply(chat_id, f"❓ Unknown command `/{cmd}`. Send /help for list.")
            return
        try:
            reply = handler(args, chat_id, raw_msg)
            if reply:
                self._reply(chat_id, reply)
        except Exception as e:
            logger.exception("Error handling /%s", cmd)
            self._reply(chat_id, f"⚠️ Error handling `/{cmd}`: {e}")

    def _post(self, chat_id: str, text: str, parse_mode: Optional[str]) -> bool:
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                data={"chat_id": chat_id, "text": text, **({"parse_mode": parse_mode} if parse_mode else {})},
                timeout=10,
            )
        except Exception as e:
            logger.error("Telegram reply request failed: %s", e)
            return False
        if resp.status_code == 200:
            return True
        # A malformed Markdown payload (e.g. an interpolated exception with a stray
        # `_`/`*`/backtick) gets HTTP 400 with ok:false — requests doesn't raise for
        # that, so a fire-and-forget send silently drops the reply. Log it.
        logger.warning("Telegram reply rejected (%s): %s", resp.status_code, resp.text[:300])
        return False

    def _reply(self, chat_id: str, text: str):
        # Telegram max 4096 chars; truncate gracefully
        if len(text) > 4000:
            text = text[:4000] + "\n… (truncated)"
        if self._post(chat_id, text, "Markdown"):
            return
        if self._post(chat_id, text, None):
            return
        logger.error("Telegram reply to %s dropped after formatted + plain-text attempts", chat_id)

    # ---------- helpers ----------
    def _save_config(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w") as f:
                yaml.safe_dump(self.config, f, default_flow_style=False, sort_keys=False)
            logger.info("Config persisted to %s", self.config_path)
        except Exception as e:
            logger.error("Failed to persist config: %s", e)
            raise

    def _fmt_price(self, v):
        try:
            return f"{float(v):.2f}"
        except Exception:
            return str(v)

    def _table(self, headers, rows):
        """
        Render headers/rows as a fixed-width table inside a ``` code block.

        Telegram only renders monospace inside code spans/blocks — plain text
        with manual space-padding (the previous approach) does NOT line up on
        the actual client, it renders in a proportional font. A code block
        also sidesteps Markdown parsing entirely, so tradingsymbols, negative
        PnL signs, etc. can never break message delivery here.
        """
        headers = [str(h) for h in headers]
        str_rows = [[str(c) for c in row] for row in rows]
        widths = [len(h) for h in headers]
        for row in str_rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(cell))

        def fmt_row(cells):
            return "  ".join(c.ljust(w) for c, w in zip(cells, widths))

        lines = [fmt_row(headers), "  ".join("-" * w for w in widths)]
        lines.extend(fmt_row(r) for r in str_rows)
        return "```\n" + "\n".join(lines) + "\n```"

    # ---------- MONITOR commands ----------
    def _cmd_status(self, args, chat_id, raw_msg):
        try:
            now = datetime.now()
            trading_allowed = self.risk.trading_allowed(now)
            kill = self.risk.kill_switch_active()
            today = self.state.today_state()
            pe = self.state.get_leg("PE")
            ce = self.state.get_leg("CE")
            mode = self.orders.mode if hasattr(self.orders, "mode") else self.config.get("mode", "?")
            try:
                spot_sym = self.config["underlying"]["spot_symbol"]
                spot_str = f"{self.kite.ltp([spot_sym])[spot_sym]['last_price']:.2f}"
            except Exception as e:
                spot_str = f"err: {e}"
            hb = self.status_ref.get("last_heartbeat", "?")
            try:
                overall, realized, unreal = self.strategy._get_overall_pnl_today()
            except Exception:
                overall, realized, unreal = today["realized_pnl"], today["realized_pnl"], 0.0

            overview = self._table(
                ["Field", "Value"],
                [
                    ["Mode", mode],
                    ["Kill-switch", "ON" if kill else "OFF"],
                    ["Trading now", "YES" if trading_allowed else "NO"],
                    ["Spot", spot_str],
                    ["Heartbeat", str(hb)],
                    ["Realized", f"{realized:.0f}"],
                    ["Unrealized", f"{unreal:.0f}"],
                    ["Overall PnL", f"{overall:.0f}"],
                    ["Rolls today", str(today["roll_count"])],
                    ["Last roll", (today["last_roll_time"] or "-")[:16]],
                ],
            )

            leg_rows = []
            for name, leg, cfg_key in (("PE", pe, "pe_leg"), ("CE", ce, "ce_leg")):
                on = "ON" if self.config[cfg_key].get("enabled") else "OFF"
                if leg:
                    leg_rows.append([name, on, leg["tradingsymbol"], leg["quantity"], f"{leg['entry_price']:.2f}", leg["entry_time"][:16]])
                else:
                    leg_rows.append([name, on, "flat", "-", "-", "-"])
            legs_table = self._table(["Leg", "State", "Symbol", "Qty", "Entry", "Since"], leg_rows)

            return f"*🤖 Status — {now.strftime('%Y-%m-%d %H:%M:%S')}*\n{overview}\n{legs_table}\n_Full parameters: /config_"
        except Exception as e:
            return f"⚠️ /status failed: `{e}`"

    def _cmd_positions(self, args, chat_id, raw_msg):
        try:
            state_pe = self.state.get_leg("PE")
            state_ce = self.state.get_leg("CE")
            try:
                broker_pos = self.kite.positions().get("net", [])
                name = self.config["underlying"]["name"]
                relevant = [p for p in broker_pos if p.get("exchange") == "NFO" and name in p.get("tradingsymbol", "") and p.get("quantity", 0) != 0]
            except Exception as e:
                return f"⚠️ Could not fetch broker positions: `{e}`"

            if not relevant and not state_pe and not state_ce:
                return "*📊 Broker vs State*\nNo open positions (broker flat, state flat)."

            rows = []
            for p in relevant:
                rows.append(["Broker", p["tradingsymbol"], p["quantity"], f"{p['average_price']:.2f}", f"{p.get('pnl', p.get('unrealised', 0)):.2f}"])
            for label, leg in (("State PE", state_pe), ("State CE", state_ce)):
                rows.append([label, leg["tradingsymbol"], leg["quantity"], f"{leg['entry_price']:.2f}", "-"] if leg else [label, "flat", "-", "-", "-"])
            table = self._table(["Source", "Symbol", "Qty", "Price", "PnL"], rows)

            broker_symbols = {p["tradingsymbol"] for p in relevant}
            state_symbols = {s["tradingsymbol"] for s in (state_pe, state_ce) if s}
            mismatch = "\n⚠️ *Mismatch* between broker and state — use /reconcile if you squared off manually." if broker_symbols != state_symbols else ""
            return f"*📊 Broker vs State*\n{table}{mismatch}"
        except Exception as e:
            return f"⚠️ /positions failed: `{e}`"

    def _cmd_legs(self, args, chat_id, raw_msg):
        try:
            rows = []
            for leg_name in ["PE", "CE"]:
                leg = self.state.get_leg(leg_name)
                if not leg:
                    rows.append([leg_name, "flat", "-", "-", "-", "-", "-"])
                    continue
                try:
                    key = f"{leg['exchange']}:{leg['tradingsymbol']}"
                    ltp = self.kite.ltp([key])[key]["last_price"]
                    unreal = (leg["entry_price"] - ltp) * leg["quantity"]
                    ltp_str, pnl_str = f"{ltp:.2f}", f"{unreal:+.2f}"
                except Exception:
                    ltp_str, pnl_str = "?", "?"
                rows.append([
                    leg_name, leg["tradingsymbol"], f"{leg['strike']:.0f}", leg["quantity"],
                    f"{leg['entry_price']:.2f}", ltp_str, pnl_str,
                ])
            table = self._table(["Leg", "Symbol", "Strike", "Qty", "Entry", "LTP", "Unreal"], rows)
            return f"*🦵 Leg Details*\n{table}"
        except Exception as e:
            return f"⚠️ /legs failed: `{e}`"

    def _cmd_pnl(self, args, chat_id, raw_msg):
        try:
            today = self.state.today_state()
            try:
                overall, realized, unreal = self.strategy._get_overall_pnl_today()
            except Exception:
                overall, realized, unreal = today["realized_pnl"], today["realized_pnl"], 0.0

            summary = self._table(
                ["Field", "Value"],
                [
                    ["Realized", f"{realized:.2f}"],
                    ["Unrealized", f"{unreal:.2f}"],
                    ["Overall", f"{overall:.2f}"],
                    ["Rolls today", today["roll_count"]],
                    ["Last roll", (today["last_roll_time"] or "-")[:16]],
                ],
            )
            from contextlib import closing
            with closing(self.state._connect()) as conn:
                recent = conn.execute(
                    "SELECT leg, action, tradingsymbol, price, quantity, time FROM roll_history ORDER BY id DESC LIMIT 5"
                ).fetchall()
            events_table = ""
            if recent:
                rows = [[r["time"][:16], r["leg"], r["action"], r["tradingsymbol"], f"{r['price']:.2f}", r["quantity"]] for r in recent]
                events_table = "\n*Last 5 events:*\n" + self._table(["Time", "Leg", "Action", "Symbol", "Price", "Qty"], rows)
            return f"*💰 Today ({today['trading_day']})*\n{summary}{events_table}"
        except Exception as e:
            return f"⚠️ /pnl failed: `{e}`"

    def _cmd_spot(self, args, chat_id, raw_msg):
        try:
            sym = self.config["underlying"]["spot_symbol"]
            ltp = self.kite.ltp([sym])[sym]["last_price"]
            return f"*Spot* `{sym}` = `Rs {ltp:.2f}`"
        except Exception as e:
            return f"⚠️ /spot failed: {e}"

    def _cmd_quote(self, args, chat_id, raw_msg):
        if not args:
            return "Usage: `/quote EXCHANGE:TRADINGSYMBOL`  e.g. `/quote NFO:NIFTY24JAN22500CE` or `/quote NSE:RELIANCE`"
        try:
            key = args[0].strip()
            if ":" not in key:
                # Assume NFO NIFTY
                key = f"NFO:{key}"
            data = self.kite.ltp([key])
            if key not in data:
                # Try quote
                data = self.kite.quote([key])
                if key in data:
                    q = data[key]
                    return f"*Quote* `{key}`\nLTP: `{q.get('last_price','?')}`  OHLC: {q.get('ohlc','?')}"
                return f"Symbol `{key}` not found."
            return f"*Quote* `{key}` LTP: `Rs {data[key]['last_price']:.2f}`"
        except Exception as e:
            return f"⚠️ /quote failed: {e}"

    def _cmd_config(self, args, chat_id, raw_msg):
        try:
            cfg = self.config
            tp = cfg['pe_leg'].get('take_profit', {})
            lot = self.store.lot_size(cfg['underlying']['name'])
            pe_table = self._table(
                ["PE Field", "Value"],
                [
                    ["Enabled", cfg["pe_leg"]["enabled"]],
                    ["Target", f"{cfg['pe_leg']['target_premium']} ±{cfg['pe_leg']['premium_tolerance']}"],
                    ["Strike range", cfg["pe_leg"]["strike_search_range"]],
                    ["Qty", f"{cfg['pe_leg']['quantity_lots']} lots (x{lot})"],
                    ["Expiry", cfg["pe_leg"]["expiry_type"]],
                    ["Stop-loss", f"+{cfg['pe_leg']['stop_loss'].get('trigger_pct')}%"],
                    ["Take-profit", "ON" if tp.get("enabled") else "OFF"],
                ],
            )
            ce_table = self._table(
                ["CE Field", "Value"],
                [
                    ["Enabled", cfg["ce_leg"]["enabled"]],
                    ["Target", f"{cfg['ce_leg']['target_premium']} ±{cfg['ce_leg']['premium_tolerance']}"],
                    ["Exit below", cfg["ce_leg"]["exit_premium_threshold"]],
                    ["Qty", f"{cfg['ce_leg']['quantity_lots']} lots (roll preserves qty)"],
                    ["Max rolls/day", cfg["ce_leg"]["max_rolls_per_day"]],
                    ["Avoid 0DTE", cfg["ce_leg"].get("avoid_zero_dte_entry")],
                ],
            )
            risk_table = self._table(
                ["Risk Field", "Value"],
                [
                    ["Max daily loss", f"{cfg['risk']['max_daily_loss']} (total=real+unreal)"],
                    ["Trading hours", f"{cfg['risk']['trading_start']}-{cfg['risk']['trading_end']}"],
                    ["EOD square-off", cfg["risk"]["eod_square_off_time"]],
                    ["Kill file", cfg["risk"]["kill_switch_file"]],
                ],
            )
            return f"*⚙️ Config* (mode `{cfg.get('mode')}`)\n{pe_table}\n{ce_table}\n{risk_table}"
        except Exception as e:
            return f"⚠️ /config failed: `{e}`"

    def _cmd_risk(self, args, chat_id, raw_msg):
        try:
            now = datetime.now()
            try:
                overall, real, unreal = self.strategy._get_overall_pnl_today()
                total_breached = self.risk.total_loss_breached(overall_pnl=overall)
            except Exception:
                overall, real, unreal = 0.0, 0.0, 0.0
                total_breached = self.risk.daily_loss_breached()
            table = self._table(
                ["Field", "Value"],
                [
                    ["Trading day", self.risk.is_trading_day(now)],
                    ["Market open", self.risk.is_market_open(now)],
                    ["EOD flag", self.risk.is_eod_square_off_time(now)],
                    ["Kill switch", "ON" if self.risk.kill_switch_active() else "OFF"],
                    ["Realized breached", self.risk.daily_loss_breached()],
                    ["Total breached", total_breached],
                    ["Trading allowed", self.risk.trading_allowed(now)],
                    ["Overall PnL", f"{overall:.0f} (r {real:.0f} + u {unreal:.0f})"],
                    ["Max daily loss", f"-{self.risk.max_daily_loss}"],
                    ["Holidays", self.risk.holidays or "none"],
                    ["Orders mode", self.orders.mode],
                ],
            )
            return f"*🛡️ Risk @ {now.strftime('%H:%M:%S')}*\n{table}"
        except Exception as e:
            return f"⚠️ /risk failed: `{e}`"

    def _cmd_health(self, args, chat_id, raw_msg):
        try:
            hb = self.status_ref.get("last_heartbeat", "?")
            ok = self.status_ref.get("ok", "?")
            mode = self.status_ref.get("mode", self.config.get("mode"))
            return f"*❤️ Health*\nHeartbeat: `{hb}`  OK: `{ok}`  Mode: `{mode}`  Port: `{self.config.get('health',{}).get('http_port',8080)}`"
        except Exception as e:
            return f"⚠️ /health failed: {e}"

    def _cmd_history(self, args, chat_id, raw_msg):
        try:
            from contextlib import closing
            n = 10
            if args and args[0].isdigit():
                n = min(int(args[0]), 30)
            with closing(self.state._connect()) as conn:
                rows_db = conn.execute(
                    "SELECT leg, action, tradingsymbol, price, quantity, time, note FROM roll_history ORDER BY id DESC LIMIT ?", (n,)
                ).fetchall()
            if not rows_db:
                return "_No history yet_"
            rows = [[r["time"][:16], r["leg"], r["action"], r["tradingsymbol"], f"{r['price']:.2f}", r["quantity"], (r["note"] or "-")[:18]] for r in rows_db]
            table = self._table(["Time", "Leg", "Action", "Symbol", "Price", "Qty", "Note"], rows)
            return f"*📜 Last {len(rows_db)} events*\n{table}"
        except Exception as e:
            return f"⚠️ /history failed: `{e}`"

    def _cmd_pe_profit(self, args, chat_id, raw_msg):
        try:
            tp = self.config['pe_leg'].get('take_profit', {})
            leg = self.state.get_leg("PE")
            status = f"PE leg: {'flat' if not leg else leg['tradingsymbol']+' @'+str(leg['entry_price'])}"
            if leg:
                try:
                    pe_ltp = self.strategy._quote_ltp(leg['exchange'], leg['tradingsymbol'])
                    trigger = round(leg['entry_price'] * (1 - tp.get('trigger_pct',15)/100.0),2)
                    profit_pts = leg['entry_price'] - pe_ltp
                    overall, _, _ = self.strategy._get_overall_pnl_today(pe_ltp=pe_ltp)
                    status += f"\nLTP: {pe_ltp:.2f}  Trigger: {trigger:.2f}  Profit pts: {profit_pts:.2f}  Overall: {overall:.2f}"
                except Exception as e:
                    status += f"\nLTP error: {e}"
            return (
                f"*📈 PE Take-Profit* (smart booking)\n"
                f"Enabled: `{tp.get('enabled', True)}`  Trigger: `{tp.get('trigger_pct',15)}%` below entry (min {tp.get('min_profit_points',20)}pts)\n"
                f"Require overall>0: `{tp.get('require_overall_profit',True)}`  Reentry next day: `{tp.get('allow_reentry_next_day',True)}`\n"
                f"{status}\n"
                f"Logic: Book if pe_ltp ≤ entry×(1-trigger%) AND (entry-pe_ltp)≥min_pts AND (overall>0 if required). See strategy.py:check_pe_take_profit"
            )
        except Exception as e:
            return f"⚠️ /pe_profit failed: {e}"

    def _cmd_set_pe_profit(self, args, chat_id, raw_msg):
        # Usage: /set_pe_profit 15  or /set_pe_profit 15 20  (pct pts)  or /set_pe_profit off/on
        tp = self.config['pe_leg'].setdefault('take_profit', {})
        if not args:
            return f"PE TP: enabled={tp.get('enabled',True)} trigger={tp.get('trigger_pct',15)}% min_pts={tp.get('min_profit_points',20)} overall>{tp.get('require_overall_profit',True)}\nUsage: `/set_pe_profit 15` or `/set_pe_profit off` `/set_pe_profit 12 30`"
        if args[0].lower() in ("off","disable","false"):
            tp['enabled']=False; self._save_config(); return "✅ PE take-profit *disabled*"
        if args[0].lower() in ("on","enable","true"):
            tp['enabled']=True; self._save_config(); return "✅ PE take-profit *enabled*"
        try:
            pct = int(args[0])
            if not 5 <= pct <= 50:
                return "Pct must be 5..50"
            tp['trigger_pct']=pct
            if len(args)>=2 and args[1].isdigit():
                tp['min_profit_points']=int(args[1])
            self._save_config()
            self.notifier.send(f"PE TP set to {pct}% by Telegram ({chat_id})")
            return f"✅ PE TP trigger: *{pct}%* (min {tp.get('min_profit_points',20)}pts)"
        except Exception as e:
            return f"⚠️ failed: {e}"

    def _cmd_overall(self, args, chat_id, raw_msg):
        try:
            overall, real, unreal = self.strategy._get_overall_pnl_today()
            pe = self.state.get_leg("PE")
            ce = self.state.get_leg("CE")
            rows = [
                ["Realized", f"{real:.2f}"],
                ["Unrealized", f"{unreal:.2f}"],
                ["Overall", f"{overall:.2f}"],
                ["Max loss limit", f"-{self.risk.max_daily_loss}"],
                ["Total breached", self.risk.total_loss_breached(overall_pnl=overall)],
                ["Realized breached", self.risk.daily_loss_breached()],
            ]
            for name, leg in (("PE", pe), ("CE", ce)):
                if not leg:
                    continue
                try:
                    ltp = self.strategy._quote_ltp(leg["exchange"], leg["tradingsymbol"])
                    rows.append([f"{name} unreal", f"{(leg['entry_price']-ltp)*leg['quantity']:.0f}"])
                except Exception:
                    pass
            table = self._table(["Field", "Value"], rows)
            return f"*📊 Overall PnL Today*\n{table}"
        except Exception as e:
            return f"⚠️ /overall failed: `{e}`"

    # ---------- CONTROL ----------
    def _cmd_pause(self, args, chat_id, raw_msg):
        try:
            self.kill_switch_path.parent.mkdir(parents=True, exist_ok=True)
            self.kill_switch_path.touch(exist_ok=True)
            self.notifier.send(f"⛔ Paused by Telegram ({chat_id}): STOP_TRADING created. No new entries/rolls until /resume. Open positions kept.")
            return f"⛔ *Paused*: `{self.kill_switch_path}` created.\nNo new PE/CE entries or CE rolls will happen. Open legs are untouched. Use /resume to continue."
        except Exception as e:
            return f"⚠️ /pause failed: {e}"

    def _cmd_resume(self, args, chat_id, raw_msg):
        try:
            existed = self.kill_switch_path.exists()
            if existed:
                self.kill_switch_path.unlink()
            self.notifier.send(f"✅ Resumed by Telegram ({chat_id}): STOP_TRADING removed. Trading allowed again.")
            return f"✅ *Resumed*: kill switch `{'removed' if existed else 'was already off'}`.\nBot will resume entries/rolls at next cycle ({self.config['polling'].get('reconcile_interval_sec',15)}s)."
        except Exception as e:
            return f"⚠️ /resume failed: {e}"

    def _cmd_stop(self, args, chat_id, raw_msg):
        """Square off all then pause — hard stop."""
        try:
            # First set pause
            self.kill_switch_path.parent.mkdir(parents=True, exist_ok=True)
            self.kill_switch_path.touch(exist_ok=True)
            # Now square off
            pe = self.state.get_leg("PE")
            ce = self.state.get_leg("CE")
            if not pe and not ce:
                return "⛔ *Paused* (already flat). Kill switch ON. No positions to square off."
            # Square off via strategy
            try:
                self.strategy.square_off_all(f"Telegram /stop by {chat_id}")
                self.notifier.send(f"🛑 Stopped by Telegram ({chat_id}): all legs squared off and paused.")
                return f"🛑 *Stopped*: all legs squared off and paused.\nKill switch ON. Use /resume to allow new entries after you review."
            except Exception as e:
                return f"Pausing done, but square-off failed: {e}\nState may need manual check via /positions."
        except Exception as e:
            return f"⚠️ /stop failed: {e}"

    def _cmd_squareoff(self, args, chat_id, raw_msg):
        if not args:
            return "Usage: `/squareoff PE|CE|ALL`  — squares off that leg at market and keeps kill switch as-is. Use /stop to also pause."
        target = args[0].upper()
        try:
            if target == "PE":
                leg = self.state.get_leg("PE")
                if not leg:
                    return "PE already flat."
                ltp = self.strategy._quote_ltp(leg["exchange"], leg["tradingsymbol"])
                fill = self.strategy.orders.buy_to_close(leg["tradingsymbol"], leg["exchange"], leg["quantity"], ltp, self.config["pe_leg"]["product"])
                pnl = (leg["entry_price"] - fill) * leg["quantity"]
                self.state.log_roll("PE", "SQUAREOFF", leg["tradingsymbol"], fill, leg["quantity"], note=f"Telegram /squareoff PE by {chat_id}")
                self.state.add_realized_pnl(pnl)
                self.state.clear_leg("PE")
                self.notifier.send(f"PE squared off by Telegram: {leg['tradingsymbol']} @ {fill:.2f} PnL {pnl:.2f}")
                return f"✅ PE squared off @ {fill:.2f} PnL {pnl:.2f}"
            elif target == "CE":
                leg = self.state.get_leg("CE")
                if not leg:
                    return "CE already flat."
                # Single CE square off
                # Use strategy helper: buy_to_close
                ltp = self.strategy._quote_ltp(leg["exchange"], leg["tradingsymbol"])
                fill = self.strategy.orders.buy_to_close(leg["tradingsymbol"], leg["exchange"], leg["quantity"], ltp, self.config["ce_leg"]["product"])
                pnl = (leg["entry_price"] - fill) * leg["quantity"]
                self.state.log_roll("CE", "SQUAREOFF", leg["tradingsymbol"], fill, leg["quantity"], note=f"Telegram /squareoff by {chat_id}")
                self.state.add_realized_pnl(pnl)
                self.state.clear_leg("CE")
                self.notifier.send(f"CE squared off by Telegram: {leg['tradingsymbol']} @ {fill:.2f} PnL {pnl:.2f}")
                return f"✅ CE squared off @ {fill:.2f} PnL {pnl:.2f}"
            elif target == "ALL":
                if not self.state.get_leg("PE") and not self.state.get_leg("CE"):
                    return "Already flat (no legs)."
                self.strategy.square_off_all(f"Telegram /squareoff ALL by {chat_id}")
                return "✅ All legs squared off."
            else:
                return "Usage: `/squareoff PE|CE|ALL`"
        except Exception as e:
            return f"⚠️ /squareoff failed: {e}"

    def _cmd_reconcile(self, args, chat_id, raw_msg):
        try:
            self.strategy.reconcile_from_broker()
            return "🔄 Reconcile done: checked broker `kite.positions()` and adopted any missing short NIFTY legs into state. Check /positions."
        except Exception as e:
            return f"⚠️ /reconcile failed: {e}"

    # ---------- MODE / QTY ----------
    def _cmd_mode(self, args, chat_id, raw_msg):
        cur = self.orders.mode if hasattr(self.orders, "mode") else self.config.get("mode", "paper")
        if not args:
            return f"Mode: `{cur}`\nUsage: `/mode paper|live`  — switches order execution. *LIVE places real money orders*."
        new_mode = args[0].lower()
        if new_mode not in ("paper", "live", "demo"):
            return "Usage: `/mode paper|live`  (demo = paper alias)"
        if new_mode == "demo":
            new_mode = "paper"
        if new_mode == cur:
            return f"Already in `{cur}` mode."
        # Extra confirmation for live
        if new_mode == "live":
            # Require explicit confirm if coming from paper
            if len(args) < 2 or args[1].lower() != "confirm":
                return (
                    "⚠️ You are switching to *LIVE* (real money).\n"
                    "Confirm with: `/mode live confirm`\n"
                    f"Current: `{cur}` → `live`  |  PE qty {self.config['pe_leg']['quantity_lots']} lots  CE qty {self.config['ce_leg']['quantity_lots']} lots"
                )
        # Apply
        try:
            self.orders.mode = new_mode
            self.config["mode"] = new_mode
            self.status_ref["mode"] = new_mode
            self._save_config()
            self.notifier.send(f"🔄 Mode switched to {new_mode.upper()} by Telegram ({chat_id})")
            return f"✅ Mode switched: `{cur}` → *`{new_mode}`*  (persisted to config.yaml)"
        except Exception as e:
            return f"⚠️ /mode failed: {e}"

    def _cmd_qty(self, args, chat_id, raw_msg):
        # /qty  -> show
        # /qty pe 2  or /qty ce 3  or /qty 2 (sets both)
        if not args:
            return (
                f"*Qty*  PE: `{self.config['pe_leg']['quantity_lots']} lots`  CE: `{self.config['ce_leg']['quantity_lots']} lots`  Lot:{self.store.lot_size(self.config['underlying']['name'])}\n"
                f"Usage: `/qty pe 2`  `/qty ce 3`  `/qty 2` (both)  — affects *next* entry/roll only; open legs keep their qty."
            )
        try:
            if len(args) == 1 and args[0].isdigit():
                # Both
                lots = int(args[0])
                if not 1 <= lots <= 10:
                    return "Qty must be 1..10 lots."
                self.config["pe_leg"]["quantity_lots"] = lots
                self.config["ce_leg"]["quantity_lots"] = lots
                self._save_config()
                self.notifier.send(f"🔢 Qty set to {lots} lots (both legs) by Telegram ({chat_id})")
                return f"✅ Qty set: PE & CE → `{lots} lots` (≈ {lots * self.store.lot_size(self.config['underlying']['name'])} qty)"
            elif len(args) == 2 and args[0].lower() in ("pe", "ce", "both") and args[1].isdigit():
                leg = args[0].lower()
                lots = int(args[1])
                if not 1 <= lots <= 10:
                    return "Qty must be 1..10 lots."
                if leg == "pe":
                    self.config["pe_leg"]["quantity_lots"] = lots
                elif leg == "ce":
                    self.config["ce_leg"]["quantity_lots"] = lots
                else:
                    self.config["pe_leg"]["quantity_lots"] = lots
                    self.config["ce_leg"]["quantity_lots"] = lots
                self._save_config()
                self.notifier.send(f"🔢 Qty {leg.upper()} set to {lots} lots by Telegram ({chat_id})")
                return f"✅ Qty {leg.upper()} → `{lots} lots`"
            else:
                return "Usage: `/qty pe 2`  `/qty ce 2`  `/qty 2` (both)  e.g. `/qty pe 1`"
        except Exception as e:
            return f"⚠️ /qty failed: {e}"

    # ---------- TOGGLES ----------
    def _cmd_enable_pe(self, args, chat_id, raw_msg):
        self.config["pe_leg"]["enabled"] = True
        self._save_config()
        self.notifier.send(f"PE leg ENABLED by Telegram ({chat_id})")
        return "✅ PE leg *enabled* (next ensure will enter if flat)"

    def _cmd_disable_pe(self, args, chat_id, raw_msg):
        self.config["pe_leg"]["enabled"] = False
        self._save_config()
        self.notifier.send(f"PE leg DISABLED by Telegram ({chat_id}) — will not enter new PE, but existing PE still managed (SL/expiry). Use /squareoff PE to close.")
        return "⛔ PE leg *disabled* (no new entries until /enable_pe)."

    def _cmd_enable_ce(self, args, chat_id, raw_msg):
        self.config["ce_leg"]["enabled"] = True
        self._save_config()
        self.notifier.send(f"CE leg ENABLED by Telegram ({chat_id})")
        return "✅ CE leg *enabled*"

    def _cmd_disable_ce(self, args, chat_id, raw_msg):
        self.config["ce_leg"]["enabled"] = False
        self._save_config()
        self.notifier.send(f"CE leg DISABLED by Telegram ({chat_id}) — no new CE rolls/entries, existing still monitored for manual /squareoff.")
        return "⛔ CE leg *disabled*"

    # ---------- TUNING ----------
    def _cmd_set_pe_target(self, args, chat_id, raw_msg):
        if not args or not args[0].isdigit():
            return f"Current PE target: `Rs {self.config['pe_leg']['target_premium']}`\nUsage: `/set_pe_target 700`"
        try:
            v = int(args[0])
            if not 50 <= v <= 2000:
                return "Value must be 50..2000"
            old = self.config["pe_leg"]["target_premium"]
            self.config["pe_leg"]["target_premium"] = v
            self._save_config()
            self.notifier.send(f"PE target {old} → {v} by Telegram ({chat_id})")
            return f"✅ PE target: `{old}` → *`{v}`* (next PE entry)"
        except Exception as e:
            return f"⚠️ failed: {e}"

    def _cmd_set_ce_target(self, args, chat_id, raw_msg):
        if not args or not args[0].isdigit():
            return f"Current CE target: `Rs {self.config['ce_leg']['target_premium']}`\nUsage: `/set_ce_target 120`"
        try:
            v = int(args[0])
            if not 10 <= v <= 500:
                return "10..500"
            old = self.config["ce_leg"]["target_premium"]
            self.config["ce_leg"]["target_premium"] = v
            self._save_config()
            self.notifier.send(f"CE target {old} → {v} by Telegram ({chat_id})")
            return f"✅ CE target: `{old}` → *`{v}`*"
        except Exception as e:
            return f"⚠️ failed: {e}"

    def _cmd_set_ce_exit(self, args, chat_id, raw_msg):
        if not args or not args[0].isdigit():
            return f"Current CE exit threshold: `Rs {self.config['ce_leg']['exit_premium_threshold']}`\nUsage: `/set_ce_exit 90`"
        try:
            v = int(args[0])
            if not 10 <= v <= 300:
                return "10..300"
            old = self.config["ce_leg"]["exit_premium_threshold"]
            self.config["ce_leg"]["exit_premium_threshold"] = v
            self._save_config()
            self.notifier.send(f"CE exit {old} → {v} by Telegram ({chat_id})")
            return f"✅ CE exit threshold: `{old}` → *`{v}`*"
        except Exception as e:
            return f"⚠️ failed: {e}"

    def _cmd_set_sl(self, args, chat_id, raw_msg):
        if not args or not args[0].isdigit():
            cur = self.config["pe_leg"]["stop_loss"].get("trigger_pct", 40)
            return f"Current PE SL: `+{cur}%`\nUsage: `/set_sl 40`  (pe_leg.stop_loss.trigger_pct)"
        try:
            v = int(args[0])
            if not 5 <= v <= 200:
                return "5..200%"
            old = self.config["pe_leg"]["stop_loss"]["trigger_pct"]
            self.config["pe_leg"]["stop_loss"]["trigger_pct"] = v
            self._save_config()
            self.notifier.send(f"PE SL {old}% → {v}% by Telegram ({chat_id})")
            return f"✅ PE SL: `+{old}%` → *`+{v}%`*"
        except Exception as e:
            return f"⚠️ failed: {e}"

    def _cmd_set_maxloss(self, args, chat_id, raw_msg):
        if not args or not args[0].lstrip("-").isdigit():
            return f"Current max_daily_loss: `Rs {self.config['risk']['max_daily_loss']}`\nUsage: `/set_maxloss 15000`"
        try:
            v = int(args[0])
            if not 1000 <= abs(v) <= 500000:
                return "1000..500000"
            old = self.config["risk"]["max_daily_loss"]
            self.config["risk"]["max_daily_loss"] = abs(v)
            self._save_config()
            self.notifier.send(f"Max daily loss {old} → {abs(v)} by Telegram ({chat_id})")
            return f"✅ Max daily loss: `Rs{old}` → *`Rs{abs(v)}`*"
        except Exception as e:
            return f"⚠️ failed: {e}"

    def _cmd_set_maxrolls(self, args, chat_id, raw_msg):
        if not args or not args[0].isdigit():
            return f"Current max_rolls_per_day: `{self.config['ce_leg']['max_rolls_per_day']}`\nUsage: `/set_maxrolls 15`"
        try:
            v = int(args[0])
            if not 0 <= v <= 50:
                return "0..50"
            old = self.config["ce_leg"]["max_rolls_per_day"]
            self.config["ce_leg"]["max_rolls_per_day"] = v
            self._save_config()
            self.notifier.send(f"Max rolls {old} → {v} by Telegram ({chat_id})")
            return f"✅ Max rolls/day: `{old}` → *`{v}`*"
        except Exception as e:
            return f"⚠️ failed: {e}"

    def _cmd_set_tolerance(self, args, chat_id, raw_msg):
        # /set_tolerance pe 60  or ce 15
        if len(args) < 2 or args[0].lower() not in ("pe", "ce") or not args[1].isdigit():
            return f"Pe tol: {self.config['pe_leg']['premium_tolerance']}  Ce tol: {self.config['ce_leg']['premium_tolerance']}\nUsage: `/set_tolerance pe 60`  or `/set_tolerance ce 15`"
        try:
            leg = args[0].lower()
            v = int(args[1])
            old = self.config[f"{leg}_leg"]["premium_tolerance"]
            self.config[f"{leg}_leg"]["premium_tolerance"] = v
            self._save_config()
            return f"✅ {leg.upper()} tolerance: `{old}` → *`{v}`*"
        except Exception as e:
            return f"⚠️ failed: {e}"

    def _cmd_ping(self, args, chat_id, raw_msg):
        """
        Zero-dependency liveness check: no state/kite/strategy calls, so it
        answers even if something else is broken — the fastest way to confirm
        the bot received your message and can reply, independent of whether
        any trading logic ran this cycle.
        """
        now = datetime.now()
        return f"🏓 pong — bot alive at `{now.strftime('%Y-%m-%d %H:%M:%S')}`"

    # ---------- HELP ----------
    def _cmd_help(self, args, chat_id, raw_msg):
        return (
            "*🤖 Telegram Control — 29+ Commands*\n"
            "Only your chat is authorized. Works on VPS (<3s) and Free Actions (≤1 min via cron-job.org).\n"
            "Data-heavy replies (`/status` `/positions` `/legs` `/pnl` `/config` `/risk` `/overall` `/history`) render as tables.\n"
            "\n*Monitor:*\n"
            "`/ping` — is the bot alive right now (no state/API calls)\n"
            "`/status` — full snapshot (overall PnL = real+unreal, legs table)\n"
            "`/positions` — broker vs state table, mismatch alert\n"
            "`/legs` — PE/CE detail table + live LTP & unreal\n"
            "`/pnl` — today real + overall + last 5 events table\n"
            "`/overall` / `/total` — overall today (real+unreal) vs MAXLOSS\n"
            "`/spot` — Nifty spot 256265\n"
            "`/quote NFO:SYMBOL` — e.g. `/quote NFO:NIFTY24JUN22500CE`\n"
            "`/config` — PE/CE/Risk tables\n"
            "`/risk` — hours, kill, real vs total breach, overall PnL\n"
            "`/pe_profit` — PE take-profit config & trigger status (currently OFF)\n"
            "`/health` — heartbeat & mode  `/history [N]` — last N events table\n"
            "\n*Control:*\n"
            "`/pause` — ⛔ STOP_TRADING → no new entries/rolls (keep positions)\n"
            "`/resume` — ✅ remove STOP_TRADING\n"
            "`/stop`/`/flatten` — 🛑 square ALL + pause\n"
            "`/squareoff PE|CE|ALL` — close one/both (qty = actual position qty)\n"
            "`/reconcile` — re-adopt broker shorts\n"
            "\n*Mode & Qty (qty = real lot from Zerodha, roll preserves qty):*\n"
            "`/mode` / `/mode paper` / `/mode live confirm`\n"
            "`/qty` `/qty 2` (both) `/qty pe 1` `/qty ce 2` — next entry lots; roll uses same qty as closed leg\n"
            "\n*Enable/Disable:*\n"
            "`/enable_pe` `/disable_pe`  `/enable_ce` `/disable_ce`\n"
            "\n*Tuning (persisted):*\n"
            "`/set_pe_target 700`  `/set_ce_target 120`  `/set_ce_exit 90`\n"
            "`/set_sl 40`  `/set_pe_profit 15` (PE TP % + min 20pts, overall>0)  `/set_maxloss 15000` (total)\n"
            "`/set_maxrolls 15`  `/set_tolerance pe 60`\n"
            "\n*Lot & Premium:* CE picks closest of ATM±2 (5 strikes, ±100) to Rs120 — whichever feasible; `lot_size` is real from kite.instruments, not 75.\n"
            "*MAXLOSS:* now total (real+unreal) via `total_loss_breached` — covers closed + open, not just realized.\n"
        )
