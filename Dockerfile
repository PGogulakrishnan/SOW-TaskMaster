# SOW-TaskMaster — Cloud Run container
# Built remotely by gcloud run deploy --source . (Cloud Build), no local docker needed.
FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source
COPY . .

# Cloud Run injects $PORT (default 8080). Listen on 0.0.0.0 so the
# platform's health checks can reach the app.
ENV WEB_HOST=0.0.0.0
EXPOSE 8080

# uvicorn entrypoint (web_app.py exposes the FastAPI `app`)
CMD ["sh", "-c", "exec python -m uvicorn web_app:app --host 0.0.0.0 --port ${PORT:-8080}"]