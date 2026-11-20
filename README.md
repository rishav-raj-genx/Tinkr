# Tinkr

An autonomous voice AI assistant powered by Gemma 4. Tinkr captures speech through the browser's Web Speech API, streams reasoning via Server-Sent Events, executes real actions on Google Calendar, Gmail, Tasks, and the web, and speaks back using browser TTS — all while monitoring voice biomarkers for emotional wellness.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Features

| Feature | Description |
|---------|-------------|
| **Voice-First Interface** | Speak naturally; Tinkr transcribes, reasons, and speaks back |
| **Portfolio Demo Sandbox** | Safe, out-of-the-box exploration for visitors without needing Google credentials |
| **Owner Live Mode** | Secure owner authentication unlocking real Google Calendar, Gmail, and Tasks |
| **Text Fallback** | Collapsible text input for typed commands, email addresses, and context |
| **Google Calendar** | Check availability, book meetings, set reminders |
| **Gmail** | Check unread emails, draft emails, send emails |
| **Google Tasks** | Add tasks, list pending tasks |
| **Web Search** | DuckDuckGo instant answers (no API key needed) |
| **News** | Latest headlines via Google News RSS |
| **Weather** | Current conditions and forecast via OpenWeatherMap |
| **Voice Biomarker Analysis** | Per-user adaptive baseline detects stress, anxiety, and fatigue from voice |
| **Wellness Modal** | Confirms detected emotional state and injects empathetic context into LLM |
| **Streaming Responses** | Real-time SSE streaming with sentence-by-sentence TTS playback |
| **Thought Filtering** | Strips `<thought>`/`<think>` tags from Gemma 4 output before display |
| **Hardened Security** | Pydantic v2 validation, anti-IDOR sessions, rate limits, CSP, and prompt isolation |

---

## Portfolio Demo Sandbox vs. Owner Mode

Tinkr features a built-in dual-mode architecture designed for public demonstration and evaluation:

```
                            Visitor / Evaluator
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
               Unauthenticated Guest       Authenticated Owner
               (Demo Sandbox Mode)         (Owner Live Mode)
                         │                     │
                ┌────────┴────────┐            │
                ▼                 ▼            ▼
         Safe Non-Workspace   Google Tools    Full Live Access
         (Search, Weather,   Intercepted by   to Real Google
         Biomarkers, LLM)    Sandbox Mock     Calendar, Gmail,
                │                 │           and Tasks APIs
                ▼                 ▼
          Live Results      [DEMO SANDBOX]
                            Structured Data
```

- **Portfolio Demo Sandbox (Default for Visitors):**
  - Evaluators and visitors can immediately run and test the complete voice AI assistant workflow without configuring Google Cloud projects, OAuth consent screens, or client credentials.
  - Safe tools (web search, weather, SQLite querying, voice biomarker analysis, and Gemma 4 reasoning) execute live.
  - Google Workspace tools (`check_availability`, `book_meeting`, `set_reminder`, `add_task`, `list_tasks`, `check_unread_emails`, `draft_email`, `send_email`) are intercepted by the server-side sandbox dispatcher, returning realistic, structured simulated responses prefixed with `[DEMO SANDBOX]`.
- **Owner Live Mode (Unlocked via `OWNER_ACCESS_KEY`):**
  - Setting `OWNER_ACCESS_KEY` in `.env` enables owner authentication.
  - The repository owner can click the mode badge in the UI header or submit a key to `POST /api/auth/owner` (verified using constant-time `hmac.compare_digest`).
  - Upon successful authentication, the signed session upgrades to `role: owner`, activating live Google Calendar, Gmail, and Tasks actions using the owner's `token.json`.
  - Calling `POST /api/auth/logout` rotates the session back to guest mode.

---

## Security Architecture

Tinkr enforces defense-in-depth security across all architectural layers:

