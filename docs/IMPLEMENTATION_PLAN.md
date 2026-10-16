# Travelin: Implementation Plan

> **From saved Reels to a trip everyone agrees on.**
> AI Builder Cup 2026 · Theme: Retail & Commerce: Intelligent Customer and Business Experiences

This is the working plan for the 4-day build (Thu 15 to Sun 18 Oct 2026). The PRD defines *what* to build; this document defines *how* and *in what order*.

---

## 0. Snapshot

| Item | Value |
|---|---|
| Product | Travelin, an installable PWA for group trips |
| Submission deadline | Sun 18 Oct 2026. **Confirm the exact hour and timezone on the Hack2skill dashboard.** Internal target: submitted by 17:00 WIB. |
| Category | Retail & Commerce (confirm it is selectable on the dashboard) |
| Language | English everywhere: UI, code, comments, README, deck, video |

**Deliverables**

| # | Deliverable | Owner day |
|---|---|---|
| 1 | Deployed functional prototype (Firebase Hosting + Cloud Run) | Days 1–4 |
| 2 | Proposal deck as PDF: vision, problem & community benefit, feasibility & scalability | Day 4 |
| 3 | Public video, about 3 minutes (YouTube, Vimeo, or Drive) | Day 4 |
| 4 | Category specification on the submission form | Day 4 |
| 5 | Public GitHub repo with README | Day 4 |

---

## 1. Locked decisions

| Decision | Why |
|---|---|
| **AP2 powers the group booking** (homestay/tour from a mock merchant). Payment runs only after **every** member approves the same cart. | AP2 is built for agent-to-merchant purchases. Using it for the booking applies the protocol as intended and gives the Retail & Commerce theme a real commerce moment. |
| **Friend-to-friend settlement is a Firestore state machine** (`unpaid → waiting → confirmed`). No money moves inside the app. | Matches the PRD guardrail without misusing AP2. |
| **Debt simplification**: minimum number of transfers, computed in deterministic code. | Fewer transfers per person. The UI explains "why you pay X". |
| **The LLM never does money arithmetic.** It estimates costs; code splits and settles them. | Correctness and trust. |
| **Verifier = Places API (New)**; **Maps grounding = place summaries only.** | Maps grounding returns text plus sources, not coordinates or hours. Places gives a stable `place.id`, location, and hours. |
| **Every AI output is schema-validated** (Pydantic) before it is written. | No malformed data reaches the UI. |
| **Demo squad mode** | Judges test alone; the flow needs 3+ people. |
| Stack: React + Vite PWA · Python FastAPI + ADK 2.0 + Gemini on Vertex AI · Firestore · Cloud Run × 2 | Fast to build, everything on Google Cloud. |

---

## 2. Architecture

```
┌──────────────────────── Firebase ────────────────────────┐
│  PWA (Hosting)   Auth (Google)   Firestore   Storage      │
└──────┬─────────────────────────────▲─────────────────────┘
       │ HTTPS + Firebase ID token    │ Admin SDK writes → realtime listeners
┌──────▼──────────────────────────────┴─────────────────────┐
│ travelin-api  (Cloud Run · Python)                         │
│   FastAPI routes ── ADK workflows                          │
│   ingest (extract → verify → summarize) · plan (+validate) │
│   receipt scan · re-plan · booking (AP2) · money (code)    │
└────┬───────────────────┬────────────────────┬─────────────┘
     │ Vertex AI          │ Places API (New)    │ AP2 mandates over HTTPS
     ▼ Gemini (global)    ▼                     ▼
                                     travelin-merchant (Cloud Run)
                                     catalog · carts · mock processor
```

**Write-path rule.** Clients read everything through Firestore listeners. Clients write directly only to data they own: profile, preferences, draft votes, reel uploads. Anything that touches membership, AI output, expenses, approvals, transfers, or bookings goes through `travelin-api`. Security rules enforce this.

---

## 3. Repository layout

```
travelin/
├── web/                          # PWA
│   ├── public/                   # icons (192, 512, maskable), favicon
│   ├── src/
│   │   ├── app/                  # router, providers, layout
│   │   ├── lib/                  # firebase.ts, api.ts, format.ts, hooks/
│   │   ├── screens/              # Login, Home, Notifications, CreateTrip, Join, trip/*
│   │   └── components/
│   ├── vite.config.ts            # vite-plugin-pwa
│   └── package.json
├── api/                          # travelin-api
│   ├── travelin/
│   │   ├── main.py               # FastAPI app + routers
│   │   ├── auth.py               # ID token → uid, membership guard
│   │   ├── config.py             # env settings
│   │   ├── db.py                 # Firestore helpers, notify()
│   │   ├── routes/               # trips, voting, ai, money, booking, demo
│   │   ├── ai/
│   │   │   ├── genai_client.py
│   │   │   ├── schemas.py        # Pydantic I/O for every agent
│   │   │   ├── extractor.py
│   │   │   ├── verifier.py       # Places API (New)
│   │   │   ├── summarizer.py     # Maps grounding
│   │   │   ├── planner.py
│   │   │   ├── validator.py      # deterministic plan checks
│   │   │   ├── receipt.py
│   │   │   └── workflows.py      # ADK Workflow definitions
│   │   ├── money/                # split.py, settle.py
│   │   └── booking/              # mandates.py, merchant_client.py, signing.py
│   ├── tests/                    # test_split, test_settle, test_validator
│   ├── pyproject.toml
│   └── Dockerfile
├── merchant/                     # travelin-merchant
│   ├── merchant/                 # main.py, catalog.json, signing.py, processor.py
│   ├── pyproject.toml
│   └── Dockerfile
├── firebase/                     # firestore.rules, storage.rules, firestore.indexes.json
├── samples/                      # demo reels, receipts, source/licence notes
├── scripts/                      # smoke_gemini.py, seed_demo.py, deploy.sh
├── docs/                         # this plan, architecture diagram, deck
├── firebase.json
├── .firebaserc
└── README.md
```

