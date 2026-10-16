# Travelin

**From saved Reels to a trip everyone agrees on.**

Travelin is a progressive web app for group trips. The squad drops in the travel Reels they keep sharing. Gemini finds the places in the videos, Google Maps verifies them, everyone votes, and a planner builds a day-by-day itinerary that explains the compromises it made. Afterwards, Travelin splits the bill fairly. Payments only go through once every member approves.

> Prototype for AI Builder Cup 2026 · Theme: Retail & Commerce. Work in progress.

## Architecture

| Layer | What runs there |
|---|---|
| `web/` | React + Vite PWA on Firebase Hosting. Firebase Auth (Google), live Firestore listeners, Cloud Storage uploads. |
| `api/` | `travelin-api` on Cloud Run: FastAPI + Agent Development Kit (ADK) workflows on Gemini (Vertex AI), Places API (New), deterministic split and settlement logic. |
| `merchant/` | `travelin-merchant` on Cloud Run: demo merchant for group bookings using Agent Payments Protocol (AP2) mandates and a mock payment processor. |
| `firebase/` | Firestore and Storage security rules, Firestore indexes. |

The full build plan, data model, and API surface are in [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

## Repository layout

```
web/        PWA (React, TypeScript, Tailwind CSS, vite-plugin-pwa)
api/        travelin-api (Python 3.12, FastAPI, google-adk, google-genai, firebase-admin)
merchant/   travelin-merchant (Python 3.12, FastAPI, AP2 SDK)
firebase/   firestore.rules, storage.rules, firestore.indexes.json
scripts/    smoke_gemini.py and other dev scripts
samples/    demo media notes (media itself lives in Cloud Storage)
docs/       implementation plan
```

## Local development

Prerequisites: Node.js 24+, [uv](https://docs.astral.sh/uv/), Google Cloud CLI, Firebase CLI (`npm i -g firebase-tools`).

```bash
# One-time: Google credentials for local Python services
gcloud auth application-default login
firebase use --add            # pick the Travelin Firebase project
```

**Web**

```bash
cd web
cp .env.example .env.local    # fill in the Firebase web config
npm install
npm run dev                   # http://localhost:5173
```

**API**

```bash
cd api
cp .env.example .env          # project ID, bucket, Places key
uv sync
uv run uvicorn travelin.main:app --reload --port 8000
```

**Merchant**

```bash
cd merchant
cp .env.example .env
uv sync
uv run uvicorn merchant.main:app --reload --port 8001
```

**Check the Gemini setup** (structured output, Maps grounding, planner model, and optionally video):

```bash
uv run --project api python scripts/smoke_gemini.py --video gs://<bucket>/samples/reels/reel-1.mp4
```

## Tests and linting

```bash
cd api && uv run pytest && uv run ruff check .
cd merchant && uv run pytest && uv run ruff check .
cd web && npm run lint && npm run format:check && npm run build
```

API integration tests (trips, ingest workflow, voting) and the Firestore/Storage security rules tests run against the Firebase emulators, on the offline `demo-travelin` project. Gemini and Places are replaced by fakes there. They need Java 21+:

```bash
cd firebase && npm install && cd ..
./scripts/test-emulators.sh
```

Without the emulators, `uv run pytest` skips those tests.

## Deploy

```bash
cd web && npm run build && cd ..
firebase deploy --only hosting,firestore,storage
gcloud run deploy travelin-api --source api --region asia-southeast2 ...
gcloud run deploy travelin-merchant --source merchant --region asia-southeast2 ...
```

Full flags, service account roles, and secrets are listed in [docs/IMPLEMENTATION_PLAN.md §4 and §15](docs/IMPLEMENTATION_PLAN.md).
