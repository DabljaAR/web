# DabljaAR — System Architecture

> **Last updated:** February 2026  
> **Architecture style:** Modular Monolith (with a clear microservices migration path)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Technology Stack](#2-technology-stack)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Backend — Module Organization](#4-backend--module-organization)
5. [Database Schema](#5-database-schema)
6. [Authentication & Security](#6-authentication--security)
7. [Async Job Processing](#7-async-job-processing)
8. [Frontend Architecture](#8-frontend-architecture)
9. [API Design Conventions](#9-api-design-conventions)
10. [Cross-Cutting Concerns](#10-cross-cutting-concerns)
11. [Deployment & Infrastructure](#11-deployment--infrastructure)
12. [Future Roadmap](#12-future-roadmap)

---

## 1. System Overview

DabljaAR is an AI-powered video dubbing platform that automatically translates and re-voices video content from English to Arabic using a four-stage pipeline:

```
Video Upload → Speech-to-Text (Whisper) → Translation (NLLB-200) → TTS (MMS) → Dubbed Video
```

The platform is a **modular monolith**: a single deployable FastAPI application divided into vertical feature modules, each with its own models, schemas, services, and router. This gives the speed of a monolith today with a clean seam to extract individual modules into microservices later.

---

## 2. Technology Stack

### Backend

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Web framework | **FastAPI** | 0.127 | Async HTTP API, OpenAPI docs |
| ORM | **SQLAlchemy** | 2.0 | Async ORM with mapped columns |
| DB driver | **asyncpg** | 0.31 | Async PostgreSQL driver |
| Migrations | **Alembic** | 1.17 | Schema versioning |
| Validation | **Pydantic v2** | 2.12 | Request/response schemas, settings |
| Auth | **python-jose + passlib** | 3.5 / 1.7 | JWT (HS256), bcrypt password hashing |
| Job queue | **Celery** | 5.4 | Async task execution |
| Message broker | **Redis** | 7 | Celery broker + result backend |
| Rate limiting | **slowapi** | 0.1.9 | Per-IP request throttling |
| Error monitoring | **TBD** | — | Reserved for future integration |
| Linting | **ruff** | 0.14 | Fast Python linter + formatter |
| Testing | **pytest + pytest-asyncio** | 8.3 / 0.24 | Async test suite |
| Test coverage | **pytest-cov** | 6.0 | Coverage reports |

### Frontend

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| UI framework | **React** | 19 | Component tree |
| Routing | **React Router DOM** | 7 | Client-side routing |
| State management | **Zustand** | 5 | Global auth/app state |
| Styling | **Tailwind CSS** | 4 | Utility-first CSS |
| Build tool | **Vite** | 4 | Dev server + bundler |
| Language | **JavaScript (JSX)** | ES2022 | — |
| Testing | **Vitest + Testing Library** | 0.34 / 16 | Component + hook tests |

### Infrastructure

| Service | Technology | Notes |
|---|---|---|
| Primary database | **PostgreSQL 16** | Containerized |
| Message broker / cache | **Redis 7** | Celery broker + result backend |
| Containers | **Docker + Docker Compose** | Multi-service orchestration |
| Worker monitoring | **Flower** | Celery dashboard on port 5555 |
| File storage | **Rust `media-service` + S3-compatible backend** | Storage and presign flow are owned by Rust for media paths |

---

## 3. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                          Browser (React)                          │
│  React Router · Zustand · Tailwind · Vitest                       │
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTPS / JSON
┌───────────────────────────▼──────────────────────────────────────┐
│                      FastAPI Application                          │
│                                                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │  core/   │  │  media/  │  │  jobs/   │  │  (stt/nmt/tts/)  │  │
│  │  auth    │  │  upload  │  │  status  │  │  AI modules      │  │
│  │  users   │  │  HLS     │  │  cancel  │  │  (future)        │  │
│  │  billing │  │          │  │          │  │                  │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘  │
│                                                                    │
│  shared/: middleware · logging · rate limiter · db session        │
└──────────┬──────────────────────────────┬─────────────────────────┘
           │ asyncpg (async SQL)           │ .delay() (async dispatch)
┌──────────▼──────────┐         ┌─────────▼─────────────────────────┐
│    PostgreSQL 16      │         │           Redis 7                 │
│                       │         │  Celery broker + result backend   │
│  users · roles        │         └──────────┬────────────────────────┘
│  subscription_plans   │                    │ task pickup
│  user_subscriptions   │    ┌───────────────┼───────────────────┐
│  payments             │    │               │                   │
│  videos               │    │  worker-media │  worker-ai        │
│  jobs                 │    │  queue:media  │  queue:ai_*       │
└───────────────────────┘    │  concurrency=2│  concurrency=1    │
                             │  FFmpeg tasks │  Whisper/NLLB/MMS │
                             └───────────────┴───────────────────┘
                                         │
                             ┌───────────▼──────────┐
                             │   Flower Dashboard    │
                             │   localhost:5555       │
                             └──────────────────────┘
```

---

## 4. Backend — Module Organization

### Directory Layout

```
backend/
├── app/
│   ├── main.py               # FastAPI app factory, lifespan, middleware
│   ├── config.py             # Pydantic Settings — all env vars in one place
│   ├── dependencies.py       # DB connect/disconnect lifecycle hooks
│   │
│   ├── core/                 # Domain: users, auth, billing
│   │   ├── models.py         # SQLAlchemy ORM: User, Role, SubscriptionPlan,
│   │   │                     #   UserSubscription, Payment
│   │   ├── schema.py         # Pydantic I/O schemas (UserCreate, TokenResponse…)
│   │   ├── repository.py     # Generic BaseRepository + domain-specific repos
│   │   ├── services.py       # Business logic (UserService, SubscriptionService…)
│   │   ├── auth.py           # AuthService: JWT creation/verification, bcrypt
│   │   ├── router.py         # HTTP endpoints mounted at /api/*
│   │   ├── enums.py          # Python enums → SQLAlchemy Enum columns
│   │   ├── exceptions.py     # Domain exceptions (UserAlreadyExists, etc.)
│   │   ├── rate_limiter.py   # slowapi Limiter singleton
│   │   └── db.py             # SQLAlchemy engine, Base, AsyncSessionLocal, get_db
│   │
│   ├── media/                # Domain: video/audio upload & orchestration
│   │   ├── models.py         # Video, AudioTrack (planned)
│   │   ├── schema.py         # VideoResponse, UploadResponse
│   │   ├── service.py        # VideoService: upload → dispatch Celery job
│   │   ├── router.py         # /api/videos/* endpoints
│   │   └── client.py         # Rust media-service client for media/storage ops
│   │
│   ├── jobs/                 # Domain: async job processing
│   │   ├── celery_app.py     # Celery instance, broker config, queue topology
│   │   ├── models.py         # Job ORM model
│   │   ├── schemas.py        # JobResponse, JobProgressUpdate
│   │   ├── service.py        # JobService: create/update/query job records
│   │   └── tasks/
│   │       ├── media.py      # process_video, process_video_hls Celery tasks
│   │       └── pipeline.py   # Full dubbing pipeline + AI stage stubs
│   │
│   ├── shared/               # Cross-cutting infrastructure
│   │   ├── middleware.py     # ExceptionLoggingMiddleware (request/response log)
│   │   ├── logging.py        # setup_logging(): rotating file + console handler
│   │   ├── utils.py          # Misc helpers
│   │   └── security.py       # (reserved for CORS, rate limit helpers)
│   │
│   └── api/                  # Future: versioned API namespace (v2, etc.)
│
├── alembic/                  # Database migrations
│   └── versions/             # One file per schema change
│
├── tests/
│   ├── test_core_crud.py
│   └── test_user_crud.py
│
├── Dockerfile
├── entrypoint.sh
└── pyproject.toml + uv.lock
```

### Layering Rules

Each module follows a strict **4-layer stack**. Calls only flow downward:

```
Router  →  Service  →  Repository  →  Database (SQLAlchemy)
  ↓           ↓
Schema      Model
(Pydantic)  (ORM)
```

| Layer | Responsibility | May import |
|---|---|---|
| **Router** | HTTP: parse request, call service, return response | Service, Schema, Auth deps |
| **Service** | Business logic, orchestration, domain rules | Repository, Schema, other Services |
| **Repository** | Data access only — no business logic | ORM Model, AsyncSession |
| **Model** | SQLAlchemy table definition | `db.Base`, Enums |
| **Schema** | Pydantic I/O contracts | Enums, standard types |

> **Rule:** Routers never touch the database directly. Services never construct HTTP responses. Repositories never raise HTTP exceptions (they raise domain exceptions or return `None`).

### Generic Repository Pattern

`BaseRepository[T, CreateSchema, UpdateSchema]` in [app/core/repository.py](../backend/app/core/repository.py) provides reusable CRUD:

```python
class BaseRepository(Generic[T, CreateSchemaType, UpdateSchemaType]):
    async def create(obj_in)  → T
    async def get_by_id(id)   → Optional[T]
    async def get_all(skip, limit) → List[T]
    async def update(id, obj_in)   → T
    async def delete(id)           → bool
    async def count()              → int
```

Domain repositories extend this with query-specific methods:

```python
class UserRepository(BaseRepository):
    async def get_by_username(username) → Optional[User]
    async def get_by_email(email)       → Optional[User]
    async def username_exists(username) → bool
    async def email_exists(email)       → bool
```

### Dependency Injection Chain

FastAPI's `Depends()` is used to wire the full call chain per-request:

```
Request
  └─ Depends(get_db)               → AsyncSession
       └─ Depends(get_auth_service) → AuthService(UserRepository(db))
            └─ Depends(get_current_user) → User (from JWT)
                 └─ Depends(get_user_service) → UserService(repo, auth_service)
```

Workers (Celery) create their own `AsyncSessionLocal()` context per task — they do **not** use `Depends()`.

---

## 5. Database Schema

### Entity Relationship Overview

```
roles ──< users >─── user_subscriptions >─── subscription_plans
                │
                └─── user_subscriptions >─── payments
                │
                └─── videos >─── jobs
```

### Tables

#### `roles`
| Column | Type | Notes |
|---|---|---|
| `role_id` | INTEGER PK | Auto-increment |
| `name` | VARCHAR(100) | Unique — `admin`, `user`, `moderator` |
| `description` | TEXT | Optional |
| `is_active` | BOOLEAN | Soft-disable a role |
| `created_at` / `updated_at` | DATETIME | Auditing |

#### `users`
| Column | Type | Notes |
|---|---|---|
| `user_id` | INTEGER PK | Auto-increment |
| `username` | VARCHAR(255) | Unique, lowercased, alphanumeric + `_-` |
| `email` | VARCHAR(255) | Unique, validated with `email-validator` |
| `password` | VARCHAR(255) | bcrypt hash |
| `first_name` / `last_name` | VARCHAR(255) | Optional |
| `preferred_language` | ENUM(`en`, `ar`) | Drives UI language |
| `avatar_url` | VARCHAR(255) | Optional profile image |
| `role_id` | INTEGER FK → roles | `SET NULL` on delete |
| `is_active` | BOOLEAN | Account soft-delete / ban |
| `last_login` / `created_at` / `updated_at` | DATETIME | Auditing |

#### `subscription_plans`
| Column | Type | Notes |
|---|---|---|
| `plan_id` | INTEGER PK | |
| `name` | VARCHAR(100) | Unique (`free`, `pro`, `enterprise`) |
| `price` | NUMERIC(10,2) | Monthly price |
| `is_active` | BOOLEAN | |

#### `user_subscriptions`
| Column | Type | Notes |
|---|---|---|
| `subscription_id` | INTEGER PK | |
| `user_id` | FK → users | |
| `plan_id` | FK → subscription_plans | |
| `status` | ENUM | `active`, `expired`, `cancelled`, `past_due`, `trialing`, `unpaid` |
| `start_date` / `end_date` | DATETIME | Subscription window |
| `auto_renew` | BOOLEAN | |

#### `payments`
| Column | Type | Notes |
|---|---|---|
| `payment_id` | INTEGER PK | |
| `subscription_id` | FK → user_subscriptions | |
| `amount` | NUMERIC(10,2) | |
| `currency` | ENUM | `USD`, `EGP`, `EUR` |
| `payment_method` | ENUM | `card`, `wallet`, `bank_transfer` |
| `payment_gateway` | ENUM | `stripe`, `paymob`, `paypal` |
| `status` | ENUM | `paid`, `pending`, `failed`, `refunded`, `cancelled` |
| `transaction_id` | VARCHAR(255) | Unique — gateway reference |

#### `videos`
| Column | Type | Notes |
|---|---|---|
| `id` | VARCHAR(36) PK | UUID v4 |
| `user_id` | FK → users | Owner |
| `title` | VARCHAR(255) | |
| `original_filename` | VARCHAR(255) | As uploaded |
| `file_path` | VARCHAR(500) | Storage key (FS path or S3 object key) |
| `audio_path` | VARCHAR(500) | Extracted audio key |
| `thumbnail_path` | VARCHAR(500) | Generated thumbnail key |
| `status` | ENUM | `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED` |
| `media_type` | ENUM | `VIDEO`, `AUDIO`, `TEXT` |
| `duration` / `width` / `height` | FLOAT / INTEGER | From FFprobe |
| `size_bytes` | BIGINT | |
| `format` / `codec` / `frame_rate` | VARCHAR | From FFprobe |
| `error_message` | TEXT | Populated on failure |

#### `jobs`
| Column | Type | Notes |
|---|---|---|
| `id` | VARCHAR(36) PK | UUID v4 |
| `video_id` | FK → videos | The video being processed |
| `user_id` | FK → users | Who triggered the job |
| `job_type` | ENUM | See Job Types below |
| `status` | ENUM | `QUEUED`, `PROCESSING`, `COMPLETED`, `FAILED`, `RETRYING`, `CANCELLED` |
| `progress` | FLOAT | 0–100, updated by workers during execution |
| `celery_task_id` | VARCHAR(255) | Celery AsyncResult ID for revocation |
| `parent_job_id` | FK → jobs (self) | For pipeline child jobs |
| `input_data` | JSON | Flexible payload (file keys, params) |
| `output_data` | JSON | Results (output keys, metadata) |
| `error_message` | TEXT | Last error from worker |
| `retry_count` / `max_retries` | INTEGER | Current vs. allowed retries |
| `created_at` / `updated_at` / `started_at` / `completed_at` | DATETIME | Full timing history |

**Job Types:**

| `job_type` | Queue | Description |
|---|---|---|
| `VIDEO_PROCESS` | `media` | Extract metadata, audio, thumbnail |
| `VIDEO_HLS` | `media` | Generate HLS stream + above |
| `STT_TRANSCRIBE` | `ai_stt` | Whisper speech-to-text |
| `NMT_TRANSLATE` | `ai_nmt` | NLLB-200 + RAG translation |
| `TTS_SYNTHESIZE` | `ai_tts` | MMS Arabic voice synthesis |
| `DUBBING_MERGE` | `ai_tts` | FFmpeg merge dubbed audio |
| `FULL_DUBBING_PIPELINE` | `pipeline` | Orchestrates all 4 AI stages |

### Migrations

Alembic is used for all schema changes. Never modify the database manually.

```bash
# Generate a new migration from model changes
alembic revision --autogenerate -m "describe the change"

# Apply all pending migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

Migration files live in [alembic/versions/](../backend/alembic/versions/). Each file has an `upgrade()` and `downgrade()` function. Migration history:

| Revision | Description |
|---|---|
| `cb61867109a6` | Initial schema: users, roles, subscriptions, payments |
| `8ff75032c048` | Add `is_active` to users |
| `a1b2c3d4e5f6` | Add `jobs` table |

---

## 6. Authentication & Security

### JWT Token Pair Strategy

The app issues **two tokens** on login:

| Token | TTL | Storage | Purpose |
|---|---|---|---|
| `access_token` | 15 minutes | `localStorage` or `sessionStorage` | Sent in every API request |
| `refresh_token` | 7 days | same as access | Silently renews expired access tokens |

Storage is chosen at login: `localStorage` if "Remember Me" is checked, `sessionStorage` otherwise.

### Token Flow

```
Client                             Server
  │                                  │
  ├── POST /api/login ──────────────► │
  │   { username, password }         │
  │◄─ { access_token, refresh_token }│
  │                                  │
  ├── GET /api/me ──────────────────► │  Authorization: Bearer <access_token>
  │◄─ { user data } ─────────────────│
  │                                  │
  │  (access_token expires)          │
  │                                  │
  ├── POST /api/refresh ────────────► │  { refresh_token }
  │◄─ { new access_token } ──────────│
```

The frontend intercepts every `401` response and **automatically retries** with a refreshed token (single-flight, no duplicate refresh calls) using the `refreshAccessToken` function in [frontend/src/services/api.js](../frontend/src/services/api.js).

### Password Security

Passwords are hashed with **bcrypt** (cost factor = default 12) via `passlib`. The plain-text password never leaves the service layer.

```python
# Hashing (on signup)
AuthService.get_password_hash(plain_password) → bcrypt_hash

# Verification (on login)
AuthService.verify_password(plain, hashed)    → bool
```

### Rate Limiting

`slowapi` (a FastAPI port of Flask-Limiter) is applied per-IP using `get_remote_address`. The limiter instance is a singleton in [app/core/rate_limiter.py](../backend/app/core/rate_limiter.py) and decorates sensitive endpoints (login, signup). A `429 Too Many Requests` response is returned on breach.

### CORS

`CORSMiddleware` is configured in `main.py` to allow the frontend origin. In production, restrict `allow_origins` to the specific domain.

---

## 7. Async Job Processing

### Why Celery + Redis

All heavy processing (FFmpeg, Whisper, NLLB, MMS) runs **outside the API process** in dedicated Celery workers. The API server only creates a job record and dispatches the task — it never blocks.

Redis was chosen as the broker because:
- Zero configuration, single binary
- Doubles as cache and pub/sub (reusable in the stack)
- Sufficient for all expected throughput
- Easy to migrate to RabbitMQ later if advanced AMQP routing is needed (task code is unchanged — only broker URL changes)

### Queue Topology

```
                     ┌──────────────────────────────┐
                     │            Redis              │
                     │                               │
                     │  Queue: media                 │
                     │  Queue: ai_stt                │
                     │  Queue: ai_nmt                │
                     │  Queue: ai_tts                │
                     │  Queue: pipeline              │
                     │  Queue: default               │
                     └──────────┬───────────────────┘
                                │
           ┌────────────────────┴────────────────────┐
           │                                         │
  ┌────────▼────────┐                     ┌──────────▼──────────┐
  │  worker-media   │                     │    worker-ai        │
  │  queues:        │                     │    queues:          │
  │  media, default │                     │    ai_stt, ai_nmt   │
  │  concurrency: 2 │                     │    ai_tts, pipeline │
  │  FFmpeg tasks   │                     │    concurrency: 1   │
  └─────────────────┘                     │    GPU tasks        │
                                          └─────────────────────┘
```

`concurrency=1` on `worker-ai` is intentional — GPU-bound models (Whisper, MMS) cannot safely run in parallel on a single device. Scale by adding more `worker-ai` containers.

### Celery Configuration Highlights

Defined in [app/jobs/celery_app.py](../backend/app/jobs/celery_app.py):

| Setting | Value | Why |
|---|---|---|
| `task_acks_late=True` | True | Task only acknowledged after completion. Worker crash → Redis redelivers |
| `task_reject_on_worker_lost=True` | True | Pair with `acks_late` to ensure redelivery |
| `worker_prefetch_multiplier=1` | 1 | One task at a time — no hoarding by one worker |
| `worker_max_tasks_per_child=50` | 50 | Restart worker process every 50 tasks to prevent memory leaks |
| `task_soft_time_limit=600` | 10 min | Raises `SoftTimeLimitExceeded` — allows graceful cleanup |
| `task_time_limit=900` | 15 min | Hard kill if soft limit handler doesn't stop it |
| `retry_backoff=True` | True | Exponential backoff: 1s → 2s → 4s → 8s… |
| `retry_backoff_max=300` | 5 min | Cap between retries |
| `retry_jitter=True` | True | Randomizes backoff to prevent thundering herd |

### Job State Machine

```
              ┌──────────┐
              │  QUEUED   │  ← Created by API on upload
              └─────┬─────┘
                    │ Worker picks up task
              ┌─────▼─────┐
         ┌───►│PROCESSING │
         │    └─────┬─────┘
         │          │
         │    ┌─────┴──────┐
         │    │             │
         │  Success       Error
         │    │             │
         │    ▼             ▼
         │ ┌──────────┐  ┌──────────┐
         │ │COMPLETED │  │ RETRYING │──┐ retry_count < max_retries
         │ └──────────┘  └──────────┘  │
         │                   ▲         │ (exponential backoff)
         │                   └─────────┘
         │                   │
         │            retry exhausted
         │                   │
         │             ┌─────▼─────┐
         │             │  FAILED   │
         │             └───────────┘
         │
         │ POST /api/jobs/{id}/cancel
         │             ┌──────────────┐
         └────────────►│  CANCELLED   │
                       └──────────────┘
```

### Job Lifecycle in Code

```python
# 1. API: create DB record and dispatch
job = await job_service.create_job(video_id, user_id, JobType.VIDEO_PROCESS)
result = process_video.delay(job_id=job.id, video_id=..., file_path_key=...)
await job_service.update_job_celery_id(job.id, result.id)
# → returns immediately to client

# 2. Worker: run async code inside sync Celery task
@celery_app.task(bind=True, base=BaseJobTask)
def process_video(self, job_id, video_id, file_path_key):
    run_async(_process_video_async(self, job_id, video_id, file_path_key))

# 3. Worker: update progress as stages complete
job.progress = 30.0; await db.commit()   # metadata done
job.progress = 60.0; await db.commit()   # audio extracted
job.progress = 80.0; await db.commit()   # thumbnail done
job.status = JobStatus.COMPLETED; job.progress = 100.0

# 4. Frontend: poll for status
GET /api/jobs/{job_id}
→ { "status": "PROCESSING", "progress": 60.0 }
→ { "status": "COMPLETED",  "progress": 100.0 }
```

### AI Dubbing Pipeline (Celery Chain)

When the full dubbing pipeline is triggered, child jobs are created for each stage and dispatched as a **Celery chain** — each stage's output is passed as input to the next:

```python
pipeline = chain(
    stt_transcribe.s(stt_job_id, video_id, audio_path),
    nmt_translate.s(nmt_job_id, video_id),    # receives STT result dict
    tts_synthesize.s(tts_job_id, video_id),   # receives NMT result dict
    dubbing_merge.s(merge_job_id, video_id),  # receives TTS result dict
)
pipeline.apply_async()
```

The frontend can track the parent job (overall progress) or each child job independently.

---

## 8. Frontend Architecture

### Directory Layout

```
frontend/src/
├── main.jsx              # React DOM root, StrictMode
├── App.jsx               # Router tree, context providers
├── index.css             # Tailwind base imports
│
├── pages/                # One directory per route
│   ├── Home/
│   ├── Login/
│   ├── Register/
│   ├── Dashboard/
│   ├── Profile/
│   ├── History/
│   ├── About/
│   └── NotFound/
│
├── components/
│   ├── common/           # ProtectedRoute, PublicRoute, shared UI
│   ├── home/             # Landing page sections
│   └── layout/           # Navbar, Sidebar, Footer
│
├── features/             # Complex feature slices (co-located logic)
│   ├── auth/             # Login form, Register form, auth guards
│   └── dashboard/        # Video list, upload, job progress panel
│
├── hooks/                # Reusable React hooks
│   ├── useAuth.js        # Session state: user, login(), logout()
│   ├── useFetch.js       # Generic data fetching with loading/error state
│   └── useTranslation.js # i18n hook powered by LanguageContext
│
├── contexts/
│   ├── ThemeContext.jsx   # Dark / light theme (CSS class on <html>)
│   └── LanguageContext.jsx # `en` / `ar` with RTL support
│
├── services/
│   ├── api.js            # All HTTP calls, token refresh interceptor
│   └── jobService.js     # Job polling, cancel, status queries
│
├── store/
│   ├── store.js          # Zustand store root
│   └── slices/           # Feature slices (authSlice, etc.)
│
├── styles/
│   └── global.css        # Global resets, custom Tailwind utilities
│
├── utils/                # Pure helpers (formatters, validators)
└── test/                 # Shared test utilities, MSW handlers
```

### Routing & Auth Guards

```
/              → Home         (public)
/about         → About        (public)
/login         → Login        (PublicRoute — redirects if already logged in)
/register      → Register     (PublicRoute — redirects if already logged in)
/dashboard     → Dashboard    (ProtectedRoute — redirects to /login if no token)
/profile       → Profile      (ProtectedRoute)
/history       → History      (ProtectedRoute)
/*             → NotFound
```

`ProtectedRoute` reads from `useAuth()` and redirects to `/login` if `user` is `null`. `PublicRoute` redirects to `/dashboard` if already authenticated.

### State Management

**Zustand** is used for global state. Local component state (`useState`) is used for forms and UI-only state.

```
Zustand Store
└── authSlice
    ├── user          { user_id, username, email, ... }
    ├── isAuthenticated
    ├── login(user, tokens, rememberMe)
    └── logout()
```

Auth state is **initialized synchronously** from `localStorage`/`sessionStorage` on page load — no flash of unauthenticated state.

### API Service Layer

All network calls go through [frontend/src/services/api.js](../frontend/src/services/api.js), which provides:

- **Base URL** from `VITE_API_BASE_URL` env var (defaults to `http://localhost:8000/api`)
- **Automatic JWT injection** via `Authorization: Bearer <token>` header
- **Silent token refresh** on `401` — single-flight (no duplicate refresh calls)
- **Automatic logout** when refresh token is also expired
- **Cross-tab sync** via `window.addEventListener('storage', ...)` in `useAuth`

### Internationalization (i18n)

`LanguageContext` exposes `{ language, setLanguage, t }`. The `t(key)` function looks up a translation dictionary for `en` or `ar`. When Arabic is active, `dir="rtl"` is set on `<html>` for full RTL layout support.

---

## 9. API Design Conventions

### Base URL

All API routes are prefixed with `/api`.

### Endpoint Naming

| Method | Path | Action |
|---|---|---|
| `POST` | `/api/signup` | Register |
| `POST` | `/api/login` | Login, returns token pair |
| `POST` | `/api/logout` | Logout (clears refresh token) |
| `POST` | `/api/refresh` | Exchange refresh → new access token |
| `GET` | `/api/me` | Current user profile |
| `PATCH` | `/api/me` | Update profile |
| `POST` | `/api/videos/upload` | Upload video (returns immediately) |
| `GET` | `/api/videos/` | List user's videos |
| `GET` | `/api/videos/{id}` | Get video detail |
| `DELETE` | `/api/videos/{id}` | Delete video |
| `GET` | `/api/jobs/{id}` | Get job status + progress |
| `GET` | `/api/jobs/video/{video_id}` | All jobs for a video |
| `GET` | `/api/jobs/` | List user's jobs |
| `POST` | `/api/jobs/{id}/cancel` | Cancel a queued/processing job |

### Response Format

**Success:**
```json
{
  "id": "uuid",
  "field": "value",
  ...
}
```

**Error:**
```json
{
  "detail": "Human-readable error message"
}
```

**Validation error (422):**
```json
{
  "detail": [
    { "loc": ["body", "email"], "msg": "value is not a valid email address", "type": "value_error" }
  ]
}
```

### Pagination

List endpoints accept `skip` and `limit` query parameters. Default: `skip=0`, `limit=10`.

### Authentication Header

```
Authorization: Bearer <access_token>
```

Protected endpoints use `Depends(get_current_user)` which extracts and verifies the JWT.

---

## 10. Cross-Cutting Concerns

### Logging

`setup_logging()` in [app/shared/logging.py](../backend/app/shared/logging.py) configures:

- **Rotating file handler**: `logs/app.log`, max 10 MB, 5 backups
- **Console handler**: colored output in development
- **Custom `SUCCESS` level (25)**: between `DEBUG` and `WARNING` — logs `2xx` responses without noise
- **JSON format option**: set `LOG_JSON_FORMAT=true` for structured log shipping (e.g., to Elasticsearch)

`ExceptionLoggingMiddleware` in [app/shared/middleware.py](../backend/app/shared/middleware.py) wraps every request and logs:
- `SUCCESS (25)` for `2xx` responses with timing
- `WARNING` for `4xx` client errors
- `ERROR` for `5xx` server errors with full traceback

Celery tasks use `get_task_logger(__name__)` which routes into the same logging system.

### Error Handling

Error handling is layered:

```
Request
  ↓
ExceptionLoggingMiddleware     ← logs everything, re-raises
  ↓
@app.exception_handler(Exception)  ← catches unhandled exceptions → 500
  ↓
FastAPI built-in RequestValidationError handler  → 422
  ↓
Domain exceptions (UserAlreadyExists, etc.) → raised in Service, caught in Router → 4xx
```

Workers use `BaseJobTask.on_failure()` and `on_retry()` hooks to update the job DB record whenever Celery's retry/failure lifecycle fires.

### Configuration Management

All configuration is in `Settings(BaseSettings)` in [app/config.py](../backend/app/config.py). Values come from:
1. Environment variables (highest priority)
2. `.env` file
3. Hardcoded defaults (for development only)

Never hardcode secrets. Use the `.env.example` as the canonical list of required variables.

### Testing Strategy

| Layer | Tool | Location |
|---|---|---|
| Backend unit/integration | `pytest + pytest-asyncio` | `backend/tests/` |
| Backend coverage | `pytest-cov` | Run: `pytest --cov=app` |
| Frontend component | `Vitest + Testing Library` | co-located `*.test.jsx` |
| Frontend hooks | `Vitest` | co-located `*.test.js` |
| Frontend coverage | `@vitest/coverage-v8` | Run: `npm run test:coverage` |

---

## 11. Deployment & Infrastructure

### Docker Services

```yaml
services:
  backend:      # FastAPI (uvicorn)       → :8000
  frontend:     # Vite / Nginx            → :5173
  db:           # PostgreSQL 16           → :5432
  redis:        # Redis 7 alpine          → :6379
  worker-media: # Celery (media queue)
  worker-ai:    # Celery (ai_* queues)
  flower:       # Celery dashboard        → :5555
```

### Worker Startup Commands

```bash
# Media worker
celery -A app.jobs.celery_app worker \
  --queues=media,default \
  --concurrency=2 \
  --hostname=worker-media@%h \
  --loglevel=info

# AI worker
celery -A app.jobs.celery_app worker \
  --queues=ai_stt,ai_nmt,ai_tts,pipeline \
  --concurrency=1 \
  --hostname=worker-ai@%h \
  --loglevel=info
```

### Environment Variables

See [backend/.env.example](../backend/.env.example) for the full list. Critical variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db` |
| `SECRET_KEY` | Long random string for JWT signing |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `ALGORITHM` | JWT algorithm — `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Default: `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Default: `7` |

### Running Locally

```bash
# Start infrastructure
docker compose up redis db -d

# Backend
cd backend
python -m uvicorn app.main:app --reload --port 8000

# Celery media worker
celery -A app.jobs.celery_app worker --queues=media,default --loglevel=info

# Frontend
cd frontend
npm run dev

# Flower monitoring
celery -A app.jobs.celery_app flower --port=5555
```

---

## 12. Future Roadmap

### AI Module Integration

Each AI module (`stt`, `nmt`, `tts`) will be added as a new top-level module following the same 4-layer structure:

```
app/
├── stt/          # Whisper: models, schema, service, router, Celery task
├── nmt/          # NLLB-200 + RAG: models, schema, service, router, Celery task
└── tts/          # MMS: models, schema, service, router, Celery task
```

The Celery task stubs in [app/jobs/tasks/pipeline.py](../backend/app/jobs/tasks/pipeline.py) are the integration points — implement the `async` bodies when each module is ready.

### Microservices Migration Path

The modular monolith is deliberately structured for extraction. When a module needs independent scaling or deployment:

1. Move the module directory to a new repo
2. Replace the in-process function call with an HTTP client or message queue publish
3. The `jobs` table and Redis queue already act as the async boundary — no redesign needed

The clearest extraction candidates are:
- `worker-ai` → standalone service (GPU-intensive, different hardware)
- `media` → standalone service (high I/O, storage-intensive)

### WebSocket Job Updates

The current polling model (`GET /api/jobs/{id}`) is straightforward and sufficient for now. When lower latency is needed, add a WebSocket endpoint:

```
WS /api/ws/jobs/{user_id}
← { "job_id": "...", "status": "PROCESSING", "progress": 60.0 }
```

Workers would publish progress updates to a Redis pub/sub channel; the WebSocket handler subscribes and forwards to the client.
