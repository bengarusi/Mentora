# Mentora

<p align="center">
  <img src="frontend/src/assets/logo.png" alt="Mentora logo" width="180" />
</p>

<p align="center">
  <strong>An AI tutor that teaches complete maths lessons and helps primary-school students work through their own homework.</strong>
</p>

Mentora combines guided lessons, adaptive practice, homework support, voice
conversation, study-material retrieval, and progressively drawn visual
explanations in one learning experience.

Its central design principle is:

> **The model teaches; the application controls the lesson.**

The LLM generates explanations, questions, and conversational feedback.
Application code owns session state, legal transitions, persistence, hint
progression, and scoring. Deterministic maths evaluators are authoritative
whenever they can safely decide; unsupported cases follow an explicit fallback
policy rather than being silently treated as correct or incorrect.

## Contents

- [What Mentora does](#what-mentora-does)
- [Architecture](#architecture)
- [Repository structure](#repository-structure)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Testing](#testing)
- [Deployment](#deployment)
- [Security and privacy](#security-and-privacy)

## What Mentora does

### Guided lessons

A student chooses a topic, subtopic, and difficulty, then moves through a fixed
pedagogical flow:

```text
teaching → pre_practice_example → practice → practice_summary → summary → completed
```

- **Teaching** — an open conversation adapted to the selected difficulty.
- **Worked example** — one complete example before independent practice.
- **Practice** — generated sets of three questions, with server-side grading
  where deterministic evaluation is supported.
- **Review** — feedback on strengths, mistakes, and topics worth revisiting.
- **Progress** — correct answers earn difficulty-weighted points toward topic
  mastery.

### Homework help

Students can upload a PDF, DOCX, presentation, text file, or photograph of a
worksheet. Mentora extracts its contents, creates a numbered exercise outline,
and works through it one exercise at a time.

The homework tutor is designed to guide rather than reveal answers. Repeated
requests for help move through a persisted hint ladder:

```text
name the idea
    → point to the relevant values
    → teach the method
    → work a similar example
    → walk through the exercise, stopping before the final answer
```

Exercises may be postponed, but postponed work remains in the session and is
offered again after untouched exercises have been attempted.

### Learning features

| Feature | How it works |
| --- | --- |
| Streaming chat | Tutor replies arrive as an NDJSON event stream. |
| Voice | Speech-to-text, streamed tutor responses, sentence-chunked text-to-speech, and barge-in. |
| Visual boards | Typed, validated diagrams are drawn block by block with synchronized narration. |
| Study materials | Relevant excerpts from a student's files are retrieved for each turn. |
| Progress tracking | Difficulty-weighted scores roll up into a topic and subtopic learning map. |
| Homework traces | Agent activity is persisted and can be inspected in the UI. |

## Architecture

Mentora is a React single-page application backed by a FastAPI service and a
relational database. Both guided lessons and homework sessions use the same
authentication, messages, streaming, voice, and persistence infrastructure.
Their pedagogical behavior differs through the lesson state machine.

### Request lifecycle

```text
React UI
  │
  │  POST /api/tutor/{session_id}/turn/stream
  ▼
FastAPI controller
  │  authenticates, validates HTTP input, delegates
  ▼
TutorService
  │  owns the use case and database transaction
  ▼
LessonContext
  │  assembles session state, recent messages, student profile,
  │  retrieved material, and recent board context
  ▼
LessonState
  │  interprets the turn according to the current phase
  ├──────────► MathRouterService   deterministic validation
  ├──────────► AgentRunner         stateful homework tool loop
  └──────────► LLMProvider         explanations and generation
  │
  ▼
Repositories
  │  construct and execute database queries
  ▼
PostgreSQL
```

The response travels back as newline-delimited JSON events such as
`text_delta`, `tool_call`, `audio_start`, `audio_delta`, and `done`. This lets
the interface display text and agent activity immediately and begin speaking
before the entire answer has been generated.

### Layer boundaries

The backend follows a small set of architectural rules:

1. **Controllers handle HTTP.** They parse, authorize, delegate, and serialize.
2. **Services own use cases and transactions.** A tutor turn is committed as
   one unit; lower layers do not commit independently.
3. **Repositories own query construction.** Domain and transport code do not
   spread database queries throughout the application.
4. **Domain state is explicit.** Lesson phases and homework progress are stored
   and rehydrated instead of inferred from model prose.
5. **AI providers sit behind interfaces.** `LLMProvider`, `FileStorage`,
   `DocumentExtractor`, and `MaterialRetriever` can be replaced without
   rewriting their callers.

### Lesson state machine

`backend/app/lesson/state.py` implements the lesson as a State pattern. The
persisted `lesson_sessions.phase` value is the source of truth, and each state
owns its valid actions and transitions.

```text
TeachingState
    → PrePracticeExampleState
    → PracticeState
    → PracticeSummaryState
    → SummaryState
    → CompletedState
```

`HomeworkHelpState` uses the same interface but represents a single-phase,
open-ended homework conversation. Invalid actions raise
`InvalidLessonAction`; the server does not guess a transition from generated
text.

### Homework agent and reducer

When `AGENT_ENABLED_HOMEWORK=true`, homework turns run through a bounded tool
loop:

```text
student message
  ▼
deterministic routing
  ▼
AgentRunner ──► evaluateAnswer
            ├─► analyzeHomework
            ├─► recordLearningAnnotation
            └─► searchStudyMaterials
  ▼
StateReducer
  ▼
SessionStateStore + StudentProgressStore + AgentTraceStore
```

The governing rule is:

> **Tools observe; the reducer determines; stores persist.**

Important guarantees within the agent flow:

- Only a server-bound evaluation marked `authoritative` can advance solved
  state or mastery. LLM prose is not evidence of correctness.
- The model can act only on the response target currently issued by the server.
- Stable turn and evaluation keys prevent retries from awarding credit twice.
- Session state is row-locked so concurrent retries serialize.
- Tool arguments are validated by bounded Pydantic schemas.
- The current hint level is persisted and included in the next prompt, so the
  tutor does not repeat the same kind of help.

When the agent is disabled, homework remains available through the simpler
single-call conversation path.

### Maths evaluation

`backend/app/math/` handles arithmetic without asking an LLM to calculate:

```text
MathRouterService
  ├── normalizer.py      mixed numbers, percentages, equations, spoken values
  ├── calculator.py      exact arithmetic with fractions.Fraction
  ├── sympy_service.py   symbolic equivalence and equation solving
  └── validator.py       student answer versus expected answer
```

Validation proceeds from exact fraction comparison to symbolic equivalence and
normalized string comparison. The key convention is:

```text
is_equivalent = true    confidently correct
is_equivalent = false   confidently incorrect
is_equivalent = null    evaluator abstained
```

An abstention is not converted into a deterministic rejection. In guided
practice and teaching chat, unsupported questions may use an isolated LLM
grading fallback. In the homework agent, a non-authoritative fallback cannot
advance solved state.

Generated tutor replies also pass through a deterministic coherence policy
that can catch contradictions with a computed answer before the student sees
them.

### Study materials and retrieval

Uploads move through four replaceable stages:

```text
upload
  → FileStorage
  → DocumentExtractor
  → paragraph-aware chunking
  → MaterialRetriever
```

Text is extracted locally from PDF, DOCX, PPTX, and plain-text documents.
Photographs are transcribed through the configured vision model. Materials move
through explicit `pending`, `processing`, `ready`, `unsupported`, or `failed`
states and can be reprocessed from the UI.

Retrieval currently uses keyword relevance ranking and a child-oriented
stopword list. Only a bounded set of relevant excerpts is added to a tutor
prompt. The storage and retrieval interfaces leave clear seams for object
storage and vector search later.

### Visual explanations

When `BOARD_EXPLANATION_ENABLED=true`, the model produces a typed board
specification rather than pixels. The backend validates the specification, and
the frontend renders supported blocks such as worked steps, callouts, fraction
bars, number lines, coordinate planes, and geometry figures.

Boards are anchored to the message or practice question they explain. A compact
deterministic digest—not the full rendering specification—is included in later
conversation context so the student can ask follow-up questions about a board.

### Voice

`VoiceService` is isolated from lesson logic and only converts audio to text or
text to audio. `SpeechChunker` emits natural sentence fragments from the text
stream so playback can begin before the complete answer is available. Audio is
processed in memory by Mentora and is not written to local storage.

### Data model

```text
students
  ├── lesson_sessions
  │     ├── messages
  │     ├── assessment_questions ──► board_explanations
  │     ├── performance
  │     ├── agent_session_state
  │     ├── agent_traces
  │     └── homework materials
  ├── study_materials ──► material_chunks
  └── student_skill_mastery
```

Alembic is the sole owner of the database schema. Application startup never
calls `create_all`; migrations run before the production server starts.

## Repository structure

```text
Mentora/
├── backend/
│   ├── app/
│   │   ├── api/             HTTP controllers and dependencies
│   │   ├── services/        use cases and transaction ownership
│   │   ├── repositories/    database queries
│   │   ├── models/          SQLAlchemy models
│   │   ├── schemas/         Pydantic request and response models
│   │   ├── lesson/          lesson state machine and reply policy
│   │   ├── agent/           homework tools, runner, reducer, and stores
│   │   ├── math/            deterministic calculation and validation
│   │   ├── files/           storage, extraction, chunking, and retrieval
│   │   ├── board/           board validation and conversational digest
│   │   ├── llm/             provider interface and OpenAI implementation
│   │   ├── main.py          development and test API
│   │   └── asgi.py          production API plus built SPA
│   ├── alembic/             database migrations
│   └── tests/               deterministic backend test suite
├── frontend/
│   └── src/
│       ├── pages/           route-level screens
│       ├── components/      chat, boards, uploads, progress, and avatar
│       ├── hooks/           streaming chat, board playback, and lip sync
│       ├── api/             typed API wrappers
│       └── data/            built-in maths curriculum
├── docs/
│   ├── DEPLOYMENT.md
│   └── MANUAL_QA_CHECKLIST.md
├── Dockerfile
├── docker-entrypoint.sh
└── railway.json
```

## Tech stack

| Area | Technologies |
| --- | --- |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, PostgreSQL, SymPy |
| Frontend | React 18, TypeScript, Vite, React Router, axios, KaTeX |
| AI | OpenAI chat, vision, speech-to-text, and text-to-speech models behind provider boundaries |
| Authentication | JWT bearer tokens and bcrypt password hashing |
| Testing | pytest, Vitest, Testing Library, SQLite in-memory, fake LLM providers |
| Deployment | Multi-stage Docker image, Railway, managed PostgreSQL, persistent upload volume |

## Getting started

### Prerequisites

- Python 3.12+
- Node.js 22+
- PostgreSQL 14+, or SQLite for a quick local setup
- An OpenAI API key for AI-powered flows

### 1. Start the backend

```sh
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
DATABASE_URL=sqlite:///./mentora.db
SECRET_KEY=replace-with-a-long-random-value
OPENAI_API_KEY=sk-...

# Optional features
AGENT_ENABLED_HOMEWORK=true
BOARD_EXPLANATION_ENABLED=true
```

For PostgreSQL, use a URL such as:

```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/mentora
```

Generate a signing key with:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Apply migrations and start the API:

```sh
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Interactive API documentation is available at
[`http://localhost:8000/docs`](http://localhost:8000/docs).

### 2. Start the frontend

In another terminal:

```sh
cd frontend
npm install
npm run dev
```

Open [`http://localhost:5173`](http://localhost:5173). The Vite development
server proxies `/api` requests to the backend on port 8000.

## Configuration

Settings are loaded from `backend/.env` by
[`backend/app/core/config.py`](backend/app/core/config.py). The most commonly
changed values are:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | required | SQLAlchemy database connection |
| `SECRET_KEY` | required | JWT signing key |
| `OPENAI_API_KEY` | empty | Enables OpenAI-backed features |
| `OPENAI_MODEL` | `gpt-5.4-mini` | Main tutor model |
| `OPENAI_VISION_MODEL` | `gpt-4o-mini` | Photograph transcription |
| `OPENAI_STT_MODEL` | `gpt-4o-transcribe` | Speech-to-text |
| `OPENAI_TTS_MODEL` | `gpt-4o-mini-tts` | Text-to-speech |
| `OPENAI_STT_LANGUAGE` | `en` | Spoken language, or empty for auto-detection |
| `AGENT_ENABLED_HOMEWORK` | `false` | Enables the bounded homework agent loop |
| `BOARD_EXPLANATION_ENABLED` | `false` | Enables generated visual boards |
| `MATERIAL_STORAGE_DIR` | `storage/materials` | Local upload directory |
| `MATERIAL_MAX_UPLOAD_MB` | `20` | Per-file upload limit |
| `LLM_DEBUG_DUMP_PROMPTS` | `false` | Local-only prompt dumps containing student data |

The agent and visual-board features default to off because each adds extra model
calls. The application continues to support lessons and basic homework chat
without them.

## Testing

Backend tests use an in-memory SQLite database and injected fake LLM providers;
they do not contact OpenAI or PostgreSQL.

```sh
cd backend
pytest
```

Run frontend tests with:

```sh
cd frontend
npm test
```

The manual acceptance suite is documented in
[`docs/MANUAL_QA_CHECKLIST.md`](docs/MANUAL_QA_CHECKLIST.md).

## Deployment

The production build uses one multi-stage Docker image:

```text
node:22-alpine    npm ci → npm run build → frontend/dist
python:3.12-slim  install backend → copy SPA → migrate → start ASGI server
```

`app.asgi:app` mounts the API under `/api` and serves the built React
application at `/`. This gives the deployment one origin and avoids a separate
frontend service.

```sh
docker build -t mentora:local .
docker run --rm -p 8000:8000 --env-file backend/.env mentora:local
```

A persistent volume is required for `MATERIAL_STORAGE_DIR`; container-local
uploads otherwise disappear during redeployment. See
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the Railway walkthrough.

## Security and privacy

Mentora processes children's conversations and schoolwork, so privacy behavior
must be understood before deployment:

- Sessions, messages, materials, boards, and progress are scoped to their
  authenticated student.
- Passwords are bcrypt-hashed and API access uses expiring JWT bearer tokens.
- Prompt and response bodies are not logged during normal operation.
- `LLM_DEBUG_DUMP_PROMPTS` must remain disabled outside local development; when
  enabled, it writes student messages and retrieved material to disk.
- Original uploads are stored behind the `FileStorage` interface using opaque
  server-generated paths rather than student filenames.
- Photographed homework is transmitted to the configured OpenAI vision model
  for transcription. Relevant extracted excerpts may be transmitted to the
  tutor model as conversation context.
- Voice recordings are transmitted to the configured OpenAI speech-to-text
  service. Mentora processes them in memory and does not persist audio files.
- Generated speech sends tutor text to the configured text-to-speech service.
- Local storage, logs, environment files, and archives are excluded from Git.

Deployers are responsible for reviewing the configured AI provider's data
handling terms and for implementing any consent, retention, deletion, and
child-protection requirements that apply in their jurisdiction.