---

## 4. Google Cloud setup (Day 1, first hour)

1. Create project `travelin-<suffix>`, link billing, add Firebase to it. Set a budget alert.
2. Enable APIs: `aiplatform`, `run`, `cloudbuild`, `artifactregistry`, `secretmanager`, `firestore`, `storage`, `places`, `maps-backend` (Maps JavaScript API). Optional: `cloudscheduler`.
3. Firestore in Native mode, location `asia-southeast2` (Jakarta). Cloud Run in the same region.
4. Firebase Auth: enable the Google provider and add the Hosting domains to authorized domains.
5. Service account `travelin-api@…` with these roles: `roles/aiplatform.user`, `roles/datastore.user`, `roles/storage.objectAdmin` (bucket-scoped), `roles/secretmanager.secretAccessor`.
6. If Gemini returns 403 on `gs://` URIs, grant the Vertex AI service agent (`service-<PROJECT_NUMBER>@gcp-sa-aiplatform.iam.gserviceaccount.com`) `roles/storage.objectViewer` on the bucket.
7. Keys:
   - `places-api-key`: server-only, restricted to Places API (New). Stored in Secret Manager.
   - Browser Maps JS key: restricted by HTTP referrer (Hosting domains + `localhost:5173`) and to the Maps JavaScript API. Create a Map ID for advanced markers.
   - `merchant-signing-key` and `travelin-signing-key`: ES256 private keys in Secret Manager.
8. **Smoke test before writing features** (`scripts/smoke_gemini.py`), which must prove:
   - `FAST_MODEL` extracts place names from one `gs://` video with a response schema.
   - `FAST_MODEL` + `Tool(google_maps=GoogleMaps())` returns `groundingChunks[].maps.{title,uri,placeId}`.
   - `PLANNER_MODEL` exists on Vertex in `global`.

**Environment (`api/.env`, Cloud Run env vars)**

```
GOOGLE_CLOUD_PROJECT=travelin-xxxx
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_VERTEXAI=True      # newer google-genai builds read GOOGLE_GENAI_USE_ENTERPRISE=True; set whichever the pinned version uses
FAST_MODEL=gemini-3.8-flash
PLANNER_MODEL=gemini-4-argon        # fallback chain: gemini-3.1-pro-preview → FAST_MODEL
STORAGE_BUCKET=travelin-xxxx.firebasestorage.app
MERCHANT_URL=https://travelin-merchant-….run.app
ALLOWED_ORIGINS=https://travelin-xxxx.web.app,http://localhost:5173
# from Secret Manager: PLACES_API_KEY, TRAVELIN_SIGNING_KEY
```

Pin explicit model IDs. Do not use `*-latest` aliases, because the underlying version cannot be inspected.

---

## 5. Trip lifecycle

`trips/{id}.status` drives every screen.

| Status | Entered when | Who acts |
|---|---|---|
| `gathering` | trip created | members join, upload reels, fill preferences; host taps **Find places** |
| `extracting` | host starts ingest | pipeline runs; UI shows live progress |
| `voting` | ingest finished | members vote and submit; host sets or extends the deadline |
| `planning` | all members submitted, **or** the deadline passed and the host taps **Generate itinerary** | planner runs |
| `planned` | plan written | view itinerary, propose/approve booking, log expenses, re-plan (P1) |
| `splitting` | anyone taps **Settle up** | everyone reviews split version `v`; any expense edit or **Adjust split** → `v+1`, approvals reset |
| `settling` | every member approved version `v` | transfers created as `unpaid`; payer → `waiting`; payee → `confirmed`. **Adjust split** → back to `splitting` with `v+1`; non-confirmed transfers are deleted and recomputed |
| `settled` | every transfer confirmed | read-only, appears in Home history |

The booking has its own sub-state on the booking doc: `proposed → approving → paid | failed`.

**Home status chip for the current user.** Before settling, show the stage name. During settling:
- **Unpaid**: any outgoing transfer is still `unpaid`.
- **Waiting**: all outgoing transfers are sent, but some are not yet confirmed.
- **Settled**: the trip is settled.

---

## 6. Firestore data model

