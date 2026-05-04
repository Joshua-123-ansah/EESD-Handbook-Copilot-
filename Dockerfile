# Python 3.12 + handbook app (chat, portfolio, voice)
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY portfolio ./portfolio
COPY imgs ./imgs

# Required for RAG. Add this file to the repo (or build context) before deploying.
COPY EESD_Handbook_2024-2025AY-FINAL.pdf ./

ENV CHROMA_DIR=/app/chroma_data

EXPOSE 8000

# Render and other hosts set PORT; default 8000 for local Docker run.
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
