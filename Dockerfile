# ====== builder ======
FROM python:3.12-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    binutils \
    libproj-dev \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --upgrade pip && pip wheel --no-cache-dir --no-deps -r requirements.txt -w /wheels

# ====== runtime ======
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN adduser --disabled-password --gecos "" appuser
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    gdal-bin \
    libproj-dev \
    libgdal-dev \
    proj-bin \
    libgeos-c1v5 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache /wheels/* && rm -rf /wheels
COPY . .
ENV DJANGO_SETTINGS_MODULE=config.settings
RUN python manage.py collectstatic --noinput
USER appuser
EXPOSE 8000
# default command pode ser sobrescrito no compose
CMD ["gunicorn","config.wsgi:application","-b","0.0.0.0:8000","--workers","3","--timeout","60"]