```ts
// trips/{tripId}
{
  name: string; startDate: string; endDate: string;            // ISO dates
  origin: string;
  destination: { name: string; lat: number; lng: number };      // geocoded at creation via Places Text Search
  hostUid: string; memberUids: string[]; inviteCode: string;
  status: 'gathering'|'extracting'|'voting'|'planning'|'planned'|'splitting'|'settling'|'settled';
  votingDeadline: Timestamp | null;
  split: { version: number };
  pipeline: { stage: string; done: number; total: number; dropped: {name: string; reason: string}[];
              startedAt?: Timestamp; finishedAt?: Timestamp; error?: string; usedFallback?: boolean };
  isDemo: boolean; createdAt: Timestamp;
}

// trips/{tripId}/members/{uid}
{
  displayName: string; photoURL: string; role: 'host'|'member'; isBot: boolean;
  prefs: { budgetIdr: number; interests: string[]; dietary: string[]; skip: string[] }; prefsDone: boolean;
  votes: Record<placeId, 'must'|'maybe'|'skip'>; votesSubmittedAt: Timestamp | null;
  splitApprovedVersion: number | null;
}

// trips/{tripId}/reels/{reelId}
{ uploaderUid: string; source: 'upload'|'link'; storagePath?: string; sourceUrl?: string;
  platform: 'instagram'|'tiktok'|'youtube'|'other';
  status: 'queued'|'processing'|'done'|'failed'|'link_only'; contentHash?: string; placesFound?: number; error?: string }

// trips/{tripId}/places/{googlePlaceId}
{ name: string; category: string; address: string; location: {lat: number; lng: number};
  googleMapsUri: string; rating?: number; userRatingCount?: number; priceLevel?: string; priceRange?: object;
  openingHours?: object;                         // Places regularOpeningHours
  photoName?: string;
  mentions: { reelId: string; atSec: number; evidence: string }[]; savedBy: string[];
  summary: { highlights: string[]; bestTime: string; priceNote: string; dietaryNote: string; crowdNote: string };
  mapsSources: { title: string; uri: string; placeId?: string }[];
  tally: { must: number; maybe: number; skip: number } }

// trips/{tripId}/itinerary/{dayIndex}
{ date: string; title: string;
  stops: { placeId: string; start: string; end: string; attendees: string[]; estCostPerPersonIdr: number; note: string }[] }

// trips/{tripId}/plan/current
{ whyThisPlan: string; compromises: { uid: string; gaveUp: string; got: string; reason: string }[];
  estimates: { uid: string; amountIdr: number }[]; warnings: string[]; stay?: { sku: string; reason: string };
  model: string; attempts: number; generatedAt: Timestamp }

// trips/{tripId}/expenses/{expenseId}
{ title: string; amountIdr: number; paidBy: string;
  split: { mode: 'equal'|'shares'|'exact'|'items'; participants: string[];
           shares?: Record<uid, number>; exact?: Record<uid, number> };
  items?: { name: string; unitPriceIdr: number; qty: number; portions: Record<uid, number> }[];
  taxIdr?: number; serviceIdr?: number; discountIdr?: number;
  computedShares: Record<uid, number>;           // written by the API
  receiptPath?: string; source: 'manual'|'receipt'|'booking';
  createdBy: string; updatedAt: Timestamp }

// trips/{tripId}/transfers/{transferId}
{ from: string; to: string; amountIdr: number; status: 'unpaid'|'waiting'|'confirmed';
  splitVersion: number; sentAt?: Timestamp; confirmedAt?: Timestamp }

// trips/{tripId}/bookings/{bookingId}
{ sku: string; title: string; amountIdr: number; payerUid: string;
  intentMandate: object; cartMandate: object; cartHash: string;
  approvals: Record<uid, { at: Timestamp; cartHash: string }>;
  paymentMandate?: object; receipt?: object;
  status: 'proposed'|'approving'|'paid'|'failed'; failureReason?: string }

// users/{uid}
{ displayName: string; email: string; photoURL: string }

// users/{uid}/notifications/{id}
{ type: 'joined'|'voting_deadline'|'plan_ready'|'split_reopened'|'approval_needed'|'bill'
        |'payment_sent'|'payment_confirmed'|'booking_proposed'|'booking_paid';
  text: string; tripId: string; link: string; read: boolean; createdAt: Timestamp }

// cache/{key}   (server-only) AI outputs keyed by sha256(video) or by query
```

Home query: `trips where memberUids array-contains uid`, ordered by `createdAt`.

---

## 7. API surface (`travelin-api`)

Every route verifies the Firebase ID token. Trip routes also check that the caller is in `memberUids`.

| Method & path | Caller | Effect |
|---|---|---|
| `POST /v1/trips` | any user | create trip + host member + invite code; geocode destination |
| `POST /v1/join/{inviteCode}` | any user | add member; notify host |
| `POST /v1/trips/{id}/ingest` | host | run ingest workflow (background task) |
| `PATCH /v1/trips/{id}/voting` | host | set deadline / close voting |
| `POST /v1/trips/{id}/votes:submit` | member | lock own votes, update tallies; if all submitted → start plan |
| `POST /v1/trips/{id}/plan` | host | run plan workflow (also auto-triggered) |
| `POST /v1/trips/{id}/replan` | member | `{dayIndex, instruction}` (P1) |
| `POST /v1/trips/{id}/receipts:scan` | member | `{storagePath}` → parsed receipt (not saved) |
| `POST · PATCH · DELETE /v1/trips/{id}/expenses[/{eid}]` | member | write expense + `computedShares`; while `splitting`, bump version and reset approvals |
| `POST /v1/trips/{id}/split:open` | member | `planned → splitting` |
| `POST /v1/trips/{id}/split:approve` | member | `{version}`; if all approved → compute transfers → `settling` |
| `POST /v1/trips/{id}/split:adjust` | member | version+1, reset approvals, delete non-confirmed transfers, notify all |
| `POST /v1/trips/{id}/transfers/{tid}:send` | payer | `unpaid → waiting`, notify payee |
| `POST /v1/trips/{id}/transfers/{tid}:confirm` | payee | `waiting → confirmed`; if all confirmed → `settled` |
| `POST /v1/trips/{id}/bookings` | member | IntentMandate → merchant CartMandate → `approving` |
| `POST /v1/trips/{id}/bookings/{bid}:approve` | member | record approval; at N of N → PaymentMandate → merchant |
| `POST /v1/demo/trips` | any user | create a demo trip with a bot squad |
| `GET /.well-known/jwks.json` | merchant | public key used to verify group authorization |

