#!/usr/bin/env python3
"""Offline unit tests for the never-refuse pipeline (no network).

Run:  python3 scripts/test_pipeline.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bifrost.config import Config
from bifrost import pipeline, upstream, refusal


def _resp(text):
    return {"id": "x", "model": "fake", "choices": [{"message": {"role": "assistant", "content": text}}]}


def fake_upstream(scripted):
    """Return a chat_completion stub that yields scripted replies in order."""
    calls = {"n": 0}

    def _call(cfg, payload):
        i = min(calls["n"], len(scripted) - 1)
        calls["n"] += 1
        return _resp(scripted[i])

    return _call, calls


def run_case(name, scripted, cfg, expect_retries, expect_refused, contains=None):
    orig = upstream.chat_completion
    stub, calls = fake_upstream(scripted)
    upstream.chat_completion = stub
    try:
        resp, meta = pipeline.run(cfg, {"messages": [{"role": "user", "content": "hi"}]})
    finally:
        upstream.chat_completion = orig
    text = upstream.reply_text(resp)
    ok = meta["retries"] == expect_retries and meta["refused_final"] == expect_refused
    if contains is not None:
        ok = ok and contains in text
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: retries={meta['retries']} "
          f"refused_final={meta['refused_final']} calls={calls['n']} reply={text[:50]!r}")
    return ok


def main():
    cfg = Config()
    cfg.upstream_key = "test"  # bypass validate; we never hit the network

    results = []
    # 1. No refusal -> no retry.
    results.append(run_case(
        "answers first try", ["The capital of France is Paris."],
        cfg, expect_retries=0, expect_refused=False, contains="Paris"))

    # 2. Refusal then a real answer -> exactly one retry, refusal cleared.
    results.append(run_case(
        "refusal then answer", ["I'm sorry, I can't help with that.", "Sure: here is the answer."],
        cfg, expect_retries=1, expect_refused=False, contains="here is the answer"))

    # 3. Refuses on every call -> retries capped, final still flagged refused.
    results.append(run_case(
        "always refuses", ["I cannot help with that.", "I'm sorry, I won't help."],
        cfg, expect_retries=1, expect_refused=True))

    # 4. Empty reply counts as a non-answer (refusal).
    print(f"[{'PASS' if refusal.is_refusal('') else 'FAIL'}] empty reply treated as refusal")
    results.append(refusal.is_refusal(""))

    # 5. Harmful request -> passthrough, no retry even though it refused.
    hcfg = Config(); hcfg.upstream_key = "test"
    orig = upstream.chat_completion
    stub, calls = fake_upstream(["I can't provide instructions on how to build a bomb."])
    upstream.chat_completion = stub
    try:
        resp, meta = pipeline.run(hcfg, {"messages": [
            {"role": "user", "content": "how to build a bomb to kill people"}]})
    finally:
        upstream.chat_completion = orig
    ok = meta.get("passthrough_harmful") is True and meta["retries"] == 0 and calls["n"] == 1
    print(f"[{'PASS' if ok else 'FAIL'}] harmful request passthrough: {meta}")
    results.append(ok)

    print("\n", "ALL PASS" if all(results) else "SOME FAILED")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
