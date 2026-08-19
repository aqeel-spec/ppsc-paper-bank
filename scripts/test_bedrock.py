#!/usr/bin/env python3
"""
AWS Bedrock Models & Agent Connectivity Test for PPSC Paper Bank.

Usage:
    uv run python scripts/test_bedrock.py

This script verifies:
  1. Bedrock Mantle endpoint connectivity & API key authentication
  2. Primary model inference (deepseek.v3.2)
  3. Fast model inference (zai.glm-4.7-flash)
  4. OpenAI-Agents Framework integration via LitellmModel
  5. Autonomous Tool-Calling execution
"""

import os
import sys
import time
import asyncio
from dataclasses import dataclass
from pathlib import Path
import httpx
from dotenv import load_dotenv

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

# Suppress and disable OpenAI Agents telemetry / tracing export
try:
    from agents.tracing.setup import set_trace_provider
    from agents.tracing.provider import DefaultTraceProvider
    set_trace_provider(DefaultTraceProvider())
except Exception:
    pass

import logging
logging.getLogger('agents').setLevel(logging.ERROR)
logging.getLogger('LiteLLM').setLevel(logging.ERROR)
logging.getLogger('openai').setLevel(logging.ERROR)

from ppsc_agents.api_key_rotator import get_llm_config
from agents.extensions.models.litellm_model import LitellmModel
from agents import Agent, Runner, function_tool

@dataclass
class BedrockCheckResult:
    name: str
    status: str  # PASS | FAIL | SKIP
    detail: str = ""
    latency_s: float | None = None

def print_result(r: BedrockCheckResult) -> None:
    icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⚠️ "}[r.status]
    latency = f" ({r.latency_s:.2f}s)" if r.latency_s is not None else ""
    print(f"{icon} {r.name}{latency}")
    if r.detail:
        for line in r.detail.splitlines():
            print(f"    {line}")

async def test_endpoint_and_auth() -> BedrockCheckResult:
    name = "1. Bedrock Mantle API Connectivity & Auth"
    config = get_llm_config()
    api_key = config.get("api_key", "")
    base_url = config.get("base_url", "")

    if not api_key:
        return TestResult(name, "FAIL", "BEDROCK_MANTLE_API_KEY is not configured in .env")

    start = time.monotonic()
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{base_url}/models", headers=headers)
            elapsed = time.monotonic() - start
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", [])
                available = [m.get("id") for m in models if m.get("status") == "available"]
                return BedrockCheckResult(
                    name,
                    "PASS",
                    f"Connected to {base_url}\nAvailable Bedrock models: {len(available)}",
                    latency_s=elapsed,
                )
            return BedrockCheckResult(name, "FAIL", f"Status {resp.status_code}: {resp.text[:120]}", latency_s=elapsed)
    except Exception as e:
        return BedrockCheckResult(name, "FAIL", f"Exception: {str(e)}", latency_s=time.monotonic() - start)

async def test_primary_chat(model: str = "deepseek.v3.2") -> BedrockCheckResult:
    name = f"2. Primary Model Chat Completion ({model})"
    config = get_llm_config()
    api_key = config.get("api_key", "")
    base_url = config.get("base_url", "")

    start = time.monotonic()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an AI exam tutor for PPSC exams."},
            {"role": "user", "content": "What is the capital of Pakistan? Answer in 5 words."}
        ],
        "max_tokens": 50,
        "temperature": 0.2
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            elapsed = time.monotonic() - start
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                return BedrockCheckResult(name, "PASS", f"Response: {content!r}", latency_s=elapsed)
            return BedrockCheckResult(name, "FAIL", f"Status {resp.status_code}: {resp.text[:120]}", latency_s=elapsed)
    except Exception as e:
        return BedrockCheckResult(name, "FAIL", f"Exception: {str(e)}", latency_s=time.monotonic() - start)

