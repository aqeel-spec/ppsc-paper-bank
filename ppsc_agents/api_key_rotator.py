"""
LLM Configuration and credentials helper supporting AWS Bedrock Mantle and GitHub Models.
"""
import os
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()


def _get_llm_config() -> Dict:
    """Build configuration preferring AWS Bedrock Mantle, with GitHub Models fallback."""
    bedrock_key = (os.getenv("BEDROCK_MANTLE_API_KEY") or "").strip()
    bedrock_region = (os.getenv("BEDROCK_MANTLE_REGION") or "us-east-1").strip()
    
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "8192"))
    
    if bedrock_key:
        model = (os.getenv("MODEL") or "deepseek.v3.2").strip()
        # Ensure litellm knows to route to openai-compatible custom base
        litellm_model = model if model.startswith("openai/") else f"openai/{model}"
        endpoint = f"https://bedrock-mantle.{bedrock_region}.api.aws/v1"
        return {
            "provider": "bedrock_mantle",
            "model": litellm_model,
            "raw_model": model,
            "api_key": bedrock_key,
            "base_url": endpoint,
            "name": "AWS Bedrock Mantle",
            "max_tokens": max_tokens,
        }

    token = (os.getenv("GITHUB_TOKEN") or "").strip()
    endpoint = (os.getenv("GITHUB_MODELS_ENDPOINT") or "https://models.github.ai/inference").strip()
    model = (os.getenv("MODEL") or "openai/gpt-4.1-mini").strip()

    return {
        "provider": "github",
        "model": model,
        "raw_model": model,
        "api_key": token,
        "base_url": endpoint,
        "name": "GitHub Models",
        "max_tokens": max_tokens,
    }


_config: Optional[Dict] = None


def get_llm_config() -> Dict:
    """Return the active LLM configuration (singleton)."""
    global _config
    if _config is None:
        _config = _get_llm_config()
    return _config


# Backward-compatibility alias
def get_github_models_config() -> Dict:
    return get_llm_config()