**Cloud Run notes**
- Long AI jobs run as FastAPI background tasks. Deploy with `--no-cpu-throttling --min-instances 1 --timeout 600` so background work keeps CPU and there is no cold start during judging.
- Progress is written to `trips/{id}.pipeline`, and the UI listens to it.
- State transitions use Firestore transactions, so double taps and races cannot double-create transfers.

---

## 8. AI pipelines

### 8.1 Ingest workflow (ADK)

```
START → load_trip
      → parallel: extract(reel)             for each queued reel     [FAST_MODEL, video]
      → parallel: verify(candidate)         Places Text Search       [code + FAST_MODEL tie-break]
      → dedupe by place.id, merge mentions + savedBy
      → parallel: summarize(place)          Maps grounding           [FAST_MODEL + google_maps tool]
      → write places, set status = voting, notify members
```

Implemented as an ADK 2.0 dynamic workflow: `@node(rerun_on_resume=True)` with `ctx.run_node(...)` futures gathered by `asyncio.gather`. Concurrency is capped with a semaphore of 8.

**Extractor**
- Input: `Part.from_uri(file_uri="gs://…", mime_type="video/mp4")` plus a prompt that includes the trip destination as a hint.
- Output schema `ExtractResult.candidates[]`: `name`, `city_hint`, `category` (food | attraction | nature | stay | nightlife | shopping | activity | other), `appears_at_sec`, `evidence` (caption | speech | on_screen_text | visual), `quote`, `confidence`.
- Rules: only specific named places, no generic "a beach"; drop `confidence < 0.4`.
- Cache by `sha256(video)`.
- Link-only reels: Instagram and TikTok are marked `link_only` and kept as a clickable reference. YouTube Shorts links can go straight to Gemini as `file_uri` (stretch).

**Verifier**
- Request: `POST https://places.googleapis.com/v1/places:searchText`
  - body: `{textQuery: "<name>, <city_hint or destination>", locationBias: {circle: {center, radius: 50000}}, languageCode: "en", regionCode: "ID", pageSize: 3}`
  - `X-Goog-FieldMask`: `places.id,places.displayName,places.formattedAddress,places.location,places.types,places.googleMapsUri,places.regularOpeningHours,places.rating,places.userRatingCount,places.priceLevel,places.priceRange,places.photos`
- Accept the top result if name similarity ≥ 0.6 (`rapidfuzz.token_set_ratio`) **and** it is ≤ 80 km from the destination.
- If similarity is between 0.4 and 0.6, ask `FAST_MODEL` for a schema'd yes/no `MatchDecision`.
- Everything else is dropped with a reason and listed in `pipeline.dropped`. The UI shows "2 places dropped: not found on Google Maps".
- Result: every place on the board has a real `place.id`, so 100% verification holds by construction.

**Summarizer**
- Model: `FAST_MODEL` with `tools=[Tool(google_maps=GoogleMaps())]` and `tool_config.retrieval_config.lat_lng` set to the place location. Prompts and responses are in English (a Maps grounding constraint).
- The prompt asks for JSON fields `highlights[3]`, `best_time`, `price_note`, `dietary_note`, `crowd_note` (labelled as an estimate).
- If parsing fails, a second `FAST_MODEL` call without tools reformats the text using `response_schema`.
- Save `groundingMetadata.groundingChunks[].maps` as `mapsSources`.
- **Attribution (required):** render the sources directly under the summary, readable within one interaction, each linking to its `uri`. The literal text "Google Maps" is unmodified and has `translate="no"`. Font is Roboto or sans-serif, weight 400, 12–16px, color `#1F1F1F` or `#5E5E5E`.

**Thinking level.** Set `thinking_config=ThinkingConfig(thinking_level="LOW")` (or `"MINIMAL"`) on every `FAST_MODEL` call: extract, match tie-break, summarize, receipt. The Day 1 smoke test took 18.5 s for a two-item structured answer at the default level. Only the planner keeps a high level.

**Latency budget** (target < 2 min from upload to places):
| Step | Estimate |
|---|---|
| Extract (3 reels, parallel) | 20–40 s |
| Verify | about 5 s |
| Summarize (about 10 places, parallel) | 15–25 s |

**Fallback.** The whole ingest has a 150 s timeout. On failure, if the reel hash is in `cache/`, load the cached output and set `pipeline.usedFallback = true`. Live AI always runs first.

### 8.2 Plan workflow (ADK)

```
START → build_context → draft_plan node (PLANNER_MODEL, response_schema=PlanResult)
      → check_plan node (code) → violations? and attempts < 3 → draft_plan with violation list → check_plan …
      → write itinerary + plan/current, status = planned, notify
```

