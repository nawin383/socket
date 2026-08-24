#!/usr/bin/env bash
# Resume new entries/rolls after stop_trading.sh.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rm -f "$DIR/data/STOP_TRADING"
echo "Kill switch OFF"
