"""
Shared table-rendering helper for Telegram messages.

Telegram only renders monospace inside code spans/blocks — plain text with
manual space-padding does NOT line up on the actual client, it renders in
a proportional font. Wrapping in a ``` code block also sidesteps Markdown
parsing entirely, so tradingsymbols, negative PnL signs, etc. can never
break message delivery.

Extracted out of telegram_bot.py so strategy.py (auto EOD summary, weekly/
monthly rollups) can build the same kind of table without importing the
Telegram bot's heavier dependencies (requests, threading).
"""


def render_table(headers, rows) -> str:
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


def short_symbol(tradingsymbol: str, underlying_name: str) -> str:
    """Strip the redundant underlying-name prefix for table cells — e.g.
    "NIFTY26SEP25000PE" -> "26SEP25000PE" when underlying_name="NIFTY"."""
    return tradingsymbol[len(underlying_name):] if tradingsymbol.startswith(underlying_name) else tradingsymbol
