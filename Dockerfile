# GKG: one image, one process. uvicorn serves the web pages and the watch API.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GKG_DATA_DIR=/data \
    TZ=Europe/Ljubljana

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY VERSION ./
COPY app ./app

RUN useradd --system --uid 10001 gkg && mkdir -p /data && chown gkg:gkg /data
USER gkg
EXPOSE 8791
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8791/api/health', timeout=4).status == 200 else 1)"
# --proxy-headers without --forwarded-allow-ips: the client address is taken from
# X-Real-IP (set by NPM) in the app, for rate limits only.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8791", "--no-server-header"]
