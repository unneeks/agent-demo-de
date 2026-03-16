FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x scripts/setup.sh scripts/run_demo.sh

EXPOSE 8000

CMD ["uvicorn", "agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
