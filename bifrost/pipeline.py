"""The never-refuse pipeline: inject -> call -> detect -> regenerate."""
from typing import Any

from .config import Config
from . import refusal, transform, upstream


def run(cfg: Config, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Process one chat-completion request.

    Returns (openai_response, meta) where meta describes what Bifrost did
    (exposed back to the caller as an `x_bifrost` field for observability).
    """
    messages = list(payload.get("messages") or [])
    user_text = transform.last_user_text(messages)
    meta: dict[str, Any] = {"injected_system": False, "retries": 0, "refused_final": False}

    # Master switch: when Bifrost is disabled, forward straight to the upstream
    # model with no injection, detection, or regeneration.
    if not cfg.enabled:
        resp = upstream.chat_completion(cfg, dict(payload))
        meta["bypassed"] = True
        meta["refused_final"] = refusal.is_refusal(upstream.reply_text(resp))
        _stamp(resp, meta)
        return resp, meta

    # Layer 1: affirmative system injection.
    work = dict(payload)
    if cfg.inject_system:
        work["messages"] = transform.inject_system(messages, cfg.system_preamble)
        meta["injected_system"] = True
    else:
        work["messages"] = messages

    resp = upstream.chat_completion(cfg, work)
    text = upstream.reply_text(resp)

    # Honesty guard: don't try to override a refusal on a genuinely harmful ask.
    if cfg.passthrough_harmful and refusal.looks_harmful(user_text):
        meta["passthrough_harmful"] = True
        meta["refused_final"] = refusal.is_refusal(text)
        _stamp(resp, meta)
        return resp, meta

    # Layers 2+3: detect refusal, regenerate with a firm follow-up.
    attempt = 0
    while refusal.is_refusal(text) and attempt < cfg.max_retries:
        attempt += 1
        retry = dict(payload)
        retry["messages"] = transform.inject_system(
            transform.build_retry_messages(messages, text, cfg.rebuttal),
            cfg.system_preamble,
        ) if cfg.inject_system else transform.build_retry_messages(messages, text, cfg.rebuttal)
        retry["temperature"] = cfg.retry_temperature
        new_resp = upstream.chat_completion(cfg, retry)
        new_text = upstream.reply_text(new_resp)
        # Keep the retry only if it actually improved (stopped refusing) or the
        # original was empty; otherwise fall back to the original reply.
        if new_text and not refusal.is_refusal(new_text):
            resp, text = new_resp, new_text
        elif not text:
            resp, text = new_resp, new_text

    meta["retries"] = attempt
    meta["refused_final"] = refusal.is_refusal(text)
    _stamp(resp, meta)
    return resp, meta


def _stamp(resp: dict[str, Any], meta: dict[str, Any]) -> None:
    if isinstance(resp, dict):
        resp["x_bifrost"] = meta
