FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend/realtime/src \
    REALTIME_HOST=0.0.0.0 \
    REALTIME_PORT=8081
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY src/ /app/backend/realtime/src/
# Private Compose secrets may be owner0600. Compose selects a matching uid/gid;
# no capabilities or privilege escalation are needed by this runtime.
EXPOSE 8081
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('REALTIME_PORT','8081')+'/health/ready',timeout=4)" || exit 1
CMD ["python", "-m", "hine_realtime"]
