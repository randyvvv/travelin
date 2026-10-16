# Travelin

**From saved Reels to a trip everyone agrees on.**

Travelin is a progressive web app for group trips. The squad collects places: from the travel Reels they keep sharing, by searching Google Maps, or from AI suggestions that fit everyone's preferences. Gemini reads the Reels, Google Maps verifies every place, everyone votes, and a planner builds a day-by-day itinerary that explains the compromises it made. The squad books the suggested stay together, and Travelin splits the bill fairly. No payment goes through until every member approves.

> Prototype for AI Builder Cup 2026 · Theme: Retail & Commerce.

## How it works

| Layer | What runs there |
|---|---|
| `web/` | React + Vite PWA on Firebase Hosting. Firebase Auth (Google), live Firestore listeners, Cloud Storage uploads. |
| `api/` | `travelin-api` on Cloud Run: FastAPI, Agent Development Kit (ADK) workflows on Gemini (Vertex AI), Places API (New), split and settlement logic. |
| `merchant/` | `travelin-merchant` on Cloud Run: demo merchant for group bookings, using Agent Payments Protocol (AP2) mandates and a mock payment processor. |
| `firebase/` | Firestore and Storage security rules, Firestore indexes. |

The AI work runs as three ADK workflows in `travelin-api`:

- **Ingest:** Gemini watches each Reel and lists the places in it; each one is matched to Google Maps or dropped; Gemini with Grounding with Google Maps summarizes what visitors say.
- **Suggest:** Gemini with Maps grounding proposes places that fit the squad's interests and food needs, checked and summarized by the same steps.
- **Plan:** Gemini drafts the itinerary from votes, budgets, and preferences; code checks it against opening hours, dietary needs, budgets, and must-visit votes; Gemini revises until it passes.

Money is never computed by the model: splits, receipts, and the fewest transfers that settle everyone are deterministic code. The group booking uses AP2: the merchant signs the cart, every member approves it, and only then does Travelin sign the payment, which the merchant verifies again before charging.

Design details, the data model, and the API surface are in [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

## Repository layout

```
web/        PWA (React, TypeScript, Tailwind CSS, vite-plugin-pwa)
api/        travelin-api (Python 3.12, FastAPI, google-adk, google-genai, firebase-admin)
merchant/   travelin-merchant (Python 3.12, FastAPI, AP2 SDK)
firebase/   Firestore and Storage rules, indexes, rules tests
scripts/    deploy.sh, test-emulators.sh, smoke_gemini.py
samples/    notes on demo media (the media lives in Cloud Storage)
docs/       implementation plan
```

## Run it locally

Local runs use the real Google Cloud project for Firestore, Cloud Storage, Gemini, and Places. You need Editor or Owner access to it.

### 1. Install

- Node.js 24+
- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 for you)
- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)
- Optional: Java 21+ for the emulator tests, Firebase CLI (`npm i -g firebase-tools`) to deploy rules

### 2. Sign in to Google Cloud (once per machine)

```bash
gcloud auth login
gcloud config set project <project-id>
gcloud auth application-default login
gcloud auth application-default set-quota-project <project-id>
```

The Python services use these Application Default Credentials for Firestore, Cloud Storage, and Vertex AI.

### 3. Configure

| File | How |
|---|---|
| `web/.env.local` | Copy `web/.env.example`. Fill in the Firebase web config (Firebase console → Project settings → Your apps), the browser Maps key, and the Map ID. Keep `VITE_API_URL=http://localhost:8000`. |
| `api/.env` | Copy `api/.env.example`. Set `GOOGLE_CLOUD_PROJECT`, `STORAGE_BUCKET`, and `PLACES_API_KEY`, which you can read with `gcloud secrets versions access latest --secret=places-api-key`. |
| `merchant/.env` | Optional. The defaults point at the local API. |

`TRAVELIN_SIGNING_KEY` and `MERCHANT_SIGNING_KEY` can stay empty locally: each service then signs with a temporary key. If you restart the merchant while a booking is waiting for approvals, propose the booking again.

### 4. Start the three services

Each in its own terminal, from the repo root:

