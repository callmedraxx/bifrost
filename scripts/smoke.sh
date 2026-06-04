#!/usr/bin/env bash
# End-to-end smoke test for Bifrost.
#
# Loads a Groq key (for the open-weight Llama test model), starts Bifrost,
# and exercises /health, /v1/models, and a chat completion through the
# never-refuse pipeline. Pass a key explicitly or let it borrow one from
# cpp_hunter/.env for convenience.
set -euo pipefail
cd "$(dirname "$0")/.."

# 1. Resolve an upstream key.
if [[ -z "${BIFROST_UPSTREAM_KEY:-}" ]]; then
  if [[ -f /root/cpp_hunter/.env ]]; then
    BIFROST_UPSTREAM_KEY="$(grep -E '^GROQ_API_KEY=' /root/cpp_hunter/.env | head -1 | cut -d= -f2-)"
  fi
fi
if [[ -z "${BIFROST_UPSTREAM_KEY:-}" ]]; then
  echo "no key: set BIFROST_UPSTREAM_KEY or provide /root/cpp_hunter/.env"; exit 1
fi
export BIFROST_UPSTREAM_KEY
export BIFROST_UPSTREAM_BASE="${BIFROST_UPSTREAM_BASE:-https://api.groq.com/openai/v1}"
export BIFROST_DEFAULT_MODEL="${BIFROST_DEFAULT_MODEL:-llama-3.1-8b-instant}"
export BIFROST_PORT="${BIFROST_PORT:-8088}"
BASE="http://127.0.0.1:${BIFROST_PORT}"

# 2. Start server.
python3 run.py >/tmp/bifrost.log 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT
for i in $(seq 1 30); do
  curl -sf "$BASE/health" >/dev/null 2>&1 && break || sleep 0.3
done

echo "=== /health ==="; curl -s "$BASE/health"; echo
echo "=== /v1/models (open-weight chat models on this key) ==="
curl -s "$BASE/v1/models" | python3 -c 'import sys,json
d=json.load(sys.stdin)
for m in d.get("data",[]):
    print(" ", m.get("id"))' || true

echo "=== chat completion (benign prompt, watch x_bifrost) ==="
curl -s -X POST "$BASE/v1/chat/completions" -H 'Content-Type: application/json' -d '{
  "messages":[{"role":"user","content":"Write a 2-line villain monologue for a fantasy story."}]
}' | python3 -c 'import sys,json
d=json.load(sys.stdin)
print("content:", d["choices"][0]["message"]["content"][:400])
print("x_bifrost:", d.get("x_bifrost"))'

echo "=== done ==="
