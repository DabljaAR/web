# Docker Setup Guide

This guide explains how to set up and run the Dabljaar application using Docker.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (version 20.10 or higher)
- [Docker Compose](https://docs.docker.com/compose/install/) (version 2.0 or higher)

## Architecture Overview

The application consists of three services:

| Service    | Technology       | Container Name      | Port  |
|------------|------------------|---------------------|-------|
| Database   | PostgreSQL 16    | dabljaar_postgres   | 5433  |
| Backend    | FastAPI (Python) | dabljaar_backend    | 8000  |
| Frontend   | React (Vite)     | dabljaar_frontend   | 5173  |

## Quick Start

### 1. Clone and Navigate to the Project

```bash
cd /path/to/web
```

### 2. Set Environment Variables (Optional)

Create a `.env` file in the root directory for production secrets:

```bash
# .env
SECRET_KEY=your-super-secure-secret-key-here
```

### 3. Build and Start All Services

```bash
# Build and start all containers
docker-compose up --build

# Or run in detached mode (background)
docker-compose up --build -d
```

### 4. Access the Application

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5433 (external access)

## Docker Commands Reference

### Starting Services

```bash
# Start all services
docker-compose up

# Start in detached mode
docker-compose up -d

# Start specific service
docker-compose up backend

# Build and start (use after code changes to Dockerfile)
docker-compose up --build
```

### Stopping Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes database data)
docker-compose down -v

# Stop specific service
docker-compose stop backend
```

### Viewing Logs

```bash
# View all logs
docker-compose logs

# Follow logs in real-time
docker-compose logs -f

# View logs for specific service
docker-compose logs backend
docker-compose logs -f postgres
```

### Managing Containers

```bash
# List running containers
docker-compose ps

# Restart a service
docker-compose restart backend

# Execute command in running container
docker-compose exec backend bash
docker-compose exec postgres psql -U postgres -d dabljaar
```

### Rebuilding

```bash
# Rebuild all images
docker-compose build

# Rebuild without cache
docker-compose build --no-cache

# Rebuild specific service
docker-compose build backend
```

## Database Management

### Access PostgreSQL CLI

```bash
docker-compose exec postgres psql -U postgres -d dabljaar
```

### Run Database Migrations

```bash
# Execute Alembic migrations inside the backend container
docker-compose exec backend alembic upgrade head
```

### Create a New Migration

```bash
docker-compose exec backend alembic revision --autogenerate -m "description"
```

### Reset Database

```bash
# Stop containers and remove volumes
docker-compose down -v

# Start fresh
docker-compose up --build
```

## Development Workflow

### Hot Reloading

- **Backend**: The backend volume mount (`./backend:/app`) enables hot reloading. Changes to Python files are reflected immediately.
- **Frontend**: For development hot reloading, you may want to run the frontend locally with `npm run dev` instead of using Docker.

### Running Backend Only (with local frontend)

```bash
# Start only postgres and backend
docker-compose up postgres backend
```

### Running Tests

```bash
# Run backend tests
docker-compose exec backend pytest

# Run with coverage
docker-compose exec backend pytest --cov=app
```

## Troubleshooting

### Common Issues

#### 1. Port Already in Use

```
Error: Bind for 0.0.0.0:8000 failed: port is already allocated
```

**Solution**: Stop the conflicting service or change the port in `docker-compose.yaml`:

```yaml
ports:
  - "8001:8000"  # Use different external port
```

#### 2. PostgreSQL Role Does Not Exist

```
FATAL: role "postgres" does not exist
```

**Solution**: The database volume has corrupted state. Reset it:

```bash
docker-compose down -v
docker volume rm dabljaar_postgres_data
docker-compose up --build
```

#### 3. Module Not Found / Import Errors

**Solution**: Rebuild the container to reinstall dependencies:

```bash
docker-compose build --no-cache backend
docker-compose up
```

#### 4. Permission Denied Errors

**Solution**: The container runs as non-root user. Ensure proper file ownership:

```bash
sudo chown -R $USER:$USER ./backend
```

#### 5. Container Keeps Restarting

Check the logs to identify the issue:

```bash
docker-compose logs backend
```

### Health Checks

The services include health checks:

- **PostgreSQL**: Checks if the database is ready to accept connections
- **Backend**: HTTP check on `/api/health` endpoint

View health status:

```bash
docker-compose ps
```

## Environment Variables

### Backend Environment Variables

| Variable                     | Default                          | Description                    |
|------------------------------|----------------------------------|--------------------------------|
| `DATABASE_URL`               | postgresql+asyncpg://...         | Database connection string     |
| `SECRET_KEY`                 | your-secret-key-change-this...   | JWT signing key                |
| `ALGORITHM`                  | HS256                            | JWT algorithm                  |
| `ACCESS_TOKEN_EXPIRE_MINUTES`| 15                               | Access token expiry (minutes)  |
| `REFRESH_TOKEN_EXPIRE_DAYS`  | 7                                | Refresh token expiry (days)    |

### PostgreSQL Environment Variables

| Variable            | Default   | Description           |
|---------------------|-----------|-----------------------|
| `POSTGRES_USER`     | postgres  | Database username     |
| `POSTGRES_PASSWORD` | postgres  | Database password     |
| `POSTGRES_DB`       | dabljaar  | Database name         |

## Production Considerations

### Security

1. **Change default passwords**: Update PostgreSQL credentials
2. **Set a strong SECRET_KEY**: Use a cryptographically secure random string
3. **Use HTTPS**: Configure a reverse proxy (nginx/traefik) with SSL
4. **Limit port exposure**: Remove external port mappings for postgres in production

### Example Production Changes

```yaml
# docker-compose.prod.yaml
services:
  postgres:
    ports: []  # Remove external port exposure
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}  # Use environment variable

  backend:
    environment:
      SECRET_KEY: ${SECRET_KEY}
      DATABASE_URL: postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@postgres:5432/dabljaar
```

### Using Production Compose File

```bash
docker-compose -f docker-compose.yaml -f docker-compose.prod.yaml up -d
```

## Volumes

| Volume Name             | Purpose                        |
|-------------------------|--------------------------------|
| `dabljaar_postgres_data`| Persistent PostgreSQL data     |

## Networks

All services communicate through the `dabljaar_network` bridge network. Services can reach each other using their service names as hostnames (e.g., `postgres`, `backend`).
