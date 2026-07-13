FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
# Shell form (not exec-form array) so $PORT gets expanded — Cloud Run
# injects its own PORT (usually 8080) and requires the container to listen
# on it; falls back to 8000 for local `docker run` / docker-compose.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
