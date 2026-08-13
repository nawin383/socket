# StockMock Option Chain Archiver

Pulls the StockMock Nifty option chain for every trading weekday over a
date range and writes it to a single Excel file, resuming safely if
interrupted or if your token expires mid-run.

## Install

```bash
pip install -r stockmock_archiver/requirements.txt
```

## Auth token

The script never stores your token in source. Provide it one of three
ways, in priority order:

1. `--token <value>`
2. `STOCKMOCK_TOKEN` environment variable
3. Interactive prompt (asked at startup if neither of the above is set)

Get a token from StockMock's site: DevTools (F12) -> Network -> Fetch/XHR
-> `getPlainAllOC` -> Headers -> `token`.

If the token expires mid-run (HTTP 401/403), the run pauses and asks for
a fresh one in the terminal, then resumes the exact same snapshot -- no
data is lost and no re-run is needed.

## Usage

```bash
# Last 4 years, expiry-day intraday snapshots (the default behaviour)
STOCKMOCK_TOKEN=your_token python -m stockmock_archiver.archiver

# Explicit date range, single daily snapshot
python -m stockmock_archiver.archiver \
  --token your_token \
  --start-date 2022-08-14 --end-date 2026-08-14 \
  --time-mode single --selected-time 09:16:00

# Intraday snapshots on every date (heaviest)
python -m stockmock_archiver.archiver --token your_token --time-mode multi_all
```

Run `python -m stockmock_archiver.archiver --help` for the full flag
list (index, cache/output paths, request delay, retry count, expiry
weekdays, etc).

### Time modes

- `single` -- one snapshot per day at `--selected-time`.
- `multi_all` -- intraday snapshots (open -> close) for every date. Heaviest.
- `expiry_weekday` (default) -- intraday snapshots only on
  `--expiry-weekdays`, a single snapshot on every other date. Good
  default for expiry-day theta-decay analysis without exploding the
  request count on non-expiry days.

**Caveat:** NSE's Nifty weekly-expiry weekday has changed more than once
(historically Thursday, briefly Monday/Wednesday, Tuesday from late
2024 onward). The script has no way to know a historical date's actual
expiry day without fetching it first, so `expiry_weekday` is a
heuristic based on weekday, not a guarantee -- pass
`--expiry-weekdays` to match the regime(s) your date range spans.

## Resuming

Every `(date, time)` snapshot is cached to `--cache` (CSV) as it's
fetched. Re-running the same command skips anything already cached --
including snapshots that came back with no data (holidays), which are
recorded with an `expiry` value of `NO_DATA` so they aren't re-fetched
either. Delete the cache file to start over.

Weekends are skipped automatically. Exchange holidays aren't known in
advance -- they come back as "no data" for that date+time and are
recorded as such rather than treated as an error.

## Output

An `.xlsx` file (`--output`) with two sheets:

- **Option Chain** -- one row per strike/expiry/snapshot, with a
  formatted, frozen header row and auto-sized columns.
- **Summary** -- index, row counts, date range, time mode, and
  generation timestamp.
