FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend

RUN mkdir -p /app/backend/uploads

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn backend.app.main:app --host ${APP_HOST:-0.0.0.0} --port ${APP_PORT:-8000}"]
