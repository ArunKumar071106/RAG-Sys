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

The backend of Arivazhai, the AAACET admission assistant: answers questions from the official website
(https://aaaenggcoll.ac.in/). The vectors are in Qdrant Cloud; this Space holds the knowledge base and the search model.

- Health: `/api/health`
- Chat: `POST /api/chat` with `{"message": "Eligibility"}`

Settings are Space secrets and variables (`QDRANT_URL`, `QDRANT_API_KEY`, optionally `ANTHROPIC_API_KEY`, and
`CORS_ORIGINS` with the frontend's address). Deployed with `scripts/deploy_hf_space.py` from the project repository.
