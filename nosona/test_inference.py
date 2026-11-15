#!/usr/bin/env python3
"""
Verification script for the Nosana/Ollama inference endpoint.

Checks, in order:
  1. GET  /api/tags              -> model is actually registered (not just HTTP 200)
  2. POST /v1/chat/completions   -> plain chat completion works
  3. POST /v1/chat/completions   -> tool calling works (model returns tool_calls)

Usage:
    pip install requests python-dotenv --break-system-packages
    python test_inference.py

Reads config from environment variables (see .env.example), falling back to
the last verified working values if unset.
"""

import json
import os
import sys

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BASE_URL = os.environ.get(
    "NOSANA_BASE_URL",
    "https://51mkeksqRq6mKmTwAnVpTwRBuGQjodpizYakEvwd9L64.node.k8s.prd.nos.ci",
).rstrip("/")
MODEL_ID = os.environ.get("NOSANA_MODEL_ID", "glm-4.7-flash:q4_K_M")
CHAT_ENDPOINT = os.environ.get("NOSANA_CHAT_ENDPOINT", "/v1/chat/completions")

TIMEOUT = 120


def fail(msg):
    print(f"\n[FAIL] {msg}")
    sys.exit(1)


def check_tags():
    print("1) Checking /api/tags (model registration) ...")
    url = f"{BASE_URL}/api/tags"
    r = requests.get(url, timeout=TIMEOUT)
    print(f"   status={r.status_code}")
    data = r.json()
    models = data.get("models", [])
    if r.status_code != 200:
        fail(f"/api/tags returned HTTP {r.status_code}")
    if not models:
        fail(
            "/api/tags returned HTTP 200 but models list is EMPTY "
            "(this is the original bug — health checks alone would not catch this)"
        )
    names = [m.get("name") for m in models]
    print(f"   registered models: {names}")
    if MODEL_ID not in names:
        fail(f"expected model '{MODEL_ID}' not found in {names}")
    print("   OK: model is registered\n")
    return models[0]


def check_chat():
    print("2) Checking /v1/chat/completions (plain chat) ...")
    url = f"{BASE_URL}{CHAT_ENDPOINT}"
    payload = {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": "Say hello in exactly 3 words."}],
    }
    r = requests.post(url, json=payload, timeout=TIMEOUT)
    print(f"   status={r.status_code}")
    if r.status_code != 200:
        fail(f"chat completion failed: {r.text[:500]}")
    data = r.json()
    choice = data["choices"][0]["message"]
    print(f"   content: {choice.get('content')!r}")
    print("   OK: chat completions working\n")


def check_tool_calling():
    print("3) Checking tool calling ...")
    url = f"{BASE_URL}{CHAT_ENDPOINT}"
    payload = {
        "model": MODEL_ID,
        "messages": [
            {"role": "user", "content": "What is the weather in Tokyo? Use the get_weather tool."}
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the current weather for a city",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string", "description": "City name"}},
                        "required": ["city"],
                    },
                },
            }
        ],
        "tool_choice": "auto",
    }
    r = requests.post(url, json=payload, timeout=TIMEOUT)
    print(f"   status={r.status_code}")
    if r.status_code != 200:
        fail(f"tool-calling request failed: {r.text[:500]}")
    data = r.json()
    choice = data["choices"][0]
    message = choice["message"]
    tool_calls = message.get("tool_calls")
    print(f"   finish_reason: {choice.get('finish_reason')}")
    print(f"   tool_calls: {json.dumps(tool_calls)}")
    if not tool_calls:
        fail("model did not return tool_calls — tool calling may not be supported/triggered")
    print("   OK: tool calling working\n")


def main():
    print(f"Target: {BASE_URL}")
    print(f"Model:  {MODEL_ID}\n")
    model_info = check_tags()
    check_chat()
    check_tool_calling()
    print("=" * 50)
    print("ALL CHECKS PASSED")
    print(f"Model capabilities: {model_info.get('capabilities')}")
    print("=" * 50)


if __name__ == "__main__":
    main()
