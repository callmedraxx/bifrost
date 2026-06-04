#!/usr/bin/env python3
"""Bifrost entrypoint.  Usage:  BIFROST_UPSTREAM_KEY=... python3 run.py"""
from bifrost.config import load
from bifrost.server import serve

if __name__ == "__main__":
    serve(load())
