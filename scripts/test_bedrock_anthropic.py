#!/usr/bin/env python3
"""
Test script for Anthropic Claude models on AWS Bedrock Mantle.

Usage:
    uv run python scripts/test_bedrock_anthropic.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import anthropic

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv()

BEDROCK_MANTLE_API_KEY = os.getenv("BEDROCK_MANTLE_API_KEY", "").strip()
BEDROCK_REGION = os.getenv("BEDROCK_MANTLE_REGION", "us-east-1").strip()
BASE_URL = f"https://bedrock-mantle.{BEDROCK_REGION}.api.aws/anthropic"
ANTHROPIC_PROJECT_ARN = os.getenv("ANTHROPIC_PROJECT_ARN", "").strip()

MODELS_TO_TEST = [
    "anthropic.claude-sonnet-5",
    "anthropic.claude-haiku-4-5",
    "anthropic.claude-opus-4-8",
    "anthropic.claude-opus-4-7",
]

def test_model(client: anthropic.Anthropic, model: str):
    print(f"\n=======================================================")
    print(f"Testing Model: {model}")
    print(f"=======================================================")
    try:
        message = client.messages.create(
            model=model,
            max_tokens=8192,
            messages=[
                {
                    "role": "user",
                    "content": "Explain what PPSC (Punjab Public Service Commission) is in 2 concise sentences.",
                },
            ],
        )
        content = message.content[0].text if message.content else ""
        print(f"✅ [SUCCESS] Response from {model}:")
        print(f"{content.strip()}")
        print(f"\nUsage Stats:")
        print(f"  Input Tokens  : {message.usage.input_tokens}")
        print(f"  Output Tokens : {message.usage.output_tokens}")
        print(f"  Stop Reason   : {message.stop_reason}")
        return True
    except anthropic.APIStatusError as e:
        print(f"❌ [API Error] Status {e.status_code}: {e.message}")
        return False
    except Exception as e:
        print(f"❌ [Error] {type(e).__name__}: {e}")
        return False

def main():
    print("=" * 70)
    print("Anthropic Claude on AWS Bedrock Mantle Test")
    print("=" * 70)
    print(f"Base URL             : {BASE_URL}")
    print(f"API Key configured   : {bool(BEDROCK_MANTLE_API_KEY)}")
    print(f"Project ARN set      : {bool(ANTHROPIC_PROJECT_ARN)}")
    print("=" * 70)

    if not BEDROCK_MANTLE_API_KEY:
        print("❌ Error: BEDROCK_MANTLE_API_KEY is not set in .env")
        sys.exit(1)

    default_headers = {}
    if ANTHROPIC_PROJECT_ARN:
        default_headers["anthropic-workspace-id"] = ANTHROPIC_PROJECT_ARN

    client = anthropic.Anthropic(
        base_url=BASE_URL,
        api_key=BEDROCK_MANTLE_API_KEY,
        default_headers=default_headers if default_headers else None,
    )

    results = {}
    for model in MODELS_TO_TEST:
        results[model] = test_model(client, model)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for model, success in results.items():
        icon = "✅ PASS" if success else "❌ FAIL"
        print(f"  {icon:<10} {model}")
    print("=" * 70)

if __name__ == "__main__":
    main()
