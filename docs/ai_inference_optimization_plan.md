# DabljaAR — AI Inference & Deployment Optimization Plan

> **Status:** Proposed
> **Scope:** `stt-service`, `nmt-service`, backend AI/TTS path, container & deployment setup
> **Goals:** (1) lighter images, (2) faster inference, (3) faster model download / cold start
> **Companion docs:** [architecture.md](architecture.md) · [microservices_lld.md](microservices_lld.md) · [deployment.md](deployment.md)

This is a **learning + execution** plan. Each item states the *root cause*, the *principle* behind the fix, and a *verification* step — but leaves the implementation to you. No code is changed by this document.

---

## How to read this plan

Issues are scored on two axes and grouped into execution phases:

- **Impact** — how much it moves one of the three goals (image size / inference latency / download time).
- **Effort** — rough implementation cost.

| Tier | Meaning |
|------|---------|
| **P0** | High impact, low effort — do first (quick wins) |
| **P1** | High impact, medium effort — core of the work |
| **P2** | Medium impact — schedule after P0/P1 |
| **P3** | Low impact / long-term / cleanup |

Legend for the goal each item serves: 🪶 lighter image · ⚡ faster inference · ⬇️ faster download/cold-start.

---

## Findings at a glance

| ID | Finding | Goal | Tier |
|----|---------|------|------|
| F1 | CPU services install the full CUDA build of `torch` | 🪶⬇️ | **P0** |
| F3 | No `.dockerignore` in `stt-service` / `nmt-service` | 🪶 | **P0** |
| F10 | NMT stage-3 "word-by-word" = one `generate()` per word; mis-enabled in dev compose | ⚡ | **P0** |
| F2 | `stt`/`nmt` Dockerfiles are single-stage; ship build toolchain | 🪶 | **P1** |
| F4 | Backend API image built with `INSTALL_AI=true` though API never infers | 🪶⬇️ | **P1** |
| F6 | Models downloaded at runtime, per-replica, no pre-bake/shared cache | ⬇️ | **P1** |
| F7 | S3 model download is single-threaded, file-by-file | ⬇️ | **P1** |
| F11 | No batched inference for NMT/TTS (per-segment `generate()`) | ⚡ | **P1** |
| F13 | NMT `num_beams=5` default (≈5× greedy cost) | ⚡ | **P1** |
| F15 | CPU inference for Whisper + SILMA in minimal prod | ⚡ | **P1** |
| F8 | No startup pre-warm for `stt`/`nmt` workers (first job pays load) | ⚡⬇️ | **P2** |
| F9 | Unpinned runtime third-party downloads (HF fallback, catt zips, silma auto-transcribe) | ⬇️ | **P2** |
| F12 | `ThreadPoolExecutor` fan-out gives no real model parallelism (GIL + tokenizer lock + 1 device) | ⚡ | **P2** |
| F14 | TTS `nfe_step=64` in prod (2× the usual 32) | ⚡ | **P2** |
| F17 | NLLB not quantized (no CTranslate2/int8 path like Whisper has) | ⚡🪶 | **P2** |
| F5 | Redundant deps (`databases`+`asyncpg`, `celery`+`pika`+`aio-pika`) | 🪶 | **P3** |
| F16 | STT `word_timestamps=True` always on | ⚡ | **P3** |

---

## Phase 0 — Quick wins (P0)

### F1 — CPU images install the CUDA build of `torch` 🪶⬇️

**Root cause.** `stt-service/requirements.txt` and `nmt-service/requirements.txt` pin `torch>=2.0.0` with **no `--index-url`**. The default PyPI `torch` wheel bundles the full NVIDIA CUDA runtime (cuDNN, cuBLAS, NCCL, …) — roughly **2.5–5 GB** of libraries that are useless on a CPU-only container. Both default Dockerfiles (`stt-service/Dockerfile`, `nmt-service/Dockerfile`) are CPU images, and the minimal prod worker runs `STT_DEVICE=cpu` / `SILMA_DEVICE=cpu`.

