# Mentora

An AI tutor for primary-school students. Mentora runs a full lesson — teach,
practise, grade, summarise — and helps a student through their own homework,
with voice conversation and progressively drawn visual explanations.

The pedagogical stance shapes the architecture: **the model teaches, the server
decides**. Whether an answer is correct, which exercise comes next, how much
help a stuck student has already been given, and how much progress was earned —
all of that is computed deterministically in Python and persisted. The LLM
writes the words around those facts. That split is why the interesting parts of
this codebase are a state machine, a reducer, and a math engine rather than a
prompt file.

---

## Table of contents

- [What it does](#what-it-does)
- [Tech stack](#tech-stack)
- [Repository layout](#repository-layout)
- [Architecture](#architecture)
  - [Request lifecycle](#request-lifecycle)
  - [Layering rules](#layering-rules)
  - [The lesson state machine](#the-lesson-state-machine)
  - [The homework agent](#the-homework-agent)
  - [The math engine](#the-math-engine)
  - [Study materials and retrieval](#study-materials-and-retrieval-rag)
  - [Visual board explanations](#visual-board-explanations)
  - [Voice](#voice)
  - [Progress scoring](#progress-scoring)
- [Data model](#data-model)
- [API surface](#api-surface)
- [Frontend](#frontend)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Feature flags](#feature-flags)
- [Testing](#testing)
- [Database migrations](#database-migrations)
- [Deployment](#deployment)
- [Security and privacy](#security-and-privacy)
- [Design decisions worth knowing](#design-decisions-worth-knowing)

---

## What it does

Mentora has two distinct modes of conversation, sharing one messages table, one
streaming transport, and one voice pipeline. Only the phase machine differs.

### 1. Guided lessons (`SessionMode.LESSON`)

A student picks a topic and subtopic from a built-in maths curriculum
(8 topics, 33 subtopics — see [mathCurriculum.ts](frontend/src/data/mathCurriculum.ts)),
then walks a fixed pedagogical ladder:

```
teaching → pre_practice_example → practice → practice_summary → summary → completed
```

- **teaching** — open chat with the tutor about the subtopic. The student picks
  a difficulty (easy / medium / hard) which scales every later explanation and
  question.
- **pre_practice_example** — one fully worked example before being asked to try.
- **practice** — sets of 3 generated questions, each with its own difficulty
  rank inside the set. Answers are graded, feedback is per-answer, and the
  student can request another set.
- **practice_summary / summary** — a generated review of what went well and
  what to revisit, plus the option to practise again.

Phases are stored in one column (`lesson_sessions.phase`) and each phase owns
its legal transitions. Attempting a practice action while in `teaching` raises
`InvalidLessonAction` rather than silently doing something odd.

### 2. Homework help (`SessionMode.HOMEWORK`)

A single-phase conversation over work the student uploaded (a PDF, a DOCX, or a
photo of a worksheet). Mentora extracts the text, segments it into a numbered
exercise outline, and then works through it one exercise at a time:

- It never gives the answer away. Being stuck escalates a **help ladder** — name
  the idea → point at the exact numbers → teach the method → work a similar
  example → walk this exercise but stop one step short.
- A student can **park** an exercise ("skip this one"). Parked work is not
  written off: once nothing untouched is left, Mentora brings it back and will
  not accept "let's stop" as an answer while work is still owed.
- Answers are checked by the **server**, not by the model — including answers
  spoken aloud ("three quarters" is credited as `3/4`).

### Cross-cutting features

| Feature | Notes |
| --- | --- |
| **Streaming replies** | NDJSON stream of `text_delta` / tool-activity / `done` events |
| **Voice in and out** | Record → STT → tutor turn → sentence-chunked TTS, with barge-in |
| **Board explanations** | Structured, validated diagrams drawn block by block with synchronized narration |
| **Study materials (RAG)** | Uploaded files are chunked and retrieved per turn, so a lesson can cite the student's own worksheet |
| **Progress tracking** | Points per correct practice answer, weighted by difficulty, rolled up into a subtopic/topic learning map |

---

## Tech stack

**Backend** — Python 3.12, FastAPI, SQLAlchemy 2.0 (sync ORM), Alembic,
Pydantic v2 + pydantic-settings, PostgreSQL (SQLite in tests), SymPy, pytest.

**Frontend** — React 18, TypeScript, Vite, React Router 6, axios,
react-markdown + KaTeX (`remark-math` / `rehype-katex`), Vitest +
Testing Library.

**AI** — OpenAI: a chat model as the tutor brain, a separate vision model for
reading photographed homework, a separate STT model, a separate TTS model, and a
separate model for board generation. Each is its own setting so one can be
upgraded without moving the others.

**Auth** — JWT (HS256) bearer tokens, bcrypt password hashing via passlib.

**Deploy** — one Docker image (multi-stage), Railway, managed Postgres, a
mounted volume for uploads.

---

## Repository layout

```
Mentora/
├── backend/
│   ├── app/
│   │   ├── main.py            # pure API: routers at the root (tests + dev proxy)
│   │   ├── asgi.py            # production ASGI: API at /api, built SPA at /
│   │   ├── api/               # controllers — HTTP only, no business logic
│   │   ├── services/          # use cases, transaction ownership
│   │   ├── repositories/      # all query construction
│   │   ├── models/            # SQLAlchemy ORM tables
│   │   ├── schemas/           # Pydantic request/response DTOs
│   │   ├── lesson/            # the lesson phase state machine
│   │   ├── agent/             # the homework agent: tools, reducer, stores, trace
│   │   ├── llm/               # provider interface, OpenAI impl, prompts, tool protocol
│   │   ├── math/              # deterministic math: normalize, calculate, validate, route
│   │   ├── files/             # upload → extract → chunk → retrieve
│   │   ├── board/             # board spec validation + digest
│   │   └── core/              # settings, enums, security, logging
│   ├── alembic/versions/      # 10 migrations — Alembic solely owns the schema
│   └── tests/                 # 418 tests, SQLite in-memory, fake LLM
├── frontend/
│   └── src/
│       ├── pages/             # one page per route
│       ├── components/        # chat, board rendering, uploads, avatar
│       ├── hooks/             # useTutorChat, useBoardPlayer, useLipSyncVolume
│       ├── api/               # thin axios wrappers, one per backend area
│       └── data/              # the maths curriculum
├── docs/
│   ├── DEPLOYMENT.md          # Railway deployment, step by step
│   └── MANUAL_QA_CHECKLIST.md # 31-case manual acceptance suite (Hebrew)
├── Dockerfile                 # node build stage + python runtime stage
├── docker-entrypoint.sh       # alembic upgrade head, then uvicorn
└── railway.json
```

---

## Architecture

### Request lifecycle

A single tutor turn, end to end:

```
React (useTutorChat)
  │  POST /api/tutor/{id}/turn/stream
  ▼
tutorController                 auth via Depends(get_current_student); no logic
  │
  ▼
TutorService                    owns the transaction — one commit per request
  │
  ▼
LessonContext                   builds the pedagogical context for this turn:
  │                             recent messages, retrieved material excerpts,
  │                             board digest, student profile, phase
  ▼
LessonState (per phase)         TeachingState / PracticeState / HomeworkHelpState…
  │                             decides what this turn *means*
  ├──────────────► MathRouterService     deterministic answer check
  ├──────────────► AgentRunner           (homework, flag on) tool loop
  └──────────────► LLMProvider           writes the reply
  │
  ▼
Repositories                    all queries live here
  │
  ▼
PostgreSQL
```

The reply streams back as newline-delimited JSON:

```jsonc
{"type":"stream_start"}
{"type":"text_delta","data":"Let's look at "}
{"type":"tool_call","name":"evaluateAnswer"}      // agent activity, when enabled
{"type":"audio_start","chunk_id":1}                // voice transports only
{"type":"audio_delta","chunk_id":1,"data":"<b64>"}
{"type":"done"}
```

### Layering rules

These are enforced by convention throughout the codebase and are worth
respecting when adding code:

1. **Controllers do HTTP.** Parse, authorize, delegate, serialize. No queries,
   no branching on domain state.
2. **Services own the transaction.** One commit per request. `AgentRunner`
   explicitly never commits — its caller does, which is what keeps a turn
   message-atomic (a cancelled stream leaves no partial state).
3. **Repositories own queries.** No `db.query(...)` outside `app/repositories/`
   (with a small number of deliberate exceptions inside the agent stores).
4. **The LLM provider is an interface.** `LLMProvider` is abstract; `OpenAIProvider`
   is one implementation and `FakeLLMProvider` in tests is another. Nothing above
   this layer imports `openai`.
5. **Every extension point is a real seam.** `FileStorage`, `DocumentExtractor`,
   `MaterialRetriever`, and `LLMProvider` are each an ABC with one working
   implementation — so local disk can become S3, and keyword ranking can become
   vector search, without touching a call site.

### The lesson state machine

`app/lesson/state.py` is a textbook State pattern. `LessonContext` is the
context object, rebuilt per request; the concrete state is rehydrated from
`lesson_sessions.phase`, which is the single source of truth.

Each state implements:

```python
generate_phase_opening_message(ctx)    # the tutor's first words in this phase
generate_reply_to_student_message(ctx, text)   # one conversational turn
# plus its own phase-specific actions and the legal transition onward
```

States: `TeachingState`, `PrePracticeExampleState`, `PracticeState`,
`PracticeSummaryState`, `SummaryState`, `CompletedState`, and — for the other
mode — `HomeworkHelpState`.

Why this matters: there is no `if phase == ...` chain scattered across services.
Adding a phase means adding a class.

### The homework agent

Behind `AGENT_ENABLED_HOMEWORK`. The design principle is stated in
[`app/agent/__init__.py`](backend/app/agent/__init__.py):

> **Tools observe; the reducer determines; stores persist.**

```
student text
   │
   ▼
routing.py         Is this an answer, a plea for help, a courtesy, or a skip?
   │               (regex, EN + HE, apostrophe-tolerant — "dont"/"don't"/"don’t")
   ▼
AgentRunner        up to AGENT_MAX_STEPS tool steps per turn
   │
   ├── ToolRegistry ──► evaluateAnswer            server-side correctness check
   │                    analyzeHomework           read the outline + position
   │                    recordLearningAnnotation  advisory note; cannot change state
   │                    searchStudyMaterials      RAG over this student's files
   │                    (registered, not exposed: getStudentProgress,
   │                     generatePracticeQuestion)
   │
   ▼
StateReducer       PURE. The sole authority on transitions.
   │               EvaluationResult + SessionState → StateTransition
   ▼
Stores             SessionStateStore    per-session agent state (row-locked)
                   StudentProgressStore long-term skill mastery
                   AgentTraceStore      every step, for debugging + the UI
```

Guarantees that come out of this shape:

- **The model cannot mark itself correct.** Only an `EvaluationResult` with
  `authoritative=True`, produced by the server-bound `evaluateAnswer` tool,
  moves state. Model prose is never evidence.
- **Substeps are server-issued capabilities.** A model may only affect the exact
  `response_target` the session is currently awaiting — it cannot invent a
  `exercise-3-step-7` and get credit for it.
- **Idempotency.** `applied_evaluation_keys` plus a stable client turn id mean a
  retried request cannot double-count an answer or double-credit mastery. The
  session state row is loaded `FOR UPDATE`, so concurrent retries serialize.
- **Every tool call is validated.** Arguments are Pydantic models with
  `extra="forbid"` and hard length bounds.
- **Hints are stateful.** `hint_level` is both persisted *and* explained to the
  model each turn — each rung of the ladder is explicitly forbidden from
  repeating the one before it.

Traces are exposed at `GET /tutor/{session_id}/agent-traces` and rendered in the
UI by [`AgentActivity.tsx`](frontend/src/components/AgentActivity.tsx).

### The math engine

`app/math/` exists so that correctness never depends on a language model.

```
MathRouterService        classifies: basic_arithmetic | fraction_arithmetic |
     │                   percentage | equation_solving | algebra_simplification |
     │                   geometry_formula | word_problem | unsupported
     ├──► normalizer.py        "1 1/2" | "50%" | "x = 2" | "0.5"  →  Fraction
     ├──► calculator.py        exact arithmetic via fractions.Fraction
     ├──► sympy_service.py     symbolic equivalence, equation solving (lazy import)
     └──► validator.py         student answer vs. correct answer
```

Validation runs in confidence order: exact `Fraction` comparison → SymPy
symbolic equivalence → normalised string comparison as a last resort.

The convention that runs through the whole engine: **`is_equivalent is None`
means "could not determine"**. A tool that cannot parse its input abstains
rather than guessing, and the caller falls back. A false "wrong" is far more
damaging to a child than a missed check.

`calculator.py` is also guarded against abuse — a character allowlist, a length
cap, and no `**`.

`reply_policy.py` adds a final deterministic pass over generated prose: if the
tutor's reply contains a number that contradicts the computed answer, or asks a
question it has already answered, the reply is corrected before the student
sees it.

### Study materials and retrieval (RAG)

`app/files/` is a four-stage pipeline, each stage a swappable interface:

```
upload → FileStorage       where the bytes live (local disk today; S3 tomorrow)
       → DocumentExtractor bytes → plain text
       → chunk_text        text → overlapping, paragraph-aligned slices
       → MaterialRetriever query → only the relevant slices
```

**Extractors** are registered per format family — PDF (`pypdf`), DOCX
(`python-docx`), PPTX (`python-pptx`), plain text, and images via a vision
model. Each optional dependency is imported lazily, so a missing one degrades
exactly one file type. `ExtractorUnavailable` (environment can't process it —
park the file) is deliberately distinct from `ExtractionError` (this file is
broken — fail it).

**Lifecycle** is explicit on the row: `pending → processing → ready`, or
`unsupported` / `failed` with a `status_detail` explaining why. A failed
material can be reprocessed from the UI.

**Chunking** is 1200 chars with 150 chars of overlap, packed on paragraph
boundaries — so a hit is specific enough to be useful but a definition
straddling a boundary survives intact in at least one chunk.

**Retrieval** today is TF-IDF-style keyword ranking with a stopword list tuned
for how children actually phrase questions ("can you explain the fractions"
must not match on *the* and *you*). `MaterialChunk.embedding` is a nullable JSON
column — the seam where vector search drops in with no schema change.

Two kinds of file, distinguished by `MaterialKind`:

- `STUDY_MATERIAL` — persistent, topic-tagged, retrieved on demand during any
  lesson. Capped per prompt by `MATERIAL_CONTEXT_CHAR_BUDGET` so a big upload
  cannot crowd out the lesson.
- `HOMEWORK` — belongs to exactly one session and is always in that session's
  context.

### Visual board explanations

Behind `BOARD_EXPLANATION_ENABLED`. A "board" is a structured diagram the tutor
draws block by block while narrating it.

The model does not emit pixels — it emits a **typed spec**, which is why the
drawing can never contradict its own parameters:

| Block | What it draws |
| --- | --- |
| `steps` | A chain of working, with per-step operation, emphasis and notes |
| `callout` | A short highlighted remark |
| `expression_compare` | Two expressions and the relation between them |
| `fraction_bars` | Fraction bars from numerator/denominator |
| `number_line` | Points and intervals on a line |
| `coordinate_plane` | Lines (slope/intercept) and points |
| `geometry_figure` | A labelled figure |

`app/board/validation.py` is careful about what "validated" means, and keeps
three things apart:

- **Rendering consistency** — total, by construction: the schema takes
  slope/intercept and numerator/denominator, never coordinates.
- **Internal consistency** — step chains, relation glyphs and fraction labels
  are cross-checked.
- **Fidelity to the question** — weak and block-dependent; only some blocks get
  a real check, plus the final answer. This is stated honestly in the module
  docstring rather than implied to be complete.

Generation gets **one repair attempt**. A second rejection returns a clear error
rather than making a child wait for a third try.

`app/board/digest.py` renders a shown board into compact text so the tutor can
answer "why did you cross that out?" two turns later — derived
deterministically, no second model call, blocks numbered so the model and the
student agree on what "step 2" means. Only `BOARD_DIGEST_LIMIT` recent boards
within `BOARD_DIGEST_CHAR_BUDGET` chars are carried forward.

Each board hangs off exactly one anchor, and the anchor says what it is for —
`message_id` for a lesson-intro or chat board, `question_id` for a
practice review board. Both anchor columns are `unique`, which makes replaying a
board free and stops a board ever being reused for something it wasn't drawn
for.

### Voice

`VoiceService` is deliberately thin and knows nothing about lessons, prompts, or
tutoring — it only converts audio ↔ text, entirely in memory. The backend never
records from a microphone or plays sound.

The latency trick is `SpeechChunker`: streamed text deltas are accumulated and
emitted at natural boundaries, so TTS starts on the first short phrase instead
of waiting for the whole reply. The first chunk is deliberately small and
aggressive; later ones are conservative. Decimals are never split — `3.14`
only breaks on a `.` followed by whitespace.

Transcription is pinned to one language (`OPENAI_STT_LANGUAGE`) so a short or
noisy clip like "eight" isn't misdetected as another tongue.

Spoken answers are a first-class path, not an afterthought: `_spoken_number_candidate`
in [`app/agent/evaluation.py`](backend/app/agent/evaluation.py) reads
numbers said in words, after dropping filler ("um", "i think", "the answer is").
It is deliberately strict — what remains after filler removal must be *nothing
but* the number — so "one more time" is never read as the answer 1.

### Progress scoring

Progress is earned per correct practice answer, weighted by the difficulty the
question was asked at:

| Level | Points |
| --- | --- |
| easy | 1 |
| medium | 3 |
| hard | 5 |

100 points completes a subtopic — so 20 correct hard answers, or 100 easy ones.
Past 100 a student can keep practising; it simply stops adding.

The level is **copied onto each question row** (`assessment_questions.level`)
rather than read back from the session, because progress is credited per
question: the level a point was earned at must not move when the lesson's
difficulty does.

Homework sessions are excluded from lesson progress and track their own
counters, cached against `messages_synced` — computing homework progress needs
an LLM read of the whole transcript, so an unchanged message count means the
cached score is still valid and the call is skipped.

---

## Data model

```
students
   ├── lesson_sessions ────────────────────────────────┐
   │      ├── messages                                 │
   │      ├── assessment_questions ──► board_explanations (unique question_id)
   │      ├── performance            (1:1)              │
   │      ├── agent_session_state    (1:1, homework)    │
   │      ├── agent_trace            (audit, by run_id) │
   │      └── study_materials        (homework files)   │
   ├── study_materials (kind=study_material) ──► material_chunks
   └── student_skill_mastery  (unique per student+subject+topic+skill)
```

Notable columns:

| Table | Column | Why it exists |
| --- | --- | --- |
| `lesson_sessions` | `mode` | `lesson` or `homework` — which phase machine applies |
| `lesson_sessions` | `phase` | Single source of truth for the state machine |
| `lesson_sessions` | `last_opened_at` | History is ordered by where the student has *been*, not what they started — reopening an old lesson brings it back to the top |
| `lesson_sessions` | `homework_outline` | The segmented exercise list (JSON) |
| `agent_session_state` | `solved_refs` / `skipped_refs` | Parked work is owed, never counted as solved |
| `agent_session_state` | `applied_evaluation_keys` | Idempotency — a retry cannot double-count |
| `agent_session_state` | `hint_level` | Which rung of the help ladder the student is on |
| `material_chunks` | `embedding` | Nullable JSON — the vector-search seam, portable across SQLite and Postgres without pgvector |
| `board_explanations` | `message_id` / `question_id` | Mutually exclusive unique anchors |
| `performance` | `messages_synced` | Cache key for expensive homework-progress recomputation |

**Alembic owns the schema, exclusively.** `main.py`'s lifespan deliberately
creates nothing — `create_all` at startup can race an upgrade and can make an
incompatible database look current after being stamped.

---

## API surface

All routes require `Authorization: Bearer <jwt>` except `/auth/register` and
`/auth/login`. In production everything below is prefixed with `/api`.

### Auth — `app/api/authController.py`

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/auth/register` | Create a student |
| POST | `/auth/login` | Exchange credentials for a JWT |
| GET | `/auth/me` | Current student profile |

### Sessions — `app/api/sessionController.py`

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/sessions/` | Start a lesson |
| GET | `/sessions/` | Lesson history (paged, by `last_opened_at`) |
| GET | `/sessions/{id}` | One session |
| POST | `/sessions/{id}/end` | End a session |
| GET | `/sessions/{id}/messages` | Transcript |

### Tutor — `app/api/tutorController.py`

**Conversation**

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/tutor/{id}/turn` | One turn, non-streaming |
| POST | `/tutor/{id}/turn/stream` | One turn, NDJSON text stream |
| POST | `/tutor/{id}/turn/speech-stream` | One turn, text + interleaved TTS audio |
| POST | `/tutor/{id}/voice-turn` | Audio in → transcript + reply + audio out |
| POST | `/tutor/{id}/tts` | Speak arbitrary text |

**Lesson flow**

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/tutor/{id}/difficulty` | Set easy / medium / hard |
| POST | `/tutor/{id}/advance` | Move to the next phase |
| POST | `/tutor/{id}/practice/start` | Generate a practice set |
| POST | `/tutor/{id}/practice/submit` | Submit and grade a set |
| POST | `/tutor/{id}/practice/next` | Another set |
| POST | `/tutor/{id}/practice/finish` | Close practice |
| GET | `/tutor/{id}/practice/summary` | Practice results |
| GET | `/tutor/{id}/lesson-summary` | Final lesson summary |

**Homework**

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/tutor/homework` | Create a homework session |
| GET | `/tutor/homework` | List homework sessions |
| POST | `/tutor/{id}/homework/analyze` | Read the upload, build the outline, open the conversation |
| PATCH | `/tutor/{id}/homework/rename` | Rename |
| DELETE | `/tutor/{id}/homework` | Delete the session and everything it holds |
| GET | `/tutor/{id}/homework/progress` | Exercises solved / total |
| GET | `/tutor/{id}/agent-traces` | Agent step trace |

**Boards**

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/tutor/{id}/boards` | List boards (`{"enabled": false}` when the flag is off) |
| POST | `/tutor/{id}/boards/lesson` | Generate a lesson-intro / chat board |
| POST | `/tutor/{id}/boards/question` | Generate a practice-review board |
| GET | `/tutor/{id}/boards/{board_id}` | Fetch a board spec (replay is free) |
| POST | `/tutor/{id}/boards/{board_id}/narration` | Stream narration audio, block by block |

### Materials — `app/api/materialController.py`

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/materials/supported-formats` | What can be extracted in this environment |
| POST | `/materials/` | Upload a study material |
| GET | `/materials/` | List / filter |
| PATCH | `/materials/{id}` | Retag (subject / topic / subtopic / title) |
| POST | `/materials/{id}/reprocess` | Retry extraction |
| DELETE | `/materials/{id}` | Delete row, chunks and bytes |
| GET | `/materials/{id}/file` | Download the original |
| POST | `/materials/homework/{session_id}` | Upload homework to a session |
| GET | `/materials/homework/{session_id}` | List a session's homework |

### Progress — `app/api/progressController.py`

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/progress/` | Aggregate metrics + recent sessions |
| GET | `/progress/map` | Per-topic / per-subtopic learning map |

Interactive docs are at `/docs` (or `/api/docs` in production).

---

## Frontend

Routes (all except login/register sit behind `ProtectedRoute`):

| Route | Page |
| --- | --- |
| `/login`, `/register` | Auth |
| `/`, `/new` | Topic picker |
| `/topic/:topicId` | Subtopic picker |
| `/lesson/:sessionId` | Lesson chat |
| `/lesson/:sessionId/pre-practice` | Worked example |
| `/lesson/:sessionId/practice` | Practice set |
| `/lesson/:sessionId/practice/summary` | Practice results |
| `/lesson/:sessionId/summary` | Lesson summary |
| `/homework/:sessionId` | Homework help |
| `/files` | My files |
| `/progress` | My lessons + learning map |

**Auth** — the JWT lives in `localStorage`. An axios response interceptor
catches any `401`, clears the token, flags `mentora_session_expired` in
`sessionStorage`, and redirects to `/login` — so an expired session explains
itself instead of silently failing.

**One base URL for both environments** — the axios client always targets `/api`.
In development the Vite proxy rewrites that to `localhost:8000`; in production
`asgi.py` mounts the API there. No frontend code changes between the two.

**Code splitting** — the heavy markdown + KaTeX bundle is pulled in only by the
lesson and practice pages, so every such route is `lazy()`-loaded and the
login bundle stays light.

**Key hooks**

- `useTutorChat` — owns the NDJSON stream: text deltas, tool-activity events,
  audio chunks, cancellation.
- `useBoardPlayer` — plays a board spec block by block against narration audio.
- `useLipSyncVolume` — drives the tutor avatar's mouth from the audio envelope.

**Math rendering** — `RichText.tsx` renders markdown with `remark-math` +
`rehype-katex`, so the tutor can write real fractions and equations.

---

## Getting started

### Prerequisites

- Python 3.12+
- Node 22+
- PostgreSQL 14+ (or use SQLite for a quick local spin)
- An OpenAI API key

### 1. Backend

```sh
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/mentora
SECRET_KEY=<a long random string — generate one, never reuse this line>
OPENAI_API_KEY=sk-...

# optional: turn the two flagged features on locally
AGENT_ENABLED_HOMEWORK=true
BOARD_EXPLANATION_ENABLED=true
```

Generate a key with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

Run the migrations and start the API:

```sh
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

`app.main:app` is the pure API with routers at the root — that's what the Vite
proxy and the test suite talk to, and it needs no frontend build.

### 2. Frontend

```sh
cd frontend
npm install
npm run dev          # http://localhost:5173
```

The dev server proxies `/api` → `localhost:8000`.

### 3. Try it

Register a student, pick a topic, and run one lesson through to its summary.
Then upload a homework PDF or a photo of a worksheet from **My Files** and start
a homework session.

---

## Configuration

Everything is read from `backend/.env` through `Settings` in
[`app/core/config.py`](backend/app/core/config.py). Unknown keys are
ignored (`extra="ignore"`).

### Required

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy connection string |
| `SECRET_KEY` | JWT signing key |
| `OPENAI_API_KEY` | Required for every AI feature |

### Models

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_MODEL` | `gpt-5.4-mini` | The tutor brain |
| `OPENAI_BOARD_MODEL` | `gpt-5.4-mini` | Board generation (one structured JSON call) |
| `OPENAI_VISION_MODEL` | `gpt-4o-mini` | Reading text off photographed homework |
| `OPENAI_STT_MODEL` | `gpt-4o-transcribe` | Speech to text |
| `OPENAI_TTS_MODEL` | `gpt-4o-mini-tts` | Text to speech |
| `OPENAI_TTS_VOICE` | `alloy` | TTS voice |
| `OPENAI_STT_LANGUAGE` | `en` | ISO-639-1; empty to auto-detect |
| `LLM_PROVIDER` | `openai` | Provider selection seam |

Each is separate on purpose: the tutor brain can be upgraded without moving
speech, vision, or board generation.

### Auth

| Variable | Default |
| --- | --- |
| `ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24h) |

### Agent

| Variable | Default | Purpose |
| --- | --- | --- |
| `AGENT_ENABLED_HOMEWORK` | `false` | The agent loop (see [Feature flags](#feature-flags)) |
| `AGENT_MAX_STEPS` | `4` | Tool steps per turn (1–4) |
| `AGENT_TOOL_TIMEOUT_S` | `10.0` | Per-tool timeout |
| `AGENT_MAX_HINT_LEVEL` | `4` | Top rung of the help ladder |

### Boards

| Variable | Default | Purpose |
| --- | --- | --- |
| `BOARD_EXPLANATION_ENABLED` | `false` | The whole board feature |
| `BOARD_MAX_BLOCKS` | `6` | Caps modal length and prompt cost (1–12) |
| `BOARD_DIGEST_CHAR_BUDGET` | `700` | How much board recall may enter a later prompt |
| `BOARD_DIGEST_LIMIT` | `2` | How many recent boards the tutor keeps in mind |

### Materials

| Variable | Default | Purpose |
| --- | --- | --- |
| `MATERIAL_STORAGE_DIR` | `storage/materials` | Where uploads live |
| `MATERIAL_MAX_UPLOAD_MB` | `20` | Upload size cap |
| `MATERIAL_CONTEXT_CHAR_BUDGET` | `4000` | Max retrieved text per prompt |

### Ops

| Variable | Default | Purpose |
| --- | --- | --- |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | JSON list. Unneeded in production — one origin |
| `FRONTEND_DIST_DIR` | `None` | Where the built SPA lives; the Docker image sets it |
| `LOG_LEVEL` | `INFO` | |
| `LOG_DIR` | `None` → `backend/logs/` | Rotating `mentora.log` + console |
| `STT_MIN_AUDIO_BYTES` | `0` | Treat smaller clips as silence. Off by default — "eight" is a valid turn |
| `LLM_DEBUG_DUMP_PROMPTS` | `false` | **Local demos only.** Writes every prompt verbatim to `logs/prompts/`, including student text and uploaded material |

---

## Feature flags

Two features default to **off**. That is a deliberate ship-dark pattern, not
unfinished work — both are merged to `main` with full test coverage, and both
cost extra OpenAI calls per turn.

**`AGENT_ENABLED_HOMEWORK`** — replaces the single-call homework path with the
agent loop over four exposed tools, up to four steps per turn. It builds an
exercise outline and tracks `current_exercise_index` / `hint_level` as real
state. The server stays the sole authority on correctness. When off, the legacy
atomic path runs instead, so homework help still works.

**`BOARD_EXPLANATION_ENABLED`** — progressively drawn boards with synchronized
TTS narration, plus recall of a compact board digest into later chat prompts.
When off, `GET /tutor/{id}/boards` answers `200 {"enabled": false}`, the
generate/fetch endpoints 404, and the UI renders no board action. Practice is
fully functional without it.

---

## Testing

### Backend — 418 tests

```sh
cd backend
pytest                          # everything
pytest tests/test_agent_runner.py -v
pytest -k homework
```

Tests run against **SQLite in-memory** with a `StaticPool`, and against
`FakeLLMProvider` / `ScriptedAgentLLM` injected through FastAPI's dependency
overrides. **No test touches the network or Postgres**, so the suite is fast and
deterministic.

What the suite deliberately covers:

| Area | Files |
| --- | --- |
| Agent loop, state, reducer | `test_agent_runner.py`, `test_agent_state.py`, `test_state_reducer.py` |
| Answer routing & evaluation | `test_answer_routing.py`, `test_evaluate_answer.py`, `test_spoken_answers.py` |
| Deterministic math safety | `test_calculator_guardrails.py`, `test_grading_validation.py` |
| Homework flows | `test_homework_flow.py`, `test_homework_agent_flow.py`, `test_homework_outline.py`, `test_homework_counting.py`, `test_skipped_exercises.py`, `test_homework_delete.py` |
| Boards | `test_board_flow.py`, `test_board_schema.py`, `test_board_validation.py`, `test_board_service.py`, `test_board_recall.py` |
| Materials & RAG | `test_materials.py`, `test_materials_edge_cases.py`, `test_extractors.py`, `test_rag_e2e.py`, `test_rag_quality.py` |
| Voice | `test_voice_turn.py`, `test_speech_stream.py`, `test_speech_chunker.py` |
| Lesson mechanics | `test_lesson_state.py`, `test_practice_progress.py`, `test_lesson_history_order.py`, `test_tutor_reply_coherence.py` |
| Isolation & schema | `test_history_visibility.py`, `test_migrations.py`, `test_system_e2e.py` |

`test_migrations.py` checks that the Alembic chain actually produces the schema
the models describe — the guard that keeps migrations honest.

### Frontend

```sh
cd frontend
npm test            # vitest run
```

### Manual QA

[`docs/MANUAL_QA_CHECKLIST.md`](docs/MANUAL_QA_CHECKLIST.md) is a
31-case manual acceptance suite (in Hebrew), written to be run with two users —
A owning the resources and B verifying isolation.

---

## Database migrations

Alembic is the sole owner of the schema. Ten migrations, `0001` through `0010`.

```sh
cd backend
alembic upgrade head
alembic revision --autogenerate -m "describe the change"
alembic downgrade -1
alembic current
```

Note that `alembic.ini` carries a SQLite fallback URL; `alembic/env.py` prefers
`DATABASE_URL` from settings, so the real target comes from the environment.

The container entrypoint runs `alembic upgrade head` with `set -e` before
uvicorn — a failed migration stops the container rather than serving against a
stale database.

---

## Deployment

One Docker image, one Railway service, a managed Postgres, and a mounted volume
for uploads. Full walkthrough in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

```
stage 1  node:22-alpine     npm ci → npm run build  →  frontend/dist
stage 2  python:3.12-slim   pip install → copy backend + dist
         entrypoint         alembic upgrade head → uvicorn app.asgi:app
```

**Why one service.** `asgi.py` mounts the API under `/api` and serves the SPA at
`/` — which is exactly the axios `baseURL` the frontend already uses. That gives
one origin (no CORS in production), one dashboard, and no frontend code change
between dev and prod.

The API *must* sit under a prefix: the SPA owns `/progress` and `/files` while
the API owns `/progress` and `/materials`, so sharing a root would collide.

`asgi.py` is kept out of `main.py` deliberately — importing it requires a built
frontend, and the tests must not.

Run the image locally:

```sh
docker build -t mentora:local .
docker run --rm -p 8000:8000 --env-file backend/.env mentora:local
```

A volume is required in production. Without it, uploaded homework is wiped on
every deploy — the container filesystem is ephemeral.

---

## Security and privacy

This application handles children's schoolwork. The following are load-bearing,
not incidental:

- **Per-student isolation on every resource.** Sessions, messages, materials,
  boards and progress are all fetched through an ownership check —
  `get_owned_session_or_404` and the equivalent per-student filters in each
  repository. `test_history_visibility.py` exists to keep this true.
- **Passwords** are bcrypt-hashed via passlib. Emails are normalised
  (trimmed, lowercased) before the uniqueness check.
- **JWTs** are HS256, 24h by default. A `401` clears the client token and
  redirects.
- **Prompt and response text is never logged** in normal operation.
  `LLM_DEBUG_DUMP_PROMPTS` is the single exception and is off by default — its
  own module docstring warns never to enable it outside a local demo, because
  the files contain full student text and uploaded material.
- **Uploads never leave the storage seam.** The DB stores only an opaque key
  (`<student_id>/<uuid><ext>`); the student's original filename is kept on the
  row for display but stays out of the path.
- **Audio is in-memory only.** The backend never records from a microphone or
  writes an audio file.
- **`.gitignore` excludes `storage/`, `logs/`, `.env` and `*.zip`** — student
  data and secrets are structurally kept out of version control.
- **Arithmetic evaluation is guarded** by a character allowlist, a 256-char
  cap, and a `**` ban.
- **Request IDs** are attached by `LoggingMiddleware` and exposed as
  `X-Request-ID`, so a user-reported problem can be traced without logging
  content.

---

## Design decisions worth knowing

A few choices that look surprising until you know why:

**The server, not the model, decides correctness.** Every state transition
requires an `authoritative` evaluation from a server-bound tool. This is the
single most important invariant in the codebase — it's what makes the tutor
trustworthy rather than merely fluent.

**The reducer is pure.** `StateReducer.reduce` is a pure function from
`(SessionState, EvaluationResult)` to `StateTransition`. All the awkward
questions — retries, concurrent requests, stale tool results, a model inventing
a target — are answered in one testable place instead of scattered across
service code.

**Abstaining beats guessing.** `is_equivalent is None` propagates through the
whole math and board stack. A check that can't parse its input reports nothing.
A false rejection makes the tutor look broken to a child; a missing check leaves
things no worse than the prose the tutor would have written anyway.

**A skip is a postponement, not a write-off.** `skipped_refs` is separate from
`solved_refs`, untouched work is always offered first, and once only parked work
remains the tutor is explicitly instructed not to accept "let's stop".

**The hint level is explained to the model, not just stored.** Persisting
`hint_level` without telling the model about it was the original bug: a student
who asked for help twice got the same reply twice. Each rung now names what the
previous rung tried and forbids repeating it.

**Prompts get a deterministic post-pass.** `reply_policy.py` checks generated
prose against computed answers before the student sees it, because a tutor that
contradicts its own grading is worse than one that says less.

**Board digests, not board specs, go into later prompts.** The full spec is
rendering data — coordinates, ranges, render hints — and says nothing a
conversation needs. The digest is the reasoning data, derived deterministically
with no second model call.

**`main.py` creates no tables.** Schema ownership is Alembic's alone. Startup
`create_all` can race an upgrade and make an incompatible database look current
after being stamped.

**Multiplication is read the way a worksheet writes it.** `7 x 8` and `7 × 8`
are rewritten to `7 * 8` for the parser — but only between digits, so the `x` in
`2x + 3 = 11` is left alone. The student is still shown the question exactly as
their worksheet wrote it.

**Non-answer detection is apostrophe-tolerant and bilingual.** Students type
`dont`, phones autocorrect to `don't`, some keyboards emit `don’t` — all three
must read the same, or the plainest way to say "I'm stuck" gets force-graded as
a wrong math answer. Hebrew patterns sit alongside the English ones.