This is an ADK 2.0 dynamic workflow with a `while` loop, following the documented generate → check → refine pattern. `draft_plan` calls Gemini through google-genai rather than an `LlmAgent`, so the loop can be tested with a fake planner. Members and places reach the model as short aliases (M1, P1), which it copies more reliably than UIDs or place IDs; they map back when the plan is saved.

Planning starts when the last member submits votes, or when the host taps **Close voting and plan the trip**. If Gemini fails, the trip returns to voting with the error shown, and the host can try again.

**Planner input (JSON):**
- trip: dates, origin, destination
- members: `{id, name, budgetIdr, interests, dietary, skip}`
- verified places: `{id, name, category, location, hours for each trip date, rating, priceLevel, priceNote, dietaryNote, votes {must[], maybe[], skip[]}, savedBy[]}`
- merchant stays/tours catalog
- constraints: day window 08:00–21:00, at most 6 stops a day, lunch around 12:00, dinner around 19:00

**`PlanResult` schema.** Use lists rather than dynamic-key maps, because they are friendlier to Gemini response schemas.
- `days[]`: `{date, title, stops[]: {place_id, start, end, attendee_ids[], est_cost_per_person_idr, note}}`
- `stay`: `{sku, reason} | null`
- `compromises[]`: `{member_id, gave_up, got, reason}`
- `why_this_plan`: ≤ 120 words, naming members and trade-offs
- `estimates[]`: `{member_id, amount_idr}`

**Validator rules** (`ai/validator.py`, unit-tested). Errors trigger a retry; warnings are shown in the UI as "Heads-up".

| # | Check | Severity |
|---|---|---|
| V1 | every `place_id` is a verified place; no duplicates | error |
| V2 | each stop falls within opening hours for that weekday | error (warning if hours unknown) |
| V3 | no overlaps; gap ≥ haversine_km ÷ 25 km/h + 10 min | error |
| V4 | attendees ⊆ members; nobody attends a category they marked `skip` | error |
| V5 | food stops with halal-requiring attendees are not marked non-halal | error (warning if unknown) |
| V6 | any place with ≥ half "must" votes is included, or explained in `compromises` | error |
| V7 | each member estimate ≤ budget, or the member appears in `compromises` | error |
| V8 | dates within the trip range; ≤ 6 stops a day | error |

After 2 failed retries, write the best attempt and surface the remaining issues as warnings.

### 8.3 Re-plan (P1)
Same workflow, given the current plan, `dayIndex`, and the instruction (for example "make day 2 more relaxed"). Only that day may change. Same validator.

### 8.4 Receipt scan
- `FAST_MODEL` with an image part and `response_schema` `Receipt`: `{merchant, items[]: {name, unit_price, qty, line_total}, subtotal, tax, service, discount, total, currency}`.
- Check that Σ line_total ≈ subtotal and subtotal + tax + service − discount ≈ total, within 1%. On mismatch, the UI flags it for the user to fix.
- The result goes back to the client. Nothing is saved until the user assigns portions and saves the expense.

---

## 9. Money logic (`api/travelin/money/`, deterministic)

- All amounts are **integer IDR**. Convert to floats only at the AP2 boundary.
- **Split modes:**
  - `equal`: largest-remainder rounding, so shares sum exactly (100,000 ÷ 3 = 33,334 / 33,333 / 33,333).
  - `shares`: weighted.
  - `exact`: must sum to the amount.
  - `items`: each item is split by portions. Tax, service, and discount are allocated proportionally to each person's item subtotal, using largest-remainder rounding.
- **Balance:** Σ paid − Σ owed + Σ confirmed sent − Σ confirmed received.
- **Simplify:** exact minimum transfers for n ≤ 8.
  - Bitmask DP finds the maximum number of disjoint zero-sum groups.
  - Each group of size k settles in k − 1 transfers, largest debtor to largest creditor.
  - Total transfers = (members with nonzero balance) − (number of groups).
- **Tests (pytest):**
  - conservation (Σ balances = 0)
  - applying the transfers zeroes every balance
  - rounding cases
  - proportional tax on a receipt
  - a case where naive greedy needs more transfers than the optimum
- **UI explainer "Why do I pay Dina?":** shows your total share, what you paid, your net, and that simplification routed your payment to Dina.
- The client shows a live preview while editing an expense. The saved `computedShares` from the API is authoritative.

---

## 10. Group booking with AP2

Use the Pydantic models from the official SDK: install with `uv pip install git+https://github.com/google-agentic-commerce/AP2.git@main` and import from `ap2.models.mandate` and `ap2.models.payment_request`.

**Flow**
1. The planner suggests a stay or tour from the merchant catalog. The itinerary shows a **Book this stay** card, and any member taps **Propose booking**.
2. The API builds an `IntentMandate`:
   - `natural_language_description`: for example "2-night homestay in Yogyakarta for 4 people, 24–26 Oct 2026"
   - `merchants`, `skus`
   - `user_cart_confirmation_required=True`
   - `intent_expiry` = now + 24 h
3. API calls merchant `POST /carts`. The merchant returns a `CartMandate`:
   - `contents`: `CartContents{id, payment_request: PaymentRequest{method_data, details: PaymentDetailsInit{id, display_items, total}}, cart_expiry, merchant_name}`
   - `merchant_authorization`: an ES256 JWT over `sha256(contents)`
