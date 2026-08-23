#!/usr/bin/env bash
# Pause new entries/rolls without stopping the process or touching open positions.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
touch "$DIR/data/STOP_TRADING"
echo "Kill switch ON: $DIR/data/STOP_TRADING"
