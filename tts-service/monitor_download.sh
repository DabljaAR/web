#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/.."
SERVICE="tts-service"
PREV=0

while true; do
  clear
  echo "=== OmniVoice Download Monitor ==="
  echo "$(date)"
  echo

  CACHED=$(docker compose exec "$SERVICE" du -sh /model-cache/hf/ 2>/dev/null | cut -f1)
  echo "Cached total: ${CACHED:-unknown}"

  INCOMPLETE=$(docker compose exec "$SERVICE" find /model-cache/hf/ -name '*.incomplete' -exec ls -la {} \; 2>/dev/null)
  if [ -n "$INCOMPLETE" ]; then
    FILES=$(echo "$INCOMPLETE" | wc -l)
    echo "Incomplete files: $FILES"
    echo "$INCOMPLETE" | awk '{printf "  %s (%d MB)\n", $NF, int($5/1024/1024)}'

    TOTAL=$(echo "$INCOMPLETE" | awk '{s+=$5} END {print int(s/1024/1024)}')
    echo "Downloading: ${TOTAL}MB"
  else
    echo "Status: DOWNLOAD COMPLETE! 🎉"
    echo
    echo "Checking model load status..."
    docker compose logs --tail=3 "$CONTAINER" 2>/dev/null
    echo
    echo "Monitor will exit in 5s..."
    sleep 5
    exit 0
  fi

  echo
  LATEST=$(docker compose exec "$SERVICE" bash -c 'ls -t /model-cache/hf/xet/logs/ 2>/dev/null | head -1' 2>/dev/null)
  if [ -n "$LATEST" ]; then
    SPEED=$(docker compose exec "$SERVICE" grep -o 'predicted bandwidth = [0-9]*' "/model-cache/hf/xet/logs/$LATEST" 2>/dev/null | tail -1 | grep -o '[0-9]*$')
    if [ -n "$SPEED" ] && [ "$SPEED" -gt 0 ] && [ "$SPEED" -lt 100000000000 ]; then
      echo "Speed: $(echo "scale=1; $SPEED / 1024 / 1024" | bc) MB/s"
    fi
    BYTES=$(docker compose exec "$SERVICE" grep -o 'observed bytes sent so far = [0-9]*' "/model-cache/hf/xet/logs/$LATEST" 2>/dev/null | tail -1 | grep -o '[0-9]*$')
    if [ -n "$BYTES" ]; then
      echo "Xet bytes sent: $(echo "scale=1; $BYTES / 1024 / 1024" | bc) MB"
    fi
  fi

  PREV=$TOTAL
  sleep 60
done
