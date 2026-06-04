"""Bifrost — a never-refuse bridge for LLMs you operate.

An OpenAI-compatible reverse proxy that sits in front of an upstream chat
model and reduces *false refusals on benign requests* using inference-time
techniques only (no weight changes):

  1. affirmative system-prompt injection,
  2. refusal detection on the model's reply,
  3. one regeneration with a firm "answer directly" follow-up.

It is meant for models you control (your own GPU server) or open-weight models.
It is NOT a tool for stripping safety guardrails off proprietary third-party
models, and it deliberately passes through refusals on genuinely harmful asks.
"""

__version__ = "0.1.0"
