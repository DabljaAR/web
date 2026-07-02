# CI Security Scanning & Docker Hardening

## Overview

Add three security scanning tools to the DabljaAR CI pipeline: Trivy for
vulnerability detection, Hadolint for Dockerfile linting, and gitleaks for
secrets scanning. All run as parallel jobs in a single GitHub Actions workflow
on every pull request and on a weekly schedule.

## Triggers

- **Pull request** — any path, any branch. Scans run in parallel. gitleaks and
  Hadolint block on any finding. Trivy blocks only on CRITICAL and HIGH
  severity findings.
- **Schedule** — Monday 06:00 UTC weekly. Rescans dependencies and image layers
  against updated CVE databases.
- **Workflow dispatch** — manual trigger for ad-hoc scans.

Concurrency: group by PR ref, cancel in-progress runs on new pushes.

## Tools

### gitleaks — Secrets & Dry-Run Scan

Scans the entire repo for leaked credentials, API keys, tokens, and placeholder
strings that indicate sensitive data in code or documentation.

**Custom rules** target patterns specific to this codebase:

- Placeholder tokens in docs and examples (`YOUR_TOKEN`, `YOUR_SECRET`,
  `YOUR_*`, `sk-...`, `ghp_...`, `AKIA...`)
- `Bearer ` tokens outside `**/tests/` and `**/*.test.*` files
- Hardcoded JWT secrets and private keys
- Generic password and connection string patterns

**Output:**

1. Full verbose log to workflow output (file, line, rule, matched snippet)
2. SARIF report uploaded to GitHub code scanning (inline PR annotations)
3. JSON report uploaded as build artifact for offline inspection

Exits with code 1 on any finding. PR annotations show the exact line and
rule triggered.

### Hadolint — Dockerfile Linter

Lints all Dockerfiles in the project against a project-wide
`.hadolint.yaml` config. Runs on every Dockerfile matched by `**/Dockerfile*`
(7 main files + GPU variants).

**Enforced rules:**

- `FROM` must pin a digest or a minor version — no `:latest` tags
- `USER` directive must exist (no root containers)
- `apt-get` must use `--no-install-recommends` and clean up with
  `rm -rf /var/lib/apt/lists/*`
- Prefer `COPY` over `ADD`
- No `sudo`, no `curl ... | bash` patterns
- `HEALTHCHECK` defined for long-running services
- No hardcoded secrets in build args or env vars

**Output:**

1. Full lint output to workflow log
2. SARIF report for GitHub code scanning annotations

### Trivy — Vulnerability Scanner

Runs three sub-scans in parallel within a single job:

1. **Filesystem scan** (`trivy fs .`) — dependency vulnerabilities across all
   manifest files: `uv.lock`, `go.sum`, `requirements*.txt`,
   `package-lock.json`, `pyproject.toml`. Skips `node_modules/` and `.venv*`.
2. **Config scan** (`trivy config .`) — misconfigurations in Dockerfiles,
   docker-compose files, and GitHub Actions workflow YAML. Detects containers
   running as root, missing read-only rootfs, overly permissive capabilities.
3. **Image scan** — scans built images for OS-level CVEs. Only the 5 services
   that can build without GPU dependencies get an image scan: backend, frontend,
   orchestrator, nmt-service, media-service. GPU-dependent services (stt-service,
   tts-service) are covered by filesystem scan and Hadolint. Build uses
   `--load` flag so the image is available locally without pushing.

**Severity thresholds:**

- `CRITICAL` and `HIGH` findings block the scan (exit code 1)
- `MEDIUM` and `LOW` are logged as warnings only

**Output:**

1. Table summary to workflow log
2. SARIF report for code scanning
3. JSON report as build artifact

## Docker Hardening

The Hadolint rules and Trivy config scan cover the hardening requirements:

- Non-root execution (`USER` directive)
- Pinned base image versions (no `latest`)
- Cleaned apt caches (smaller images, fewer CVE surfaces)
- No build-time secrets in image layers
- Minimal runtime packages (slim images, no build tooling in final stage)
- `HEALTHCHECK` for service observability

Existing Dockerfiles already follow most of these patterns. The CI gates will
prevent regressions.

## Existing Findings to Address

- **Frontend Dockerfile** (`frontend/Dockerfile`): production stage runs as root
  (no `USER` directive). `serve` is installed globally instead of using a
  static file server as a non-root user.
- **Orchestrator Dockerfile** (`orchestrator/Dockerfile`): uses `alpine:latest`
  (unpinned). Final stage runs as root. No `WORKDIR` that matches the binary
  location.
- **Placeholder tokens in docs**: `backend/AGENTS.md` and `README.md` contain
  `Bearer YOUR_TOKEN`, `YOUR_SECRET`, `sk-...` examples that gitleaks will
  flag. These should be moved to a gitleaks allowlist or replaced with
  non-secret strings like `EXAMPLE_BEARER_TOKEN`.

The hardening phase of implementation will fix these.

## Permissions

Workflow requires `contents: read` and `security-events: write` (for SARIF
upload to code scanning). No other permissions needed.

## File Outline

```
.github/workflows/security-scan.yml   — single workflow, all three tools
.hadolint.yaml                         — project-wide Hadolint configuration
.trivyignore                           — Trivy exclusion rules
.gitleaks.toml                         — custom gitleaks rules
```

## Unchanged Scope

This design does **not**:

- Add SAST rules for application logic (Semgrep). The project is AI pipeline
  orchestration, not a web app with user input — SQLi/XSS rules would produce
  noise.
- Modify build, test, or deploy workflows. Security scanning is its own
  concern.
- Add pre-commit hooks. CI gate is sufficient for this project size.
