FROM python:3.12-slim-bookworm

WORKDIR /app

# zoneinfo : requis pour le scheduler (TZ) et les dates OpenAgenda —
# absent de python:*-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY generate_slides.py webui.py ./
COPY nextevents/ nextevents/
COPY assets/ assets/

ENV OUT_DIR=/data \
    PORT=8080

EXPOSE 8080
VOLUME /data

CMD ["python", "webui.py"]
