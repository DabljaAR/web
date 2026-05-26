#!/usr/bin/env bash
# start.sh - Robust Ubuntu 22.04 local dev environment bootstrap and service manager.

set -Eeuo pipefail

trap 'exit_handler' EXIT

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

RUNTIME_DIR="$ROOT_DIR/.runtime"
PID_DIR="$RUNTIME_DIR/pids"
LOG_DIR="$RUNTIME_DIR/logs"
MINIO_DATA_DIR="$RUNTIME_DIR/minio-data"
MODEL_CACHE_DIR="$RUNTIME_DIR/model-cache"

BACKEND_ENV_EXAMPLE="$BACKEND_DIR/.env.example"
BACKEND_ENV_FILE="$BACKEND_DIR/.env"
FRONTEND_ENV_EXAMPLE="$FRONTEND_DIR/.env.example"
FRONTEND_ENV_FILE="$FRONTEND_DIR/.env"

BACKEND_VENV="$BACKEND_DIR/.venv"
SELECTED_PYTHON_BIN=""

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
FRONTEND_NODE_MAJOR="${FRONTEND_NODE_MAJOR:-24}"
FLOWER_PORT="${FLOWER_PORT:-5555}"
MINIO_PORT="${MINIO_PORT:-9000}"
MINIO_CONSOLE_PORT="${MINIO_CONSOLE_PORT:-9001}"
NVM_DIR="${NVM_DIR:-$HOME/.nvm}"

PG_DB="${PG_DB:-dabljaar}"
PG_USER="${PG_USER:-postgres}"
PG_PASSWORD="${PG_PASSWORD:-postgres}"

ENABLE_FRONTEND=1
ENABLE_FLOWER=1
RUN_MIGRATIONS=1
DEBUG_MODE=0

if [[ -t 1 ]]; then
    GREEN='\033[0;32m'
    BLUE='\033[0;34m'
    YELLOW='\033[1;33m'
    RED='\033[0;31m'
    NC='\033[0m'
else
    GREEN=''
    BLUE=''
    YELLOW=''
    RED=''
    NC=''
fi

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok() { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_err() { echo -e "${RED}[ERROR]${NC} $*"; }
log_debug() {
    if [[ "$DEBUG_MODE" -eq 1 ]]; then
        echo -e "${BLUE}[DEBUG]${NC} $*" >&2
    fi
}

exit_handler() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log_err "Script exited with error code $exit_code"
    fi
}

die() {
    log_err "$*"
    exit 1
}

ensure_sudo_access() {
    if [[ "$EUID" -ne 0 ]]; then
        log_info "Checking sudo access (will prompt for password once if needed)..."
        if ! sudo -v; then
            die "sudo access required but denied. Run with appropriate permissions."
        fi
    fi
}

usage() {
    cat <<'EOF'
Usage: ./start.sh <command> [options]

Commands:
    setup         Install dependencies and configure local dev environment.
    run           Start local development services in background.
    stop          Stop services started by this script.
    status        Show service/process status.
    logs [name]   Tail logs for one service or all services.
    help          Show this help message.

Options:
    --no-frontend      Skip frontend service for run/status output.
    --no-flower        Skip Flower service for run/status output.
    --skip-migrations  Do not run alembic migrations during setup.
    --debug            Enable debug logging for troubleshooting.

Examples:
    ./start.sh setup
    ./start.sh setup --debug
    ./start.sh run
    ./start.sh run --no-frontend
    ./start.sh logs backend
    ./start.sh logs worker_media
    ./start.sh stop
EOF
}

ensure_runtime_dirs() {
    mkdir -p "$RUNTIME_DIR" "$PID_DIR" "$LOG_DIR" "$MINIO_DATA_DIR" "$MODEL_CACHE_DIR"
}

pid_file_for() {
    local name="$1"
    echo "$PID_DIR/${name}.pid"
}

log_file_for() {
    local name="$1"
    echo "$LOG_DIR/${name}.log"
}

