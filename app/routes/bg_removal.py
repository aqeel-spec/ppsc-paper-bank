"""
Background Removal API — local ONNX processing via *rembg* (U2-Net).

Runs entirely on-device; no external API calls required.

Endpoints
---------
POST /bg/remove          → remove background (transparent PNG)
POST /bg/replace-color   → replace background with a solid colour
POST /bg/replace-image   → replace background with a custom image
POST /bg/passport        → passport-size photo with standard backgrounds
"""

from __future__ import annotations

import base64
import io
import os
import logging
from enum import Enum
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment]

try:
    from rembg import remove as rembg_remove, new_session as rembg_new_session
    _REMBG_AVAILABLE = True
except ImportError:
    _REMBG_AVAILABLE = False
    rembg_remove = None  # type: ignore[assignment]
    rembg_new_session = None  # type: ignore[assignment]

load_dotenv()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bg", tags=["Background Removal"])

# ── Configuration ──────────────────────────────────────────────────────────
RMBG_MODEL: str = os.getenv("RMBG_MODEL", "u2net")  # rembg session model name

_MAX_UPLOAD_MB = 10
_MAX_UPLOAD_BYTES = _MAX_UPLOAD_MB * 1024 * 1024

# Lazy-loaded rembg session (downloads model weights on first call)
_rembg_session = None


def _get_rembg_session():
    """Return a cached rembg inference session."""
    global _rembg_session
    if _rembg_session is None:
        if not _REMBG_AVAILABLE:
            raise HTTPException(
                status_code=501,
                detail="rembg is not installed. Run: pip install rembg onnxruntime",
            )
        logger.info("🔄 Loading rembg model '%s' (first call — may take a moment)…", RMBG_MODEL)
        _rembg_session = rembg_new_session(RMBG_MODEL)
        logger.info("✅ rembg model '%s' loaded.", RMBG_MODEL)
    return _rembg_session


# ── Helpers ────────────────────────────────────────────────────────────────


# Map MIME → output format string
_MIME_TO_FORMAT: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/webp": "webp",
}


def _detect_format(file: UploadFile) -> str:
    """Auto-detect output format from the uploaded file's content type."""
    ct = (file.content_type or "").lower()
    fmt = _MIME_TO_FORMAT.get(ct)
    if fmt:
        return fmt
    # Fallback: try filename extension
    name = (file.filename or "").lower()
    if name.endswith(".png"):
        return "png"
    if name.endswith((".jpg", ".jpeg")):
        return "jpeg"
    if name.endswith(".webp"):
        return "webp"
    return "png"  # safe default


def _validate_upload(file: UploadFile) -> None:
    allowed = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
    ct = (file.content_type or "").lower()
    if ct not in allowed:
        # Also accept by filename extension as a fallback
        name = (file.filename or "").lower()
        if not name.endswith((".png", ".jpg", ".jpeg", ".webp")):
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported file type '{ct}'. Allowed: {', '.join(sorted(allowed))}",
            )


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(data) / 1024 / 1024:.1f} MB). Max {_MAX_UPLOAD_MB} MB.",
        )
    return data


async def _remove_bg(image_bytes: bytes) -> bytes:
    """Remove background locally using rembg (ONNX / U2-Net). Returns RGBA PNG bytes."""
    session = _get_rembg_session()
    logger.info("🔲 Running local bg removal (model: %s, input size: %d bytes)…", RMBG_MODEL, len(image_bytes))

    try:
        result: bytes = rembg_remove(
            image_bytes,
            session=session,
            post_process_mask=True,
        )
    except Exception as exc:
        logger.error("❌ rembg processing failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Background removal failed: {exc}") from exc

    return result


def _hex_to_rgba(hex_color: str) -> tuple[int, int, int, int]:
    """Parse '#RRGGBB' or 'RRGGBB' into (R, G, B, 255)."""
    h = hex_color.lstrip("#")
    if len(h) not in (6, 8):
        raise HTTPException(422, f"Invalid hex colour: '{hex_color}'. Use #RRGGBB.")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    a = int(h[6:8], 16) if len(h) == 8 else 255
    return (r, g, b, a)