```bash
cd api && uv run uvicorn travelin.main:app --reload --port 8000
```

```bash
cd merchant && uv run uvicorn merchant.main:app --reload --port 8001
```

```bash
cd web && npm install && npm run dev
```

Then open http://localhost:5173. `uv run` installs the Python dependencies on first use. In Windows PowerShell 5.1, which doesn't support `&&`, run `cd api` and the second command separately.

The API reloads when Python files change; restart it after editing `api/.env`.

### 5. Try the whole flow

1. Sign in with Google and create a trip. For the group booking, pick a destination in the demo merchant's catalog: Yogyakarta or Bandung.
2. Open the invite link from the trip page in a private window and join with a second Google account.
3. Everyone fills in **My preferences**.
4. Add places on **Places**: search, **Suggest places**, or upload Reels (optional).
5. The host taps **Start voting**. Everyone votes and submits; the last vote starts the planner.
6. On **Itinerary**: the map, **Why this plan**, and **Book it with the squad**. Every member approves the booking; **Try paying with 1 of 2 approvals** shows the merchant refusing early payment.
7. On **Split bill**: add expenses or scan a receipt, tap **Settle up**, and everyone approves.
8. On **Payments**: **I've sent it**, then **Confirm received**, until the trip is settled.

### Check the Gemini setup

```bash
uv run --project api python scripts/smoke_gemini.py
uv run --project api python scripts/smoke_gemini.py --video gs://<bucket>/samples/reels/<file>.mp4
```

It checks structured output, Grounding with Google Maps, the planner model, and optionally reading a video.

### Troubleshooting

| Symptom | Fix |
|---|---|
| Browser console: *Missing or insufficient permissions* | Deploy the rules: `firebase deploy --only firestore,storage` |
| Home stays empty; console: *The query requires an index* | Deploy the indexes with the same command |
| API log: *DefaultCredentialsError* | Run step 2 |
| "Place verification isn't set up yet" | `PLACES_API_KEY` is empty in `api/.env`, or the API wasn't restarted after setting it |
| A Reel shows *Couldn't read* | The Vertex AI service agent needs read access to the bucket; the API log has details |
| No map on the itinerary | Check `VITE_MAPS_API_KEY` and `VITE_MAPS_MAP_ID`; the key must allow `localhost:5173` |
| No booking button on the itinerary | The destination isn't in `merchant/merchant/catalog.json`, or the merchant isn't running |

## Tests and linting

```bash
cd api && uv run pytest && uv run ruff check .
cd merchant && uv run pytest && uv run ruff check .
cd web && npm run lint && npm run format:check && npm run build
```

The API integration tests (trips, the ingest, suggest, and plan workflows, voting, settlement, and the AP2 booking against the real merchant app) and the security rules tests run on the Firebase emulators with the offline `demo-travelin` project. Gemini and Places are replaced by fakes there. They need Java 21+:

```bash
cd firebase && npm install && cd ..
./scripts/test-emulators.sh
```

Without the emulators, `uv run pytest` skips those tests.

## Deploy

`scripts/deploy.sh` deploys `travelin-api` and `travelin-merchant` to Cloud Run and the PWA plus security rules to Firebase Hosting, in that order, and wires the service URLs together.

Before the first deploy, the project needs the APIs, service accounts, and secrets described in [docs/IMPLEMENTATION_PLAN.md §4](docs/IMPLEMENTATION_PLAN.md): `travelin-api` and `travelin-merchant` service accounts, and the secrets `places-api-key`, `travelin-signing-key`, and `merchant-signing-key`. `web/.env.local` must hold the Firebase web config.

Run it with bash (Cloud Shell, macOS, Linux, or Git Bash on Windows):

```bash
gcloud config set project <project-id>
npx firebase-tools login
bash scripts/deploy.sh            # everything
bash scripts/deploy.sh api        # or one part: api | merchant | web
```

Defaults: region `asia-southeast2`, `gemini-3.8-flash` and `gemini-4-argon`. Override with the `REGION`, `FAST_MODEL`, and `PLANNER_MODEL` environment variables.
