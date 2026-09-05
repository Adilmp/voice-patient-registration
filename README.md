# Voice AI Patient Registration

A phone number you can call to register as a patient by talking naturally,
backed by a REST API and a persistent database. Built for the Voice AI
Agent take-home challenge.

## Architecture

```
Caller (phone)
     |
     v
Vapi Assistant  ---- system prompt (vapi/system_prompt.md)
 (telephony + speech-to-text + LLM + text-to-speech)
     |  tool call, HTTPS webhook, only after Vapi decides to invoke a tool
     v
POST /vapi/tool-calls  (app/vapi_webhook.py)
     |  same functions the REST API uses -- one source of truth
     v
Service layer (app/crud.py)
     |
     v
SQLite (patients.db)
     ^
     |  same REST API
Reviewer / curl / Postman  <-- GET/POST/PUT/DELETE /patients
```

Three things can reach the database, and all three go through the same
`app/crud.py` functions: the REST API directly, the Vapi tool webhook, and
(if you seed it) the startup script. There is exactly one place that knows
how to validate and persist a patient record.

## Tech stack, and why

| Layer | Choice | Why |
|---|---|---|
| Backend framework | **FastAPI** (Python) | Automatic request validation via Pydantic, minimal boilerplate, fast to write correctly under a time limit. |
| Validation | **Pydantic v2** | Runs independently of the voice agent -- garbage in from a phone call still gets rejected before it reaches the database. |
| Database | **SQLite** | Zero setup, a single file, trivially survives restarts. The challenge explicitly calls out "SQLite over Postgres" as a smart trade-off for a time-boxed build -- there's no separate DB server to install, configure, or host. Swapping to Postgres later is a one-line `DATABASE_URL` change (SQLAlchemy already abstracts the engine). |
| ORM | **SQLAlchemy** | Table structure is defined once in `app/models.py`, in Python, instead of hand-written SQL living out of sync with the code. |
| Voice/telephony | **Vapi** | Handles STT, TTS, turn-taking, interruptions, and phone provisioning. The challenge FAQ explicitly says this is the intended path ("we encourage it... assessing integration skills, not STT/TTS implementation"). Free tier: $10 signup credit + a free US phone number, no separate Twilio account needed. |
| LLM | Vapi's built-in model routing | No separate OpenAI/Anthropic key required; billed out of the same Vapi credit. |
| Hosting | **Render** (free tier) | No credit card required, real persistent free tier (unlike Railway, which dropped its free tier in 2024). Trade-off: free-tier services sleep after 15 minutes idle (~30-60s cold start on the next request) -- mitigated with an optional free UptimeRobot ping (see Deployment below). |

## Project structure

```
app/
  main.py          FastAPI app: the 5 REST endpoints, error handling, envelope, logging, seed data
  vapi_webhook.py  Adapter: translates Vapi's tool-call webhook format into calls to crud.py
  models.py        SQLAlchemy Patient table definition
  schemas.py       Pydantic request/response validation (names, phone, DOB, state, zip, etc.)
  crud.py          Service layer: the only code that reads/writes the database
  database.py      SQLite engine/session setup, .env loading
  errors.py        Shared validation-error message formatting
  constants.py     US state codes, valid `sex` values
vapi/
  system_prompt.md The voice agent's conversational instructions (paste into Vapi dashboard)
  tools.json       The 3 tool/function definitions the agent can call (paste into Vapi dashboard)
```

## Data model

`patients` table -- see `app/models.py` for exact types/constraints:

first_name, last_name, date_of_birth, sex, phone_number, email (optional),
address_line_1, address_line_2 (optional), city, state, zip_code,
insurance_provider (optional), insurance_member_id (optional),
preferred_language (optional, default "English"), emergency_contact_name
(optional), emergency_contact_phone (optional), plus auto-generated
`patient_id` (UUID), `created_at`, `updated_at`, and `deleted_at` (soft
delete -- rows are never hard-deleted).

## REST API

All responses use the envelope `{ "data": ..., "error": ... }`.

| Method | Endpoint | Notes |
|---|---|---|
| GET | `/patients` | Optional filters: `?last_name=`, `?date_of_birth=`, `?phone_number=` |
| GET | `/patients/:id` | 404 if missing or soft-deleted |
| POST | `/patients` | 201 on success, 422 on validation failure |
| PUT | `/patients/:id` | Partial update -- only send the fields you're changing |
| DELETE | `/patients/:id` | Soft delete (sets `deleted_at`), never hard-deletes |