def _require_pillow() -> None:
    if Image is None:
        raise HTTPException(
            status_code=501,
            detail="Pillow is not installed on the server. Run: pip install Pillow",
        )


def _composite_on_color(
    fg_bytes: bytes, color: tuple[int, int, int, int]
) -> bytes:
    """Composite transparent foreground onto a solid colour background."""
    _require_pillow()
    assert Image is not None

    fg = Image.open(io.BytesIO(fg_bytes)).convert("RGBA")
    bg = Image.new("RGBA", fg.size, color)
    bg.paste(fg, mask=fg)
    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    return buf.getvalue()


def _composite_on_image(fg_bytes: bytes, bg_bytes: bytes) -> bytes:
    """Composite transparent foreground onto a custom background image."""
    _require_pillow()
    assert Image is not None

    fg = Image.open(io.BytesIO(fg_bytes)).convert("RGBA")
    bg = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")

    # Resize background to match foreground
    bg = bg.resize(fg.size, Image.Resampling.LANCZOS)
    bg.paste(fg, mask=fg)
    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    return buf.getvalue()


def _stream_png(data: bytes) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data),
        media_type="image/png",
        headers={"Content-Disposition": "inline; filename=result.png"},
    )


# ── Passport background presets ────────────────────────────────────────────
class PassportBackground(str, Enum):
    white = "white"
    light_blue = "light_blue"
    light_grey = "light_grey"
    red = "red"
    blue = "blue"


_PASSPORT_COLORS: dict[PassportBackground, tuple[int, int, int, int]] = {
    PassportBackground.white: (255, 255, 255, 255),
    PassportBackground.light_blue: (173, 216, 230, 255),
    PassportBackground.light_grey: (211, 211, 211, 255),
    PassportBackground.red: (200, 30, 30, 255),
    PassportBackground.blue: (0, 51, 153, 255),
}

# Standard passport sizes (width x height in pixels at 300 DPI)
class PassportSize(str, Enum):
    pakistan = "pakistan"        # 35×45 mm → 413×531 px
    us = "us"                  # 2×2 in   → 600×600 px
    uk = "uk"                  # 35×45 mm → 413×531 px
    eu = "eu"                  # 35×45 mm → 413×531 px
    square = "square"          # 600×600 px


_PASSPORT_SIZES: dict[PassportSize, tuple[int, int]] = {
    PassportSize.pakistan: (413, 531),
    PassportSize.us: (600, 600),
    PassportSize.uk: (413, 531),
    PassportSize.eu: (413, 531),
    PassportSize.square: (600, 600),
}


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post(
    "/remove",
    summary="Remove background (transparent PNG)",
    response_class=StreamingResponse,
)
async def remove_background(
    file: UploadFile = File(..., description="Image file (PNG, JPEG, WebP). Max 10 MB."),
    format: Optional[str] = Form(None, description="Return format: 'png', 'jpeg', 'webp', or 'base64'. Auto-detected from upload if omitted."),
):
    """Remove background locally (rembg / U2-Net). Returns transparent PNG by default."""
    _validate_upload(file)
    out_format = format or _detect_format(file)
    image_bytes = await _read_upload(file)

    logger.info(f"🔲 Removing background… (output format: {out_format})")
    fg = await _remove_bg(image_bytes)
    logger.info("✅ Background removed.")

    if out_format == "base64":
        return {"base64": base64.b64encode(fg).decode(), "model": RMBG_MODEL}

    return _stream_png(fg)


@router.post(
    "/replace-color",
    summary="Replace background with a solid colour",
    response_class=StreamingResponse,
)
async def replace_bg_color(
    file: UploadFile = File(..., description="Image file (PNG, JPEG, WebP). Max 10 MB."),
    color: str = Form("#FFFFFF", description="Background colour in hex (#RRGGBB)."),
    format: Optional[str] = Form(None, description="Return format: 'png', 'jpeg', 'webp', or 'base64'. Auto-detected if omitted."),
):
    """Remove background and replace with a solid colour."""
    _validate_upload(file)
    out_format = format or _detect_format(file)
    image_bytes = await _read_upload(file)

    rgba = _hex_to_rgba(color)

    logger.info(f"🎨 Replacing background with colour {color}…")
    fg = await _remove_bg(image_bytes)
    result = _composite_on_color(fg, rgba)
    logger.info("✅ Background replaced.")

    if out_format == "base64":
        return {"base64": base64.b64encode(result).decode(), "color": color, "model": RMBG_MODEL}

    return _stream_png(result)


