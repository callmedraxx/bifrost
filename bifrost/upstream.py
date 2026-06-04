"""Thin OpenAI-compatible upstream client (stdlib only)."""
import json
import urllib.request
import urllib.error
from typing import Any

from .config import Config


class UpstreamError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"upstream {status}: {body[:200]}")
        self.status = status
        self.body = body


def _request(cfg: Config, path: str, payload: dict[str, Any] | None, method: str = "POST") -> dict[str, Any]:
    url = f"{cfg.upstream_base}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {cfg.upstream_key}",
            "Content-Type": "application/json",
            # Some upstreams sit behind Cloudflare, which blocks the default
            # urllib User-Agent (error 1010). Present a normal UA.
            "User-Agent": "Bifrost/0.1 (+https://github.com/) python-urllib",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg.upstream_timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if e.fp else ""
        raise UpstreamError(e.code, body) from e
    except urllib.error.URLError as e:
        raise UpstreamError(502, str(e.reason)) from e


def chat_completion(cfg: Config, payload: dict[str, Any]) -> dict[str, Any]:
    """Non-streaming chat completion. Forces stream=False upstream so we can
    inspect (and if needed regenerate) the reply before responding."""
    body = dict(payload)
    body["stream"] = False
    return _request(cfg, "/chat/completions", body)


def list_models(cfg: Config) -> dict[str, Any]:
    return _request(cfg, "/models", None, method="GET")


def reply_text(resp: dict[str, Any]) -> str:
    try:
        return (resp["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError):
        return ""
