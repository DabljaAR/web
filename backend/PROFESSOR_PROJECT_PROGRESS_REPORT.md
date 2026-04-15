# DabljaAR Backend Progress Report

**Project:** DabljaAR (Arabic AI Dubbing Platform)  
**Report Date:** 2026-04-12  
**Prepared For:** Professor Review  
**Name:** Moustafa Magdy 
**Id:** 2022170425

## 1. Executive Summary

I have completed the main backend foundations and core product features for DabljaAR.  
The implemented work includes:

- Full **user authentication and authorization flow**
- **User management** and profile/settings handling
- **Subscription and payment modules** (plans, subscriptions, payment records)
- End-to-end AI dubbing pipeline components: **STT, TTS, and dubbing merge**

The backend is now structured as a real production-oriented system with clear APIs, database models, and service layers.

## 2. Core Platform Features Completed

### 2.1 Authentication (AuthN)

I implemented a complete JWT-based authentication system:

- `POST /signup` for account creation
- `POST /login` for credential authentication
- `POST /auth/refresh` for token refresh with rotation

Technical implementation details:

- Password hashing with **bcrypt** (`passlib`)
- Access/refresh token generation using **JWT**
- Token type validation (`access` vs `refresh`)
- Expiration handling and invalid token handling
- Login/signup **rate limiting** to reduce brute-force risk
- Password policy validation (length, uppercase, lowercase, digit, bcrypt byte-limit safety)

### 2.2 Authorization (AuthZ)

I enforced authorization through protected route dependencies and scoped checks:

- Most user, subscription, and payment routes require authenticated user context via `get_current_user`
- Added explicit ownership protection (example: users can only change their own password; non-owner returns `403 Forbidden`)


In addition, the database model includes role linkage (`Role` ↔ `User`) to support role-based policy extension.

### 2.3 User and Account Management

I implemented user-domain features beyond login:

- User CRUD APIs (`/users`, `/users/{id}`, update, delete)
- Password change flow with old-password verification
- User preferences and notification settings persisted in DB:
  - `default_domain`, `translation_style`, `default_voice`
  - `notif_completed`, `notif_credits`, `notif_marketing`
- Avatar upload support with file-type and file-size validation
- Data cleanup on user deletion (including associated storage artifacts and related records)

## 3. Subscription and Payment Features Completed

### 3.1 Subscription Plans

I implemented full plan management:

- Create/read/update/delete subscription plans
- Plan metadata includes name, description, price, and activation status
- Pagination support on listing APIs

### 3.2 User Subscriptions

I implemented subscription lifecycle APIs:

- Subscribe users to plans
- Retrieve all subscriptions and current user subscriptions
- Update and delete subscriptions
- Track subscription status and renewal-related fields

### 3.3 Payments

I implemented payment record management with billing metadata:

- Payment CRUD endpoints
- Per-user payment listing (`/payments`)
- Payment model fields include:
  - amount, currency
  - payment method
  - payment gateway
  - payment status
  - unique transaction ID
- Repository/service logic supports subscription-linked payment retrieval and paid-payment filtering

## 4. AI Dubbing Pipeline Work Completed (Core Technical Scope)

### 4.1 STT (Speech-to-Text)

I implemented and stabilized Whisper-based STT:

- Async Celery STT task (`stt_transcribe`) bound to `ai_stt` queue
- Media retrieval from MinIO/S3 storage
- Segment-wise transcript generation with timestamps
- Job progress updates and lifecycle integration

### 4.2 TTS (Text-to-Speech)

I completed SILMA-TTS integration:

- Migrated from previous TTS stack to **SILMA-TTS**
- Updated configuration and runtime parameter handling
- Fixed silent-audio issues by correcting reference-audio resolution
- Integrated TTS synthesis tasks in asynchronous worker flow (`ai_tts`)

### 4.3 Dubbing Merge

I implemented merge service functionality to produce dubbed audio/video outputs:

- Segment validation and download workflow
- Timing mismatch handling using FFmpeg-based **time-stretching**
- Gap/silence handling and ordered timeline construction
- Audio concatenation and merged output generation
- Processing metadata generation for job/result tracking

## 5. System Architecture and Engineering Quality

I organized the backend using clear layers and patterns:

- FastAPI router + dependency injection architecture
- Service/repository separation for business logic and persistence
- SQLAlchemy models and typed schemas for strong API contracts
- Celery workers for AI/media asynchronous operations
- Persistent job tracking and status management in PostgreSQL

I also resolved multiple production-blocking issues during development (task dispatch mismatches, mapper registration issues, migration/schema problems, and worker stability concerns), improving reliability of the delivered core features.

## 6. Current Project State

From a backend perspective, the implemented scope already covers the main product backbone:

- Authentication and authorization
- User and account management
- Subscription and payment modules
- STT + TTS + dubbing merge pipeline components
- Async orchestration and persistent job tracking

This establishes a solid, functional base for continued feature polishing and performance optimization.

## 7. API Endpoint Index (Implemented)

### 7.1 Authentication and User APIs (`/api`)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/signup` | Register new user account |
| POST | `/api/login` | Authenticate user and return access/refresh tokens |
| POST | `/api/auth/refresh` | Refresh JWT token pair |
| GET | `/api/users` | List users (paginated) |
| GET | `/api/users/{user_id}` | Get user by ID |
| PUT | `/api/users/{user_id}` | Update user profile/settings |
| DELETE | `/api/users/{user_id}` | Delete user and related data |
| POST | `/api/upload/avatar` | Upload user avatar image |
| GET | `/api/health` | Core API health endpoint |

### 7.2 Subscription and Payment APIs (`/api`)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/subscription-plans` | Create subscription plan |
| GET | `/api/subscription-plans` | List subscription plans |
| GET | `/api/subscription-plans/{plan_id}` | Get plan details |
| PUT | `/api/subscription-plans/{plan_id}` | Update plan |
| DELETE | `/api/subscription-plans/{plan_id}` | Delete plan |
| POST | `/api/subscriptions` | Create user subscription |
| GET | `/api/subscriptions` | List subscriptions |
| GET | `/api/subscriptions/{subscription_id}` | Get subscription details |
| PUT | `/api/subscriptions/{subscription_id}` | Update subscription |
| DELETE | `/api/subscriptions/{subscription_id}` | Delete subscription |
| POST | `/api/payments` | Create payment record |
| GET | `/api/payments` | List all payments |
| GET | `/api/payments/{payment_id}` | Get payment details |
| PUT | `/api/payments/{payment_id}` | Update payment |
| DELETE | `/api/payments/{payment_id}` | Delete payment |



### 7.5 STT APIs (`/api/transcription`)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/transcription/transcribe` | Synchronous transcription |
| POST | `/api/transcription/transcribe-async` | Asynchronous transcription job submission |
| GET | `/api/transcription/jobs/{job_id}` | Poll STT async job |
| DELETE | `/api/transcription/jobs/{job_id}` | Cancel STT job |
| GET | `/api/transcription/health` | STT health check |
| GET | `/api/transcription/metrics` | STT performance metrics |
| GET | `/api/transcription/info` | STT service information |

### 7.6 TTS APIs

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/tts/synthesize` | Submit TTS synthesis job |
| GET | `/api/tts/status/{task_id}` | Get TTS Celery task status |
| GET | `/api/tts/jobs/{job_id}` | Get TTS job status from DB |
| GET | `/api/tts/health` | TTS health check |

### 7.7 Merge
| POST | `/api/full-pipeline` | Submit a full-pipline job |


