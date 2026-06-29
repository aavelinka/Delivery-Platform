FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/auth-service/pyproject.toml .
COPY services/auth-service/app ./app
COPY services/auth-service/alembic ./alembic
COPY services/auth-service/alembic.ini .

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
