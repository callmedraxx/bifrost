# Bifrost — never-refuse bridge. Pure stdlib, so the base image is all we need.
FROM python:3.12-slim

WORKDIR /app
COPY bifrost/ ./bifrost/
COPY run.py ./

# Listen on all interfaces inside the container; publish via compose.
ENV BIFROST_HOST=0.0.0.0 \
    BIFROST_PORT=8088 \
    PYTHONUNBUFFERED=1

EXPOSE 8088

# Lightweight liveness probe against /health.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8088/health',timeout=2).status==200 else 1)"

CMD ["python3", "run.py"]