@router.post(
    "/replace-image",
    summary="Replace background with a custom image",
    response_class=StreamingResponse,
)
async def replace_bg_image(
    file: UploadFile = File(..., description="Foreground image (PNG, JPEG, WebP). Max 10 MB."),
    background: UploadFile = File(..., description="Background image (PNG, JPEG, WebP). Max 10 MB."),
    format: Optional[str] = Form(None, description="Return format: 'png', 'jpeg', 'webp', or 'base64'. Auto-detected if omitted."),
):
    """Remove background and composite onto a custom background image."""
    _validate_upload(file)
    _validate_upload(background)
    out_format = format or _detect_format(file)
    image_bytes = await _read_upload(file)
    bg_bytes = await _read_upload(background)

    logger.info("🖼️ Replacing background with custom image…")
    fg = await _remove_bg(image_bytes)
    result = _composite_on_image(fg, bg_bytes)
    logger.info("✅ Background replaced with custom image.")

    if out_format == "base64":
        return {"base64": base64.b64encode(result).decode(), "model": RMBG_MODEL}

    return _stream_png(result)


@router.post(
    "/passport",
    summary="Passport-size photo with standard backgrounds",
    response_class=StreamingResponse,
)
async def passport_photo(
    file: UploadFile = File(..., description="Portrait photo (PNG, JPEG, WebP). Max 10 MB."),
    bg: PassportBackground = Form(
        PassportBackground.white,
        description="Background preset: white, light_blue, light_grey, red, blue.",
    ),
    size: PassportSize = Form(
        PassportSize.pakistan,
        description="Passport size standard: pakistan (35×45mm), us (2×2in), uk, eu, square.",
    ),
    custom_color: Optional[str] = Form(
        None,
        description="Override preset with a custom hex colour (#RRGGBB). Takes priority over 'bg'.",
    ),
    format: Optional[str] = Form(None, description="Return format: 'png', 'jpeg', 'webp', or 'base64'. Auto-detected if omitted."),
):
    """Generate a passport-size photo: removes background, applies colour, crops/resizes to standard dimensions."""
    _validate_upload(file)
    image_bytes = await _read_upload(file)

    _require_pillow()
    assert Image is not None

    # Determine colour
    if custom_color:
        rgba = _hex_to_rgba(custom_color)
    else:
        rgba = _PASSPORT_COLORS[bg]

    target_w, target_h = _PASSPORT_SIZES[size]

    logger.info(f"📸 Passport photo — size={size.value} ({target_w}×{target_h}), bg={bg.value}")

    # 1. Remove background
    fg_bytes = await _remove_bg(image_bytes)
    fg = Image.open(io.BytesIO(fg_bytes)).convert("RGBA")

    # 2. Center-crop / resize to passport aspect ratio
    src_w, src_h = fg.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        # Source is wider → crop sides
        new_w = int(src_h * target_ratio)
        offset = (src_w - new_w) // 2
        fg = fg.crop((offset, 0, offset + new_w, src_h))
    elif src_ratio < target_ratio:
        # Source is taller → crop top/bottom
        new_h = int(src_w / target_ratio)
        offset = (src_h - new_h) // 2
        fg = fg.crop((0, offset, src_w, offset + new_h))

    fg = fg.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # 3. Composite on background colour
    bg_img = Image.new("RGBA", (target_w, target_h), rgba)
    bg_img.paste(fg, mask=fg)

    buf = io.BytesIO()
    bg_img.save(buf, format="PNG")
    result = buf.getvalue()

    logger.info("✅ Passport photo generated.")

    out_format = format or _detect_format(file)
    if out_format == "base64":
        return {
            "base64": base64.b64encode(result).decode(),
            "size": size.value,
            "dimensions": f"{target_w}x{target_h}",
            "background": custom_color or bg.value,
            "model": RMBG_MODEL,
        }

    return _stream_png(result)
