FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY libs/platform-common ./libs/platform-common
RUN pip install --no-cache-dir ./libs/platform-common

COPY services/api-gateway/pyproject.toml .
COPY services/api-gateway/app ./app

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