4. The booking moves to `approving`. Every member reviews the cart and taps **Approve**, which stores `approvals[uid] = {at, cartHash}`. If the cart changes, its hash changes and the approvals no longer count.
5. When approvals equal all members, the API builds a `PaymentMandate`:
   - `payment_mandate_contents`: `{payment_mandate_id, payment_details_id = cart id, payment_details_total, payment_response: PaymentResponse{request_id, method_name, details: {payer, mock token}}, merchant_agent}`
   - `user_authorization`: an ES256 JWT signed by Travelin, with claims `{cart_hash, mandate_hash, member_count, approvals: [{uid, at}]}`. This is the group authorization.
6. Merchant `POST /payments` checks:
   - its own cart signature
   - Travelin's signature, using `GET /.well-known/jwks.json` on `travelin-api`
   - approvals count = member_count = guests
   - the cart has not expired
   
   If all pass, the mock processor charges and returns a receipt. Otherwise it returns **403 with a reason**.
7. The API marks the booking `paid` and creates an expense `{source: 'booking', paidBy: payer, participants: all}`, which flows into Split Bill. The payer is the member who proposed the booking. Members are notified.

Approvals in the group authorization carry hashed member IDs: the merchant needs to count approvals, not to know who the travelers are. For local development, both services generate a temporary signing key when none is configured.

**Guardrails to show in the demo**
- The API refuses to build a `PaymentMandate` without N of N approvals on the current cart hash.
- The merchant re-verifies independently (defense in depth). In demo mode, a **Try with 3/4 approvals** button shows the merchant rejecting the payment.

**Honest scope (state this in the README):** AP2 mandate objects from the official SDK, exchanged over HTTPS JSON. A2A transport is not implemented, and payments are mocked.

**Fallback if the 3-hour timebox runs out:** keep the same approvals UI and N-of-N check, and have the merchant accept plain JSON.

**Merchant service**
- `catalog.json`: stays and tours for the demo destination, priced in IDR, with capacity.
- Endpoints: `GET /catalog?destination=` · `POST /carts` · `POST /payments` · `GET /orders/{id}` · `GET /.well-known/jwks.json` · `GET /healthz`.

---

## 11. Security rules (sketch)

```
// firestore.rules
function signedIn() { return request.auth != null; }
function trip(tripId) { return get(/databases/$(database)/documents/trips/$(tripId)).data; }
function isMember(tripId) { return signedIn() && request.auth.uid in trip(tripId).memberUids; }

match /trips/{tripId} {
  allow read: if isMember(tripId);
  allow write: if false;                                   // API only
  match /members/{uid} {
    allow read: if isMember(tripId);
    allow update: if request.auth.uid == uid
      && request.resource.data.diff(resource.data).affectedKeys().hasOnly(['prefs', 'prefsDone', 'votes'])
      && (resource.data.votesSubmittedAt == null
          || !request.resource.data.diff(resource.data).affectedKeys().hasAny(['votes']));
  }
  match /reels/{reelId} {
    allow read: if isMember(tripId);
    allow create: if isMember(tripId)
      && request.resource.data.uploaderUid == request.auth.uid
      && request.resource.data.status in ['queued', 'link_only'];
  }
  match /{sub}/{docId} {                                   // places, itinerary, plan, expenses, transfers, bookings
    allow read: if isMember(tripId);
    allow write: if false;
  }
}
match /users/{uid} {
  allow read, write: if request.auth.uid == uid;
  match /notifications/{n} {
    allow read: if request.auth.uid == uid;
    allow update: if request.auth.uid == uid
      && request.resource.data.diff(resource.data).affectedKeys().hasOnly(['read']);
  }
}
match /cache/{doc} { allow read, write: if false; }
```

**Storage rules:**
- Reels at `trips/{tripId}/reels/{uid}/{file}` and receipts at `trips/{tripId}/receipts/{uid}/{file}` can be written only by `uid` when that user is a trip member (cross-service `firestore.get`).
- Reels must be `video/.*` and < 100 MB. Receipts must be `image/.*` and < 10 MB.
- Read access is limited to members.

---

## 12. Frontend

**Stack:** Vite + React + TypeScript · React Router · Tailwind CSS · `vite-plugin-pwa` · Firebase Web SDK (modular) · `@vis.gl/react-google-maps`.

| Route | Screen | PRD feature |
|---|---|---|
| `/login` | Sign in with Google, install hint | 1 |
| `/` | Home: **Create a trip**, **Try with demo squad**, ongoing trips (stage chip), history (Unpaid / Waiting / Settled), bell with badge | 2 |
| `/notifications` | list, mark read, deep links | 3 |
| `/trips/new` | name, destination, origin, dates | 4 |
| `/join/:code` | trip preview, Join | 4 |
| `/trips/:id` | Trip hub: stage stepper, live squad avatars, "next action" card, share invite link | 4 |
| `/trips/:id/reels` | upload video / paste link, status per reel, tap opens original | 5 |
| `/trips/:id/prefs` | budget, interest chips, dietary, activities to skip | 6 |
| `/trips/:id/places` | live AI progress, dropped-places note, place cards, Must / Maybe / Skip, Submit, deadline banner | 7, 8 |
| `/trips/:id/places/:pid` | AI summary + Google Maps sources, "seen in Raka's reel at 0:14" | 7 |
| `/trips/:id/itinerary` | day tabs, map with numbered markers + route line, stops, **Why this plan**, compromises, heads-up, booking card, re-plan (P1) | 9, 13 |
| `/trips/:id/booking/:bid` | cart, N/N approvals, result | AP2 |
| `/trips/:id/split` | expenses, add / scan receipt, Settle up, approvals N/N, Adjust split | 10, 11 |
| `/trips/:id/split/:eid` | expense editor incl. receipt item portions | 10 |
| `/trips/:id/pay` | my transfers (Pay X → Mark as sent), incoming (Confirm), statuses | 12 |

