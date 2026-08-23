# Kite Auto Trader

Fully automated Nifty option-selling bot built on top of this repo's
`kite_websocket` client (for live monitoring) plus the official
`kiteconnect` SDK (for auth/orders). Designed to run unattended on a
server 24/7 instead of on your own machine — see `deploy/DEPLOY.md`.

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
│   ├── ticker_feed.py    live LTPs via this repo's kite_websocket.KiteWebSocket
│   ├── health.py         HTTP healthcheck endpoint for uptime monitoring
│   └── main.py           wires it all together, runs the loop
├── deploy/                Docker + systemd + step-by-step VPS deployment guide
├── scripts/               stop_trading.sh / resume_trading.sh (kill switch)
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
3. Deploy per `deploy/DEPLOY.md` so it survives your machine going offline.
4. Keep `quantity_lots: 1` until you trust it; scale up deliberately.

## Kill switch

```bash
./scripts/stop_trading.sh    # pause new entries/rolls; open positions untouched
./scripts/resume_trading.sh  # resume
```

If `risk.max_daily_loss` is breached, the bot squares off both legs and
halts new entries for the rest of that day automatically.

## Tests

```bash
cd auto_trader
pytest
```

These cover the pure decision logic (ATM/ITM/OTM math, roll-trigger
conditions, risk guards) with no live API calls.

## Known limitations / possible next steps

- Single account, single underlying (NIFTY), two legs exactly as
  described above — not a general-purpose multi-strategy engine.
- No margin pre-check before placing entry orders (`kite.order_margins`)
  — an order can still fail at the broker if margin is insufficient.
- No hedge legs; the PE/CE are fully naked.
- NSE holiday calendar isn't built in — add dates to `risk.holidays` in
  `config.yaml` as they come up, or the bot will otherwise assume it's a
  trading day.
