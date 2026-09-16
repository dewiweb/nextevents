FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY generate_slides.py webui.py ./

ENV OUT_DIR=/data \
    PORT=8080

EXPOSE 8080
VOLUME /data

CMD ["python", "webui.py"]
