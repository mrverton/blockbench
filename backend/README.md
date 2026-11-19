# Optional FastAPI backend

You do **not** need the backend just to open Blockbench inside Telegram.
It is required only for the custom **Telegram > Отправить модель на сервер** command.

Install Python 3.10+, then:

```bash
cd backend
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
```

Create environment variables `BOT_TOKEN` and `CORS_ORIGINS` based on `.env.example`.
**The Python code reads environment variables, not the `.env` file itself.**

For example, Linux/macOS:

```bash
export BOT_TOKEN='TOKEN_FROM_BOTFATHER'
export CORS_ORIGINS='https://your-blockbench.vercel.app,http://localhost:3000'
uvicorn main:app --host 127.0.0.1 --port 8000
```

PowerShell:

```powershell
$env:BOT_TOKEN='TOKEN_FROM_BOTFATHER'
$env:CORS_ORIGINS='https://your-blockbench.vercel.app,http://localhost:3000'
uvicorn main:app --host 127.0.0.1 --port 8000
```

`http://localhost:8000/health` returns `{ "ok": true }`.

Expose your local backend through HTTPS with **Cloudflare Tunnel**:

```bash
cloudflared tunnel --url http://localhost:8000
```

Copy the `https://...trycloudflare.com` URL into `telegram/config.js` as
`window.BLOCKBENCH_TELEGRAM_API_URL`, commit and redeploy the frontend.

Alternatively, use `ngrok http 8000` and set its HTTPS URL.
Local tunnels only work while both the backend and tunnel are running;
free public URLs may change. Use persistent cloud hosting for a long-term API.

Security: NEVER place the bot token in frontend JS, a public GitHub repository,
a Telegram message to helpers, or in screenshots. The backend validates Telegram
`initData` before storing files. Only registered, authorized Telegram users can
upload when `ALLOWED_USER_IDS` is configured. Files go to `saved_models/` and
remain on the machine running FastAPI.
