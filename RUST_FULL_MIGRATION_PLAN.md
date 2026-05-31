# Rust Migration Plan — Media & Storage Ownership

Goal: centralize all media processing and object-storage ownership in the Rust `media-service` while keeping the Python backend as the orchestrator during migration (optionally fully migrate later).

**Scope**
- Move media processing (probe, extract, thumbnail, HLS, mux/dub) into Rust.
- Move object storage ownership (upload/download/presign/delete) into Rust.
- Provide stable, well-documented JSON endpoints from Rust that match existing Python expectations.
- Keep Python as orchestrator until parity is proven; then progressively deprecate Python media helpers.

**Current status (snapshot)**
- Inventory of Python media/ffmpeg callsites: completed.
- `backend/app/ffmpeg_service.py`: replaced with a non-breaking shim that forwards work to `media-service` (implemented).
- Rust `media-service` already implements core ffmpeg endpoints (`/ffmpeg/metadata`, `/ffmpeg/extract-audio`, `/ffmpeg/thumbnail`, `/ffmpeg/hls`, `/ffmpeg/dub`).
- TODO mapping in repo updated; switching callers marked in-progress.

Migration steps (safe, incremental)

1) Stabilize Rust endpoints (complete parity)
	- Verify Rust endpoints return the same JSON shapes the Python callers expect.
	- Ensure `/storage/presign` supports both GET and PUT presigns with the same semantics (MinIO parity).
	- Add/adjust missing Rust endpoints for any gap discovered during tests.

2) Provide a non-breaking shim (done)
	- `backend/app/ffmpeg_service.py` now forwards to Rust. This preserves runtime behavior while allowing iterative testing.

3) Switch Python callers to use explicit media-service client paths (incremental)
	- Replace direct uses of the local Python ffmpeg helpers with either the shim or direct calls to `MediaServiceClient`.
	- Prioritize callers used by production flows: job processing, dubbing merge, upload handling, and the frontend presign flow.

4) Harden storage parity
	- Implement/verify PUT presign parity in Rust (MinIO differences are common; replicate the aioboto3 behavior if necessary).
	- Confirm `presign PUT` + direct PUT by clients works end-to-end.

5) Move dubbing/merge into Rust
	- Implement `/ffmpeg/dub` behavior in Rust to match existing Python merging/muxing semantics.
	- Add e2e parity tests using sample assets.

6) Remove duplicate Python implementations
	- After parity and e2e validation, deprecate and remove `backend/app/ffmpeg_service.py` and `backend/app/object_storage.py`.
	- Replace any remaining direct subprocess ffmpeg calls.

7) Tests and verification
	- Add Rust unit tests for parsing, duration, and ffmpeg output parsing.
	- Add Rust integration tests for each endpoint (metadata, extract, thumbnail, hls, dub).
	- Add parity tests comparing Python outputs (before removal) and Rust outputs for representative files.

Rollout strategy
- Stage 1 (dev/staging): enable shim and run parity tests against the Rust service with MinIO.
- Stage 2 (canary): switch a small subset of jobs to call Rust endpoints directly for production-like traffic.
- Stage 3 (full): after successful canary and test pass, switch all callers and deprecate Python media helpers.

Risks and mitigations
- Presign differences (MinIO vs AWS): test both MinIO and AWS S3; add a Python fallback only if strictly necessary.
- JSON/shape mismatches: keep shim behavior tolerant (ignore extra fields, fill missing defaults) and log mismatches.
- Performance regressions: benchmark rust ffmpeg calls and ensure process concurrency is tuned (Tokio worker sizing, ffmpeg concurrency limits).

Next immediate actions (what I will do now)
- Update `backend/app/dubbing/service.py` callers to use the shim (`backend/app/ffmpeg_service.py`) where direct ffmpeg calls are present (I can implement this change next).
- Add a small smoke test script that exercises `get_metadata`, `extract_audio`, `generate_thumbnail`, and `generate_hls` via the shim against a local MinIO+media-service in dev.
- Work on Rust PUT presign parity if tests show failures.

Mapping to repo TODOs
- Inventory: done.
- Implement missing Rust ffmpeg endpoints: in-progress (validate parity gaps).
- Implement Rust S3/MinIO PUT presign parity: not-started (next if presign failures appear).
- Switch Python callers to Rust media endpoints: in-progress (I'll start with dubbing).

Commands to run locally (dev) — quick smoke
```bash
# run Python unit tests (dev env)
cd backend
uv run pytest tests/ -q

# run frontend checks (if you want to verify presign flows)
cd frontend
npm ci && npm run test -- --run
```

Definition of Done
- Rust `media-service` is the single runtime owning media processing and storage for all production paths.
- Python no longer shells out to ffmpeg or directly manipulates media files in production paths.
- All media endpoints have unit and integration tests and parity tests validated against representative sample assets.

---
Plan maintained by the migration working set; update this file as endpoints, tests, or status change.

