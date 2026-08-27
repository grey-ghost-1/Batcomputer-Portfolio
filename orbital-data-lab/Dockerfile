FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY orbital-data-lab /app/orbital-data-lab
RUN useradd --create-home orbital && mkdir /data && chown -R orbital:orbital /app /data
USER orbital
WORKDIR /app/orbital-data-lab
EXPOSE 8010
CMD ["sh", "-c", "uvicorn orbital_lab.api:app --host 0.0.0.0 --port ${PORT:-8010}"]
