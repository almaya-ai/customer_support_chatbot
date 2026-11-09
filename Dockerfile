FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py store.py answers.py ./
COPY templates ./templates
COPY static ./static
USER nobody
CMD exec gunicorn --bind "0.0.0.0:${PORT:-8080}" --workers 1 --threads 4 --timeout 45 'main:create_app()'
