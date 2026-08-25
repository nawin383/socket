# Kite Auto Trader

Fully automated Nifty option-selling bot built on top of this repo's
`kite_websocket` client (for live monitoring) plus the official
`kiteconnect` SDK (for auth/orders). Designed to run unattended instead of
on your own machine, via either of two deployment paths:

- **`deploy/DEPLOY.md`** — an always-on VPS running `src/main.py`, with a
  live tick feed and sub-second roll reaction time. Needs a server and a
  terminal.
- **`deploy/GITHUB_ACTIONS.md`** — no server at all: GitHub runs
  `src/poll_once.py` on a schedule (~every 5 min) during market hours.
  Everything is configured through a browser (repo Settings, the web file
  editor, the Actions tab) — no terminal required. Roll reactions lag by
  up to one polling interval instead of being instant.

## ⚠️ Read this first

- This places **real orders with real money** once `mode: live` in
  `config/config.yaml`. Always validate in `mode: paper` first.
- The strategy sells **naked options** (uncovered short PE and short CE).
  Risk on each leg is large and, in principle, unbounded if the market
  moves sharply against it — there is no hedge leg in this build. Position
  size (`quantity_lots`), the daily loss limit (`risk.max_daily_loss`),
  and the kill switch are your safety controls; understand them before
  going live.
- The automated daily login (`src/auth.py`) drives Zerodha's own login
  pages with your username/password/TOTP secret. It's a well-known
  community pattern, not an official API — it can break if Zerodha
  changes that flow, and it means those credentials live in your `.env`
  on the server. Test it explicitly (`python -m src.auth`) before relying
  on it unattended, and keep Telegram alerts on so a failed login doesn't
  go unnoticed.
- You are solely responsible for compliance with Zerodha's terms of use
  and applicable regulations for your account and jurisdiction.

## The strategy, as configured

- **PE leg**: one short ITM PE on the **monthly** expiry, entered near a
  ₹700 premium (`pe_leg.target_premium`). Held; automatically squared off
  on its expiry day at `pe_leg.close_before_expiry.time`.
- **CE leg**: one short ATM CE on the **weekly** expiry, entered near a
  ₹120 premium (`ce_leg.target_premium`). Continuously monitored on live
  ticks: whenever its premium decays below ₹90
  (`ce_leg.exit_premium_threshold`) **and** the strike has drifted OTM
  relative to spot, it's bought back and a fresh ATM CE is sold
  immediately — repeating all session, subject to `max_rolls_per_day` and
  `min_seconds_between_rolls` so it can't thrash on noisy ticks.

Both entry premiums, thresholds, quantities, and moneyness are config
values (`config/config.yaml`), not hardcoded — tune them there.

- **PE stop-loss + one tighter re-entry**: if held PE premium rises 40%
  above entry, exit and rest a SELL LIMIT re-entry 20 points cheaper on the
  same strike; if that fills, its own stop is a flat price (not a fresh
  40%), capping the second attempt's max loss at exactly that 20-point
  discount — with no third attempt either way. See
  [`docs/pe_stop_loss_reentry.md`](docs/pe_stop_loss_reentry.md) for the
  config reference and the honest tradeoff (helps whipsaws, costs a bit
  extra on real trends), and the architecture diagram artifact for the
  full flowchart.

## Project layout

```
auto_trader/
├── config/config.yaml   strategy + risk parameters
├── .env.example         secrets template (copy to .env, fill in, never commit)
├── src/
│   ├── auth.py           automated daily TOTP login -> access_token (cached per day)
│   ├── settings.py       loads .env + config.yaml
│   ├── instruments.py    expiry/strike lookup, ATM/ITM/OTM, premium search
│   ├── state.py          SQLite state: open legs, roll history, daily P&L
│   ├── risk.py           market hours, kill switch, daily loss limit
│   ├── order_manager.py  marketable-limit-then-market order execution (or paper simulation)
│   ├── strategy.py       the PE/CE entry + CE-rolling logic described above
│   ├── notifier.py       Telegram alerts
│   ├── ticker_feed.py    live LTPs via this repo's kite_websocket.KiteWebSocket (VPS path only)
│   ├── health.py         HTTP healthcheck endpoint for uptime monitoring (VPS path only)
│   ├── main.py           always-on entrypoint: wires it all together, runs the loop (VPS path)
│   ├── poll_once.py      single-shot entrypoint for the GitHub Actions schedule
│   └── backtest.py       test SL/roll parameter changes against a premium CSV you supply
├── deploy/                Docker + systemd VPS guide, and the GitHub Actions guide
├── scripts/               stop_trading.sh / resume_trading.sh (kill switch, VPS path)
└── tests/                 unit tests for the pure decision logic
```