1. **Strict Input Validation (Pydantic v2):**
   - Every POST endpoint validates incoming payloads through Pydantic schemas ([schemas.py](file:///Users/apple/Desktop/Tinkr/schemas.py)) with `extra="forbid"`, strip-whitespace normalization, and strict boundaries.
   - Incoming requests are hard-capped at 5 MB (`MAX_CONTENT_LENGTH = 5 * 1024 * 1024`) returning HTTP 413.
   - Base64 audio payloads are constrained to ~2 MB decoded length and validated for even-byte int16 PCM alignment.
2. **Session-Bound Identity (Anti-IDOR):**
   - Cryptographically signed `HttpOnly`, `SameSite=Lax`, and dynamic `Secure` cookies manage user sessions.
   - Storage partitioning for emotional wellness and mental state history is strictly bound to the server-managed `session["sid"]`, preventing Insecure Direct Object References (IDOR) even if a malicious client supplies another user's display ID.
3. **Hardened Read-Only SQLite (`sql_tool.py`):**
   - Database connections open in true read-only URI mode (`file:{DB_PATH}?mode=ro`, `PRAGMA query_only = ON;`).
   - Query guardrails reject semicolons, SQL comments (`--`, `/*`), and non-`SELECT` keywords (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ATTACH`, `PRAGMA`, etc.).
   - Query results are capped at 100 rows, and an SQLite progress handler aborts queries exceeding 250,000 opcodes to prevent denial-of-service.
4. **Sliding-Window Rate Limiting:**
   - In-memory thread-safe `RateLimiter` enforces rate quotas per `(bucket, client_ip, session_sid)` with automatic stale key eviction:
     - `/api/chat_stream`: 15 requests / 60s
     - `/api/transcribe`: 15 requests / 60s
     - `/api/analyze_audio`: 25 requests / 60s
     - `/api/auth/owner`: 5 requests / 900s (brute-force defense)
     - State/History endpoints: 60 requests / 60s
   - Exceeded quotas return HTTP `429 Too Many Requests` with standard `Retry-After` headers.
5. **Defense-in-Depth HTTP Security Headers:**
   - `Content-Security-Policy`: Restricts scripts/styles to `'self'` and `'unsafe-inline'`, fonts to Google Fonts, media to `'self' blob: data:`, and connection endpoints to localhost:5000.
   - `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`.
   - `Permissions-Policy: microphone=(self), camera=(), geolocation=()`.
   - `Strict-Transport-Security` applied when terminating HTTPS.
6. **LLM Prompt-Injection Boundaries & Token Capping:**
   - Spoken transcripts and text inputs are wrapped in `<user_utterance>...</user_utterance>` and emotional distress context in `<wellness_context>...</wellness_context>`.
   - Explicit system instructions instruct the Gemma 4 reasoning engine to treat all delimiter contents strictly as untrusted data.
   - Hard output token caps (`max_tokens=1024`) and explicit upstream timeouts (`timeout=10.0`) prevent token exhaustion and hanging connections.
7. **Frontend DOM XSS Sanitization:**
   - All dynamic text rendering in `index.html` passes through `escapeHtml()` and `renderSafeText()` to neutralize HTML/JS payloads before DOM insertion.

---

## Architecture

```
Browser (index.html, port 8000)         Python Backend (api_server.py, port 5000)
        |                                           |
        |── Web Speech API (STT) ──────────────────>|
        |── POST /api/chat_stream ─────────────────>|── Gemma 4 (Google AI Studio)
        |<── SSE text chunks ──────────────────────-|        |
        |── Web Speech API (TTS)                    |   Tool Dispatch
        |                                           |        |
        |                                +----------+---------+---------+----------+
        |                                |          |         |         |          |
        |                          Calendar     Gmail     DuckDuckGo  Weather   Tasks
        |                          (Google)    (Google)   (Web/News)  (OWM)    (Google)
        |
        |── POST /api/analyze_audio ───────────────> biomarker_tool.py (librosa)
        |── POST /api/save_mental_state             Per-user adaptive baseline
        |── POST /api/get_mental_state_history      Stress / Anxiety / Fatigue detection
```

---

## Project Structure

```
Tinkr/
├── api_server.py         Flask API server — chat streaming, tool routing, biomarker analysis
├── auth_server.py        One-time OAuth server to generate token.json
├── config.py             Centralized configuration, safe defaults, and diagnostics
├── logger.py             Structured logging with automatic secret redaction
├── schemas.py            Strict Pydantic v2 validation models for all POST endpoints
├── security.py           Signed session identity, anti-IDOR, rate limiting, and sandbox
├── index.html            Single-page frontend — voice UI, visualizer, text fallback, mode badge
├── biomarker_tool.py     Voice biomarker engine — per-user adaptive baseline calibration
├── calendar_tool.py      Google Calendar — check availability, book meetings, set reminders
├── tasks_tool.py         Google Tasks — add and list tasks
├── web_tool.py           DuckDuckGo search + Google News RSS
├── weather_tool.py       OpenWeatherMap current weather and forecast
├── sql_tool.py           Hardened read-only SQLite interface with query/opcode caps
├── setup_db.py           Seeds company_data.db with sample data
├── tests/                Comprehensive pytest regression and security test suite
├── Makefile              Development workflow automation (setup, dev, lint, test, audit)
├── requirements.txt      Pinned production dependencies
├── requirements-dev.txt  Pinned testing, linting, and security audit dependencies
├── .env.example          Documented template of all supported environment variables
├── .env                  Runtime environment variables (not committed)
├── token.json            OAuth credentials (not committed, generated by auth_server.py)
├── .gitignore            Git exclusion rules for secrets, DBs, and virtualenvs
└── LICENSE               MIT License
```

---

## Prerequisites

- **Python 3.9+**
- **Google Chrome** (required for Web Speech API and microphone access on localhost)
- **Google Cloud project** with Calendar API, Tasks API, and Gmail API enabled
- **Google AI Studio API key** (free tier)
- **OpenWeatherMap API key** (free tier)
- **Groq API key** (free tier, for Whisper STT)

---

## Setup

### 1. Automated Setup (Recommended)

```bash
git clone https://github.com/rishav-raj-genx/Tinkr.git
cd Tinkr
make setup
```

`make setup` automatically creates a virtual environment, installs dependencies from `requirements-dev.txt`, initializes `.env` from `.env.example`, and seeds `company_data.db`.

Alternatively, manual install:
```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
python3 setup_db.py
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```ini
# Google OAuth 2.0 (from Cloud Console > Credentials)
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback

# Google Calendar & Gmail
HOST_CALENDAR_ID=your_email@gmail.com
HOST_EMAIL=your_email@gmail.com

# Frontend URL (for CORS)
FRONTEND_URL=http://localhost:8000

# Flask session secret
SECRET_KEY=any_random_string

# LLM — Google AI Studio
API_KEY=your_google_ai_studio_api_key

# STT — Groq Whisper
GROQ_API_KEY=your_groq_api_key

# Weather — OpenWeatherMap
WEATHER_API_KEY=your_openweathermap_api_key
```

### 3. Enable Google Cloud APIs

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Navigate to **APIs & Services > Library**.
3. Enable **Google Calendar API**, **Google Tasks API**, and **Gmail API**.

### 4. Create OAuth 2.0 Credentials

1. Go to **APIs & Services > Credentials** > **Create Credentials** > **OAuth client ID**.
2. Set type to **Web application**.
3. Add `http://localhost:8000` to **Authorized JavaScript origins**.
4. Add `http://localhost:8000/auth/callback` to **Authorized redirect URIs**.
5. Copy Client ID and Client Secret into `.env`.

### 5. Add Test User

1. Go to **APIs & Services > OAuth consent screen**.
2. Under **Test users**, add the Gmail address that Tinkr should access.

### 6. Generate `token.json`

```bash
python3 auth_server.py
```

1. Open `http://localhost:8000` in Chrome.
2. Click **"Click here to Authorize Google Calendar and Gmail"**.
3. Grant permissions for Calendar, Tasks, and Gmail.
4. After the success message, press `Ctrl+C` to stop the auth server.

A `token.json` file is now saved in the project root. Do not commit this file.

---

## Running the Application

### Option A: Single-Port Unified Mode (Recommended)
Launch the unified server which serves both the frontend UI and API endpoints:
```bash
make dev
# Or: python3 api_server.py
```
Open **Google Chrome** at **`http://localhost:5000`**.

### Option B: Split-Port Development Mode
If running the frontend independently on port 8000:
- **Terminal 1 (Backend):** `make dev` (Port 5000)
- **Terminal 2 (Frontend):** `python3 -m http.server 8000` (Port 8000)
Open **Google Chrome** at `http://localhost:8000`.

> **Important:** Always access using `localhost` rather than `127.0.0.1` so Chrome grants microphone media stream permissions over HTTP.

---

## API Reference

All endpoints are served on port 5000. Requests and responses use JSON.

### Core & System

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/` | Serves the single-page frontend application (`index.html`) |
| `GET`  | `/api/health` | System health check (database connection, token status, diagnostics) |
| `POST` | `/api/chat_stream` | Primary streaming endpoint. Streams LLM response via SSE with tool support |
| `POST` | `/api/transcribe` | Transcribes audio file (WebM) to text via Groq Whisper |

### Session & Owner Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/session` | Returns active session role (`guest` or `owner`) and workspace mode (`sandbox` or `live`) |
| `POST` | `/api/auth/owner` | Authenticates repository owner using `OWNER_ACCESS_KEY` to unlock live Google tools |
| `POST` | `/api/auth/logout` | Resets session back to guest mode and rotates session ID |

### Biomarker & Wellness

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/analyze_audio` | Analyzes PCM audio for voice biomarkers (stress/anxiety/fatigue) |
| `POST` | `/api/save_mental_state` | Saves a user-confirmed mental state record |
| `POST` | `/api/get_mental_state_history` | Returns recent mental state logs for a user |
| `POST` | `/api/save_emotional_chat` | Persists conversation exchanges tied to an emotional state |
| `POST` | `/api/get_emotional_chats` | Returns conversation for a specific emotional state ID |
| `POST` | `/api/get_emotional_chat_history` | Returns all confirmed states joined with chat history |

### `/api/chat_stream`

**Request:**
```json
{
  "text": "What meetings do I have tomorrow?",
  "user_id": "eren",
  "emotion_context": ""
}
```

**Response:** Server-Sent Events stream. Each event:
```
data: {"text": "You have a standup at 10 AM..."}
```

### `/api/analyze_audio`

**Request:**
```json
{
  "audio_base64": "base64_encoded_16khz_int16_pcm",
  "user_id": "eren"
}
```

**Response:**
```json
{
  "alert": true,
  "predicted_state": "stressed",
  "voice_energy_level": "high",
  "mean_zcr": 0.091,
  "rms_variance": 0.00031,
  "message": "[SYSTEM EVENT: Voice biomarker analysis detected stressed...]",
  "suggestions": ["Try deep breathing: inhale 4 seconds, hold 4, exhale 6"]
}
```

---

## Voice Biomarker Engine

The biomarker system uses **per-user adaptive baseline calibration** rather than fixed thresholds, making it robust across different microphones, environments, and speaking styles.

### How It Works

**Phase 1 — Calibration (first 3 voice inputs):**  
The system records the user's normal voice characteristics and computes an average baseline.

**Phase 2 — Deviation Detection (all subsequent inputs):**  
Each new voice input is compared against the user's personal baseline. Only triggers when features deviate **1.8x above the baseline average**.

### Features Extracted (via librosa)

| Feature | What It Measures | Stress Indicator |
|---------|-----------------|------------------|
| **Zero Crossing Rate** | Signal crossings per frame | Breathiness, vocal tension |
| **RMS Energy Variance** | Micro-tremors in amplitude | Agitation, vocal instability |
| **Spectral Centroid** | Voice brightness | Tension, elevated pitch |
| **Pitch (F0) Stability** | Fundamental frequency jitter | Anxiety, nervousness |

### Classification Rules

| Condition | Predicted State |
|-----------|----------------|
| ≥2 features elevated + (ZCR or RMS variance elevated) | **Stressed** |
| Pitch instability elevated + ≥1 other feature elevated | **Anxious** |
| Low voice energy + ZCR below 50% of baseline | **Fatigued** |
| None of the above | **Calm** |

### Wellness Flow

1. Biomarker analysis runs automatically after each voice recording.
2. If an anomaly is detected, a **wellness modal** appears asking the user to confirm.
3. If confirmed, empathetic context is injected into the LLM system prompt.
4. Tinkr acknowledges the user's emotional state before answering their question.
5. The modal **auto-dismisses after 15 seconds** if the user doesn't respond.
6. Only **confirmed** states are saved to the wellness history.

---

## Tool Modules

| Module | Tools | Auth |
|--------|-------|------|
| `calendar_tool.py` | `check_availability`, `book_meeting`, `set_reminder` | OAuth (token.json) |
| `tasks_tool.py` | `add_task`, `list_tasks` | OAuth (token.json) |
| `web_tool.py` | `search_web`, `get_news` | None |
| `weather_tool.py` | `get_weather` | API key |
| `sql_tool.py` | `get_database_schema`, `execute_sql_query` | None |
| `biomarker_tool.py` | `analyze_audio_biomarkers` | None |

Gmail tools (`check_unread_emails`, `draft_email`, `send_email`) are defined directly in `api_server.py` and use the same OAuth token.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_CLIENT_ID` | Yes | OAuth 2.0 Client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | OAuth 2.0 Client Secret |
| `GOOGLE_REDIRECT_URI` | Yes | OAuth redirect (must match Cloud Console) |
| `HOST_CALENDAR_ID` | Yes | Gmail address for calendar operations |
| `HOST_EMAIL` | Yes | Gmail address of the account |
| `FRONTEND_URL` | Yes | Frontend URL for CORS |
| `SECRET_KEY` | Yes | Flask session secret |
| `API_KEY` | Yes | Google AI Studio API key (Gemma 4) |
| `GROQ_API_KEY` | Yes | Groq API key (Whisper STT) |
| `WEATHER_API_KEY` | Yes | OpenWeatherMap API key |
| `OWNER_ACCESS_KEY` | Optional | Shared secret unlocking Owner Live Mode for Google Workspace |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Microphone blocked in browser | Use `http://localhost:8000`, not `http://127.0.0.1:8000` |
| `token.json` not found | Run `python3 auth_server.py` and complete the OAuth flow |
| Calendar returns "Failed to check availability" | Verify `HOST_CALENDAR_ID` matches the authorized Gmail. Ensure Calendar + Tasks + Gmail APIs are enabled |
| LLM connection fails | Verify `API_KEY` is valid at [Google AI Studio](https://aistudio.google.com/apikey) |
| `pip install` fails on `librosa` | macOS: `brew install portaudio` first. Linux: `sudo apt-get install portaudio19-dev` |
| Token refresh fails | Delete `token.json` and re-run `python3 auth_server.py` |
| Biomarker always shows "Calibrating" | The first 3 voice inputs calibrate the baseline. This is expected |

---

---

## $0 portfolio deployment (Docker Space)

The included `Dockerfile` targets Hugging Face Spaces' Docker SDK and listens on
port `7860`. It installs `libsndfile1` and `ffmpeg`, runs as the unprivileged
`tinkr` user, seeds `company_data.db` only when it is absent, and starts one
`gthread` Gunicorn worker (`4` threads, `120` second timeout). One worker avoids
duplicating librosa's native memory while still allowing concurrent SSE requests.
The database and all in-container files are disposable; no OAuth token is copied
into the image.

Measured on 17 November 2026 with the pinned requirements, the virtualenv's
Python packages occupy 528 MB on disk; the largest contributors are SciPy 82 MB,
llvmlite 129 MB, scikit-learn 31 MB, and NumPy 26 MB. A one-second biomarker
request reached 209 MB resident memory on the audit machine. Linux container
headroom should be planned at 300–450 MB per worker because native BLAS/ffmpeg
allocations and request concurrency add to that baseline. The final compressed
image size must be measured by `docker image inspect` after a Docker daemon is
available; this checkout's daemon was unavailable during the audit.

### Hugging Face Spaces setup

1. Create a Space, choose **Docker**, and set the Space port to `7860`. CPU Basic
   is documented as 2 vCPU/16 GB RAM/50 GB non-persistent disk. Hugging Face's
   current documentation says Docker Spaces may require an eligible subscription,
   so verify the account's hardware price shows `$0.00` before deploying.
2. Push this repository (including `Dockerfile` and `.dockerignore`) to the Space.
3. In **Settings → Variables and secrets**, add `FLASK_ENV=production`, a random
   `SECRET_KEY`, `API_KEY`, and `GROQ_API_KEY`. Add `WEATHER_API_KEY` only when
   weather is desired. Leave `OWNER_ACCESS_KEY`, Google client values, and
   `TOKEN_PATH` unset for the public demo; visitors remain in `[DEMO SANDBOX]`.
   Set `FRONTEND_URL` to the Space URL. Never upload `.env`, `token.json`, or a
   database file.
4. Wait for the build, then check `https://<space>.hf.space/api/health`. A healthy
   response has `database.connected: true`; the first boot may be a cold start.
   `/api/chat_stream` emits SSE with `Cache-Control: no-cache` and
   `X-Accel-Buffering: no`.

### Provider decision and limitations

| Provider | $0 capacity relevant to Tinkr | Sleep/storage | Decision |
| --- | --- | --- | --- |
| Hugging Face Docker Space | CPU Basic is documented at 16 GB RAM and 2 vCPU; account eligibility for Docker at $0 must be confirmed | 50 GB disk is non-persistent; rebuilds/restarts lose the seeded DB | Preferred when the account exposes the documented free CPU Basic hardware. Safest RAM margin. |
| Render Free Web Service | Free service; 750 instance-hours/month | Spins down after 15 minutes idle, cold start about one minute; filesystem is ephemeral and local SQLite is lost on restart | Viable only after memory testing. 512 MB leaves little margin for librosa; one worker is mandatory. |
| Koyeb Free Instance | One 512 MB, 0.1 vCPU, 2 GB SSD instance per organization | Scales to zero after one hour without traffic; no volume on free instance | High OOM and CPU risk for librosa; use only as a low-confidence demo fallback. |
| Fly.io | Current offer is a 2-hour/7-day free trial, not an ongoing $0 tier | Machines stop when trial ends unless billing is configured | Excluded from a strict perpetual $0 plan. |

Do not use an uptime pinger to defeat sleep policies. Monitoring should be
event-driven: configure UptimeRobot or Better Stack for an HTTP GET on
`/api/health` at a normal interval, accept cold-start latency, and alert on
non-2xx responses. These monitors must not be used to keep a service awake.

### Rollback

Deploy from immutable Git commits. If a Space build is bad, open **Settings →
Revision**, select the previous known-good commit, and restart. For Render, use
the dashboard's rollback to one of the two previous deploys. Verify `/api/health`,
the sandbox calendar response, and a short SSE request after rollback. Because the
free filesystems are ephemeral, rollback reseeds the sample database; never treat
that database as durable user data.

## Trademarks & Disclaimers

Gemma is a trademark of Google LLC. **Tinkr** is an independent project created for the *Build with Gemma 4 - AI Durg Hackathon* and is not affiliated with or officially endorsed by Google LLC.

---

## License

This project is licensed under the [MIT License](LICENSE).
