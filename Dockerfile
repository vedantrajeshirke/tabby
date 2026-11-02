FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api ./api
COPY core ./core
COPY config ./config
COPY fixtures/mock_extractions ./fixtures/mock_extractions

RUN useradd --create-home app && mkdir -p data && chown app data
USER app

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
