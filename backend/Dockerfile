FROM python:3.12-slim

# opencv (pulled in by rapidocr) needs libGL/glib at runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ARG WITH_ML=false
WORKDIR /app
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$WITH_ML" = "true" ]; then \
         pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
         && pip install --no-cache-dir -r requirements-ml.txt; \
       fi

COPY rag ./rag
COPY eval ./eval
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app /data
USER app

ENV DATA_DIR=/data PYTHONUNBUFFERED=1
EXPOSE 8000
# Only nginx (frontend container) can reach this port, so its X-Forwarded-For (the visitor's
# address) is trusted: rate limits then apply per visitor, not to nginx as a whole.
CMD ["uvicorn", "rag.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
