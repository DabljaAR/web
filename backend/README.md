# DabljaAR Backend

This directory contains the backend server code for the DabljaAR web platform, built using FastAPI and PostgreSQL.

## Project Structure

- `app/`: Main application code including models, routes, and configuration.
    - `core/`: Core application logic and utilities.
    - `stt/`: Speech-to-text related modules.
    - `nmt/`: Neural machine translation related modules.
    - `tts/`: Text-to-speech related modules.
- `db/`: Database migration files and scripts.
- `tests/`: Unit and integration tests for the backend.

```bash
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app entry point, mounts all routers
│   ├── config.py                   # App configuration (env vars, settings)
│   ├── dependencies.py             # Shared dependencies (db session, auth, etc.)
│   │
│   ├── core/                       # Core website logic module
│   │   ├── __init__.py
│   │   ├── router.py               # Core routes (login, signup, profile, homepage)
│   │   ├── schemas.py              # Pydantic models for core
│   │   ├── models.py               # SQLAlchemy/ORM models for users, etc.
│   │   ├── services.py             # Business logic (auth, user management)
│   │   ├── repository.py           # Data access layer
│   │   └── exceptions.py           # Core-specific exceptions
│   │
│   ├── stt/                        # Speech-to-Text module
│   ├── nmt/                        # Neural Machine Translation module
│   ├── tts/                        # Text-to-Speech module
│   │
│   └── shared/                     # Shared utilities across modules
│       ├── __init__.py
│       ├── database.py             # Database connection setup
│       ├── security.py             # Auth utilities (JWT, hashing)
│       ├── middleware.py           # Custom middleware
│       └── utils.py                # Common helper functions
│
├── db/
│   └── migrations/                 # dbmate migration files
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Pytest fixtures
│
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

## Setup Instructions

**Prerequisites**
- Python 3.10+
- PostgreSQL database

**Installation**
1. Clone the repository:
    ```bash
    git clone https://github.com/yourusername/dabljaAR.git
    cd dabljaAR/web/backend
    ```
2. Create a virtual environment and activate it:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```
3. Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4. Set up the database:
    ```bash
    alembic upgrade head
    ```
5. Start the development server:
    ```bash
    uvicorn app.main:app --reload
    ```

### Environment Variables

To run the application, you need to set the following environment variables:

- `DATABASE_URL`: The database connection URL.
- `SECRET_KEY`: A secret key used for encryption and authentication.

You can create a `.env` file in the root of the project and add the variables there:

```env
DATABASE_URL=postgresql://user:password@localhost/dbname
SECRET_KEY=your_secret_key
```

### Development Commands

To generate new database migrations after making changes to the models, use:

```bash
alembic revision --autogenerate -m "Your migration message"
alembic upgrade head
```

### Running Tests
To run the tests, use the following command:

```bash
pytest tests/
```

## License
This project is licensed under the MIT License. See the LICENSE file for details.