Example:
```bash
curl -X POST https://<your-app>/patients -H "Content-Type: application/json" -d '{
  "first_name": "Jane", "last_name": "Doe", "date_of_birth": "05/14/1990",
  "sex": "Female", "phone_number": "5551234567",
  "address_line_1": "123 Main St", "city": "Springfield", "state": "IL", "zip_code": "62704"
}'
```

## Voice agent integration

`POST /vapi/tool-calls` is a single endpoint that Vapi calls whenever the
assistant invokes one of three tools:

- `lookup_patient_by_phone` -- checks for a returning caller by phone number
- `register_patient` -- creates a new patient (after the agent reads back and confirms all fields)
- `update_patient` -- updates an existing patient by `patient_id`

The full conversational flow (greeting, field collection, corrections,
confirmation, error re-prompting, optional-field opt-in, graceful closing)
is defined in `vapi/system_prompt.md`. The tool argument schemas are in
`vapi/tools.json`.

## Local setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8010
```

Visit `http://localhost:8010/patients` -- with `SEED_DATA=true` in `.env`,
two demo patients load automatically on first run.

## Deployment

### 1. Backend -> Render (free, no card)
1. Push this repo to GitHub.
2. On [render.com](https://render.com), New -> Web Service -> connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. **Database**: Render's free-tier local disk is not guaranteed to survive a redeploy, and "data persists across calls/restarts" is a directly graded requirement -- don't leave this on SQLite in production. Instead: New -> PostgreSQL (free, expires after 30 days -- plenty for this assessment), then copy its "Internal Connection String" into this web service's `DATABASE_URL` env var. No code changes needed -- `app/database.py` already normalizes the URL and `psycopg2-binary` is in `requirements.txt`. (SQLite stays the default for local dev via `.env`.)
6. Add the remaining environment variables from `.env.example` (`SEED_DATA`, etc.).
7. Deploy. Note the public URL, e.g. `https://your-app.onrender.com`.

### 2. Voice agent -> Vapi (free $10 credit + free US number)
1. Sign up at [vapi.ai](https://vapi.ai), create an Assistant.
2. Paste the contents of `vapi/system_prompt.md` into the system prompt field.
3. In `vapi/tools.json`, replace every `BASE_URL` with your Render URL, then create each of the 3 tools in the Vapi dashboard (Tools -> Create Tool -> Function) using those definitions.
4. Attach all 3 tools to the assistant.
5. Claim a free US phone number under Phone Numbers and attach it to this assistant.
6. Call the number to test.

### 3. Optional: keep Render awake (free)
Render's free tier sleeps after 15 minutes idle. Sign up at [uptimerobot.com](https://uptimerobot.com) (free) and add an HTTP monitor pinging `https://your-app.onrender.com/` every 5 minutes.

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./patients.db` |
| `SEED_DATA` | Insert 2 demo patients if the table is empty | `false` |
| `PORT` | Local dev port (Render provides its own `$PORT`) | `8000` |

No API keys are required in this codebase -- the LLM and voice pipeline are
configured entirely inside the Vapi dashboard, not in this repo, so there
is nothing telephony-related to hardcode or leak here.

## Known limitations & trade-offs

- **SQLite is for local development only.** The deployed instance should use Render's free managed Postgres (see Deployment) since local disk on Render's free web services isn't guaranteed to survive a redeploy -- and losing data between calls would fail this challenge's core "second call, no data loss" requirement.
- **No authentication on the REST API** -- anyone with the URL can read/write patient records. Acceptable for a fake-data technical assessment; would need API keys or OAuth in production.
- **No automated test suite** -- validated manually via curl against both the REST API and simulated Vapi webhook payloads (see conversation/commit history). Would add pytest coverage next.
- **No rate limiting** on the API or the webhook.
- **Multi-language, appointment scheduling, and call transcripts are not implemented** -- listed as bonus/stretch items in the challenge and out of scope for the core 3-hour build.
- **Render free-tier cold starts** can add latency to the very first tool call after idle time; mitigated optionally via UptimeRobot, not solved outright.

## Next steps (if continuing past the time limit)

- Move to a persistent managed Postgres instance.
- Add pytest integration tests for the API layer (bonus item).
- Store a call transcript/summary linked to `patient_id` (bonus item).
- Add basic API-key auth in front of `/patients`.
- Multi-language support by detecting caller language in the system prompt and switching Vapi's voice/transcriber language.
