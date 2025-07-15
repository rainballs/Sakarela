# Build stage
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      gcc \
      python3-dev \
      libpq-dev \
      libssl-dev \
      libffi-dev \
      libxml2-dev \
      libxslt1-dev \
      libjpeg-dev \
      zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

# Install runtime dependencies including netcat
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      libpq-dev \
      libssl-dev \
      libffi-dev \
      libxml2-dev \
      libxslt1-dev \
      libjpeg-dev \
      zlib1g-dev \
      dos2unix \
      netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy entrypoint and helper, normalize line endings & make executable
COPY wait-for-it.sh entrypoint.sh ./
RUN dos2unix wait-for-it.sh entrypoint.sh && \
    chmod +x wait-for-it.sh entrypoint.sh

# Copy the rest of the app
COPY . .

EXPOSE 8000

ENTRYPOINT ["/usr/src/app/entrypoint.sh"]