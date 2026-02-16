"""
Image Generation API — FLUX.1-schnell via Hugging Face Inference API (free).

Endpoints
---------
POST /images/generate   → generate an image from a text prompt
"""

from __future__ import annotations

import base64
import io
import os
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["Image Generation"])

# ── Configuration ──────────────────────────────────────────────────────────
HF_TOKEN: str = os.getenv("HF_TOKEN", "")
HF_MODEL: str = "black-forest-labs/FLUX.1-schnell"
HF_API_URL: str = f"https://router.huggingface.co/hf-inference/models/{HF_MODEL}"

_TIMEOUT = 120  # seconds — image gen can be slow on free tier


# ── Request / Response schemas ─────────────────────────────────────────────
class ImageGenerateRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Text prompt describing the image to generate.",
        examples=["student studying in classroom, realistic"],
    )
    negative_prompt: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Things to avoid in the image.",
    )
    width: int = Field(default=1024, ge=256, le=1024, description="Image width in pixels.")
    height: int = Field(default=1024, ge=256, le=1024, description="Image height in pixels.")
    format: str = Field(
        default="png",
        description="Return format: 'png' (binary stream) or 'base64' (JSON).",
        pattern="^(png|base64)$",
    )


class ImageGenerateResponse(BaseModel):
    base64: str = Field(description="Base-64 encoded PNG image data.")
    prompt: str
    model: str


# ── Endpoint ───────────────────────────────────────────────────────────────
@router.post(
    "/generate",
    summary="Generate image from text (FLUX.1-schnell)",
    responses={
        200: {
            "description": "Generated image (PNG stream or base64 JSON).",
            "content": {
                "image/png": {},
                "application/json": {
                    "schema": ImageGenerateResponse.model_json_schema()
                },
            },
        }
    },
)
async def generate_image(payload: ImageGenerateRequest):
    """Generate an image using FLUX.1-schnell on Hugging Face (free tier)."""

    if not HF_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="HF_TOKEN is not configured. Set it in .env to use image generation.",
        )

    # Build HF Inference API payload
    hf_payload: dict = {"inputs": payload.prompt}
    parameters: dict = {}
    if payload.negative_prompt:
        parameters["negative_prompt"] = payload.negative_prompt
    if payload.width != 1024 or payload.height != 1024:
        parameters["width"] = payload.width
        parameters["height"] = payload.height
    if parameters:
        hf_payload["parameters"] = parameters

    headers = {"Authorization": f"Bearer {HF_TOKEN}"}

    logger.info(f"🎨 Generating image — prompt: {payload.prompt[:80]}...")

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(HF_API_URL, json=hf_payload, headers=headers)

    if resp.status_code == 503:
        # Model is loading
        raise HTTPException(
            status_code=503,
            detail="Model is loading on Hugging Face. Please retry in ~30 seconds.",
        )

    if resp.status_code != 200:
        detail = resp.text[:300] if resp.text else f"HF API returned {resp.status_code}"
        raise HTTPException(status_code=resp.status_code, detail=detail)

    image_bytes: bytes = resp.content
    content_type = resp.headers.get("content-type", "")

    if "image" not in content_type:
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected content-type from HF: {content_type}. Body: {resp.text[:200]}",
        )

    logger.info("✅ Image generated successfully.")

    # Return based on requested format
    if payload.format == "base64":
        b64 = base64.b64encode(image_bytes).decode()
        return ImageGenerateResponse(
            base64=b64,
            prompt=payload.prompt,
            model=HF_MODEL,
        )

    # Default: stream raw PNG
    return StreamingResponse(
        io.BytesIO(image_bytes),
        media_type="image/png",
        headers={"Content-Disposition": "inline; filename=generated.png"},
    )
