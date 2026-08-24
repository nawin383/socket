# PE stop-loss and tighter re-entry

Visual walkthrough: see the "PE stop-loss, and one tighter re-entry" section
of the [architecture diagram](https://claude.ai/code/artifact/665bf965-522b-4b85-8f47-da906a8e643c).
This doc is the config reference and the reasoning behind it.

## The mechanism

1. **Original PE leg** — stop-loss trigger is `entry_price × (1 + trigger_pct / 100)`.
   e.g. entry 700, `trigger_pct: 40` → trigger at 980. Hitting it buys to close,
   locking in the full loss (280 points/lot in this example).
2. **If `reentry_after_stop_loss.enabled`**, that exit immediately rests a
   **SELL LIMIT** order on the *same strike* at `trigger_price - discount_points`
   (default discount 20 → 960). It does not chase price with a market order —
   it only fills if the premium actually comes back down to that level.
3. **If it fills**, that becomes a new PE leg — but its stop is a **flat price**
   at the *original* trigger (980), not a fresh 40% calculation from the new
   entry. Its max possible loss is therefore capped at exactly
   `discount_points` (20), by construction.
4. **That second leg never gets a third attempt.** If its flat stop hits, the
   bot goes flat on PE for the rest of the day — full stop.
5. **If the resting order never fills** by `order_valid_until` (default
   15:20 IST), it's cancelled and the bot stays flat for the rest of the day.

## Config (`pe_leg` in `config/config.yaml`)

```yaml
stop_loss:
  enabled: true
  trigger_pct: 40

reentry_after_stop_loss:
  enabled: true
  discount_points: 20
  order_valid_until: "15:20"
```

## The actual tradeoff — read this before trusting it blind

This is **not** a way to make stop-losses cheaper. It's a bet about *why*
the stop got hit:

- **Whipsaw** (price spiked, hit the stop, then genuinely came back): you
  get a cheaper second entry and, if it spikes again, lose only
  `discount_points` this time instead of nothing extra. Net: better than
  taking the original stop alone and staying out.
- **Real trend** (price keeps going against you, doesn't come back): you
  eventually get re-filled as it consolidates on the way, then get stopped
  again at the same level. Net: original stop-loss amount **plus**
  `discount_points` — worse than just taking the one stop and staying flat.

Whether this is worth it depends on how often stops on this specific PE leg
turn out to be whipsaws versus real moves — that's not something to guess
from first principles, it's something to read off `roll_history` /
`sl_events` in `data/state.db` after it's run for a while. If re-entries are
mostly landing on `STOP_LOSS_REENTRY` exits rather than expiring unfilled or
riding out the day, that's a sign real trends are triggering more of these
than whipsaws — worth reconsidering `discount_points` or disabling it.

## Tracking what happened

Every event lands in `roll_history` with an `action` you can filter on:

| action | what happened |
|---|---|
| `ENTER` | original leg opened |
| `STOP_LOSS` | original leg's percentage stop hit |
| `STOP_LOSS_REENTRY` | the re-entered leg's flat stop hit (the capped-loss case) |
| `EXPIRY_SQUAREOFF` | closed on its expiry day |
| `SQUAREOFF` | closed by daily-loss-limit or a manual square-off |

Telegram gets a message at every step too: the original stop firing, the
re-entry order being placed, it filling (with the computed max further
loss), or it expiring unfilled.
