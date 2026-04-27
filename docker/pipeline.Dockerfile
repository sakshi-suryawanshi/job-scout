FROM python:3.11-slim

WORKDIR /app

# System deps: Playwright needs Chromium dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2-dev libxslt1-dev curl \
    # Chromium system deps
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright + Chromium browser
RUN playwright install chromium && playwright install-deps chromium

COPY . .

ENV PYTHONPATH=/app

# Default: run the scheduler (blocks forever, fires at PIPELINE_RUN_TIME)
# Override with --now for a one-shot run
ENTRYPOINT ["python", "-m", "job_scout.pipeline.scheduler"]
