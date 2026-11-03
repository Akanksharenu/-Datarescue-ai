# DataRescue AI backend. Built and run by docker-compose.yml at the repo root.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so code changes do not invalidate this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

EXPOSE 8000

# Configuration comes from environment variables (see backend/.env.example).
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
