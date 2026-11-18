#!/bin/bash
set -euo pipefail
cd /opt/exnova-bot

journalctl -u exnova-runner.service --since "today" --no-pager \
  | grep -E 'connect:|balance|WIN|LOSS|=== |ssid|error|rechazada|sin pares|payout bajo|kill' \
  | tail -n 60 > /tmp/session_journal.txt || true

TG_TOKEN=$(grep -oP '(?<=^TELEGRAM_TOKEN=).*' .env | tr -d '"' | tr -d "'")
TG_CHAT_ID=$(grep -oP '(?<=^TELEGRAM_CHAT_ID=).*' .env | tr -d '"' | tr -d "'")

docker run --rm --entrypoint python \
  -v /opt/exnova-bot/db:/app/db:ro \
  -v /opt/exnova-bot/scripts/session_report.py:/app/session_report.py:ro \
  -v /tmp/session_journal.txt:/tmp/session_journal.txt:ro \
  -e BOT_DB_PATH=/app/db/bot_data.db \
  -e TELEGRAM_TOKEN="$TG_TOKEN" -e TELEGRAM_CHAT_ID="$TG_CHAT_ID" \
  ghcr.io/angelrmatoz/exnova-bot-runner:latest /app/session_report.py
