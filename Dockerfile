FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

RUN mkdir -p /data && useradd -r -u 1000 botuser && chown -R botuser:botuser /app /data
USER botuser

ENV STATE_FILE=/data/state.json
ENV PYTHONUNBUFFERED=1

CMD ["python", "-u", "bot.py"]
