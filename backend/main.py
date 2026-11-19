"""Receive PNG skins from Blockbench and send them to Telegram."""

import base64
import binascii
import hashlib
import hmac
import io
import json
import logging
import os
import re
import time
from urllib.parse import parse_qsl

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# IMPORTANT: httpx can log the Telegram bot token in request URLs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID", "")

CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ORIGINS",
        "https://blockbench-editor.vercel.app"
    ).split(",")
    if origin.strip()
]

ALLOWED_USER_IDS = {
    int(value)
    for value in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if value.strip().isdigit()
}

MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_PNG_BYTES = 2 * 1024 * 1024

app = FastAPI(title="Blockbench PNG Telegram API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def verify_init_data(raw: str) -> int:
    if not BOT_TOKEN or not OWNER_CHAT_ID:
        raise HTTPException(503, "Server is not configured")

    if not isinstance(raw, str) or not raw or len(raw) > 20000:
        raise HTTPException(401, "Missing Telegram authentication")

    try:
        pairs = parse_qsl(
            raw,
            keep_blank_values=True,
            strict_parsing=True
        )
        fields = dict(pairs)

        if len(fields) != len(pairs):
            raise ValueError("Duplicate fields")

        received_hash = fields.pop("hash")
        auth_date = int(fields["auth_date"])
        user_id = int(json.loads(fields["user"])["id"])

    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(401, "Invalid Telegram authentication")

    check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(fields.items())
    )

    secret = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode(),
        hashlib.sha256
    ).digest()

    expected = hmac.new(
        secret,
        check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, received_hash.lower()):
        raise HTTPException(401, "Invalid Telegram signature")

    now = int(time.time())

    if auth_date < now - 86400 or auth_date > now + 60:
        raise HTTPException(401, "Expired Telegram authentication")

    if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
        raise HTTPException(403, "User is not allowed to upload")

    return user_id


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/api/skins")
async def send_skin(request: Request):

    # Start measuring server processing time.
    request_started = time.perf_counter()

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

    if (
        not isinstance(image_data, str)
        or not image_data.startswith("data:image/png;base64,")
    ):
        raise HTTPException(400, "Expected a PNG data URL")

    try:
        png = base64.b64decode(
            image_data.split(",", 1)[1],
            validate=True
        )
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Invalid PNG encoding")

    if (
        len(png) < 24
        or len(png) > MAX_PNG_BYTES
        or not png.startswith(b"\x89PNG\r\n\x1a\n")
        or png[12:16] != b"IHDR"
    ):
        raise HTTPException(400, "Invalid or oversized PNG file")

    width = int.from_bytes(png[16:20], "big")
    height = int.from_bytes(png[20:24], "big")

    if not (1 <= width <= 4096 and 1 <= height <= 4096):
        raise HTTPException(400, "Invalid PNG dimensions")

    raw_filename = str(payload.get("filename") or "skin.png")

    safe_stem = re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        raw_filename.rsplit(".", 1)[0]
    )[:60]

    filename = (safe_stem or "skin") + ".png"

    # Measure time spent processing the incoming PNG.
    processing_time = time.perf_counter() - request_started

    print(
        f"[PNG] Received: {filename} | "
        f"Size: {len(png)} bytes | "
        f"Processing: {processing_time:.3f}s",
        flush=True
    )

    # Measure the Telegram Bot API request separately.
    telegram_started = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={
                    "chat_id": OWNER_CHAT_ID,
                    "caption": (
                        "Новый PNG-скин из Blockbench "
                        f"(от Telegram ID {sender_id})"
                    ),
                },
                files={
                    "document": (
                        filename,
                        io.BytesIO(png),
                        "image/png"
                    )
                },
            )

            answer = response.json()

    except (httpx.HTTPError, ValueError) as error:
        elapsed = time.perf_counter() - telegram_started

        # Do not log the exception URL: it contains BOT_TOKEN.
        print(
            f"[PNG] Telegram ERROR | "
            f"Type: {type(error).__name__} | "
            f"Time: {elapsed:.3f}s",
            flush=True
        )

        raise HTTPException(502, "Telegram delivery failed")

    telegram_time = time.perf_counter() - telegram_started
    total_time = time.perf_counter() - request_started

    print(
        f"[PNG] Telegram HTTP: {response.status_code} | "
        f"Telegram time: {telegram_time:.3f}s | "
        f"Total server time: {total_time:.3f}s",
        flush=True
    )

    if not response.is_success or not (
        isinstance(answer, dict) and answer.get("ok") is True
    ):
        raise HTTPException(
            502,
            "Bot could not send the file. Check server configuration."
        )

    print(
        f"[PNG] SUCCESS | {filename} | "
        f"{total_time:.3f}s",
        flush=True
    )

    return {
        "ok": True,
        "filename": filename,
        "telegram_time": round(telegram_time, 3),
        "total_time": round(total_time, 3),
    }
