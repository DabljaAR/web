# CI Security Scanning & Docker Hardening

## Overview

Add three security scanning tools to the DabljaAR CI pipeline: Trivy for
vulnerability detection, Hadolint for Dockerfile linting, and gitleaks for
secrets scanning. All run as parallel jobs in a single GitHub Actions workflow
on every pull request and on a weekly schedule.

## Triggers

- **Pull request** — any path, any branch. FS + config scan runs
  unconditionally. Image scan runs only when path filter matches (Dockerfiles,
  lockfiles, or service source under buildable services). gitleaks and Hadolint
  block on any finding. Trivy blocks only on CRITICAL and HIGH severity
  findings.
- **Push to main** — FS + config scan always. Image scan always. Acts as safety
  net for anything a narrow PR path filter misses.
- **Schedule** — Monday 06:00 UTC weekly. FS + config scan + image scan all
  run unconditionally. Rescans against updated CVE databases.
- **Workflow dispatch** — manual trigger, runs all scans.

Concurrency — two groups:

- **Pull requests:** group key constructed from PR number,
  cancel-in-progress: true. Only the latest commit matters per PR.
- **Push to main:** group key scoped to commit SHA,
  cancel-in-progress: false. Two merges landing close together must both
  scan independently.

## Tools

### gitleaks — Secrets & Dry-Run Scan

Scans for leaked credentials, API keys, tokens, and placeholder strings that
indicate sensitive data in code or documentation.

**Scan scope varies by trigger:**

- **Pull request** — diff scan only. Uses the exact PR commit range:
  ```
  gitleaks detect --log-opts=${{ github.event.pull_request.base.sha }}...${{ github.event.pull_request.head.sha }}
  ```
  This is robust regardless of target branch name and does not depend on
  ref-naming conventions. Requires `fetch-depth: 0` on checkout so both
  base and head SHAs are available.
- **Weekly schedule / workflow_dispatch** — full working-tree scan. Catches
  anything that may have slipped through diff scans.

**Custom rules** target patterns specific to this codebase:

- Placeholder tokens in docs and examples (`YOUR_TOKEN`, `YOUR_SECRET`,
  `YOUR_*`, `sk-...`, `ghp_...`, `AKIA...`)
- `Bearer ` tokens outside `**/tests/` and `**/*.test.*` files
- Hardcoded JWT secrets and private keys
- Generic password and connection string patterns

**Output:**

1. Full verbose log to workflow output (file, line, rule, matched prefix)
 2. SARIF report uploaded to GitHub code scanning (inline PR annotations, category: gitleaks)
3. JSON report as build artifact (retention-days: 7; matched value redacted
   to avoid embedding real secrets in downloadable artifacts)

Exits with code 1 on any finding. PR annotations show the exact line and
rule triggered.

**Fork PRs:** Not applicable. DabljaAR does not accept external contributions.
Revisit `pull_request_target` handling if that changes.

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
 2. SARIF report for GitHub code scanning annotations (category: hadolint)

### Trivy — Vulnerability Scanner

Runs three sub-scans. Frequency depends on scan type:

**Filesystem scan** — always on every PR, main push, and weekly schedule.
Scans dependency manifests (`uv.lock`, `go.sum`, `requirements*.txt`,
`package-lock.json`, `pyproject.toml`) for known CVEs. Skips `node_modules/`
and `.venv*`. Cheap (~1-2 min). Uses Trivy action's built-in DB cache to
avoid rate-limit flakiness from GHCR pulls.

**Config scan** — always on every PR, main push, and weekly schedule.
Scans Dockerfiles, docker-compose files, and GitHub Actions YAML for
misconfigurations (containers running as root, missing read-only rootfs,
overly permissive capabilities).

**Image scan** — path-filtered on PRs, always on main push + weekly.
Builds and scans images for OS-level CVEs (libc, openssl, ffmpeg, curl).
Only the 5 services that can build without GPU dependencies: backend,
frontend, orchestrator, nmt-service, media-service. GPU-dependent services
(stt-service, tts-service) are covered by FS + config scan and Hadolint.

Path filter for image scan on PRs includes: `Dockerfile*`, `requirements*`,
`uv.lock`, `go.sum`, `package-lock.json`, `pyproject.toml`, and service
source under the 5 buildable services. Main-branch push acts as a safety
net for anything a narrow path filter misses.