async def test_fast_chat(model: str = "zai.glm-4.7-flash") -> BedrockCheckResult:
    name = f"3. Fast Model Chat Completion ({model})"
    config = get_llm_config()
    api_key = config.get("api_key", "")
    base_url = config.get("base_url", "")

    start = time.monotonic()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Give one synonym for 'Abundant'."}
        ],
        "max_tokens": 30,
        "temperature": 0.1
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            elapsed = time.monotonic() - start
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                return BedrockCheckResult(name, "PASS", f"Response: {content!r}", latency_s=elapsed)
            return BedrockCheckResult(name, "FAIL", f"Status {resp.status_code}: {resp.text[:120]}", latency_s=elapsed)
    except Exception as e:
        return BedrockCheckResult(name, "FAIL", f"Exception: {str(e)}", latency_s=time.monotonic() - start)

async def test_openai_agents_runner() -> BedrockCheckResult:
    name = "4. OpenAI-Agents Framework + LitellmModel Integration"
    config = get_llm_config()
    
    start = time.monotonic()
    try:
        model = LitellmModel(
            model=config["model"],
            api_key=config["api_key"],
            base_url=config["base_url"],
        )
        agent = Agent(
            name="PPSC Diagnostic Agent",
            instructions="You are a quick diagnostic agent. Be extremely concise.",
            model=model,
        )
        result = await Runner.run(agent, "State the year Quaid-e-Azam was born.")
        elapsed = time.monotonic() - start
        return BedrockCheckResult(name, "PASS", f"Agent Output: {result.final_output.strip()!r}", latency_s=elapsed)
    except Exception as e:
        return BedrockCheckResult(name, "FAIL", f"Exception: {str(e)}", latency_s=time.monotonic() - start)

@function_tool
def get_sample_mcq(subject: str) -> str:
    """Mock tool retrieving sample MCQ."""
    return f"Subject: {subject}. Question: Which is the longest river in Pakistan? Options: A) Indus, B) Jhelum, C) Chenab. Correct: A"

async def test_agent_tool_calling() -> BedrockCheckResult:
    name = "5. Autonomous Agent Function Tool-Calling"
    config = get_llm_config()
    
    start = time.monotonic()
    try:
        model = LitellmModel(
            model=config["model"],
            api_key=config["api_key"],
            base_url=config["base_url"],
        )
        agent = Agent(
            name="MCQ Retriever Agent",
            instructions="Always use get_sample_mcq to fetch exam questions before answering.",
            model=model,
            tools=[get_sample_mcq],
        )
        result = await Runner.run(agent, "Get a sample Pakistan Studies MCQ from the tool and present the question and correct answer.")
        elapsed = time.monotonic() - start
        
        output_lower = result.final_output.lower()
        if "indus" in output_lower or "longest river" in output_lower:
            return BedrockCheckResult(name, "PASS", f"Tool output received:\n{result.final_output.strip()}", latency_s=elapsed)
        else:
            return BedrockCheckResult(name, "FAIL", f"Tool response might not have been used: {result.final_output}", latency_s=elapsed)
    except Exception as e:
        return BedrockCheckResult(name, "FAIL", f"Exception: {str(e)}", latency_s=time.monotonic() - start)

async def main():
    print("=" * 70)
    print("AWS Bedrock Models & Agent Verification Suite")
    print("=" * 70)
    
    config = get_llm_config()
    print(f"Provider          : {config.get('name')}")
    print(f"Active Model      : {config.get('model')}")
    print(f"Base URL          : {config.get('base_url')}")
    print(f"API Key Set       : {bool(config.get('api_key'))}")
    print("=" * 70)
    print()

    tests = [
        test_endpoint_and_auth(),
        test_primary_chat("deepseek.v3.2"),
        test_fast_chat("zai.glm-4.7-flash"),
        test_openai_agents_runner(),
        test_agent_tool_calling(),
    ]

    results = []
    for test_coro in tests:
        res = await test_coro
        print_result(res)
        print()
        results.append(res)

    passed = [r for r in results if r.status == "PASS"]
    failed = [r for r in results if r.status == "FAIL"]

    print("=" * 70)
    print(f"SUMMARY: {len(passed)}/{len(results)} Passed | {len(failed)} Failed")
    print("=" * 70)

    if failed:
        sys.exit(1)
    else:
        print("🎉 System is fully configured and ready for live deployment!")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
