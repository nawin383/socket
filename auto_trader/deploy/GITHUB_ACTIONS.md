# Deploying via GitHub Actions (no server, no terminal required)

An alternative to `DEPLOY.md`'s VPS setup: instead of an always-on server,
GitHub runs `src/poll_once.py` on a schedule (every 5 minutes during and
around market hours). There's no persistent process, no SSH, no Docker —
every step below can be done from a browser, which matters if you don't
have a working terminal/personal computer available.

## What's different from the VPS version

- **No live tick feed.** Each run fetches the spot and CE prices once via
  REST and checks the roll condition, then exits. A roll can lag up to
  one polling interval (~5 min, sometimes more — GitHub's schedule
  trigger is best-effort) behind where the always-on/tick-based bot would
  catch it instantly.
- **No persistent server to health-check.** There's nothing to `curl` for
  a heartbeat; monitoring instead means watching for the workflow itself
  to stop running (see "Monitoring" below).
- **State lives in the repo, not on a machine.** `auto_trader/data/state.db`
  (open legs, roll history, daily P&L) is committed back to the repo by
  the workflow after every run that changes it. `auto_trader/data/access_token.json`
  (today's login token) is *not* committed — it's kept in GitHub Actions
  cache instead, since it's a credential-adjacent value that shouldn't sit
  in permanent git history.
- **The kill switch is a file in the repo.** Create an empty file at
  `auto_trader/data/STOP_TRADING` via GitHub's web UI to pause new
  entries/rolls; delete it to resume. No terminal needed.

## 1. Add your secrets (browser only)

Repo → **Settings → Secrets and variables → Actions → New repository
secret**. Add each of these (same values as `.env.example` describes):

`KITE_API_KEY`, `KITE_API_SECRET`, `KITE_USER_ID`, `KITE_PASSWORD`,
`KITE_TOTP_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

These never appear in logs or in any committed file — only the workflow
run can read them, injected as environment variables.

## 2. Review the strategy config (browser only)

Open `auto_trader/config/config.yaml` in the repo, click the pencil
("Edit this file") icon, and check:

- `mode: paper` — **leave this as `paper` for your first several days.**
  There is no live-tick feedback loop here to catch a config mistake
  quickly; a bad strike/threshold could sit unnoticed for a whole 5-minute
  cycle in live mode.
- `pe_leg.target_premium`, `ce_leg.target_premium`,
  `ce_leg.exit_premium_threshold` — match what you described (₹700 / ₹120 / ₹90).
- `risk.max_daily_loss` — your circuit breaker amount.

Commit the change directly on `main` (or your working branch) via the
web editor's "Commit changes" button.

## 3. Enable and test the workflow (browser only)

1. Repo → **Actions** tab → find "Kite Auto Trader" in the left sidebar →
   if prompted, click "I understand my workflows, go ahead and enable
   them."
2. Click **Run workflow** (the manual `workflow_dispatch` trigger) to fire
   one poll cycle immediately, instead of waiting for the next scheduled
   tick.
3. Click into the run and watch the "Run one poll cycle" step's log. A
   successful first run logs in via TOTP and prints `Generated fresh Kite
   access_token`. Any failure here (wrong credentials, TOTP secret typo,
   Zerodha login flow changed) shows in this log and is also sent to
   Telegram if notifications are configured.
4. Once that's clean, the `*/5 2-10 * * 1-5` schedule in
   `.github/workflows/trade.yml` takes over automatically — no further
   action needed.

## 4. Monitoring — knowing if it stops running

- **Telegram** fires on every entry, roll, square-off, and login failure
  — same as the VPS version.
- **The Actions tab is your dashboard.** Repo → Actions → "Kite Auto
  Trader" shows every run's status. GitHub also emails the repo owner by
  default when a scheduled workflow run fails.
- **Optional dead-man's-switch**: sign up free at healthchecks.io (no
  card), create a check with an expected period of ~10 minutes, copy its
  ping URL, and add it as a repository **variable** (not secret) named
  `HEALTHCHECKS_PING_URL` under Settings → Secrets and variables →
  Actions → Variables. The workflow pings it after every run; if GitHub
  Actions itself stops firing (quota exhausted, repo inactivity, a GitHub
  outage), healthchecks.io notices the ping stopped arriving and alerts
  you by email — catching the one failure mode Telegram-from-inside-the-run
  can't (the run never happening at all).

## 5. Cost: GitHub Actions minutes

- If this repository is **public**, Actions minutes are unlimited and
  free. Nothing sensitive is ever committed (secrets stay in Actions
  Secrets, never in files) — `state.db` only holds tradingsymbols, prices,
  and P&L numbers.
- If it's **private**, the free plan includes 2,000 minutes/month. The
  default schedule (every 5 minutes, ~9 hours/weekday) uses roughly
  1,000–1,900 minutes/month depending on run speed — close enough to the
  limit that it's worth watching Settings → Billing → Actions usage for
  the first month. If you're going over, narrow the cron window in
  `.github/workflows/trade.yml` to more tightly match `risk.trading_start`
  /`risk.trading_end`, or make the repo public.

## 6. Going live

Same discipline as the VPS path: once you've watched a full clean day in
`paper` mode, set `mode: live` via the web editor, keep `quantity_lots: 1`
on both legs, and watch the first few live rolls closely.
