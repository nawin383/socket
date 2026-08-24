# Deploying to a cheap always-on VPS

This gets the bot running 24/7 on a server that isn't your laptop, so it
doesn't stop when your machine goes offline. Two options are covered:
Docker (recommended — easiest to keep updated/restarted) and bare-metal
systemd (if you'd rather not use Docker).

**Not using Oracle Cloud** — its Always Free tier's signup/fraud checks
are well known to reject valid accounts for no clear reason, which isn't
worth fighting. Instead, use a small paid VPS from a provider with an
India data center — that also happens to put the bot physically close to
Zerodha's own infrastructure (Mumbai), which is the thing that actually
affects order-placement latency, more than which cloud brand you pick.

**Recommended: DigitalOcean, Bangalore region (BLR1)** — smoothest signup
of the mature providers, simple billing, ~$6/mo for a 1 GB droplet (this
bot barely uses any CPU/RAM, so the smallest size is plenty). Equally good
drop-in alternatives if DigitalOcean's signup gives you any trouble:
**Vultr** (Mumbai region) or **Linode/Akamai** (Mumbai region) — same
price range, same setup steps below, just pick their India region at
creation time. All three take a card or PayPal, none of them run the kind
of aggressive identity-verification gauntlet Oracle's free tier does.

Realistically, at the polling/roll cadence this bot runs at (seconds, not
milliseconds), the India-region latency advantage over a US/EU box is a
few tens of milliseconds — it won't make or break the strategy's P&L. It's
worth having anyway since it costs nothing extra, but don't mistake it for
the difference between a fast and slow fill.

## 1. Provision the server

1. Sign up at digitalocean.com (or vultr.com / linode.com as a backup).
2. Create a Droplet (DO) / Instance (Vultr) / Linode:
   - **Region**: Bangalore (DO) or Mumbai (Vultr/Linode).
   - **Image**: Ubuntu 22.04 LTS.
   - **Size**: the smallest/cheapest tier (1 vCPU, 1 GB RAM is comfortable).
   - **Auth**: add your SSH public key; skip password auth.
3. Once it boots, SSH in and lock down the firewall:
   `ufw allow OpenSSH && ufw allow 8080/tcp && ufw enable` (8080 is the
   healthcheck endpoint — only open it if you want external uptime
   monitoring to hit it directly; otherwise leave it closed and check
   health via `curl localhost:8080` over SSH instead).

## 2. Option A — Docker (recommended)

```bash
# On the server
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin git

git clone <your-fork-of-this-repo>.git
cd socket/auto_trader
cp .env.example .env
nano .env               # fill in API key/secret, Kite login, TOTP secret, Telegram

# Review config/config.yaml — leave mode: paper for your first run.

cd deploy
docker compose up -d --build
docker compose logs -f          # watch it start up and log in
```

To upgrade later: `git pull && docker compose up -d --build`.

To check health: `curl localhost:8080` (from the server) should return
JSON with a recent `last_heartbeat`.

## 2. Option B — Bare metal + systemd

```bash
apt install -y python3.11-venv git
git clone <your-fork-of-this-repo>.git /opt/kite-trader
cd /opt/kite-trader
python3 -m venv venv
./venv/bin/pip install -e .                              # installs kite_websocket
./venv/bin/pip install -r auto_trader/requirements.txt

cd auto_trader
cp .env.example .env
nano .env

sudo cp deploy/kite-trader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kite-trader
sudo systemctl status kite-trader
tail -f /var/log/kite-trader.log
```

## 3. Validate before going live

1. `python -m src.auth` (inside the container: `docker compose exec
   kite-trader python -m src.auth`) — confirms the automated TOTP login
   actually works, before trusting it to run unattended at 8 AM.
2. Leave `mode: paper` in `config/config.yaml` for at least a full trading
   day. Watch the Telegram messages / logs to confirm strikes, premiums,
   and roll triggers look right.
3. Only then set `mode: live` and restart (`docker compose up -d` or
   `systemctl restart kite-trader`).
4. Start with `quantity_lots: 1` on both legs until you trust the
   behavior — this strategy sells naked options (undefined-risk short
   PE/CE), so size it deliberately.

## 4. Stay aware if it goes down

- Point a free uptime monitor (UptimeRobot, healthchecks.io, Better
  Uptime) at `http://<server-ip>:8080` on a 1-5 minute interval, alerting
  you by SMS/push/email if it stops responding.
- Telegram alerts fire on every entry, roll, square-off, daily re-login,
  and crash — keep notifications on for that chat.
- Docker: `restart: unless-stopped` and systemd: `Restart=always` mean a
  crashed process comes back on its own; but a *server* reboot, network
  outage, or Zerodha changing its login page won't fix itself — that's
  what the uptime monitor + Telegram alerts are for.

## 5. Pausing without stopping the service

Touch the kill-switch file to pause new entries/rolls without killing the
process (existing open positions are left alone, not force-closed):

```bash
touch auto_trader/data/STOP_TRADING     # pause
rm auto_trader/data/STOP_TRADING        # resume
```

## 6. Backing up state

`auto_trader/data/state.db` is the bot's memory of what's currently open.
Back it up periodically (e.g. a nightly `scp` off the box) — losing it
while a position is open means the bot won't know that leg exists until
`reconcile_from_broker()` picks it back up from your actual Kite positions
at next startup (best-effort; verify manually after any data loss).