## Local setup (for testing before deploying)

```bash
cd auto_trader
python -m venv venv && source venv/bin/activate
pip install -e ..                      # installs kite_websocket from the repo root
pip install -r requirements.txt

cp .env.example .env                   # fill in your credentials
python -m src.auth                     # confirms automated login works
python -m src.main                     # runs the bot (mode: paper by default)
```

`curl localhost:8080` while it's running shows a JSON heartbeat.

## Going live

1. Confirm a full day of clean `paper` mode behavior (check Telegram/logs
   for the strikes it picked and any roll events).
2. Set `mode: live` in `config/config.yaml`.
3. Deploy per `deploy/DEPLOY.md` (VPS) or `deploy/GITHUB_ACTIONS.md`
   (no server/terminal needed) so it survives your machine going offline.
4. Keep `quantity_lots: 1` until you trust it; scale up deliberately.

## Kill switch

VPS path: `./scripts/stop_trading.sh` / `./scripts/resume_trading.sh`
(pause/resume new entries/rolls; open positions untouched either way).

GitHub Actions path: create/delete an empty file at
`auto_trader/data/STOP_TRADING` via GitHub's web file editor.

If `risk.max_daily_loss` is breached, the bot squares off both legs and
halts new entries for the rest of that day automatically.

## Tests

```bash
cd auto_trader
pytest
```

These cover the pure decision logic (ATM/ITM/OTM math, roll-trigger
conditions, risk guards) with no live API calls.

## Backtesting a parameter change

`src/backtest.py` replays the PE stop-loss/re-entry and CE roll trigger
math against a premium time series you supply — e.g. to check whether a
different `trigger_pct` or `exit_premium_threshold` would have behaved
better on a real stretch of history, before changing it live. It does
**not** pick strikes/expiries automatically across time (that needs a
historical option-chain database this repo doesn't have) — you provide
the premium path for the contract(s) you want to test, e.g. via
`kite.historical_data(instrument_token, from_date, to_date, "day")` run
with your own credentials.

```bash
# PE: date,premium CSV, one held contract from entry to expiry
python -m src.backtest pe 700 75 40 pe_history.csv --reentry 20

# CE: date,premium,strike,spot CSV — reports roll-condition FREQUENCY
# (not a full re-entered-leg PnL chain; see the module docstring for why)
python -m src.backtest ce 90 ce_history.csv
```

## Web dashboard (free, always-on, no server)

`docs/index.html` is a static, single-file dashboard: legs, today's PnL,
recent events, and a 7-day trend, read live from `data/state.db` in the
repo — no VPS, no cost, hosted for free by GitHub Pages. A settings panel
lets you change the same fields the Telegram `/set_*` commands expose
(target premiums, stop-loss %, exit threshold, quantities, max daily loss,
mode) from a form instead of typing commands; saving commits straight to
`config/config.yaml`, edited surgically so every comment in the file is
preserved (not a full YAML parse+re-dump, which would silently wipe them —
worth knowing since that's what the Telegram bot's own `_save_config()`
does today).

**One-time setup:**
1. Repo **Settings → Pages** → Source: *Deploy from a branch* → branch:
   this repo's default branch, folder: `/docs` → Save. GitHub gives you a
   URL like `https://nawin383.github.io/socket/` within a minute or two —
   bookmark it, that's your dashboard from any browser, no login needed to
   just *view* it (the repo is public).
2. To *change* settings from the dashboard (not required just to watch
   it): create a fine-grained token at
   `github.com/settings/personal-access-tokens/new` — Repository access:
   only this repo; Permissions → Contents: **Read and write**. Paste it
   into the dashboard's Settings panel once; it's stored only in that
   browser's local storage and sent only to `api.github.com`.

Refresh is roughly 30 seconds client-side, plus whatever GitHub's own raw-
content CDN caches on top of that — this is a monitoring/tuning dashboard,
not a tick-by-tick terminal.

## Known limitations / possible next steps

- Single account, single underlying (NIFTY), two legs exactly as
  described above — not a general-purpose multi-strategy engine.
- No margin pre-check before placing entry orders (`kite.order_margins`)
  — an order can still fail at the broker if margin is insufficient.
- No hedge legs; the PE/CE are fully naked.
- NSE holiday calendar isn't built in — add dates to `risk.holidays` in
  `config.yaml` as they come up, or the bot will otherwise assume it's a
  trading day.
