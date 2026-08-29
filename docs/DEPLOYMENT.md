# Deploying Mentora

A single service on [Railway](https://railway.app): one Docker image that serves
both the API and the built React app, plus a managed Postgres and a volume for
student uploads.

## Why one service

The frontend's axios client talks to `/api` ([`frontend/src/api/client.ts`](../frontend/src/api/client.ts)).
In development the Vite proxy makes that work; in production
[`backend/app/asgi.py`](../backend/app/asgi.py) does, by mounting the API under
`/api` and serving the SPA at `/`. One origin means:

- no CORS configuration,
- no second dashboard or deploy to keep in sync,
- no frontend code change between dev and prod.

`app.main:app` is left untouched as the pure API — routers at the root — which is
what the test suite and the Vite dev proxy talk to.

The API must sit under a prefix rather than at the root: the SPA owns `/progress`
and `/files` while the API owns `/progress` and `/materials`, so sharing a root
would collide.

## What ships

| File | Role |
| --- | --- |
| [`Dockerfile`](../Dockerfile) | Two stages — `node:22-alpine` builds the SPA, `python:3.12-slim` runs it |
| [`docker-entrypoint.sh`](../docker-entrypoint.sh) | `alembic upgrade head`, then uvicorn |
| [`backend/app/asgi.py`](../backend/app/asgi.py) | Production ASGI app: API at `/api`, SPA at `/` |
| [`railway.json`](../railway.json) | Builder, healthcheck (`/api/`), restart policy |
| [`.dockerignore`](../.dockerignore) | Keeps `.env`, `node_modules`, `.venv`, uploads and tests out of the image |

## Deploy

### 1. Push

```sh
git add -A && git commit -m "chore(deploy): containerize as a single service" && git push
```

### 2. Create the project

On [railway.app](https://railway.app): **New Project → Deploy from GitHub repo →
`bengarusi/Mentora`**. Railway reads `railway.json` and builds the Dockerfile.

### 3. Add Postgres

**New → Database → PostgreSQL**, in the same project. It exposes a
`DATABASE_URL` you reference from the app service.

### 4. Add the volume

On the app service: **Settings → Volumes → Add Volume**, mount path `/data`.
Without it, uploaded homework is wiped on every deploy — the container
filesystem is ephemeral.

### 5. Set the variables

On the app service, **Variables**:

```
DATABASE_URL=${{Postgres.DATABASE_URL}}
SECRET_KEY=<a fresh 48-byte random string — never the development one>
OPENAI_API_KEY=<your key>

OPENAI_MODEL=gpt-5.4-mini
OPENAI_STT_MODEL=gpt-4o-transcribe
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=alloy

AGENT_ENABLED_HOMEWORK=true
BOARD_EXPLANATION_ENABLED=true

MATERIAL_STORAGE_DIR=/data/materials
LOG_DIR=/data/logs
```

`${{Postgres.DATABASE_URL}}` is Railway's reference syntax — it resolves to the
database in the same project, so the credentials are never copied by hand.

`PORT` is injected by Railway; the entrypoint reads it. Leave it unset.

`CORS_ORIGINS` needs no value: the SPA and API share an origin. Should you ever
set it, `pydantic-settings` parses `list[str]` as JSON — `["https://x.dev"]`.

### 6. Generate the domain

**Settings → Networking → Generate Domain**. Migrations run on boot, so the
first successful deploy already has its schema.

## Verifying

```sh
curl https://<your-app>.up.railway.app/api/          # {"message":"Mentora backend is running"}
curl -I https://<your-app>.up.railway.app/           # 200, text/html
```

Then register a user through the UI and run one lesson end to end.

## Feature flags

Both default to off in [`config.py`](../backend/app/core/config.py) — a
deliberate ship-dark pattern, not unfinished work. Both are merged to `main`
with full test coverage.

**`AGENT_ENABLED_HOMEWORK`** — replaces the single-call homework path with an
agent loop over four tools (`evaluateAnswer`, `analyzeHomework`,
`recordLearningAnnotation`, `searchStudyMaterials`), up to four steps per turn.
It builds an exercise outline and tracks `current_exercise_index` / `hint_level`
as real state. The server stays the sole authority on correctness. Off, the
legacy atomic path runs instead.

**`BOARD_EXPLANATION_ENABLED`** — progressively drawn board explanations with
synchronized TTS narration, plus recall of a compact board digest into later
chat prompts. Off, `list_boards` answers `200 {"enabled": false}` and the UI
renders no board action.

Both cost extra OpenAI calls per turn.

## Running the image locally

```sh
docker build -t mentora:local .
docker run --rm -p 8000:8000 --env-file backend/.env mentora:local
```

`backend/.env` points at `localhost:5434`, which is not reachable from inside the
container — override `DATABASE_URL` with `host.docker.internal:5434`, or point it
at the deployed database.

## Tearing down

**Project Settings → Danger → Delete Project.** Removes the service, the
database and the volume together. Nothing else to clean up — no DNS, no
certificates, no external object storage.
