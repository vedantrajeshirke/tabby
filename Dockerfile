FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
# One thread: on a small shared CPU, Tesseract's extra threads only slow it down.
ENV OMP_THREAD_LIMIT=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api ./api
COPY core ./core
COPY config ./config
COPY scripts ./scripts
COPY fixtures/mock_extractions ./fixtures/mock_extractions

RUN useradd --create-home app
USER app

# Hosts choose the port through PORT.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
