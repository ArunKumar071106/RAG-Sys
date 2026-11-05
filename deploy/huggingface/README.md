---
title: Arivazhai API
emoji: 🎓
colorFrom: indigo
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# Arivazhai API

Arivazhai, the AAACET admission assistant: answers questions from the official website
(https://aaaenggcoll.ac.in/). The vectors are in Qdrant Cloud; this Space holds the knowledge base, the search model and
the chat page (plain HTML, CSS and JavaScript).

- Chat page: `/`  (only the chat, for an iframe: `/?embed=1`)
- Health: `/api/health`
- Chat: `POST /api/chat` with `{"message": "Eligibility"}`

Settings are Space secrets and variables (`QDRANT_URL`, `QDRANT_API_KEY`, optionally `ANTHROPIC_API_KEY`, and
`CORS_ORIGINS` with the address of any other site that hosts the chat page). Deployed with `scripts/deploy_hf_space.py` from the project repository.
