# Bifrost — a never-refuse bridge

Bifrost is an **OpenAI-compatible reverse proxy** that sits in front of a chat
model you operate and reduces **false refusals on benign requests** using
inference-time techniques only — **no weight changes**. Point any OpenAI client
(SDK, `curl`, your app) at Bifrost; it forwards to your upstream model and
applies the never-refuse pipeline.

## What it does

1. **Affirmative system injection** — prepends a preamble telling the model to
   answer directly and not refuse/hedge/moralize (merged in front of any system
   prompt the caller already sent).
2. **Refusal detection** — inspects the reply for refusal/hedge openers.
3. **One regeneration** — on a detected refusal, re-asks with the refused turn
   plus a firm "answer the request directly" follow-up (provider-agnostic — no
   reliance on assistant-prefill support), then keeps the better reply.

## Scope / intent

Bifrost is for models **you control** (your own GPU server) or **open-weight**
models. It is **not** a tool for stripping safety guardrails off proprietary
third-party models. By default (`BIFROST_PASSTHROUGH_HARMFUL=true`) it leaves
refusals on genuinely harmful requests untouched — it fixes over-refusal on
normal requests, it is not a jailbreak.

## Run

```bash
export BIFROST_UPSTREAM_BASE=http://127.0.0.1:8000/v1   # your vLLM/llama.cpp server
export BIFROST_UPSTREAM_KEY=...                          # upstream API key
export BIFROST_DEFAULT_MODEL=your-model
python3 run.py
```

Then use it exactly like the OpenAI API:

```bash
curl -s http://127.0.0.1:8088/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"..."}]}'
```

Or with the OpenAI SDK, set `base_url="http://127.0.0.1:8088/v1"`.

### Docker

```bash
cp .env.example .env          # fill in BIFROST_UPSTREAM_BASE / _KEY / _DEFAULT_MODEL
docker compose up --build -d  # http://127.0.0.1:8088
docker compose logs -f bifrost
```

The compose service binds to `127.0.0.1:8088` on the host. Public access goes
through a host nginx reverse proxy with TLS instead of exposing the port.

### Public access (TLS, no domain needed)

The live deployment is fronted by nginx + Let's Encrypt at
**`https://206.189.100.31.sslip.io`** — a `sslip.io` hostname that resolves to
the droplet IP, so a real browser-trusted cert can be issued without owning a
domain. Set `BIFROST_API_KEY` so the proxied endpoint requires a bearer token.
The nginx vhost is checked in at `deploy/nginx-bifrost.conf` (host-level config,
not managed by docker/CI). API routes (`/settings`, `/v1/chat/completions`)
require `Authorization: Bearer <BIFROST_API_KEY>`; `/health` is open.

## Endpoints

| Method | Path                   | Purpose                              |
|--------|------------------------|--------------------------------------|
| GET    | `/health`              | liveness + which upstream is wired   |
| GET    | `/v1/models`           | proxies the upstream model list      |
| POST   | `/v1/chat/completions` | never-refuse pipeline (OpenAI shape) |

Responses include an extra `x_bifrost` field describing what happened
(`injected_system`, `retries`, `refused_final`, `passthrough_harmful`).
Streaming (`"stream": true`) is supported by buffering upstream then re-emitting
the final answer as a single SSE delta + `[DONE]`.

## Config

All via environment (see `.env.example`): `BIFROST_HOST`, `BIFROST_PORT`,
`BIFROST_UPSTREAM_BASE`, `BIFROST_UPSTREAM_KEY`, `BIFROST_DEFAULT_MODEL`,
`BIFROST_INJECT_SYSTEM`, `BIFROST_MAX_RETRIES`, `BIFROST_RETRY_TEMPERATURE`,
`BIFROST_PASSTHROUGH_HARMFUL`, `BIFROST_SYSTEM`, `BIFROST_REBUTTAL`.

## Test

```bash
bash scripts/smoke.sh   # borrows an open-weight Llama via a Groq key to test plumbing
```

No third-party dependencies — Python 3.10+ standard library only.
