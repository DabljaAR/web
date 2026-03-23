#!/bin/bash
# start.sh - Single script to run the DabljaAR platform services (Host Linux optimized)

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting DabljaAR Development Stack (Native Local Mode)...${NC}"

# Check for .venv in backend
if [ ! -d "backend/.venv" ]; then
    echo -e "${RED}Error: backend/.venv not found! Please create it first.${NC}"
    exit 1
fi

# Function to kill all backgrounds on exit
cleanup() {
    echo -e "\n${BLUE}Stopping all services...${NC}"
    PIDS=$(jobs -p)
    if [ -n "$PIDS" ]; then
        # Send SIGQUIT for cold shutdown (instant exit, tasks stay in queue thanks to late_acks)
        kill -s SIGQUIT $PIDS 2>/dev/null
        sleep 2
        # Force kill any remaining jobs
        kill -9 $PIDS 2>/dev/null
    fi
    exit
}
trap cleanup SIGINT SIGTERM EXIT

# --- PRE-START CLEANUP ---
# Kill any lingering processes from previous failed runs to avoid port conflicts
echo -e "${GREEN}Cleaning up old services...${NC}"
# Kill Celery workers
pkill -f "celery -A app.jobs.celery_app worker" 2>/dev/null
# Kill Backend / Uvicorn
pkill -f "uvicorn app.main:app" 2>/dev/null
# Kill Flower
pkill -f "celery -A app.jobs.celery_app flower" 2>/dev/null
# Kill Vite (Frontend dev server)
pkill -f "vite" 2>/dev/null

# Force kill anything on our specific ports if still running
for port in 8000 5173 5555 9000 9001; do
    fuser -k ${port}/tcp 2>/dev/null
done
sleep 1

# 0. Start Redis if not already running
if ! pgrep -x "redis-server" > /dev/null; then
    echo -e "${GREEN}Starting Redis Server...${NC}"
    redis-server --daemonize yes
fi

# Ensure logs directory exists
mkdir -p backend/logs

cd ~
MINIO_ROOT_USER=minioadmin MINIO_ROOT_PASSWORD=minioadmin \
  nohup ./minio server ./minio-data --console-address ":9001" \
  > ~/minio.log 2>&1 &
echo "✅ MinIO started (log: ~/minio.log)"
sleep 5 # Give MinIO time to initialize

# 2. Start Backend (FastAPI)
echo -e "${GREEN}Starting Backend API...${NC}"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
source backend/.venv/bin/activate
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 > logs/backend.log 2>&1 &
BACKEND_PID=$!

# 3. Start Celery Workers
echo -e "${GREEN}Starting STT Worker (Concurrency=1)...${NC}"
celery -A app.jobs.celery_app worker --loglevel=info -Q ai_stt --concurrency=2 --max-tasks-per-child=1000 --hostname=worker-stt@%h > logs/worker_stt.log 2>&1 &

echo -e "${GREEN}Starting NMT/Pipeline Worker (Concurrency=3)...${NC}"
celery -A app.jobs.celery_app worker --loglevel=info -Q ai_nmt,ai_tts,pipeline --concurrency=2 --max-tasks-per-child=1000 --hostname=worker-nmt@%h > logs/worker_nmt.log 2>&1 &

# echo -e "${GREEN}Starting Media Worker...${NC}"
# celery -A app.jobs.celery_app worker --loglevel=info -Q media --concurrency=2 --hostname=worker-media@%h > logs/worker_media.log 2>&1 &

# 4. Start Flower (Dashboard)
echo -e "${GREEN}Starting Flower Dashboard...${NC}"
export FLOWER_UNAUTHENTICATED_API=true
celery -A app.jobs.celery_app flower --port=5555 > logs/flower.log 2>&1 &

cd ..

# 5. Start Frontend (React/Vite)
# echo -e "${GREEN}Starting Frontend...${NC}"
# cd frontend
# npm run dev  &
# cd ..

echo -e "\n${GREEN}==================================================${NC}"
echo -e "${GREEN}All services are running in the background!${NC}"
echo -e "${BLUE}Frontend:   http://localhost:5173${NC}"
echo -e "${BLUE}Backend:    http://localhost:8000/docs${NC}"
echo -e "${BLUE}Flower:     http://localhost:5555   (Worker Monitoring)${NC}"
echo -e "${BLUE}MinIO Console: http://localhost:9001${NC}"
echo -e "${GREEN}==================================================${NC}"
echo -e "Logs are being saved to ${BLUE}backend/logs/*.log${NC}"
echo -e "To tail STT logs: ${GREEN}tail -f backend/logs/worker_stt.log${NC}"
echo -e "Press ${RED}Ctrl+C${NC} to stop all services."

# Wait for all background processes
wait
