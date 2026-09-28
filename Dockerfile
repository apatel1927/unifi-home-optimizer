FROM python:3.12-slim
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && curl -fsSL https://packagecloud.io/install/repositories/ookla/speedtest-cli/script.deb.sh | bash \
 && apt-get install -y --no-install-recommends speedtest \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY VERSION /app/VERSION
RUN python -m py_compile app/*.py
ENV PYTHONUNBUFFERED=1
EXPOSE 8090
CMD ["gunicorn","--bind","0.0.0.0:8090","--workers","1","--timeout","120","app.app:app"]
