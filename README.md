# web
The main web platform for the DabljaAR website.

## Structure
- `backend/`: Contains the backend server code.
- `frontend/`: Contains the frontend client code.
Each subdirectory has its own README file with specific instructions and details.

## Setup Instructions
Please refer to the README files in the `backend/` and `frontend/` directories for setup instructions for each component.
- `backend/README.md`: Instructions for setting up and running the backend server.
- `frontend/README.md`: Instructions for setting up and running the frontend client.

## Quick Start (Ubuntu 22.04 Native Dev)

Use the root `start.sh` script to bootstrap and run the local stack natively:

```bash
# From project root
./start.sh setup
./start.sh run
```

Useful commands:

```bash
./start.sh status
./start.sh logs backend
./start.sh logs all
./start.sh stop
```

Optional flags:

```bash
./start.sh setup --skip-migrations
./start.sh run --no-frontend --no-flower
```

The script is idempotent and manages local runtime files under `.runtime/`.

## Technologies Used
- Backend: Python, FastAPI, dbmate, PostgreSQL
- Frontend: Typescript, React, Vite, Tailwind CSS

## Quick Start (with docker-compose)

1. Ensure you have Docker and Docker Compose installed on your machine.
2. Navigate to the `web/` directory.
3. Run the following command to start both the backend and frontend services:
   ```bash
   docker-compose up --build
   ```
4. Access the frontend at `http://localhost:5173` and the backend API at `http://localhost:3000`.

## Production (Docker Compose + Caddy)

```bash
cp .env.production.example .env.production
# Edit .env.production and set DOMAIN and secrets

docker compose --env-file .env.production \
   -f docker-compose.yaml -f docker-compose.prod.yml up -d --build
```

Optional GPU overlay for AI worker:

```bash
docker compose --env-file .env.production \
   -f docker-compose.yaml -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d --build
```
