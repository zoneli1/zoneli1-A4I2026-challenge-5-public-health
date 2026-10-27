FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    GOOGLE_GENAI_USE_VERTEXAI=1 \
    GOOGLE_CLOUD_PROJECT=qwiklabs-gcp-04-f5825262a0a0 \
    GOOGLE_CLOUD_LOCATION=global \
    A4I_DATASET=a4i_health \
    A4I_MODEL=gemini-3.6-flash

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/ ./agent/
COPY frontend/ ./frontend/
COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY app.py .

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
