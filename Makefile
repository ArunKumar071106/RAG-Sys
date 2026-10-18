PY ?= .venv/bin/python
PIP ?= .venv/bin/pip
CHROMIUM ?= /opt/pw-browsers/chromium

.PHONY: install install-ml test test-backend test-frontend e2e demo crawl index all serve dev brand eval

install:            ## backend + frontend dependencies (no ML extras)
	python3 -m venv .venv
	$(PIP) install -r backend/requirements-dev.txt
	cd frontend && npm ci

install-ml:         ## BGE-M3 embeddings (PyTorch + sentence-transformers)
	$(PIP) install -r backend/requirements-ml.txt

test: test-backend test-frontend

test-backend:
	cd backend && ../$(PY) -m pytest -q

test-frontend:
	cd frontend && npx tsc --noEmit && npx vitest run

e2e:                ## Playwright UI tests against the real API on the fictional demo data
	cd frontend && PLAYWRIGHT_CHROMIUM_PATH=$(CHROMIUM) npx playwright test

demo:               ## offline: build + index the fictional demo site into data/
	cd backend && EMBEDDING_PROVIDER=hashing ../$(PY) -m rag.cli demo

crawl:
	cd backend && ../$(PY) -m rag.cli crawl

index:
	cd backend && ../$(PY) -m rag.cli index

all:                ## crawl the official site, extract, images/OCR, chunk, index
	cd backend && ../$(PY) -m rag.cli all

eval:
	cd backend && ../$(PY) -m rag.cli eval

serve:              ## API on :8000
	cd backend && ../$(PY) -m uvicorn rag.api.app:app --host 127.0.0.1 --port 8000

dev:                ## frontend dev server on :5173
	cd frontend && npm run dev

brand:              ## measure colours/fonts/logo/menu from the official website
	$(PY) scripts/extract_brand.py