**Principle.** Match the wheel to the runtime. PyTorch ships a dedicated CPU index (`https://download.pytorch.org/whl/cpu`) whose wheels are ~200 MB instead of multi-GB. The GPU `Dockerfile.gpu` already does the right thing with `--index-url .../cu118` — mirror that idea for CPU.

**Direction (not a patch).** Install CPU torch from the CPU index in the CPU Dockerfiles; keep the CUDA index only in `*.gpu` images. Consider whether NMT (NLLB-600M) even needs torch's GPU path at all in your default deployment.

**Verify.**
```bash
docker images | grep -E 'stt|nmt'           # compare before/after
docker run --rm <img> python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```
Expect a multi-GB drop per image and `cuda=False` on CPU builds.

> **Question to reason about:** the GPU Dockerfile installs torch *before* `requirements.txt` so pip sees the constraint already satisfied. If you add a CPU index install, where in the Dockerfile must it go so pip doesn't "upgrade" you back to the CUDA wheel from PyPI?

---

### F3 — Missing `.dockerignore` in the AI services 🪶

**Root cause.** Neither `stt-service/` nor `nmt-service/` has a `.dockerignore`, yet both Dockerfiles do `COPY . .`. That copies `.pytest_cache/`, `tests/`, local `.env`, `__pycache__`, and any stray virtualenv into the image — bloat plus a secrets-leak risk.

**Principle.** The build context should contain only what runs in production. `backend/` and `frontend/` already have `.dockerignore` — the AI services were missed.

**Direction.** Add a `.dockerignore` to each AI service excluding caches, tests, envs, and VCS noise. Use the existing `backend/.dockerignore` as a template.

**Verify.**
```bash
docker build -t stt-test ./stt-service
docker run --rm stt-test sh -c "ls -la /app && du -sh /app"
```
No `.pytest_cache`, no `tests/`, smaller `/app`.

---

### F10 — NMT "word-by-word" stage and the mis-set fallback flag ⚡

**Root cause.** `NLLBTranslatorWrapper._translate_word_by_word()` calls `model.generate()` **once per word**. For a sentence of *N* words that's *N* sequential decoder passes instead of one — easily 10–30× slower per segment. It only runs when `NMT_FALLBACK_MODE != "stage2_only"`. But `docker-compose.yml` sets `NMT_FALLBACK_MODE: false` — and `false` is not `"stage2_only"`, so the expensive stage-3 path is **silently enabled in dev**. (Minimal prod correctly sets `stage2_only`.)

**Principle.** Hot paths must be opt-in and explicit. A "quality fallback" that costs an order of magnitude in latency should never be the accidental default, and config values should be validated.

**Direction.** Make `stage2_only` the safe default everywhere; fix the dev compose value; treat any unknown `NMT_FALLBACK_MODE` as `stage2_only` (fail safe, not fail slow). Separately, reconsider whether word-by-word is the right tool at all vs. constrained decoding or a better target-language forcing.

**Verify.** Translate a 40-segment sample with timing logs; confirm stage-3 logs do **not** appear and per-segment time drops.

> **Question:** the code does `if fallback_mode == "stage2_only": return`. What's the smallest change that makes *unknown* values behave like `stage2_only` instead of falling through to the slow path?

---

## Phase 1 — Core optimizations (P1)

### F2 — Single-stage AI Dockerfiles ship the build toolchain 🪶

**Root cause.** `stt`/`nmt` Dockerfiles `apt-get install gcc libc6-dev` (needed to *build* some wheels) and never remove them — they remain in the runtime image. `backend/Dockerfile.prod` already demonstrates the fix: a `builder` stage compiles/installs, then a slim final stage copies only the installed artifacts.

**Principle.** Multi-stage builds — compile in a fat stage, run in a thin one. Build-time deps never reach production.

