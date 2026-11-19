"""Receive an authenticated Blockbench PNG and forward it to bot owner's DM."""
import base64
import binascii
import hashlib
import hmac
import io
import json
import os
import re
import time
from urllib.parse import parse_qsl

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID", "")
CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ORIGINS", "https://blockbench-editor.vercel.app"
    ).split(",")
    if origin.strip()
]
# Optional: restrict uploads to your own / your friend's Telegram user IDs.
ALLOWED_USER_IDS = {
    int(value) for value in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if value.strip().isdigit()
}
MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_PNG_BYTES = 2 * 1024 * 1024

app = FastAPI(title="Blockbench PNG Telegram delivery")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def verify_init_data(raw: str) -> int:
    """Validate the Telegram Mini App's signed initData on the server."""
    if not BOT_TOKEN or not OWNER_CHAT_ID:
        raise HTTPException(503, "Server is not configured")
    if not isinstance(raw, str) or not raw or len(raw) > 20_000:
        raise HTTPException(401, "Missing Telegram authentication")

    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError("Duplicate fields")
        received_hash = fields.pop("hash")
        auth_date = int(fields["auth_date"])
        user_id = int(json.loads(fields["user"])["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(401, "Invalid Telegram authentication")

    check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash.lower()):
        raise HTTPException(401, "Invalid Telegram signature")

    now = int(time.time())
    if auth_date < now - 86400 or auth_date > now + 60:
        raise HTTPException(401, "Expired Telegram authentication")
    if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
        raise HTTPException(403, "This Telegram user is not allowed to upload")
    return user_id


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/api/skins")
async def send_skin(request: Request):
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_REQUEST_BYTES:
            raise HTTPException(413, "Request too large")
        chunks.append(chunk)

    try:
        payload = json.loads(b"".join(chunks))
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(400, "Invalid JSON request")
    if not isinstance(payload, dict):
        raise HTTPException(400, "Invalid JSON body")

    sender_id = verify_init_data(payload.get("initData"))
    image_data = payload.get("imageData")
    if not isinstance(image_data, str) or not image_data.startswith(
        "data:image/png;base64,"
    ):
        raise HTTPException(400, "Expected a PNG data URL")

    try:
        png = base64.b64decode(image_data.split(",", 1)[1], validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Invalid PNG encoding")
    if (len(png) < 24 or len(png) > MAX_PNG_BYTES or
            not png.startswith(b"\x89PNG\r\n\x1a\n") or
            png[12:16] != b"IHDR"):
        raise HTTPException(400, "Invalid or oversized PNG file")

    width = int.from_bytes(png[16:20], "big")
    height = int.from_bytes(png[20:24], "big")
    if not (1 <= width <= 4096 and 1 <= height <= 4096):
        raise HTTPException(400, "Invalid PNG dimensions")

    raw_filename = str(payload.get("filename") or "skin.png")
    safe_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_filename.rsplit(".", 1)[0])[:60]
    filename = (safe_stem or "skin") + ".png"

    # sendDocument keeps the original skin PNG instead of recompressing it as a photo.
    # Use POST multipart/form-data; never expose BOT_TOKEN to frontend.
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={
                    "chat_id": OWNER_CHAT_ID,
                    "caption": f"Новый PNG-скин из Blockbench (от Telegram ID {sender_id})",
                },
                files={"document": (filename, io.BytesIO(png), "image/png")},
            )
            answer = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Telegram delivery failed")

    if not response.is_success or answer.get("ok") is not True:
        # Do not return private bot configuration or Telegram API details.
        raise HTTPException(502, "Bot could not send the file. Start the bot and check OWNER_CHAT_ID.")

    return {"ok": True, "filename": filename}
