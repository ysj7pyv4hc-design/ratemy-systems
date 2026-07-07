FROM python:3.11-slim

# Non-root runtime user (defense in depth)
RUN useradd --create-home --shell /usr/sbin/nologin rms

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary==2.9.9

COPY app/ ./app/
COPY config/ ./config/
COPY public/ ./public/

# Fallback SQLite dir (prod uses DATABASE_URL=postgresql://…)
RUN mkdir -p /app/data && chown -R rms:rms /app

ENV PORT=8080 RMS_ENV=prod
EXPOSE 8080
USER rms

# Bind whatever port the platform assigns ($PORT on Railway/Render/etc.), fall back to 8080.
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
