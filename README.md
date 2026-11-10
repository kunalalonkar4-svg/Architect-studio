# Drafta — AI Architect Studio

Conversational architectural drafting. Describe a building in English, Hindi or Hinglish; get a dimensioned, to‑scale concept drawing set
(site plan, floor plan, roof plan, elevations, section, door/window and room schedules, index with title block) and export it as
**vector PDF** (exact paper size and scale), **layered DXF** (1:1, millimetres) and **PNG**.

All drawings are generated from one canonical geometry model in millimetres, never from images. Concept drawings only: they are
labelled *CONCEPT DRAFT — NOT REVIEWED* and never carry a signature, stamp or approval.

## Stack
React + TypeScript (Vite) · FastAPI · PostgreSQL 16 · SQLAlchemy/Alembic · DB‑backed job queue · reportlab (PDF) · ezdxf (DXF) · PyMuPDF (PNG + verification) · Anthropic API (server side only).

## Run locally
```bash
cp .env.example .env                       # then edit JWT_SECRET (and ANTHROPIC_* if you have a key)
createdb studio                            # or: docker compose up db
cd backend && pip install -r requirements.txt && alembic upgrade head
cd ../frontend && npm ci && npm run build  # backend serves frontend/dist
cd ../backend && set -a && . ../.env && set +a
uvicorn app.main:app --port 8000           # http://localhost:8000
python -m scripts.seed_demo                # optional: demo@example.com / demo-password-123 with a full 7-sheet project
```
Docker: `cp .env.example .env && docker compose up --build` (runs migrations on start).
Dev UI with hot reload: `cd frontend && npm run dev` (proxies `/api` to :8000).
Separate worker processes: set `RUN_WORKER_IN_API=0` and run `python -m app.jobs`.

## AI configuration — what you must provide
* `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` (a model id your key can use). Without a key the app runs a **deterministic mock assistant**
  (keyword understanding of English/Hinglish/Hindi). The UI shows a "Mock AI" badge and banner so it is never mistaken for Claude.
* The fixed system prompt lives only in `backend/app/ai/prompt.py` and is sent only to Anthropic. The key and prompt never reach the browser.
* The model can only call 8 allow‑listed, schema‑validated tools (`update_brief`, `ask_clarification`, `generate_layout`, `propose_options`,
  `propose_edit`, `generate_views`, `request_export`, `explain_validation`). It never produces coordinates: the server converts units and computes geometry.
* Every length carries a unit; `unspecified` stops and asks. Bounded tool rounds, request timeout/retries and per‑user daily limits (`AI_*` settings in `app/config.py`).
* **Privacy:** chat text and project summary are sent to Anthropic when a key is configured. Uploaded files are sent only after an explicit in‑app confirmation that lists the files, and are wrapped as reference data (instructions inside them are not followed).

## Supported drawing modes (honest limits)
* Ground floor, single dwelling template: front band (parking + living), middle band (dining/passage + stair or toilet/store), rear row (bed 1, kitchen, bed 2). **1 or 2 bedrooms**; open or closed kitchen; parking yes/no; stair front or rear. Future levels are recorded in the brief, not drawn.
* Sheets: site, ground‑floor plan, roof plan, elevations (4), section, room/opening schedules, index/cover. Paper A4–A0, scales 1:20–1:500.
* Layouts that cannot fit (e.g. a 20×30 ft plot with 3 m/1.5 m open space) are refused with concrete alternatives; nothing existing is overwritten.
* Open‑space/setback values are never invented: if not supplied they are shown as labelled concept assumptions (front 3 m, rear 1.5 m, sides 0) and the user must opt in.
* Room‑size and clearance checks are advisory (“commonly used” values), not code compliance.

## Verification performed (this build)
Backend: `cd backend && pytest -q` → **33 passed** (PostgreSQL 16, mock provider, real renderers):
1. Hinglish prompt, no attachment → brief, follow‑up question, dimensioned plan preview, real vector PDF (parsed with PyMuPDF; text + vector paths present).
2. One opening changed → plan, schedule and elevations agree (`check_agreement`), only affected sheets advance their revision, unchanged sheets reuse identical files; tampering is detected.
3. 6000 mm segment measures 120.0 mm at 1:50 and 60.0 mm at 1:100 in the PDF, and 6000 mm in the DXF; A3 page size exact.
4. Ambiguous dimension, impossible layout, sheet overflow, provider unavailable (real `AnthropicProvider` aimed at a closed port) and failed render each return a clear next action and keep existing work.
5. A second user gets 404 on every project/revision/artifact/attachment/job/proposal route (~23 routes); upload type/size checks; consent gate.
6. Mocked Anthropic client: exact system prompt sent, strict allow‑listed tools, invalid/unknown tool calls rejected, key never in the request, usage limits, bounded rounds.

Browser (headless Chrome, Playwright; scripts in `e2e/`): register → create project → Hinglish chat → assumptions → generated A3 plan in viewer → zoom/fit/keyboard → quick edit → proposal → confirm → revision 2 → compare (changes + overlay) → PDF export + download; attachment consent; rename/duplicate/search (incl. chat text)/archive/delete; branding. Run at 1400 px and 390 px (mobile tabs + drawer). No console errors.

**Not verified:** the real Anthropic API (no key was available) — including strict tool use against the live service (the client falls back to non‑strict tools if the API rejects strict mode); production deployment; screen‑reader testing beyond roles/labels/focus management; load testing; print‑to‑paper accuracy on a physical printer.

## Security notes
Bearer‑JWT auth (bcrypt); every route checks ownership server‑side (non‑owners get 404); uploads are sniffed by magic bytes, size‑limited and stored privately (served only through authorised routes with `nosniff`; SVG with a restrictive CSP); the API key and JWT secret are redacted from logs and message/upload contents are not logged; no signature, stamp or approval is ever generated. Before production: set a strong `JWT_SECRET`, serve over HTTPS, restrict `CORS_ORIGINS`, back up PostgreSQL + `STORAGE_DIR`, and add rate limiting at the proxy.
