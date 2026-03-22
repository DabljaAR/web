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
│   │   ├── routers/                # Sub-routers for different entities
│   │       ├── subscription_plan.py
│   │       ├── user_subscription.py
│   │       ├── payment.py
│   │       └── recipe.py
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
    *   Create a `.env` file in the project root and add the following environment variables:
        ```env
        DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/dabljaar
        SECRET_KEY=your_secret_key
        ```
    *   Run database migrations:
        ```bash
        alembic upgrade head
        ```
5. Start the development server:
    ```bash
    uvicorn app.main:app --reload
    ```
    The application will be available at `http://127.0.0.1:8000`.

6. MinIO Storage Setup

- Installation (Once)

```bash
wget https://dl.min.io/server/minio/release/linux-amd64/minio -O minio \
&& chmod +x minio \
&& sudo mv minio /usr/local/bin/ \
&& mkdir -p ~/minio-data
```

- Add this to your `.env` file

```env
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_NAME=dablajaar
MINIO_SECURE=false
```

- Start MinIO (every time before running backend)

```bash
export MINIO_ROOT_USER=minioadmin
export MINIO_ROOT_PASSWORD=minioadmin
minio server ~/minio-data --console-address ":9001"
```

- Open MinIO Dashboard

http://localhost:9001

- Login with:

Username: minioadmin  
Password: minioadmin

## Background Tasks (Celery)

The project uses Celery for asynchronous task processing (STT, NMT, TTS, etc.) with Redis as the broker.

### Running Celery Worker

1.  **Ensure Redis is running** (default: `localhost:6379`).
2.  Start the worker:
    ```bash
    export PYTHONPATH=$PYTHONPATH:.
    .venv/bin/python3 -m celery -A app.jobs.celery_app worker --loglevel=info -Q ai_tts,ai_nmt,pipeline,media,ai_stt
    ```

### Monitoring with Flower

Flower provides a real-time web dashboard for monitoring Celery tasks.

1.  Start Flower:
    ```bash
    export PYTHONPATH=$PYTHONPATH:.
    .venv/bin/python3 -m celery -A app.jobs.celery_app flower --port=5555
    ```
2.  Open the Flower Dashboard:
    [http://localhost:5555](http://localhost:5555)


 /home/eslam/Desktop/dablaja2/dablaja/web/.venv/bin/python /home/eslam/Desktop/dablaja2/dablaja/web/nmt/demo_translation.py



<!-- 
/home/eslam/Desktop/dablaja2/dablaja/web/.venv/bin/python /home/eslam/Desktop/dablaja2/dablaja/web/nmt/demo_translation.py





/home/eslam/Desktop/dablaja2/dablaja/web/.venv/bin/python /home/eslam/Desktop/dablaja2/dablaja/web/nmt/demo_finetuned.py



 -->
## API Endpoints

### User Endpoints (`/api/users`)
- `POST /api/signup`: Register a new user.
- `POST /api/login`: Authenticate user and get access/refresh tokens.
- `POST /api/auth/refresh`: Refresh access token using refresh token.
- `GET /api/users/{user_id}`: Get a user by ID.
- `GET /api/users`: List all users with pagination.
- `PUT /api/users/{user_id}`: Update a user's information.
- `DELETE /api/users/{user_id}`: Delete a user by ID.
- `GET /api/health`: Simple health check endpoint.

### Subscription Plan Endpoints (`/api/subscription-plans`)
- `POST /api/subscription-plans/`: Create a new subscription plan.
- `GET /api/subscription-plans/{plan_id}`: Get a subscription plan by ID.
- `GET /api/subscription-plans/`: List all subscription plans with pagination.
- `PUT /api/subscription-plans/{plan_id}`: Update a subscription plan.
- `DELETE /api/subscription-plans/{plan_id}`: Delete a subscription plan.

### User Subscription Endpoints (`/api/user-subscriptions`)
- `POST /api/user-subscriptions/`: Create a new user subscription.
- `GET /api/user-subscriptions/{subscription_id}`: Get a user subscription by ID.
- `GET /api/user-subscriptions/`: List all user subscriptions with pagination.
- `PUT /api/user-subscriptions/{subscription_id}`: Update a user subscription.
- `DELETE /api/user-subscriptions/{subscription_id}`: Delete a user subscription.

### Payment Endpoints (`/api/payments`)
- `POST /api/payments/`: Create a new payment.
- `GET /api/payments/{payment_id}`: Get a payment by ID.
- `GET /api/payments/`: List all payments with pagination.
- `PUT /api/payments/{payment_id}`: Update a payment.
- `DELETE /api/payments/{payment_id}`: Delete a payment.

### Recipe Endpoints (`/api/recipes`)
- `POST /api/recipes/`: Create a new recipe.
- `GET /api/recipes/{recipe_id}`: Get a recipe by ID.
- `GET /api/recipes/`: List all recipes with pagination.
- `PUT /api/recipes/{recipe_id}`: Update a recipe.
- `DELETE /api/recipes/{recipe_id}`: Delete a recipe.

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