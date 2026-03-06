FROM python:3.11-slim

# Install Poetry
RUN pip install --no-cache-dir poetry==1.8.3

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml poetry.lock* ./

# Install dependencies only (no project package needed)
RUN poetry config virtualenvs.create false \
    && poetry lock --no-update \
    && poetry install --only main --no-interaction --no-ansi

COPY . .

# Run as non-root for container security
RUN adduser --disabled-password --gecos "" appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
