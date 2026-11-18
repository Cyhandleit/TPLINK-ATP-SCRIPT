# TP-Link ATP automated testing — Dockerized base image
# Based on Microsoft official Playwright Python image, built-in Chromium and system dependencies
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Lock Python dependencies, ensure build reproducibility
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium && \
    playwright install-deps chromium

# curl: for HEALTHCHECK (http://127.0.0.1:5000/) and container troubleshooting, install single package only, keep lightweight
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Application code
COPY atp_engine.py atp_web.py known_issues.md ./

# Flask debug off by default in production (fixes SEC-03), can enable via ATP_DEBUG=1
RUN sed -i 's/debug=True/debug=False/' atp_web.py

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    ATP_DEBUG=0

ENTRYPOINT ["/entrypoint.sh"]
# Default starts Web UI; single-service image, all stages can be executed via Web API /api/run inside container
CMD ["python", "atp_web.py"]
