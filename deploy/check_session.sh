#!/bin/bash
set -euo pipefail
cd /opt/exnova-bot

journalctl -u exnova-runner.service --since "today" --no-pager \
  | grep -E 'connect:|balance|WIN|LOSS|=== |ssid|error|rechazada|sin pares|payout bajo|kill' \
  | tail -n 60 > /tmp/session_journal.txt || true

DISCORD_WEBHOOK_URL=$(grep -oP '(?<=^DISCORD_WEBHOOK_URL=).*' .env | tr -d '"' | tr -d "'")

docker run --rm --entrypoint python \
  -v /opt/exnova-bot/db:/app/db:ro \
  -v /opt/exnova-bot/scripts/session_report.py:/app/session_report.py:ro \
  -v /tmp/session_journal.txt:/tmp/session_journal.txt:ro \
  -e BOT_DB_PATH=/app/db/bot_data.db \
  -e DISCORD_WEBHOOK_URL="$DISCORD_WEBHOOK_URL" \
  ghcr.io/angelrmatoz/exnova-bot-runner:latest /app/session_report.py