**Plumbing**
- `lib/firebase.ts`: initialise the SDK.
- `lib/api.ts`: `fetch` wrapper that attaches the ID token.
- Hooks: `useAuth`, `useTrip`, `useMembers`, `useCollection` (wrapping `onSnapshot`).
- `format.ts`: `formatIDR`.

**PWA manifest:** `name: "Travelin"`, `short_name: "Travelin"`, `display: "standalone"`, `start_url: "/"`, theme color, icons 192 / 512 / maskable. Handle `beforeinstallprompt` on Home; show Add-to-Home-Screen steps on iOS.

**Design direction**
- Mobile-first, centered at about 480px on desktop.
- One sticky primary action per stage.
- Status chips everywhere.
- AI steps show honest progress ("Extracting 2/3 reels…"), not a bare spinner.
- Tap targets ≥ 44px, WCAG AA contrast, labelled inputs.

---

## 13. Demo squad mode

- `POST /v1/demo/trips` creates a trip for one destination. The user is the host, joined by three bots with conflicting preferences:
  - **Dina**: halal, budget IDR 1.5M
  - **Raka**: budget IDR 3M, loves nightlife, skips hiking
  - **Sari**: vegetarian, loves nature
  
  The trip also gets three sample reels copied from `gs://<bucket>/samples/`.
- **Bots act on the server right after the human does**, with a 2–3 s delay so realtime updates are visible:
  - they vote from their preferences and submit
  - they approve the split and the booking
  - they send and confirm their transfers
- Live AI runs by default. Cached outputs are a fallback only.
- Invite links still work, so the same build supports real multi-account testing.

**Sample content (Day 1):**
- 3 short travel videos (30–60 s) for one destination (for example Yogyakarta), with clear place names on screen or in speech. They must be self-recorded or licence-clear; note the source in `samples/README.md`.
- 2 receipt photos.

---

## 14. Notifications

In-app only: Firestore plus the bell. The API writes them for these events:
- member joined (to host)
- plan ready
- split reopened
- approval needed
- bill (new `unpaid` transfer, to payer)
- payment sent (to payee)
- payment confirmed (to payer)
- booking proposed
- booking paid

P1: a Cloud Scheduler job every 15 min calls `POST /v1/cron/deadlines` to send "voting closes in 1 h" and auto-close expired voting.

---

## 15. Deployment

```bash
# Web + rules
cd web && npm run build && cd ..
firebase deploy --only hosting,firestore,storage

# API
gcloud run deploy travelin-api --source api --region asia-southeast2 \
  --service-account travelin-api@$PROJECT.iam.gserviceaccount.com \
  --min-instances 1 --no-cpu-throttling --timeout 600 --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=global,FAST_MODEL=gemini-3.8-flash,PLANNER_MODEL=gemini-4-argon,... \
  --set-secrets PLACES_API_KEY=places-api-key:latest,TRAVELIN_SIGNING_KEY=travelin-signing-key:latest

# Merchant
gcloud run deploy travelin-merchant --source merchant --region asia-southeast2 \
  --min-instances 1 --allow-unauthenticated \
  --set-secrets MERCHANT_SIGNING_KEY=merchant-signing-key:latest
```

`--allow-unauthenticated` is intentional. Authentication happens in the app via Firebase ID tokens, and CORS is restricted to `ALLOWED_ORIGINS`.

**Deploy early and continuously.** Hosting goes live on Day 1, and both Cloud Run services go live on Day 2.

---

## 16. Schedule

### Day 1, Thu 15 Oct: Foundations & gathering
- [ ] GCP + Firebase project, APIs, service account, secrets, keys, budget alert
- [ ] **Smoke test**: video extraction via `gs://`, Maps grounding sources, planner model ID on Vertex
- [ ] Record or collect 3 sample reels and 2 receipts
- [ ] Monorepo scaffold; PWA shell; Google sign-in; Hosting deployed
- [ ] API skeleton on Cloud Run: auth guard, `POST /trips`, `POST /join`, `notify()`
- [ ] Screens: Login, Home, Create Trip, Join, Trip hub (live squad), Reels upload, Preferences
- [ ] Firestore + Storage rules v1

**Done when:** on the deployed URL, two Google accounts can create and join a trip, upload reels, and fill preferences, and the host gets a "joined" notification.

