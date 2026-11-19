"""Minimal authenticated Blockbench model storage API for Telegram Mini Apps."""
import hashlib
import hmac
import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
CORS_ORIGINS = [s.strip().rstrip('/') for s in os.environ.get(
    'CORS_ORIGINS', 'http://localhost:3000'
).split(',') if s.strip()]
ALLOWED_USER_IDS = {int(x) for x in os.environ.get('ALLOWED_USER_IDS', '').split(',') if x.strip().isdigit()}
MAX_BYTES = 25 * 1024 * 1024
DATA_DIR = Path(__file__).with_name('saved_models')
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title='Telegram Blockbench API')
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=['GET', 'POST', 'OPTIONS'],
    allow_headers=['Content-Type', 'ngrok-skip-browser-warning'],
)


def verify_telegram_init_data(raw: str) -> dict:
    """Telegram Mini Apps HMAC validation (not login-widget verification)."""
    if not BOT_TOKEN or BOT_TOKEN == 'PASTE_YOUR_BOT_TOKEN_HERE':
        raise HTTPException(500, 'Server BOT_TOKEN is not configured')
    if not isinstance(raw, str) or len(raw) > 20_000:
        raise HTTPException(401, 'Missing or invalid Telegram initData')
    try:
        fields = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise HTTPException(401, 'Malformed Telegram initData')
    data = dict(fields)
    if len(data) != len(fields):
        raise HTTPException(401, 'Duplicate initData field')
    their_hash = data.pop('hash', None)
    if not their_hash:
        raise HTTPException(401, 'Missing Telegram signature')
    check_string = '\n'.join(f'{k}={v}' for k, v in sorted(data.items()))
    secret = hmac.new(b'WebAppData', BOT_TOKEN.encode('utf-8'), hashlib.sha256).digest()
    calculated = hmac.new(secret, check_string.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, their_hash):
        raise HTTPException(401, 'Invalid Telegram signature')
    try:
        auth_date = int(data['auth_date'])
    except (ValueError, TypeError, KeyError):
        raise HTTPException(401, 'Invalid auth_date')
    now = int(time.time())
    if auth_date < now - 24 * 3600 or auth_date > now + 60:
        raise HTTPException(401, 'Expired Telegram authorization')
    try:
        user = json.loads(data['user'])
        user_id = int(user['id'])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise HTTPException(401, 'Missing Telegram user ID')
    if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
        raise HTTPException(403, 'Not allowed to upload')
    return {'user_id': user_id}


@app.get('/health')
def health():
    return {'ok': True}


@app.post('/api/models')
async def save_model(request: Request):
    # Enforce a size limit while reading (even when no Content-Length is sent).
    chunks = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BYTES:
            raise HTTPException(413, 'Model payload exceeds 25 MB')
        chunks.append(chunk)
    try:
        payload = json.loads(b''.join(chunks))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, 'Expected JSON body')
    if not isinstance(payload, dict):
        raise HTTPException(400, 'Expected a JSON object')
    identity = verify_telegram_init_data(payload.get('initData', ''))
    model = payload.get('model')
    if not isinstance(model, dict) or not isinstance(model.get('meta'), dict):
        raise HTTPException(400, 'Expected a .bbmodel JSON object')
    model_id = uuid.uuid4().hex
    # Never trust a client-chosen file path. Save under a random filename.
    path = DATA_DIR / f'{model_id}.bbmodel'
    path.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
    return {'ok': True, 'id': model_id, 'user_id': identity['user_id']}