**Severity thresholds:**

- `CRITICAL` and `HIGH` findings block the scan (exit code 1)
- `MEDIUM` and `LOW` are logged as warnings only

**Output:**

1. Table summary to workflow log
 2. SARIF reports for code scanning (one upload per sub-scan: categories
    trivy-fs, trivy-config, trivy-image)
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

## Rollout Order

All findings below are fixed in the same PR that adds the workflow, not as a
follow-up. The PR contains two commits:

1. **Commit 1** — fixes findings (Dockerfile hardening, placeholder token
   cleanup, gitleaks allowlist). Does not yet add or modify CI files.
2. **Commit 2** — adds the security workflow and config files (`.hadolint.yaml`,
   `.trivyignore`, `.gitleaks.toml`, `security-scan.yml`).

This ordering means `git bisect` or revert on the workflow file never leaves
the pipeline permanently red. If commit 2 is reverted, findings from commit 1
are still gone. If commit 1 has a breaking change (e.g., a Dockerfile fix
that breaks a build), it's a clean revert without touching CI.

## Findings to Fix (Commit 1)

### Dockerfiles

- **Frontend** (`frontend/Dockerfile`): production stage runs as root (no
  `USER` directive). `serve` runs as a non-root user by default, but `USER`
  must be explicit. Add `USER node` after `COPY --from=builder`.
- **Orchestrator** (`orchestrator/Dockerfile`): uses `alpine:latest` (unpinned).
  Pin to `alpine:3.20`. Final stage runs as root — add `USER 1000`. Add
  `WORKDIR /app` matching the binary location.

Audit remaining Dockerfiles during implementation — the two listed are the
confirmed violations.

### Placeholder Tokens in Docs

- `backend/AGENTS.md` and `README.md` contain `Bearer YOUR_TOKEN`,
  `YOUR_SECRET`, `sk-...` examples that gitleaks flags. Replace each with
  non-secret strings: `EXAMPLE_BEARER_TOKEN`, `EXAMPLE_SECRET_KEY`,
  `sk_example_key`. Add remaining false-positive patterns to `.gitleaks.toml`
  allowlist.

## Job Configuration

All jobs set `timeout-minutes: 15`. Image scan may need longer — set
`timeout-minutes: 30` for that job to accommodate builds.

Trivy action uses `cache: true` to persist the vulnerability DB across runs,
preventing GHCR rate-limit failures on shared runners.

**SARIF categories:** every SARIF upload step sets a distinct `category`
input so findings from different tools do not overwrite each other in the
code scanning UI:

| Upload step | Category |
|---|---|
| gitleaks | `gitleaks` |
| Hadolint | `hadolint` |
| Trivy filesystem | `trivy-fs` |
| Trivy config | `trivy-config` |
| Trivy image | `trivy-image` |

**Path-filtered image scan:** use `dorny/paths-filter` action with a filter
pattern, not a workflow-level `on.pull_request.paths` gate. FS + config scan
jobs run unconditionally. The image-scan job runs only when the filter output
is true (`if: steps.filter.outputs.image == 'true'`). Filter pattern:
`Dockerfile*`, `requirements*`, `uv.lock`, `go.sum`, `package-lock.json`,
`pyproject.toml`, and service source under the 5 buildable services.

gitleaks JSON artifact sets `retention-days: 7` and redacts the matched value
in the artifact payload (keeps file, line, rule — not the snippet).

## Branch Protection

The three jobs must be added as required status checks in the repository's
branch protection rules for `main`. Otherwise exit-code-1 exits are visible
in CI but do not prevent merging.

```
Required checks (all):
- gitleaks-scan
- hadolint-lint
- trivy-scan
```

## MEDIUM/LOW Findings

Trivy MEDIUM and LOW findings are logged to the workflow run but not tracked
elsewhere. If the team wants visibility into these later, options include
auto-creating GitHub Issues or forwarding to a dashboard. For now they are
informational only.

## SBOM Generation

Not included. Trivy supports CycloneDX SBOM output (`--format cyclonedx`) if
supply-chain provenance becomes a requirement. Add as a future enhancement.

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