is_pid_running() {
    local pid="$1"
    [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

is_service_running() {
    local name="$1"
    local pid_file
    pid_file="$(pid_file_for "$name")"

    if [[ ! -f "$pid_file" ]]; then
        return 1
    fi

    local pid
    pid="$(<"$pid_file")"
    if is_pid_running "$pid"; then
        return 0
    fi

    rm -f "$pid_file"
    return 1
}

wait_for_port() {
    local port="$1"
    local retries="${2:-30}"
    local delay="${3:-1}"

    log_info "Waiting for port $port to be available (up to ${retries}s)..."
    
    for i in $(seq 1 "$retries"); do
        if ss -tlnp "( sport = :$port )" 2>/dev/null | grep -q ":$port"; then
            log_ok "Port $port is listening."
            return 0
        fi
        if [[ $i -eq 1 ]]; then
            echo -n "  Progress: "
        fi
        echo -n "."
        sleep "$delay"
    done
    echo ""
    
    return 1
}

run_with_sudo() {
    if [[ "$EUID" -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        die "Missing command: $cmd. Please install it or check your PATH."
    fi
}

version_ge() {
    local got="$1"
    local want="$2"
    [[ "$(printf '%s\n' "$want" "$got" | sort -V | head -n1)" == "$want" ]]
}

assert_ubuntu_2204() {
    if [[ ! -f /etc/os-release ]]; then
        die "Cannot detect OS. /etc/os-release is missing."
    fi
    # shellcheck disable=SC1091
    source /etc/os-release
    if [[ "${ID:-}" != "ubuntu" ]]; then
        die "This script currently supports Ubuntu only. Detected: ${ID:-unknown}."
    fi
    if [[ "${VERSION_ID:-}" != "22.04" ]]; then
        log_warn "Detected Ubuntu ${VERSION_ID:-unknown}. Script is tested on 22.04 and 24.04; other versions may work."
    fi
}

install_apt_packages_if_missing() {
    local -a packages=(
        curl
        wget
        git
        jq
        ca-certificates
        lsb-release
        gnupg
        software-properties-common
        build-essential
        python3
        python3-venv
        python3-pip
        redis-server
        postgresql
        postgresql-contrib
        postgresql-client
        lsof
        psmisc
          iproute2
    )

    local -a missing=()
    for pkg in "${packages[@]}"; do
        if ! dpkg -s "$pkg" >/dev/null 2>&1; then
            missing+=("$pkg")
        fi
    done

    if [[ ${#missing[@]} -eq 0 ]]; then
        log_ok "Required apt packages already installed."
        return
    fi

    log_info "Installing missing apt packages: ${missing[*]}"
    if ! run_with_sudo apt-get update -y; then
        die "Failed to update package list. Check your network and apt sources."
    fi
    
    if ! run_with_sudo apt-get install -y "${missing[@]}"; then
        die "Failed to install packages: ${missing[*]}"
    fi
    
    log_ok "All required packages installed."
}

select_python_bin() {
    if [[ -n "$SELECTED_PYTHON_BIN" ]]; then
        return
    fi

    local -a candidates=(
        python3.12
        python3.11
        /usr/bin/python3
        python3
    )

    local candidate
    for candidate in "${candidates[@]}"; do
        if ! command -v "$candidate" >/dev/null 2>&1; then
            continue
        fi

        local version
        version="$($candidate -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
        if [[ -z "$version" ]]; then
            continue
        fi

        local major minor
        major="${version%%.*}"
        minor="${version##*.}"
        if [[ "$major" -eq 3 && "$minor" -ge 12 ]]; then
            SELECTED_PYTHON_BIN="$candidate"
            log_ok "Using Python $version from $candidate"
            return
        fi
    done

    die "No supported Python version found (need Python 3.12+). Install python3.12 and rerun setup."
}

venv_healthy() {
    [[ -x "$BACKEND_VENV/bin/python" ]] || return 1
    "$BACKEND_VENV/bin/python" -c "import sys; print(sys.executable)" >/dev/null 2>&1 || return 1
    return 0
}

install_uv_if_needed() {
    if command -v uv >/dev/null 2>&1; then
        log_ok "uv already installed ($(uv --version 2>/dev/null || echo 'version unknown'))."
        return
    fi

    log_info "Installing uv..."
    if ! command -v curl >/dev/null 2>&1; then
        die "curl is required to install uv but not found."
    fi

    if ! curl -fsSL https://astral.sh/uv/install.sh | sh; then
        die "Failed to install uv. Check your internet connection."
    fi

    export PATH="$HOME/.local/bin:$PATH"

    if ! command -v uv >/dev/null 2>&1; then
        die "uv installation verification failed. Try adding ~/.local/bin to PATH and rerunning."
    fi

    log_ok "uv installed ($(uv --version))."
}

ensure_nvm_loaded() {
    if [[ ! -s "$NVM_DIR/nvm.sh" ]]; then
        die "nvm is not installed or nvm.sh not found at $NVM_DIR/nvm.sh"
    fi
    # shellcheck disable=SC1090
    source "$NVM_DIR/nvm.sh"
}

use_frontend_node() {
    ensure_nvm_loaded
    if ! nvm use "$FRONTEND_NODE_MAJOR" >/dev/null 2>&1; then
        die "Node v${FRONTEND_NODE_MAJOR} is not available in nvm. Run './start.sh setup' to install it."
    fi
}

install_node_if_needed() {
    if ! command -v curl >/dev/null 2>&1; then
        die "curl is required to install nvm/Node.js but not found."
    fi

    if [[ ! -s "$NVM_DIR/nvm.sh" ]]; then
        log_info "Installing nvm..."
        if ! curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash; then
            die "Failed to install nvm. Check your internet connection."
        fi
    else
        log_ok "nvm already installed."
    fi

    ensure_nvm_loaded

    if ! nvm use "$FRONTEND_NODE_MAJOR" >/dev/null 2>&1; then
        log_info "Installing Node.js v${FRONTEND_NODE_MAJOR} via nvm..."
        if ! nvm install "$FRONTEND_NODE_MAJOR"; then
            die "Failed to install Node.js v${FRONTEND_NODE_MAJOR} with nvm."
        fi
    fi

    nvm alias default "$FRONTEND_NODE_MAJOR" >/dev/null 2>&1 || true
    nvm use "$FRONTEND_NODE_MAJOR" >/dev/null 2>&1 || die "Failed to activate Node.js v${FRONTEND_NODE_MAJOR}."

    require_cmd node
    require_cmd npm
    local final_version
    final_version="$(node -v 2>/dev/null | sed 's/^v//' || echo 'unknown')"
    local major="${final_version%%.*}"
    if [[ "$major" != "$FRONTEND_NODE_MAJOR" ]]; then
        die "Activated Node.js version is $final_version, expected v${FRONTEND_NODE_MAJOR}. Check your nvm setup."
    fi
    log_ok "Node.js v$final_version ready via nvm."
}

install_minio_if_needed() {
    if command -v minio >/dev/null 2>&1; then
        log_ok "MinIO binary already installed."
        return
    fi

    log_info "Installing MinIO binary to /usr/local/bin/minio"
    
    if ! command -v curl >/dev/null 2>&1; then
        die "curl is required to install MinIO but not found."
    fi

    local tmp_minio
    tmp_minio="$(mktemp /tmp/minio.XXXXXX)" || die "Failed to create temp file for MinIO"
    
    log_info "Downloading MinIO..."
    if ! curl -fsSL https://dl.min.io/server/minio/release/linux-amd64/minio -o "$tmp_minio"; then
        rm -f "$tmp_minio"
        die "Failed to download MinIO binary. Check your internet connection."
    fi
    
    if ! chmod +x "$tmp_minio"; then
        rm -f "$tmp_minio"
        die "Failed to make MinIO executable."
    fi
    
    if ! run_with_sudo install -m 0755 "$tmp_minio" /usr/local/bin/minio; then
        rm -f "$tmp_minio"
        die "Failed to install MinIO to /usr/local/bin/. Check permissions."
    fi
    
    rm -f "$tmp_minio"
    
    if ! command -v minio >/dev/null 2>&1; then
        die "MinIO installation verification failed. Binary not found in PATH."
    fi
    
    log_ok "MinIO installed."
}

bootstrap_env_file() {
    local example_file="$1"
    local target_file="$2"

    if [[ -f "$target_file" ]]; then
        log_ok "Found existing $(basename "$target_file")."
        return
    fi

    [[ -f "$example_file" ]] || die "Missing env example: $example_file"
    cp "$example_file" "$target_file"
    log_ok "Created $(basename "$target_file") from example."
}

normalize_frontend_env_key() {
    [[ -f "$FRONTEND_ENV_FILE" ]] || return

    if grep -q '^VITE_API_BASE_URL=' "$FRONTEND_ENV_FILE"; then
        return
    fi

    if grep -q '^VITE_API_URL=' "$FRONTEND_ENV_FILE"; then
        sed -i 's/^VITE_API_URL=/VITE_API_BASE_URL=/' "$FRONTEND_ENV_FILE"
        log_ok "Updated frontend env key: VITE_API_URL -> VITE_API_BASE_URL"
    else
        echo "VITE_API_BASE_URL=http://localhost:${BACKEND_PORT}/api" >> "$FRONTEND_ENV_FILE"
        log_ok "Added VITE_API_BASE_URL to frontend .env"
    fi
}

ensure_python_env() {
    if [[ ! -f "$BACKEND_DIR/pyproject.toml" ]]; then
        die "Backend pyproject.toml not found at $BACKEND_DIR/pyproject.toml"
    fi

    log_info "Installing backend dependencies (uv sync --group ai)..."
    pushd "$BACKEND_DIR" >/dev/null
    if ! uv sync --group ai; then
        popd >/dev/null
        die "uv sync failed. Check internet connection and pyproject.toml."
    fi
    popd >/dev/null

    log_ok "Backend Python environment ready."
}

ensure_frontend_deps() {
    use_frontend_node

    if [[ ! -d "$FRONTEND_DIR" ]]; then
        die "Frontend directory not found at $FRONTEND_DIR"
    fi

    log_info "Installing frontend dependencies..."
    pushd "$FRONTEND_DIR" >/dev/null
    
    if [[ ! -f package.json ]]; then
        die "Frontend package.json not found at $FRONTEND_DIR/package.json"
    fi
    
    local npm_cmd="install"
    if [[ -f package-lock.json ]]; then
        npm_cmd="ci"
    fi
    
    if ! npm "$npm_cmd" >/dev/null 2>&1; then
        die "Failed to install frontend dependencies. Check package.json and internet connection."
    fi
    
    popd >/dev/null
    log_ok "Frontend dependencies ready."
}

ensure_system_services() {
    log_info "Ensuring Redis and PostgreSQL are enabled and running."
    
    if ! run_with_sudo systemctl enable --now redis-server; then
        die "Failed to enable/start Redis. Check: sudo systemctl status redis-server"
    fi
    
    if ! run_with_sudo systemctl enable --now postgresql; then
        die "Failed to enable/start PostgreSQL. Check: sudo systemctl status postgresql"
    fi

    if ! wait_for_port 6379 30 1; then
        die "Redis failed to become ready on port 6379 after 30 seconds. Check logs: sudo journalctl -u redis-server"
    fi
    
    if ! wait_for_port 5432 30 1; then
        die "PostgreSQL failed to become ready on port 5432 after 30 seconds. Check logs: sudo journalctl -u postgresql"
    fi
    
    log_ok "Redis and PostgreSQL are running."
}

ensure_postgres_database() {
    log_info "Ensuring PostgreSQL role/database exist."

    if ! run_with_sudo -u postgres env PGCONNECT_TIMEOUT=5 \
        psql -w -d postgres -tAc "SELECT 1" >/dev/null 2>&1; then
        die "Cannot connect to PostgreSQL. Ensure the service is running: sudo systemctl status postgresql"
    fi

    if ! run_with_sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${PG_USER}'" | grep -q 1; then
        log_info "Creating PostgreSQL role '${PG_USER}'..."
        if ! run_with_sudo -u postgres psql -c "CREATE ROLE ${PG_USER} LOGIN PASSWORD '${PG_PASSWORD}';"; then
            die "Failed to create PostgreSQL role. Check the password contains no special shell characters."
        fi
        log_ok "Created PostgreSQL role '${PG_USER}'."
    else
        log_ok "PostgreSQL role '${PG_USER}' already exists."
    fi

    if ! run_with_sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${PG_DB}'" | grep -q 1; then
        log_info "Creating PostgreSQL database '${PG_DB}'..."
        if ! run_with_sudo -u postgres psql -c "CREATE DATABASE ${PG_DB} OWNER ${PG_USER};"; then
            die "Failed to create PostgreSQL database."
        fi
        log_ok "Created PostgreSQL database '${PG_DB}'."
    else
        log_ok "PostgreSQL database '${PG_DB}' already exists."
    fi
}

run_migrations_if_enabled() {
    if [[ "$RUN_MIGRATIONS" -ne 1 ]]; then
        log_warn "Skipping alembic migrations (--skip-migrations)."
        return
    fi

    if [[ ! -f "$BACKEND_DIR/alembic.ini" ]]; then
        die "alembic.ini not found at $BACKEND_DIR/alembic.ini"
    fi

    log_info "Running Alembic migrations (upgrade head)..."
    pushd "$BACKEND_DIR" >/dev/null
    
    local alembic_output
    if ! alembic_output="$(uv run alembic upgrade head 2>&1)"; then
        printf '%s\n' "$alembic_output"

        if grep -q "Can't locate revision identified by" <<<"$alembic_output"; then
            local missing_rev
            missing_rev="$(sed -n "s/.*Can't locate revision identified by '\([^']*\)'.*/\1/p" <<<"$alembic_output")"
            if [[ -z "$missing_rev" ]]; then
                missing_rev="unknown"
            fi
            log_err "Alembic can't find revision '$missing_rev'. Your database points to a migration missing from this repo."
            log_err "Local dev fix: cd backend && uv run alembic stamp head && uv run alembic upgrade head"
            log_err "Or drop/recreate the database and re-run ./start.sh setup."
        else
            log_err "Database migrations failed. Check your .env file and database connection."
        fi

        popd >/dev/null
        exit 1
    fi
    
    popd >/dev/null
    log_ok "Database migrations applied."
}

start_managed_process() {
    local name="$1"
    local working_dir="$2"
    local command="$3"
    local pid_file
    local log_file

    pid_file="$(pid_file_for "$name")"
    log_file="$(log_file_for "$name")"

    if is_service_running "$name"; then
        log_warn "$name already running (pid $(<"$pid_file"))."
        return
    fi

    log_info "Starting $name"
    (
        cd "$working_dir"
        exec setsid bash -c "$command"
    ) >>"$log_file" 2>&1 &

    local pid=$!
    echo "$pid" >"$pid_file"
    sleep 1

    if is_pid_running "$pid"; then
        log_ok "$name started (pid $pid)."
    else
        rm -f "$pid_file"
        die "$name failed to start. Check log: $log_file"
    fi
}

stop_managed_process() {
    local name="$1"
    local pid_file
    pid_file="$(pid_file_for "$name")"

    if [[ ! -f "$pid_file" ]]; then
        log_warn "$name is not managed/running."
        return
    fi

    local pid
    pid="$(<"$pid_file")"
    if ! is_pid_running "$pid"; then
        rm -f "$pid_file"
        log_warn "$name had stale pid file."
        return
    fi

    log_info "Stopping $name (pid/pgid $pid)."
    kill -- -"$pid" >/dev/null 2>&1 || kill "$pid" >/dev/null 2>&1 || true

    for _ in $(seq 1 20); do
        if ! is_pid_running "$pid"; then
            rm -f "$pid_file"
            log_ok "$name stopped."
            return
        fi
        sleep 0.5
    done

    log_warn "$name did not stop gracefully; sending SIGKILL."
    kill -9 -- -"$pid" >/dev/null 2>&1 || kill -9 "$pid" >/dev/null 2>&1 || true
    rm -f "$pid_file"
}

kill_port_orphans() {
    local port="$1"
    local pids=""

    # Extract unique listeners on the requested TCP port.
    pids="$(ss -tlnp "( sport = :$port )" 2>/dev/null | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u | tr '\n' ' ' | xargs || true)"

    if [[ -z "$pids" ]]; then
        return
    fi

    log_warn "Port $port already bound by PID(s): $pids. Attempting cleanup."
    kill $pids >/dev/null 2>&1 || true
    sleep 1
}

print_runtime_summary() {
    cat <<EOF

${GREEN}Development stack started.${NC}

    Frontend:       http://localhost:${FRONTEND_PORT}
    Backend Docs:   http://localhost:${BACKEND_PORT}/docs
    Flower:         http://localhost:${FLOWER_PORT}
    MinIO API:      http://localhost:${MINIO_PORT}
    MinIO Console:  http://localhost:${MINIO_CONSOLE_PORT}

Logs directory:
    $LOG_DIR

Use:
    ./start.sh status
    ./start.sh logs <service>
    ./start.sh stop
EOF
}

cmd_setup() {
    ensure_sudo_access
    assert_ubuntu_2204
    ensure_runtime_dirs

    install_apt_packages_if_missing
    install_node_if_needed
    install_minio_if_needed
    install_uv_if_needed

    ensure_system_services
    ensure_postgres_database

    bootstrap_env_file "$BACKEND_ENV_EXAMPLE" "$BACKEND_ENV_FILE"
    bootstrap_env_file "$FRONTEND_ENV_EXAMPLE" "$FRONTEND_ENV_FILE"
    normalize_frontend_env_key

    ensure_python_env
    ensure_frontend_deps
    run_migrations_if_enabled

    log_ok "Setup completed successfully."
}

cmd_run() {
    ensure_sudo_access
    ensure_runtime_dirs
    ensure_system_services

    install_uv_if_needed

    if ! venv_healthy; then
        log_warn "Backend virtualenv missing or invalid. Running uv sync now."
        ensure_python_env
    fi

    [[ -f "$BACKEND_ENV_FILE" ]] || die "Missing backend .env. Run './start.sh setup' first."
    [[ -f "$FRONTEND_ENV_FILE" ]] || die "Missing frontend .env. Run './start.sh setup' first."

    log_info "Starting managed services..."

    # Keep AI model caches writable in local dev (avoid /model-cache permission issues)
    local hf_home="$MODEL_CACHE_DIR/hf"
    local hf_hub_cache="$MODEL_CACHE_DIR/hf/hub"
    local transformers_cache="$MODEL_CACHE_DIR/hf/transformers"
    local xdg_cache="$MODEL_CACHE_DIR/xdg-cache"
    local torch_home="$MODEL_CACHE_DIR/torch"
    local nmt_local_path="$MODEL_CACHE_DIR/nmt-v4"
    local stt_local_path="$MODEL_CACHE_DIR/whisper-small"
    mkdir -p "$hf_home" "$hf_hub_cache" "$transformers_cache" "$xdg_cache" "$torch_home" "$nmt_local_path" "$stt_local_path"

    kill_port_orphans "$MINIO_PORT"
    start_managed_process "minio" "$ROOT_DIR" "MINIO_ROOT_USER=minioadmin MINIO_ROOT_PASSWORD=minioadmin minio server '$MINIO_DATA_DIR' --address ':$MINIO_PORT' --console-address ':$MINIO_CONSOLE_PORT'"
    if ! wait_for_port "$MINIO_PORT" 30 1; then
        die "MinIO failed to become ready on port $MINIO_PORT. Check log: $LOG_DIR/minio.log"
    fi

    kill_port_orphans "$BACKEND_PORT"
    start_managed_process "backend" "$BACKEND_DIR" "INSTALL_AI=${INSTALL_AI:-true} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True HF_HOME='$hf_home' HUGGINGFACE_HUB_CACHE='$hf_hub_cache' TRANSFORMERS_CACHE='$transformers_cache' XDG_CACHE_HOME='$xdg_cache' TORCH_HOME='$torch_home' uv run uvicorn app.main:app --host '$BACKEND_HOST' --port '$BACKEND_PORT'"
    if ! wait_for_port "$BACKEND_PORT" 30 1; then
        die "Backend failed to become ready on port $BACKEND_PORT. Check log: $LOG_DIR/backend.log"
    fi

    start_managed_process "worker_media" "$BACKEND_DIR" "INSTALL_AI=${INSTALL_AI:-true} HF_HOME='$hf_home' HUGGINGFACE_HUB_CACHE='$hf_hub_cache' TRANSFORMERS_CACHE='$transformers_cache' XDG_CACHE_HOME='$xdg_cache' TORCH_HOME='$torch_home' uv run celery -A app.jobs.celery_app worker --loglevel=info -Q media --concurrency=2 --max-tasks-per-child=1000 --hostname=worker-media@%h"
    start_managed_process "worker_stt" "$BACKEND_DIR" "INSTALL_AI=${INSTALL_AI:-true} HF_HOME='$hf_home' HUGGINGFACE_HUB_CACHE='$hf_hub_cache' TRANSFORMERS_CACHE='$transformers_cache' XDG_CACHE_HOME='$xdg_cache' TORCH_HOME='$torch_home' STT_MODEL_LOCAL_PATH='$stt_local_path' uv run celery -A app.jobs.celery_app worker --loglevel=info -Q ai_stt --concurrency=1 --max-tasks-per-child=1000 --hostname=worker-stt@%h"
    start_managed_process "worker_nmt" "$BACKEND_DIR" "INSTALL_AI=${INSTALL_AI:-true} HF_HOME='$hf_home' HUGGINGFACE_HUB_CACHE='$hf_hub_cache' TRANSFORMERS_CACHE='$transformers_cache' XDG_CACHE_HOME='$xdg_cache' TORCH_HOME='$torch_home' NMT_MODEL_LOCAL_PATH='$nmt_local_path' uv run celery -A app.jobs.celery_app worker --loglevel=info -Q ai_nmt,ai_tts,pipeline --concurrency=1 --max-tasks-per-child=1000 --hostname=worker-nmt@%h"

    if [[ "$ENABLE_FLOWER" -eq 1 ]]; then
        if uv run python -c "import flower" >/dev/null 2>&1; then
            start_managed_process "flower" "$BACKEND_DIR" "INSTALL_AI=${INSTALL_AI:-true} FLOWER_UNAUTHENTICATED_API=true uv run celery -A app.jobs.celery_app flower --port='$FLOWER_PORT'"
        else
            log_warn "Flower is not installed in the backend environment. Skipping Flower startup."
            log_warn "To enable Flower, run: cd backend && uv sync --group dev"
            log_warn "Or run without Flower: ./start.sh run --no-flower"
        fi
    fi

    if [[ "$ENABLE_FRONTEND" -eq 1 ]]; then
        kill_port_orphans "$FRONTEND_PORT"
        rm -rf "$FRONTEND_DIR/node_modules/.vite"
        local frontend_cmd=""
        if [[ -s "$NVM_DIR/nvm.sh" ]]; then
            frontend_cmd="export NVM_DIR='$NVM_DIR'; . '$NVM_DIR/nvm.sh'; nvm use '$FRONTEND_NODE_MAJOR' >/dev/null; npm run dev -- --host 0.0.0.0 --port '$FRONTEND_PORT'"
        else
            log_warn "nvm not found at $NVM_DIR/nvm.sh; using system node/npm for frontend."
            frontend_cmd="npm run dev -- --host 0.0.0.0 --port '$FRONTEND_PORT'"
        fi
        start_managed_process "frontend" "$FRONTEND_DIR" "$frontend_cmd"
    fi

    print_runtime_summary
}

cmd_stop() {
    stop_managed_process "frontend"
    stop_managed_process "flower"
    stop_managed_process "worker_nmt"
    stop_managed_process "worker_stt"
    stop_managed_process "worker_media"
    stop_managed_process "backend"
    stop_managed_process "minio"
    log_ok "Stop command completed."
}

print_service_status() {
    local name="$1"
    local pid_file
    pid_file="$(pid_file_for "$name")"
    if is_service_running "$name"; then
        local pid
        pid="$(<"$pid_file")"
        printf "%-12s : running (pid %s)\n" "$name" "$pid"
    else
        printf "%-12s : stopped\n" "$name"
    fi
}

cmd_status() {
    echo "Managed processes:"
    print_service_status "minio"
    print_service_status "backend"
    print_service_status "worker_media"
    print_service_status "worker_stt"
    print_service_status "worker_nmt"
    [[ "$ENABLE_FLOWER" -eq 1 ]] && print_service_status "flower"
    [[ "$ENABLE_FRONTEND" -eq 1 ]] && print_service_status "frontend"

    echo
    echo "System services:"
    printf "%-12s : %s\n" "redis" "$(systemctl is-active redis-server 2>/dev/null || echo unknown)"
    printf "%-12s : %s\n" "postgresql" "$(systemctl is-active postgresql 2>/dev/null || echo unknown)"

    echo
    echo "Port checks:"
    for port in "$BACKEND_PORT" "$FRONTEND_PORT" "$FLOWER_PORT" "$MINIO_PORT" "$MINIO_CONSOLE_PORT"; do
        if ss -ltn "( sport = :$port )" | grep -q ":$port"; then
            printf "%-12s : listening\n" "$port"
        else
            printf "%-12s : not-listening\n" "$port"
        fi
    done
}

cmd_logs() {
    ensure_runtime_dirs
    local target="${1:-all}"

    case "$target" in
        all)
            local files=()
            while IFS= read -r file; do
                files+=("$file")
            done < <(find "$LOG_DIR" -maxdepth 1 -type f -name '*.log' | sort)

            if [[ ${#files[@]} -eq 0 ]]; then
                die "No log files found in $LOG_DIR"
            fi
            tail -n 100 -f "${files[@]}"
            ;;
        backend|minio|worker_media|worker_stt|worker_nmt|flower|frontend)
            local file
            file="$(log_file_for "$target")"
            [[ -f "$file" ]] || die "Log file not found: $file"
            tail -n 100 -f "$file"
            ;;
        *)
            die "Unknown log target '$target'. Use: all, backend, minio, worker_media, worker_stt, worker_nmt, flower, frontend"
            ;;
    esac
}

parse_options() {
    POSITIONAL_ARGS=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --no-frontend)
                ENABLE_FRONTEND=0
                shift
                ;;
            --no-flower)
                ENABLE_FLOWER=0
                shift
                ;;
            --skip-migrations)
                RUN_MIGRATIONS=0
                shift
                ;;
            --debug)
                DEBUG_MODE=1
                shift
                ;;
            --help|-h)
                usage
                exit 0
                ;;
            --)
                shift
                while [[ $# -gt 0 ]]; do
                    POSITIONAL_ARGS+=("$1")
                    shift
                done
                ;;
            *)
                POSITIONAL_ARGS+=("$1")
                shift
                ;;
        esac
    done
}

main() {
    local cmd="${1:-help}"
    shift || true
    parse_options "$@"

    if [[ "$cmd" != "logs" && ${#POSITIONAL_ARGS[@]} -gt 0 ]]; then
        die "Unexpected argument(s) for '$cmd': ${POSITIONAL_ARGS[*]}"
    fi

    case "$cmd" in
        setup)
            cmd_setup
            ;;
        run)
            cmd_run
            ;;
        stop)
            cmd_stop
            ;;
        status)
            cmd_status
            ;;
        logs)
            cmd_logs "${POSITIONAL_ARGS[0]:-all}"
            ;;
        help|-h|--help)
            usage
            ;;
        *)
            usage
            die "Unknown command: $cmd"
            ;;
    esac
}

main "$@"
