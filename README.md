# AAACET Virtual Assistant: multimodal RAG chatbot

A retrieval-augmented chatbot for **AAA College of Engineering and Technology (AAACET)** that answers questions from the
official website [aaaenggcoll.ac.in](https://aaaenggcoll.ac.in/), cites every source page, and shows relevant college
images (photos, posters, notices) alongside the answer.

* **Text:** Structure-Aware Recursive Chunking
* **Images:** Caption/OCR-Based Image Chunking
* **Retrieval:** Hybrid Retrieval, which fuses semantic search (Qdrant) and BM25 with Reciprocal Rank Fusion (RRF)
* **Answers:** grounded generation with Claude, with citations validated server-side; an extractive no-LLM fallback
* **Stack:** Python, FastAPI, Scrapy, Qdrant, BM25, BAAI/bge-m3, Claude (text + vision), React + TypeScript + Vite

| Answer with real campus photos | Exact intake table from the admission page |
|---|---|
| ![Hostel photos](docs/screenshots/real-photos.png) | ![Intake](docs/screenshots/real-intake.png) |

> Real answers from the shipped AAACET knowledge base in extractive mode (no API key). With `ANTHROPIC_API_KEY` set,
> Claude writes the answer from the same cited sources. The page layout, colours, fonts, logo, menu and footer were
> **measured from the official website** ([details](#matching-the-official-website)).

---

## Status

| Area | Status |
|---|---|
| **Knowledge base** | Crawled from https://aaaenggcoll.ac.in/ on 2026-10-18/19: **2,115 pages** (all 1,979 sitemap pages: main pages, department and lab pages, news posts, plus 69 PDFs) → 2,029 documents → **3,388 text chunks**; **4,785 images** (439 duplicates removed) with OCR text in 3,516. Shipped in `data/processed/`. |
| Retrieval quality on the real site | 35 labelled questions with the official pages that answer them (including every suggested question in the UI and a faculty-list question for each department), plus one off-topic question (`backend/eval/questions_aaacet.jsonl`): **Recall@1 = 0.77, Recall@3 = 0.97, Recall@5 = 0.97, MRR = 0.87**, image hit rate 1.0, with the offline hashing embedder; hybrid search with a semantic stand-in (all-MiniLM-L6-v2, the only model the build environment could download) measured the same. Asked for a department's faculty, the extractive answer lists every name for all 10 departments, the main faculty list first (for CSE, EEE and Civil the visiting professors page is the top search hit, the faculty list second). Misses: "What courses does AAACET offer?" ("offer" matches a job-offer post) |
| Official branding | Measured from the rendered site: red `#db2c1d` menu and buttons, white→indigo `#323496` header, gold `#e0ac2a` title box, `#151414` footer, Poppins / League Spartan, official logo, banner photo, full menu with dropdowns, contact details |
| Tests | 110 backend tests, 28 frontend unit tests, 22 Playwright tests on desktop, tablet and mobile |
| Embeddings | `bge-m3` (BGE-M3 via PyTorch, `requirements-ml.txt`) → falls back to **FastEmbed BGE-small** (`BAAI/bge-small-en-v1.5`, ONNX, installed by default, downloads ~70 MB on first start; `FASTEMBED_MODEL` selects another FastEmbed model) → falls back to an offline hashing embedder. The build environment could not download BGE weights; the hybrid numbers above use all-MiniLM-L6-v2 as a stand-in (a model of the same size class), so BGE-small itself is unmeasured. |
| Claude answers / vision descriptions | Implemented and unit-tested with a mocked client. Needs `ANTHROPIC_API_KEY`. Without a key the app answers in extractive mode (it quotes the most relevant sentences and tables). |
| Off-topic questions | With Claude, the model replies "not covered" via a `[[NO_ANSWER]]` marker. In extractive mode, an off-topic question that shares a word with some page may still get loosely related quotes. |
| Docker images / Compose | Written, but not built in the build environment (no Docker daemon). |

---

## Architecture

```mermaid
flowchart LR
  subgraph Ingestion["Ingestion (python -m rag.cli all)"]
    A[Scrapy crawler<br/>robots.txt, delays] --> B[HTML / PDF extractor<br/>headings, tables, links, images + context]
    B --> C[Boilerplate + duplicate removal]
    C --> D[Structure-aware recursive chunker]
    C --> E[Image stage<br/>download, validate, dedupe,<br/>OCR, optional vision description]
    E --> F[Caption/OCR image chunks]
    D & F --> G[Embedder<br/>BGE-M3 or hashing]
    G --> H[(Qdrant<br/>text + image collections)]
    D & F --> I[(BM25 indexes<br/>JSON)]
  end
  subgraph Serving["Serving (FastAPI)"]
    Q[Question] --> R[Semantic search] & S[BM25]
    R & S --> T[RRF fusion + dedupe<br/>+ optional reranker]
    T --> U[Image retrieval<br/>semantic + BM25 + page links → RRF]
    T & U --> V[Claude, grounded prompt<br/>or extractive fallback]
    V --> W[Citation + link validation]
  end
  H --> R
  I --> S
  W --> X[React UI: answer, sources, image cards]
```

### Text: Structure-Aware Recursive Chunking (`backend/rag/chunking/text_chunker.py`)
1. Each page is parsed in document order into heading / text / table blocks, with a heading stack. Every block records
   its heading path (`Page title > H1 > H2 > …`). Menus built from link cards (a list whose items are only a link
   around a heading, like each department's sub-page menu) are navigation, not headings, so a department's faculty
   table sits under "Artificial Intelligence and Data Science" rather than under the menu's last entry.
   A page's first heading followed directly by other headings (a department banner over its menu) stays the parent
   of everything below, even under same-level headings such as Civil's `<h2>ACADEMIC YEAR 2025 – 2026</h2>`.
   Table header rows written with `<td>` cells are recognised even with long labels, so every row reads
   `Name of the Faculty: Dr.M.Karuppasamy | Highest Degree: Ph.D. | …`.
2. Blocks are grouped into sections by heading. Small sibling sections under the same top-level heading are merged
   while they fit, so short facts stay with their context.
3. Oversized sections are split recursively: paragraphs/tables, then sentences, then words. The sentence splitter
   knows Indian academic abbreviations (B.E., Ph.D., Rs., Dr., …).
4. Tables are split only on row boundaries, and every piece repeats the header, so a row such as
   `Programme: B.Tech | Fee: Rs. 60,000` is never cut.
5. Consecutive pieces overlap by whole sentences (default 100 tokens; chunks default to 650 tokens, both configurable).
6. Each chunk stores its ID, text, page title, heading path, source URL, document ID, content hash, token count and
   duplicate URLs. Identical chunks found on several pages are stored once.

### Images: Caption/OCR-Based Image Chunking (`backend/rag/images/`)
* The extractor collects `<img>` tags (including lazy `data-src` and the largest `srcset` candidate), figure captions
  and CSS background banners. For each it records alt text, title, filename, nearest heading path, and the text before
  and after the image.
* Downloads are restricted to the allowed hosts and capped in size. Each file is verified with Pillow and stored under
  its SHA-256 (remote filenames are never used as paths). Exact duplicates are caught by SHA-256 and resized copies by
  a perceptual hash. Logos/icons repeated on most pages are marked `boilerplate`. Tiny images, broken links and invalid
  files each get a recorded status.
* OCR (RapidOCR, ONNX models bundled, works offline; Tesseract optional) reads posters, notices and banners.
* With `VISION_ENABLED=true`, a vision-capable Claude model writes a short factual description. The prompt forbids
  naming people or guessing facts that aren't visible.
* One chunk per image, with every field labelled by provenance: `Alt text`, `Caption`, `Text in image (OCR)`,
  `Nearby text`, `AI-generated description`. Keywords come from extracted fields only.

### Hybrid retrieval (`backend/rag/retrieval/hybrid.py`)
* **Query:** request words are dropped ("show me photos of") and department short forms are spelled out the way the
  website names them (`QUERY_EXPANSIONS`: "AI&DS" → "Artificial Intelligence and Data Science", CSE, ECE, EEE, MECH, IT,
  S&H, HOD). They are replaced, not appended: event posts repeat "III AI&DS" in class names, department pages don't.
* **Text:** Qdrant cosine top-30, BM25 top-30 and a BM25 ranking over page titles, URL path words and section headings
  (so "Faculty List" under "/ai-dept/" or "Principal Message" pages are found by their title; weight
  `TITLE_RANK_WEIGHT=6`, scaled by the square of the share of the question the title covers, so a title sharing one
  word with the question barely counts; chosen on the eval set in both keyword-only and hybrid mode) are fused with RRF (`k=60`)
  together with a query-coverage ranking. The best match's section, and any section with two or more matches, is
  completed in page order (`SECTION_EXPAND_MAX=10` chunks), so a faculty table split over several chunks reaches the
  answer whole. Exact-duplicate chunks are dropped and an
  optional cross-encoder reranker can reorder the results. A semantic-only hit below `TEXT_MIN_SEMANTIC_SCORE` cannot
  enter the results on its own, so off-topic questions return "no answer" instead of noise.
* **Images:** three ranked lists (semantic over image chunks, BM25 over image chunks, and images located on the
  retrieved text pages) are fused with RRF. An image is shown only if it matched the question lexically or
  semantically; appearing on a relevant page is never enough by itself. Images are retrieved through their text
  evidence, because the configured embedders are text models. Direct pixel-vector search would need a genuinely
  multimodal embedding model.

### Grounded answers (`backend/rag/llm/`)
* Claude receives only the retrieved evidence, as `<source id="S1">` and `<image id="I1">` blocks. OCR text and
  AI-generated descriptions are labelled differently in the prompt and in the UI.
* The system prompt requires a citation for every fact and a `[[NO_ANSWER]]` marker when the evidence does not cover
  the question. It also tells Claude to ignore instructions embedded in page content.
* Server-side, citations to non-existent sources are removed and the rest renumbered. **Any URL the model writes that
  is not one of the retrieved official URLs is stripped.** Only cited sources are returned.
* Defaults: `claude-opus-5-5`, effort `low` (fast chat answers), and refusal fallbacks enabled (`fallbacks: "default"`).
  All are configurable in `.env`.
* Answers are written to be easy to read: a direct answer first, plain words, only what answers the question, and a
  small table (3-5 columns) for lists.
* **Any language:** a question that is not in English (Tamil, Hindi, Arabic, French..., also Tamil typed in Latin
  letters) is translated by Claude into an English search query (the website is in English) and answered in the
  question's language, with names, numbers and citations unchanged (`backend/rag/llm/language.py`, `TRANSLATE_PROMPT`).
  This needs `ANTHROPIC_API_KEY`; without it, answers stay English quotes and the UI says so.
* If no key is configured, or the LLM API fails, the answer falls back to quoting the website (extractive mode), and
  the UI shows a notice. Extractive answers are formatted too: a table answer becomes one compact Markdown table
  ("**Faculty List – Artificial Intelligence and Data Science** · 13 entries") with the useful columns (serial numbers,
  mostly empty and long official columns dropped, columns named in the question kept). Tables that match about as well
  are shown too, the one whose page title names the question first, then the bigger (a department's faculty list
  before its visiting professors; B.E. and B.Tech intake), and text answers are short bullet lists grouped by page, keeping only
  sentences that score at least half as well as the best one.

### Suggestions while typing (`backend/rag/retrieval/suggest.py`, `GET /api/suggest?q=`)
* Candidates: common questions, four questions for each department in `DEPARTMENTS` (faculty, about, labs, vision and
  mission), and "Tell me about …" for each section page of the website (titles used by one page only).
* Every word typed must start a word of the suggestion, and department short forms are spelled out first, so
  "ai&ds fac" suggests "Who are the faculty of the Artificial Intelligence and Data Science department?".
* The input is an accessible combobox: ↑/↓ to pick, Enter or click to ask, Tab to copy into the box, Esc to close.

### Arivazhai, the animated assistant (`frontend/src/robot/`)
The chat is presented by **Arivazhai**, the robot from the design project ("Animation states" and "Launcher icon").
The robot is the design's own SVG rig and CSS, unchanged: `robot.css` is copied verbatim from `States.dc.html` and
`Icon.dc.html`, and `Robot.tsx` / `LauncherIcon.tsx` are the same SVG markup converted to JSX, with gradient ids made
unique per instance. The design tool's viewer runtime (`support.js`, `vendor/react*.js`) is not needed and not used.

* **Floating launcher** in the bottom-right corner: the full-body robot from 640 px up, the design's head-only accent
  disc (64 px) on phones, as its launcher rules require. It greets on a first visit (2 s after load), waves once per
  session after 8 s without scrolling or input, and reaches toward the chat while hovered or focused.
* **Chat panel**: the same robot moves into the panel header (only one robot is ever rendered), with a status line.
  The panel is 400 px wide on desktop and full screen on phones; Esc closes it and focus returns to the launcher. The
  conversation, and a search still running, survive closing the panel.
* **One mapping from chat events to animation states** (`states.ts`, `reactionFor`), driven by the real request:

| Chat event | State | Shown for |
|---|---|---|
| chat opened, new chat, first visit | `greet` | one cycle |
| typing, moving through suggestions | `attend` | while typing (4 s after the last key) |
| launcher hovered or focused | `support` | while hovered |
| question sent: RAG retrieval and answering in flight | `think` | exactly until the API replies |
| answer with sources | `answer` | one cycle |
| visitor opens a cited official page, document or image | `confirm` | one cycle |
| no answer, but related pages found (ambiguous question); message rejected as invalid | `unsure` | until the visitor types again |
| nothing in the knowledge base; network, timeout, rate-limit or server failure | `error` | until the visitor types again |

  `RobotDirector` plays them without conflicts: thinking wins while a request runs, short reactions return to the
  resting state, and unsure/error stay until the visitor moves on. `prefers-reduced-motion` stops the motion (the
  design's own rule) but keeps the expressions.
* **On the college website** add one line before `</body>`; it inserts the launcher and panel as a small transparent
  iframe (`/?widget=1`) that grows when the chat opens:
  ```html
  <script src="https://<assistant-domain>/arivazhai-widget.js" defer></script>
  ```
  `frontend/nginx.conf` already allows framing by `aaaenggcoll.ac.in`.

| Launcher | Thinking during retrieval | Answer ready | Not sure (ambiguous) |
|---|---|---|---|
| ![Launcher](docs/screenshots/robot/01-idle-launcher.png) | ![Thinking](docs/screenshots/robot/05-think-retrieving.png) | ![Answer](docs/screenshots/robot/06-answer-ready.png) | ![Unsure](docs/screenshots/robot/08-unsure-ambiguous.png) |

All eleven scenario screenshots are in `docs/screenshots/robot/`, written by `frontend/e2e/robot.spec.ts`.

---

## Project structure

```
backend/
  rag/
    crawler/        Scrapy spider + runner (robots.txt, delays, PDFs)
    extraction/     HTML/PDF → structured blocks; boilerplate & duplicate page removal
    chunking/       structure-aware recursive chunker, token counting
    images/         downloader/validation, OCR, vision descriptions, image chunks
    embeddings/     BGE-M3 and hashing embedders
    index/          Qdrant store, BM25 index, incremental indexer + validation
    retrieval/      RRF, hybrid text + image retrieval
    llm/            prompts, Claude client, extractive fallback, answer service
    api/            FastAPI app, rate limiting, admin auth, services/reindex jobs
    eval/           Recall@K / MRR evaluation
    demo/           fictional demo website generator (tests + offline demo)
    cli.py          command-line entry point
  eval/             labelled question sets (demo + AAACET samples)
  tests/            pytest suite
frontend/
  src/components/   Header, ChatWidget (floating launcher + panel), ChatWindow, MessageBubble, ChatInput,
                    SuggestedQuestions, SourceList, ImageCard, LoadingIndicator, ErrorMessage, Footer
  src/robot/        Arivazhai rig from the design project + chat event -> animation state mapping
  public/arivazhai-widget.js   one-line loader that adds Arivazhai to the college website
  src/brand/        brand.json + brand.css (measured from the official site by scripts/measure_brand.mjs)
  public/brand/     official logo, banner photo and favicon downloaded by the same script
  src/__tests__/    Vitest + Testing Library tests
  e2e/              Playwright tests (desktop / tablet / mobile) + screenshots
data/processed/     the AAACET knowledge base snapshot (chunks + image metadata) shipped with the repo
scripts/
  measure_brand.mjs measure colours, fonts, logo, menu, contacts from the rendered official site
  extract_brand.py  fallback: parse stylesheets / a saved page without a browser
  e2e_backend.sh    API on the demo dataset for UI tests
docs/screenshots/   generated by the e2e tests
```

---

## Setup

Requirements: Python 3.11+ and Node 20+. Optional: Docker (for a Qdrant server) and a GPU for BGE-M3.

```bash
cp .env.example .env            # then fill in ANTHROPIC_API_KEY and ADMIN_TOKEN
make install                    # venv + backend deps + frontend deps
make install-ml                 # BGE-M3 (PyTorch, sentence-transformers); skip for the offline demo
cp frontend/.env.example frontend/.env
```

### 1. Try it offline in two minutes (fictional demo data)
```bash
make demo                                   # builds, serves, crawls and indexes the FICTIONAL demo site into data/
EMBEDDING_PROVIDER=hashing make serve       # API on http://127.0.0.1:8000
make dev                                    # UI on http://localhost:5173
```

### 2. Use the real AAACET knowledge base (shipped in the repo)
The repository includes the processed content of the official website in `data/processed/` (text chunks and image
metadata, crawled from https://aaaenggcoll.ac.in/). On the first start the API builds the Qdrant and BM25 indexes from it
automatically, so you only need to start the two servers. The keyword (BM25) index is ready within seconds and the
assistant answers with it straight away; the semantic vectors (3,388 text and 4,785 image chunks) are embedded in the
background, which can take a long time on a laptop CPU, and the API switches to hybrid search when they are done. The
backend terminal logs `Indexing aaacet_text: 1152/3388 (34%)`-style progress, `/api/health` reports
`"status": "indexing"` meanwhile, and an interrupted build resumes where it stopped on the next start:
```bash
make serve        # API on http://127.0.0.1:8000  (first start: "Building the search index ...")
make dev          # UI on http://localhost:5173
```
Image cards load the photos from the official website. The downloaded copies are not committed; run the image stage
locally if you want local copies.

Open http://localhost:5173 and click Arivazhai in the bottom-right corner (or **Ask Arivazhai** on the page). To watch it
react: type (listening), send a question (thinking until the answer arrives), read the answer (cheering), open a
source link (checkmark), ask something the website does not cover (unsure when only related pages are found,
error when nothing is), or stop the API and ask again (error).
`http://localhost:5173/?widget=1` is the launcher alone, as the college website shows it, and `/?embed=1` the panel alone.

### 3. Refresh the knowledge base from the live website
```bash
make all          # crawl → extract → images/OCR → chunk → index  (python -m rag.cli all)
```
The crawler reads `robots.txt`, seeds itself from the WordPress sitemaps (all pages, department pages, labs and news
posts), skips archive listings, and keeps a polite rate of about one request per second, so a full crawl takes 45 to
60 minutes. Individual stages: `python -m rag.cli crawl | extract | images | chunk | index [--full] | status` (run
from `backend/`). Indexing is **incremental** by default: only changed pages are re-embedded and removed pages are
deleted. Changing the embedding model or dimension automatically triggers a full rebuild, so vectors from different
models are never mixed.

Evaluate retrieval against labelled questions with the official source pages that answer them
(`backend/eval/questions_aaacet.jsonl`):
```bash
make eval          # Recall@1/3/5, Hit@K, MRR, image hit rate, unanswerable rejection
```

### Matching the official website
The frontend reads every colour, font, the logo, the banner photo, the menu (with its dropdowns), the header buttons,
footer links and contact details from `frontend/src/brand/` and `frontend/public/brand/`. These were **measured from
the rendered official site** and are committed. To re-measure after the website changes:
```bash
make brand        # = cd frontend && node ../scripts/measure_brand.mjs --inner /aaa-hostels/
```
The script opens the live site in headless Chromium and reads the *computed* styles of the real header (white→indigo
diagonal), menu bar, buttons, page-banner title box and footer, plus the fonts (Poppins, League Spartan). It downloads
the official header logo, a banner photo and the favicon, and extracts the menu, header buttons, footer link columns,
social links and contact details. Text colours that fail WCAG AA contrast are adjusted, and every adjustment is
reported. For example, the site's white-on-gold banner title (2.1:1) is rendered dark-on-gold (8.9:1). Anything it
cannot find keeps its previous value. `scripts/extract_brand.py` is a browser-free fallback that parses stylesheets or
a saved page. Confirm with the college that using the official logo on the assistant is permitted.

The chat is offered three ways:
* **as a page** that reproduces the site's header, menu, page banner/breadcrumb and footer, at `/`, with Arivazhai's
  floating launcher
* **as a floating launcher on any page** of the college website, with `arivazhai-widget.js` (see
  [Arivazhai](#arivazhai-the-animated-assistant-frontendsrcrobot))
* **as an embeddable panel** at `/?embed=1`, for example
  `<iframe src="https://assistant.example/?embed=1" title="AAACET Virtual Assistant" style="width:100%;height:640px;border:0"></iframe>`.
  `frontend/nginx.conf` already allows framing by `aaaenggcoll.ac.in`.

---

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/chat` | grounded answer + cited sources + images |
| GET | `/api/suggest?q=` | type-ahead question suggestions |
| POST | `/api/search/text` | hybrid text retrieval (with semantic/BM25 ranks) |
| POST | `/api/search/images` | image retrieval |
| GET | `/api/sources/{chunk_id}` | full chunk text and metadata |
| GET | `/api/images/{image_id}` / `/file` | image metadata / the downloaded file |
| GET | `/api/health` | readiness, embedder, LLM, Qdrant point counts |
| GET | `/api/status` | crawl / extract / images / chunk / index status |
| POST | `/api/admin/reindex` | start a background reindex (Bearer `ADMIN_TOKEN`) |
| GET | `/api/admin/jobs/{id}` | reindex job status (Bearer `ADMIN_TOKEN`) |

```bash
curl -s localhost:8000/api/chat -H 'Content-Type: application/json' \
  -d '{"message": "What is the admission procedure?", "history": []}' | jq
curl -s localhost:8000/api/search/images -H 'Content-Type: application/json' -d '{"query": "hostel", "top_k": 3}' | jq
curl -s -X POST localhost:8000/api/admin/reindex -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d '{"recrawl": true, "full": false}'
```

Example `/api/chat` response (abridged):
```json
{
  "answer": "Admission is through TNEA counselling [S1] …",
  "mode": "llm",
  "insufficient_evidence": false,
  "sources": [{"id": "S1", "title": "Admission", "url": "https://aaaenggcoll.ac.in/…", "heading": "…", "snippet": "…"}],
  "images": [{"id": "I1", "src": "/api/images/ab12…/file", "original_url": "…", "source_page": "…",
              "alt": "…", "caption": "…", "ocr_text": "…", "description": "", "description_is_ai_generated": false}],
  "related_sources": [], "notice": "", "model": "claude-opus-5-5"
}
```
`mode` is `llm`, `extractive` (no key, or the LLM was unavailable; `notice` explains which) or `no_answer`.

---

## Testing

```bash
make test-backend     # pytest: crawler (real Scrapy run against a local site), extraction, chunking, OCR,
                      # image validation/dedupe, embeddings, Qdrant, BM25, RRF, incremental indexing,
                      # hybrid retrieval, citations, answer generation, Claude client, API, brand extractor,
                      # Recall@K / MRR thresholds
make test-frontend    # tsc + Vitest: chat submission, Enter/Shift+Enter, loading, sources, image cards,
                      # broken-image fallback, no-answer, network error + retry, new chat, embed mode,
                      # launcher/panel, event -> animation state mapping and timing
make e2e              # Playwright against the real API (demo data): desktop 1366px, tablet 820px,
                      # mobile 390px; checks no horizontal scrolling, real image loading, keyboard use,
                      # mobile menu, the robot in every conversation scenario and the website loader;
                      # writes docs/screenshots/*
```
`make e2e` uses `PLAYWRIGHT_CHROMIUM_PATH` when set (pre-installed Chromium); otherwise run `npx playwright install chromium` first.

---

## Configuration and credentials

All configuration lives in environment variables (see `.env.example`). The external credentials are:

| Variable | Needed for | Without it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude answers, vision descriptions | extractive answers, no AI image descriptions |
| `ADMIN_TOKEN` | `/api/admin/*` | admin endpoints return 503 |
| `QDRANT_API_KEY` | secured Qdrant server / cloud | not needed for local or embedded Qdrant |
| Hugging Face access | first download of `BAAI/bge-m3` | set `EMBEDDING_MODEL` to a local path, or use `hashing` |

---

## Security notes
* Secrets come only from the environment. `.env` is git-ignored and no key appears in source.
* Inputs are validated: message length (`MAX_QUESTION_CHARS`), history size and roles, request body size (64 KB), and
  per-IP rate limiting (`RATE_LIMIT_PER_MINUTE`, in-memory; use a shared limiter behind several workers).
* Admin endpoints use a constant-time Bearer token check and are disabled when no token is set. Only one reindex job
  can run at a time.
* Files: images are stored under content hashes and served only by ID, with traversal-safe path resolution, the stored
  MIME type, and `nosniff`. Image size and pixel count are capped (decompression-bomb guard). BM25 indexes are JSON,
  never pickle.
* Output safety: model-written URLs not in the retrieved set are removed. The UI renders Markdown without raw HTML,
  renders only `http(s)` links, and opens external links with `rel="noopener noreferrer"`. Page text is treated as
  data, not instructions.
* Crawling obeys `robots.txt`, stays on the allowed domains, and uses AutoThrottle with a polite delay and a descriptive
  User-Agent.
* CORS is limited to `CORS_ORIGINS`.

## Deployment
```bash
cp .env.example .env    # set ANTHROPIC_API_KEY, ADMIN_TOKEN
docker compose up -d --build
docker compose run --rm backend python -m rag.cli all      # first crawl + index
# UI: http://localhost:8080   (nginx proxies /api to the backend; Qdrant runs as a server)
```
Schedule refreshes with cron (`docker compose run --rm backend python -m rag.cli all`, incremental) or call
`POST /api/admin/reindex`. Put the frontend behind HTTPS on the college's domain and point `CORS_ORIGINS` at it.
Embedded Qdrant (`QDRANT_URL` empty) is for single-process development. Use the Qdrant server in production.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `/api/health` says `degraded` / chat returns 503 | Run the pipeline first (`make all` or `make demo`), or read the `error` field (e.g. BGE-M3 not installed) |
| `Storage folder … is already accessed by another instance` | Embedded Qdrant allows one process: stop the API before running CLI indexing, use `/api/admin/reindex`, or set `QDRANT_URL` to a server |
| `Collection … has N-d vectors but the embedder produces M-d` | You changed the embedding model: `python -m rag.cli index --full` |
| Crawl finishes with 0 pages | Check network access to the site, `CRAWL_ALLOWED_DOMAINS`, and `robots.txt` (`python -m rag.cli status` shows `robots_forbidden`) |
| Answers say "AI answer generation is not configured" | Set `ANTHROPIC_API_KEY` (or log in with `ant auth login`) and restart |
| OCR text empty | `OCR_ENGINE=rapidocr` needs `libgl1`/`libglib2.0-0` on slim Linux images; check `/api/status` → `images.ocr_engine` |
| Images missing in the UI | They fall back to the original URL, then to a placeholder; check `data/processed/images.jsonl` statuses (`http_error`, `too_large`, …) |
| Frontend can't reach the API | `npm run dev` forwards `/api` to `http://127.0.0.1:8000` when `VITE_API_BASE_URL` is empty (set `VITE_DEV_API_PROXY` for another port). If you set `VITE_API_BASE_URL` in `frontend/.env`, `CORS_ORIGINS` in `.env` must include the frontend's address |
