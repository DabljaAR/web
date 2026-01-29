# GEMINI.md

## Project Overview

This project is the backend for the DabljaAR web platform. It's a FastAPI application written in Python, using a PostgreSQL database for data storage. The project follows a modular architecture, with the core logic separated into a `core` module. It uses SQLAlchemy for database interaction, Alembic for database migrations, and Pydantic for data validation.

The API provides endpoints for user authentication (signup, login, token refresh) and user management (CRUD operations on users).

## Building and Running

### Prerequisites

*   Python 3.10+
*   PostgreSQL database

### Setup Instructions

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/dabljaAR.git
    cd dabljaAR/web/backend
    ```

2.  **Create a virtual environment and activate it:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up the database:**
    *   Create a `.env` file in the project root and add the following environment variables:
        ```env
        DATABASE_URL=postgresql://user:password@localhost/dbname
        SECRET_KEY=your_secret_key
        ```
    *   Run database migrations:
        ```bash
        alembic upgrade head
        ```

5.  **Run the development server:**
    ```bash
    uvicorn app.main:app --reload
    ```
    The application will be available at `http://127.0.0.1:8000`.

## Running Tests

To run the tests, use the following command:
```bash
pytest tests/
```

## Containerization

The project is fully containerized using Docker and Docker Compose. To run the application and the database in Docker containers, you can use the following command:

```bash
docker-compose up -d
```

This will build the application image, start the PostgreSQL database, and run the application. The application will be available at `http://127.0.0.1:8000`.

To stop the containers, use:

```bash
docker-compose down
```

## Development Conventions

*   **Code Style:** The project uses `ruff` for linting.
*   **API Documentation:** The API is documented using OpenAPI, and the documentation is available at `http://127.0.0.1:8000/docs` when the application is running.
*   **Database Migrations:** Database migrations are handled by Alembic. To create a new migration script, use the following command:
    ```bash
    alembic revision --autogenerate -m "A descriptive message about the migration"
    ```
    This will generate a new migration script in the `alembic/versions` directory. You should review the generated script before applying it.

    To apply the migrations to the database, use the following command:
    ```bash
    alembic upgrade head
    ```

*   **Dependencies:** Project dependencies are managed in the `requirements.txt` file.
