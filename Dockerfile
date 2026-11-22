# Slim, multi-stage image. The runtime user is non-root (uid 10001).
# The entrypoint is root only long enough to chown the data volume, then drops privileges.

FROM python:3.11-slim AS builder

WORKDIR /build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# INSTALL_AWS=true adds langchain-aws + boto3 for LLM_PROVIDER=bedrock
# (docker build --build-arg INSTALL_AWS=true .). Off by default to keep the image small.
ARG INSTALL_AWS=false

COPY requirements.txt requirements-aws.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_AWS" = "true" ]; then \
         /opt/venv/bin/pip install --no-cache-dir -r requirements-aws.txt; \
       fi

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data \
    PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data

COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY static ./static
COPY docker-entrypoint.sh /docker-entrypoint.sh

RUN chmod 755 /docker-entrypoint.sh \
    && chown -R appuser:appuser /app

EXPOSE 8000
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
