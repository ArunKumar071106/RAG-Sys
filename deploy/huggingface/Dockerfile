# Arivazhai backend on Hugging Face Spaces (Docker SDK). scripts/deploy_hf_space.py uploads this file to the
# Space's root together with backend/ and data/processed/; the vectors stay in Qdrant Cloud.
FROM python:3.12-slim

# opencv (pulled in by rapidocr) needs libGL/glib at import time
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Spaces run the container as uid 1000
RUN useradd --create-home --uid 1000 user
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# the search model in the image, so a start does not download it
ENV FASTEMBED_CACHE_DIR=/app/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/app/models')"

COPY backend/rag ./rag
COPY data /data
RUN mkdir -p /data/index && chown -R user /data /app/models

USER user
ENV DATA_DIR=/data \
    EMBEDDING_PROVIDER=fastembed \
    PYTHONUNBUFFERED=1
EXPOSE 7860
CMD ["uvicorn", "rag.api.app:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers"]
