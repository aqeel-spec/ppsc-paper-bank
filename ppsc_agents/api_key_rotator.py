"""
Simple API-key helper for the GitHub Models (OpenAI-compatible) endpoint.

Reads GITHUB_TOKEN, GITHUB_MODELS_ENDPOINT, and MODEL from the environment
and provides a single key entry that the agent system can use.
"""
import os
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()


def _get_github_models_config() -> Dict:
    """Build the single key config from GitHub Models env vars."""
    token = (os.getenv("GITHUB_TOKEN") or "").strip()
    endpoint = (os.getenv("GITHUB_MODELS_ENDPOINT") or "https://models.github.ai/inference").strip()
    model = (os.getenv("MODEL") or "openai/gpt-4.1").strip()

    return {
        "provider": "github",
        "model": model,
        "api_key": token,
        "base_url": endpoint,
        "name": "GitHub Models",
    }


# ---------------------------------------------------------------------------
# Public helpers consumed by agent_system.py
# ---------------------------------------------------------------------------

_config: Optional[Dict] = None


def get_github_models_config() -> Dict:
    """Return the GitHub Models configuration (singleton)."""
    global _config
    if _config is None:
        _config = _get_github_models_config()
    return _config