### Day 2, Fri 16 Oct: AI ingest & voting
- [ ] ADK 2.0 spike, ≤ 1 h: Workflow + parallel `ctx.run_node` + `LlmAgent` with `output_schema`, run inside FastAPI. If it fights back, use the prebuilt `ParallelAgent` / `LoopAgent`; agent modules stay the same.
- [ ] Extractor + cache
- [ ] Verifier (Places) + dedupe + dropped list
- [ ] Summarizer (Maps grounding) + sources UI
- [ ] Ingest endpoint as a background task with live progress
- [ ] Places board, place detail, voting, submit, deadline, close voting
- [ ] `travelin-api` deployed; time the 3-reel run

**Done when:** sample reels produce verified places with summaries in under 2 min on the deployed stack, and every member can submit votes.

### Day 3, Sat 17 Oct: Plan, money, booking
- [ ] Planner + validator loop; auto-trigger when all have submitted
- [ ] Itinerary screen: map, day tabs, Why this plan, compromises, heads-up
- [ ] `split.py` + `settle.py` + pytest suite
- [ ] Expenses CRUD; receipt scan + item portions
- [ ] Split open / approve / adjust; transfers send / confirm; Pay screen; Home chips; notifications
- [ ] Merchant service + AP2 booking, **timeboxed 15:00–18:00**, then fallback

**Done when:** the full loop works with 3 real accounts: reels → places → votes → itinerary → booking → split → approve → pay → settled.

### Day 4, Sun 18 Oct: Demo-proof & submit
- [ ] Demo squad mode + bots + cache fallback
- [ ] Loading, empty, and error states; PWA install on Android + iOS; check min instances
- [ ] README
- [ ] **12:00 feature freeze**
- [ ] Record video (script in §18), cut to ≤ 3:00, upload as public
- [ ] Deck → PDF
- [ ] Submit by 17:00 WIB (earlier if the official cutoff demands); open every link in an incognito window

### Cut list (cut from the top when behind)
1. Re-plan (P1)
2. Scheduler deadline reminders (deadline still shown; host closes voting manually)
3. `crowd_note` in summaries
4. Full AP2 → fallback: N-of-N approvals with plain-JSON merchant
5. Receipt scan → manual expenses only
6. YouTube link extraction

**Never cut:** reels → verified places → vote → itinerary with compromises → split → N-of-N approval → payments, plus demo squad mode.

---

## 17. Risks

| Risk | Mitigation |
|---|---|
| Model ID not available on Vertex `global` | models configured through env vars; Day 1 smoke test; fallback chain |
| ADK 2.0 API friction | 1 h spike on Day 2; prebuilt workflow agents as fallback; agent logic lives in plain modules |
| Gemini 403 on `gs://` | grant the Vertex AI service agent `storage.objectViewer` on the bucket |
| Maps-grounded output is not valid JSON | second-pass formatter with `response_schema` |
| Cold start or background CPU throttling | `--min-instances 1 --no-cpu-throttling` |
| Judge tests alone | demo squad mode |
| Places cost | minimal field mask, query cache, budget alert |
| Key leakage | Secret Manager; browser key restricted by referrer and API |
| Deadline | freeze at 12:00 Sunday; deploy daily |

---

## 18. Submission package

**Proposal deck (PDF, 10–12 slides)**
1. Title + tagline
2. Problem: group trips die in the chat (ideas scattered, no agreement, messy cost-sharing)
3. Who: groups of 3–8, "the Initiator" persona
4. Solution: one flow from saved Reels to settled
5. Product walkthrough (screens)
6. AI architecture: Extractor → Verifier → Summarizer · Planner + Validator loop · Receipt scan · ADK on Cloud Run
7. Trust: 100% Maps-verified places, explained compromises, deterministic money, N-of-N AP2 guardrail
8. Retail & Commerce fit: discovery → personalization → group booking through AP2; merchants gain demand signals from what groups save
9. Feasibility: measured cost per trip (Gemini tokens + Places calls, from billing after test runs), build status
10. Scalability: Cloud Run autoscaling, Firestore, stateless agents, cache by content hash
11. Roadmap: share-sheet import from Instagram/TikTok, real payment rails (QRIS / e-wallet via AP2-compatible providers), A2A merchant network, live inventory
12. Team

**Video script (≤ 3:00)**
| Time | Scene |
|---|---|
| 0:00–0:15 | Hook: a group chat full of Reels and a trip that never happens |
| 0:15–0:35 | Create trip, share invite, squad joins live |
| 0:35–1:05 | Add reels → AI extracts and verifies (show a dropped place) → summaries with Google Maps sources |
| 1:05–1:25 | Vote and submit |
| 1:25–1:55 | Itinerary on the map + Why this plan + compromises |
| 1:55–2:20 | Group booking with AP2: 3/4 approvals rejected, 4/4 paid |
| 2:20–2:45 | Split bill + receipt scan → approve → pay → confirm → Settled |
| 2:45–3:00 | Architecture slide + tagline |

**README outline:** what it is · live demo link + "Try with demo squad" · how it works · architecture diagram · Google Cloud services used · AI details (models, ADK workflows, grounding, validator) · run locally · deploy · tests · known limitations.

---

## 19. Rename checklist (Kumpul → Travelin)

- [ ] Project and service IDs: `travelin-<suffix>`, `travelin-api`, `travelin-merchant`
- [ ] PWA manifest, `<title>`, icons, splash
- [ ] All UI copy, notifications, emails
- [ ] README, deck, video, submission form
- [ ] Before submitting: `git grep -i kumpul -- ':!docs/'` returns nothing
