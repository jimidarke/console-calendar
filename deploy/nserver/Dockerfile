# Build context = repo root (../..) so we can copy cc_env.py alongside cal-quickadd/.
# Build with:  docker compose -f deploy/nserver/docker-compose.yml build
FROM python:3.12-slim

WORKDIR /app

COPY cal-quickadd/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cc_env.py /app/cc_env.py
COPY cal-quickadd/app/ /app/app/

EXPOSE 8419

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8419"]
