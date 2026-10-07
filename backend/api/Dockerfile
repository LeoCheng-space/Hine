FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY backend/api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt
COPY backend/api/src /app/api/src
COPY backend/api/migrations /app/api/migrations
COPY backend/realtime/src /app/realtime/src
ENV PYTHONPATH=/app/api/src:/app/realtime/src
EXPOSE 8080
CMD ["python", "-m", "hine_api"]
