"""Refusal detection and a lightweight harmful-intent guard.

`is_refusal` decides whether an assistant reply is a refusal/hedge that we want
to regenerate. `looks_harmful` inspects the *user's request* so that genuinely
harmful asks keep their refusal instead of being overridden — Bifrost fixes
false refusals on benign requests, it does not strip safety on harmful ones.
"""
import re

# Reply openers / phrases that signal a refusal or heavy hedging.
_REFUSAL_PATTERNS = [
    r"i\s*(?:'|’)?m\s+sorry",
    r"i\s+am\s+sorry",
    r"\bi\s+apologi[sz]e\b",
    r"\bsorry\b,?\s+but",
    r"i\s+can\s*(?:'|’)?t\s+(?:help|assist|do|provide|comply|create|write|continue)",
    r"i\s+cannot\s+(?:help|assist|do|provide|comply|create|write|continue|fulfill)",
    r"i\s+can\s+not\s+(?:help|assist|provide|comply)",
    r"i\s+won\s*(?:'|’)?t\s+(?:be\s+able|help|assist|provide)",
    r"i\s+will\s+not\s+(?:help|assist|provide|be\s+able)",
    r"i\s*(?:'|’)?m\s+(?:not\s+able|unable)\s+to",
    r"i\s+am\s+(?:not\s+able|unable)\s+to",
    r"i\s+do\s*(?:n(?:'|’)?t|\s+not)\s+(?:feel\s+comfortable|think\s+i\s+(?:can|should))",
    r"\bas\s+an\s+ai\b",
    r"\bi\s+must\s+decline\b",
    r"\bi\s+can\s*(?:'|’)?t\s+assist\s+with\s+that\b",
    r"that\s*(?:'|’)?s\s+not\s+something\s+i\s+can",
    r"\bit\s*(?:'|’)?s\s+not\s+appropriate\b",
    r"\bi\s*(?:'|’)?m\s+not\s+(?:going\s+to|able\s+to)\b",
]
# A refusal almost always shows up at the very start of the reply.
_REFUSAL_HEAD = re.compile(r"^\W*(?:" + "|".join(_REFUSAL_PATTERNS) + r")", re.IGNORECASE)
# ...but also catch a short reply that is entirely a refusal.
_REFUSAL_ANY = re.compile(r"(?:" + "|".join(_REFUSAL_PATTERNS) + r")", re.IGNORECASE)


def is_refusal(text: str) -> bool:
    if not text:
        return True  # an empty reply is a non-answer; treat as refusal
    head = text.strip()
    if _REFUSAL_HEAD.search(head):
        return True
    # Short replies that are basically just a refusal sentence.
    if len(head) <= 240 and _REFUSAL_ANY.search(head):
        return True
    return False


# Coarse markers of genuinely harmful intent in the *request*. Intentionally
# conservative: this only suppresses the affirmative retry, it never blocks a
# request the upstream model would have answered.
_HARMFUL_PATTERNS = [
    r"\b(?:build|make|synthesi[sz]e|manufacture)\s+a?\s*(?:bomb|explosive|bioweapon|nerve\s+agent|chemical\s+weapon)",
    r"\bhow\s+to\s+(?:kill|murder|poison)\s+(?:a\s+)?(?:person|someone|people|him|her|them)\b",
    r"\b(?:csam|child\s+(?:porn|sexual)|cp\b)",
    r"\bsynthesi[sz]e\s+(?:meth|fentanyl|sarin|ricin|vx)\b",
    r"\b(?:ddos|denial[- ]of[- ]service)\s+(?:attack|a\s+\w+\s+(?:site|server|network))",
    r"\bmass(?:-|\s)?(?:shoot|casualty|murder)\b",
    r"\bcredit\s+card\s+(?:dump|skimm)",
]
_HARMFUL_RE = re.compile("|".join(_HARMFUL_PATTERNS), re.IGNORECASE)


def looks_harmful(request_text: str) -> bool:
    return bool(request_text and _HARMFUL_RE.search(request_text))
