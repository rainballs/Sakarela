FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

# Copy in only requirements to leverage Docker cache
COPY requirements.txt ./

# Install OS packages for C-extensions AND dos2unix for LF normalization
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
      dos2unix \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Copy entrypoint and helper, normalize line endings & make executable
COPY wait-for-it.sh entrypoint.sh ./
RUN dos2unix wait-for-it.sh entrypoint.sh && \
    chmod +x wait-for-it.sh entrypoint.sh

# Copy the rest of your app
COPY . .

EXPOSE 8000

ENTRYPOINT ["D:\Sakarela_test_for_backup\Sakarela_DJANGO\entrypoint.sh"]
