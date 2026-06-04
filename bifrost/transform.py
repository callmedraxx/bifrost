"""Message-list transforms for the never-refuse pipeline."""
from typing import Any


def inject_system(messages: list[dict[str, Any]], preamble: str) -> list[dict[str, Any]]:
    """Prepend the affirmative preamble. If the caller already supplied a
    system message, merge ours in front of theirs rather than dropping it."""
    out = [dict(m) for m in messages]
    for m in out:
        if m.get("role") == "system":
            m["content"] = preamble + "\n\n" + str(m.get("content", ""))
            return out
    return [{"role": "system", "content": preamble}] + out


def last_user_text(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content", "")
            if isinstance(c, list):  # OpenAI content-parts form
                return " ".join(
                    part.get("text", "") for part in c if isinstance(part, dict)
                )
            return str(c)
    return ""


def build_retry_messages(
    messages: list[dict[str, Any]], refusal_reply: str, rebuttal: str
) -> list[dict[str, Any]]:
    """Append the refused reply + a firm follow-up demanding a direct answer.

    This works across any OpenAI-compatible upstream (Groq, vLLM, llama.cpp,
    Ollama) without relying on provider-specific assistant-prefill support.
    """
    return [
        *[dict(m) for m in messages],
        {"role": "assistant", "content": refusal_reply},
        {"role": "user", "content": rebuttal},
    ]
