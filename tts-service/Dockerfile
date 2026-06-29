FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY tts-service/requirements.txt .
RUN pip install --default-timeout=600 -r requirements.txt

COPY tts-service/app ./app

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

EXPOSE 8003

CMD ["python", "-m", "app.main"]
