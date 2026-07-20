FROM python:3.12-slim

WORKDIR /app

COPY libs/platform-common ./libs/platform-common
RUN pip install --no-cache-dir ./libs/platform-common

COPY services/admin-service/pyproject.toml .
COPY services/admin-service/app ./app

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
