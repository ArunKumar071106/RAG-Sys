PY ?= .venv/bin/python
PIP ?= .venv/bin/pip
CHROMIUM ?= /opt/pw-browsers/chromium
PLAYWRIGHT_CHROMIUM_PATH ?=

.PHONY: install install-test-ui install-ml test test-backend test-frontend e2e demo crawl index all serve dev brand eval

install:            ## backend dependencies (no ML extras); the chat page needs none
	python3 -m venv .venv
	$(PIP) install -r backend/requirements-dev.txt

install-test-ui:    ## Node tools for the page's tests only (Vitest, Playwright)
	cd frontend && npm ci

install-ml:         ## BGE-M3 embeddings (PyTorch + sentence-transformers)
	$(PIP) install -r backend/requirements-ml.txt

test: test-backend test-frontend

test-backend:
	cd backend && ../$(PY) -m pytest -q

test-frontend:
	cd frontend && npx vitest run

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

serve:              ## the assistant on http://127.0.0.1:8000/ (API and chat page)
	cd backend && ../$(PY) -m uvicorn rag.api.app:app --host 127.0.0.1 --port 8000

dev: serve          ## the backend serves the chat page itself: edit frontend/, reload the browser

brand:              ## measure colours/fonts/logo/menu from the rendered official website
	cd frontend && PLAYWRIGHT_CHROMIUM_PATH=$(PLAYWRIGHT_CHROMIUM_PATH) node ../scripts/measure_brand.mjs --inner /aaa-hostels/
