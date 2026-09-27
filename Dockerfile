FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY VERSION /app/VERSION
ENV PYTHONUNBUFFERED=1
EXPOSE 8090
CMD ["gunicorn","--bind","0.0.0.0:8090","--workers","1","--timeout","120","app.app:app"]