**Direction.** Convert the AI Dockerfiles to multi-stage (builder installs into a venv/prefix; final stage copies it + only runtime apt packages like `ffmpeg`, `curl`). Mirror `backend/Dockerfile.prod`.

**Verify.** `docker history <img>` shows no `gcc`; image size drops; service still starts and passes `/readiness`.

---

### F4 — Backend API image carries the full AI stack 🪶⬇️

**Root cause.** `docker-compose.prod.minimal.yml` builds **backend**, **celery-worker-ai**, and reuses the same `Dockerfile.prod` with `INSTALL_AI=true` for the API. The FastAPI API only *creates jobs and serves status* — inference happens in workers/microservices. So `torch`, `transformers`, `silma-tts`, `faster-whisper` (multiple GB) are baked into the API image and its memory footprint for no functional reason.

**Principle.** Separate the inference runtime from the request-serving runtime. The API should be lightweight and fast to start/scale; heavy ML deps belong only where inference runs.

**Direction.** Build the API with `INSTALL_AI=false`; keep `INSTALL_AI=true` only for the worker (and, in the target architecture, only the AI microservices need ML deps at all). Confirm the API has no import-time dependency on `torch`/`transformers`.

**Verify.** API image size ≈ core-only; `docker run <api-img> python -c "import torch"` should fail (proving it's gone) while the app still boots.

> **Question:** the API and worker currently share one Dockerfile. Is the cleanest separation a build-arg difference (as today) or two images? What does the migration doc say the end state should be?

---

### F6 — Runtime model download, per-replica, no pre-bake or shared cache ⬇️

**Root cause.** Models resolve at *first inference* via local volume → S3 → HF Hub. Each replica has its own `ai_model_cache`/`nmt_model_cache` volume, so every new replica re-downloads gigabytes. There's no image pre-bake and (per the migration doc) the shared **ReadWriteMany** cache is only a future K8s idea.

**Principle.** Decide *when* the model arrives and *who* shares it:
- **Bake into the image** → zero cold-download, but bigger image / rebuild on model change.
- **Init container / pre-pull** → image stays slim, download happens once before traffic.
- **Shared RWX volume (PVC)** → replicas mount one cache; only the first download pays.

**Direction.** Short term: pre-pull into the named volume on deploy (one-time) rather than lazily on first request. Medium term: a shared read-only model cache mounted by all replicas. Long term (K8s): the RWX PVC from `microservices_migration.md` §13. Choose per environment; document the trade-off.

**Verify.** Start a second replica and confirm it does **not** re-download (log shows `local_disk_hit`). Measure first-job latency before/after.

---

### F7 — S3 model download is single-threaded, file-by-file ⬇️

**Root cause.** Both `_download_model_from_s3` (STT) and `_s3_download_fn` (NMT) loop over keys calling `client.download_file` one at a time. A sharded model (many `.safetensors` parts) downloads serially, leaving bandwidth idle.

**Principle.** Object-storage throughput comes from concurrency. boto3's `TransferConfig` (multipart + threads) or a thread pool over keys saturates the link.

**Direction.** Parallelize the per-key downloads (bounded pool) and/or pass a tuned `TransferConfig` for multipart concurrency. Keep it idempotent (overwrite-safe keys per the LLD).

**Verify.** Time a cold model pull before/after on a multi-shard model; expect download time to fall roughly with the concurrency factor (until bandwidth-bound).

---

### F11 — No batched inference (NMT & TTS translate/synthesize one segment at a time) ⚡

**Root cause.** NMT calls `_run_inference` per segment; TTS synthesizes per segment. Modern transformer/accelerator throughput is dominated by batching — running 16 short segments as one padded batch is far cheaper than 16 separate `generate()` calls, especially on GPU.

**Principle.** Throughput ≠ latency. Batch the independent units (segments) through one forward/`generate` call with padding + attention masks. Tokenizer supports `padding=True`; `generate` handles batched inputs.

**Direction.** Replace the per-segment loop with batched generation (group segments, pad, single `generate`, unpad). Mind the per-segment `src_lang` detection — batch by detected language so `forced_bos_token_id`/`src_lang` are consistent within a batch. For TTS, batch where the model API allows; otherwise this is where a real worker-pool/GPU-stream helps.

**Verify.** Translate a 40-segment file; compare wall-clock and GPU/CPU utilization vs. the per-segment baseline.

> **Question:** the current `ThreadPoolExecutor` (F12) tries to get parallelism with threads. Why does *batching* beat *threading* here for a single model on a single device?

---

### F13 — `num_beams=5` is the default decoding strategy ⚡

**Root cause.** `translate_segment(... num_beams=5)` and the `video_tasks.num_beams` default of 5. Beam search with width 5 runs ~5× the decoder compute of greedy decoding, for often-marginal quality gains on short dubbing segments.

**Principle.** Pick the decoding strategy to match the quality/latency budget. Greedy or beam=1–2 is dramatically cheaper; reserve wide beams for cases that measurably need them (you already have a quality-driven stage-2/3 escalation).

**Direction.** Lower the default beam width; rely on the existing english-ratio escalation to widen only when needed. Make it configurable per `output_type` (captions vs. full dubbing may want different budgets).

**Verify.** A/B a sample set: measure per-segment latency and an Arabic-quality proxy (your `_arabic_script_ratio` / `_mixed_token_penalty`) at beams 1 vs 2 vs 5.

---

### F15 — CPU inference for Whisper + SILMA in minimal prod ⚡

**Root cause.** `docker-compose.prod.minimal.yml` sets `STT_DEVICE=cpu` and `SILMA_DEVICE=cpu`. SILMA-TTS is an F5/diffusion-style model whose cost scales with `nfe_step` — on CPU this is the pipeline's dominant latency. Whisper-small on CPU is tolerable (CTranslate2 int8), but TTS on CPU is the bottleneck.

**Principle.** Right-size hardware to the model. Diffusion TTS effectively needs a GPU for interactive latency; on CPU you must compensate with smaller models, fewer steps, and quantization.

**Direction.** For any latency-sensitive deployment, run TTS (and ideally STT) on GPU (the `docker-compose.gpu.yml` overlay + a GPU NLLB/Whisper path). If GPU is unavailable, combine F14 (lower `nfe_step`), F17 (quantization), and batching to claw back time, and set expectations accordingly.

**Verify.** Benchmark end-to-end `fullDubbing` on a 1-minute clip: CPU vs GPU; record per-stage seconds (STT / NMT / TTS / merge).

---

## Phase 2 — Secondary optimizations (P2)

### F8 — No startup pre-warm for `stt`/`nmt` microservices ⚡⬇️

**Root cause.** The `PREWARM_*` flags only drive the Celery worker (`celery_app.py`), and even there STT/NMT prewarm is a no-op now that they're separate services. The microservice workers lazy-load on first message, so the first user after a deploy waits for download **plus** model load.

**Principle.** Pay initialization cost at startup, not on the user's request. Load the model in the FastAPI `lifespan`/readiness path so `/readiness` only goes green once the model is ready (also gives correct K8s readiness semantics).

**Direction.** Trigger model load during service startup (guarded by an env flag for fast local dev), and/or gate `/readiness` on `/health/model`. Combine with F6 so the warm-up isn't also doing a slow download.

**Verify.** First real job after deploy shows no model-load delay; `/readiness` flips only after the model is loaded.

---

### F9 — Unpinned third-party runtime downloads ⬇️

**Root cause.** Several network pulls happen at runtime and outside your control:
- HF Hub fallback (`NMT_HF_FALLBACK`, Whisper HF id) downloads from the internet if S3/local miss.
- `catt_tashkeel` ONNX models fetched from **GitHub releases** via single-connection `urllib` (in `tts/models.py`).
- `silma-tts` auto-transcription downloads a Whisper model when `ref_text` is empty.

**Principle.** In production, every artifact should come from a source you control and pin. Surprise internet fetches are slow, version-drift-prone, and a availability risk.

**Direction.** Mirror all of these into your S3 models bucket (or bake them) and point the services at that; always pass a non-empty `ref_text`; treat HF Hub as a *break-glass* fallback, not a normal path. Pin versions/digests.

**Verify.** Run the full pipeline with outbound internet blocked except S3; it should still complete.

---

### F12 — `ThreadPoolExecutor` fan-out provides little real parallelism ⚡

**Root cause.** NMT's `_translate_all_segments` runs `NMT_INTERNAL_CONCURRENCY=4` threads, but each thread calls into the same model on one device, contends on the Python GIL, and serializes on `_tokenizer_lock`. The "concurrency" is mostly illusory for the compute-bound `generate()`.

**Principle.** Threads help with I/O-bound work, not GIL-bound tensor math on a single device. Use **batching** (F11) for throughput, or true multi-process/multi-GPU workers (the migration's "competing consumers") for horizontal scale.

**Direction.** After F11, reduce or remove the internal thread pool; let batching + replicas provide throughput. If you keep threads, scope them to genuinely I/O-bound parts (e.g., Groq length-adjust calls), not model inference.

**Verify.** Compare segments/sec at concurrency 1 vs 4 *with batching on* — confirm threads add little so the simpler code wins.

---

### F14 — TTS `nfe_step=64` in prod ⚡

**Root cause.** `TTS_DEFAULT_NFE_STEP` is set to 64 in minimal prod; the code's own default is 32. `nfe_step` is the number of function evaluations in the TTS sampler — latency scales ~linearly with it.

**Principle.** Tune the quality/latency knob deliberately. Doubling steps roughly doubles TTS time for diminishing perceptual gains.

**Direction.** Benchmark perceptual quality at 24 / 32 / 48 / 64 and pick the lowest acceptable. Make it per-tier if premium users justify higher quality.

**Verify.** MOS-style listening test (or internal preference) vs. per-clip seconds at each step count.

---

### F17 — NLLB has no quantized/optimized inference path ⚡🪶

**Root cause.** STT uses CTranslate2 via faster-whisper (int8/float16) — fast and small. NMT loads vanilla `transformers` NLLB (fp32 on CPU, fp16 on GPU), with no int8/CTranslate2 equivalent.

**Principle.** Use an inference-optimized runtime for the model, not just the training framework. NLLB can run on **CTranslate2** (the same engine behind faster-whisper) with int8 quantization — smaller memory, faster decode, no `torch` needed for inference.

**Direction.** Evaluate converting NLLB-distilled-600M to CTranslate2 int8. Bonus: if NMT runs on CTranslate2, the service may not need `torch`/`transformers` at all — feeding back into F1/F2 image savings.

**Verify.** Compare decode latency, RAM, and Arabic quality proxy: `transformers` fp32 vs CTranslate2 int8.

---

## Phase 3 — Cleanup / long-term (P3)

### F5 — Redundant dependencies 🪶
`backend/pyproject.toml` ships `databases` *and* `asyncpg` *and* SQLAlchemy; and `celery` + `pika` + `aio-pika` coexist during the Celery→RabbitMQ migration. Audit which are actually imported; drop the dead ones (the migration's Phase 2 already plans to retire Celery/Redis). Smaller dependency surface = smaller, safer images.

### F16 — STT `word_timestamps=True` always on ⚡
Word-level timestamps add decoding cost in faster-whisper. If downstream only needs segment-level timing, make it configurable and default off; enable only for features that need word timing.

---

## Suggested execution order

```
Phase 0 (1 sitting):   F1  →  F3  →  F10
Phase 1 (core):        F2  →  F4  →  F6  →  F7  →  F11  →  F13  →  F15
Phase 2 (tuning):      F8  →  F9  →  F12  →  F14  →  F17
Phase 3 (cleanup):     F5  →  F16
```

**Rationale.** Phase 0 are near-free wins (a CPU index, a `.dockerignore`, one config value) that immediately shrink images and kill a pathological slow path. Phase 1 attacks the structural costs (image layering, where ML deps live, how models arrive, and the dominant inference levers). Phase 2 is measurement-driven tuning. Phase 3 is hygiene that also feeds back into image size.

---

## Measure before and after (define your baseline first)

Don't optimize blind. Capture these for a fixed sample (e.g. one 60s clip) before starting:

| Metric | How to capture |
|--------|----------------|
| Image size per service | `docker images` |
| Cold-start to ready | time from `up` to `/readiness` 200 |
| Model download time | first-load logs (`_download_*` / `[CACHE] source=`) |
| Per-stage inference seconds | existing `processing_time` logs (STT) + add timing to NMT/TTS |
| End-to-end pipeline wall-clock | job `created_at` → parent `completed_at` |
| Peak RAM / VRAM per service | `docker stats` / `nvidia-smi` |

Re-measure after each phase and record deltas in this doc.

---

## Resources to study

**AI inference & serving fundamentals**
- *Making Deep Learning Go Brrrr From First Principles* — Horace He (compute vs memory-bandwidth vs overhead bound). https://horace.io/brrr_intro.html
- Hugging Face — *Efficient Inference* & *Optimizing Inference* guides. https://huggingface.co/docs/transformers/llm_optims and https://huggingface.co/docs/transformers/perf_infer_gpu_one
- Hugging Face — *Generation strategies* (greedy vs beam vs sampling, the cost of `num_beams`). https://huggingface.co/docs/transformers/generation_strategies
- NVIDIA — *Inference Optimization* overview & Triton Inference Server (batching/concurrency concepts). https://developer.nvidia.com/triton-inference-server

**Quantization & optimized runtimes**
- CTranslate2 docs (the engine under faster-whisper; supports NLLB int8). https://opennmt.net/CTranslate2/
- faster-whisper. https://github.com/SYSTRAN/faster-whisper
- ONNX Runtime — model optimization & quantization. https://onnxruntime.ai/docs/performance/
- Dynamic/static quantization overview (PyTorch). https://pytorch.org/docs/stable/quantization.html

**Batching, throughput & autoscaling for queue workers**
- *Continuous/Dynamic batching* (vLLM blog explains the concept well even beyond LLMs). https://blog.vllm.ai/2023/06/20/vllm.html
- KEDA — event-driven autoscaling on queue depth (matches the migration's plan). https://keda.sh/docs/latest/concepts/
- Enterprise Integration Patterns — *Competing Consumers*, *Claim Check* (already used in your design). https://www.enterpriseintegrationpatterns.com/

**Lean containers for Python/ML**
- PyTorch — installing CPU-only wheels (the CPU index). https://pytorch.org/get-started/locally/
- Docker — *multi-stage builds* & *build cache* best practices. https://docs.docker.com/build/building/multi-stage/ and https://docs.docker.com/build/cache/
- Docker — `.dockerignore` reference. https://docs.docker.com/build/concepts/context/#dockerignore-files
- boto3 — `TransferConfig` / multipart concurrency for fast S3 transfers. https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-transfers.html
- Hugging Face — `huggingface_hub` caching & `HF_HOME` (controlling where/when downloads happen). https://huggingface.co/docs/huggingface_hub/guides/manage-cache

**Cold start & model loading**
- Hugging Face — *Download files / offline mode* (`local_files_only`, pre-fetching). https://huggingface.co/docs/huggingface_hub/guides/download
- Kubernetes — init containers & RWX volumes (shared model cache pattern). https://kubernetes.io/docs/concepts/workloads/pods/init-containers/
```
