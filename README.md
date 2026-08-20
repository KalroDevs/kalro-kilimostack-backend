# KilimoSTACK / OpenAgriNet — KALRO Advisory Content & AI Backend

Reference backend implementation establishing **KALRO** as the certified
agricultural content **and** AI provider on the KilimoSTACK/OpenAgriNet
(OAN) network, per the Beckn-based architecture:

```
Provider Platform <-> Middleware <-> Beckn Adaptor-Provider <-> beckn <-> Beckn Adaptor-Seeker <-> Middleware <-> AI Layer <-> client
                                              ^                                    ^
                                              |                  Beckn protocol    |
                                              +----------------- Gateway ----------+
                                              |                                    |
                                              +------------- Beckn Registry -------+
```

This project builds the two boxes on the **left and right ends** of that diagram that are specific to KALRO, not the generic Beckn network infrastructure (Adaptors, Gateway, Registry) in the middle — those are standard KilimoSTACK/OAN network components this project integrates with, not reimplements.

| Diagram box | This project | Tech |
|---|---|---|
| **Provider Platform** | `kilimo_daftari/` | Django + Django REST Framework + Postgres |
| **AI Layer** | `kalro_knowledge_brain/` | FastAPI + Ollama (self-hosted LLM) + Chroma (vector DB) |
| *(client)* | `frontend/` | React + Vite — screens/certifies content and queries the AI Layer |

## Multi-provider, multi-service network (`providers/`)

The Provider Platform started as a single-institution (KALRO) system. The
`providers/` Django app extends it into a real multi-tenant network **without
modifying `advisory/` at all** — `AdvisoryResource` remains exactly as built,
and there's a test (`NetworkCatalogMergeTests.test_advisory_resource_model_is_unmodified`)
that guards this.

- **`Provider`** — a first-class institution/tenant (KALRO, a partner
  university, an FPO, a financial institution, an equipment-rental
  business, ...), replacing the old single `PROVIDER_ID` /
  `PROVIDER_INSTITUTION_NAME` settings with real rows. Seed the initial
  KALRO row (and a starter category set) with:
  ```bash
  python manage.py seed_providers
  ```
- **`ProviderMembership`** — which Django users may screen/manage which
  provider's listings. This is the actual multi-tenancy enforcement point
  (`providers/permissions.py`): a reviewer can only edit/screen listings
  for providers they belong to; staff/superusers bypass. Verified live: a
  KALRO-authenticated user attempting to screen another provider's listing
  gets `403 Forbidden`, and the listing is left untouched.
- **`ServiceCategory`** — the category taxonomy (`market_prices`,
  `equipment_rental`, `farmer_registry`, `credit_services`,
  `agro_input_supply`, `aggregation_services`, `fpo_services`, plus
  `advisory_content` representing the existing corpus) stored as **data**,
  not a Python enum — a new category needs an admin adding a row, not a
  deploy.
- **`CatalogItem`** — one flexible model covering every non-advisory service
  type. Shared fields (`price`, `price_unit`, `location`, `availability`,
  `fulfillment`) are real columns; whatever is specific to a category (a
  loan's interest rate, a tractor's coverage counties, a market price's
  commodity/date) lives in the `attributes` JSONField, by a convention
  documented per-category on `ServiceCategory.schema_hint`. This is the
  actual flexibility mechanism: onboarding a wildly different service type
  needs zero migration.
- Same **Screen & Classify vocabulary** (`currency_status`, `validation_status`,
  `risk_level`, `quality_flag`, `screening_notes`) is reused on `CatalogItem`
  as on `AdvisoryResource`, so every provider — whatever they sell — goes
  through one consistent certification workflow before it's network-visible.

### New API surface

| Endpoint | Purpose |
|---|---|
| `GET/POST /api/v1/providers/` | Provider registry (staff-managed writes; open reads) |
| `GET /api/v1/providers/mine/` | Providers the current user can screen/manage |
| `GET/POST /api/v1/service-categories/` | The category taxonomy (staff-managed writes) |
| `GET/POST /api/v1/catalog-items/` | Listings across every category; filter by `?provider=&category=&quality_flag=` |
| `PATCH /api/v1/catalog-items/{id}/screen/` | Screen & Classify workflow for a listing — provider-membership gated |
| `GET /beckn/network/providers/` | Every active provider network-wide, with which certified categories each has |
| `GET /beckn/network/{provider_id}/catalog/?category=` | Merged, certified catalog for one provider — combines `AdvisoryResource` (for KALRO) with `CatalogItem` |

The existing `/beckn/provider-profile/`, `/beckn/catalog/`, and
`/beckn/catalog/{publication_id}/` endpoints are untouched and keep working
exactly as before — they're KALRO's own advisory-content catalog. The
`/beckn/network/...` endpoints sit alongside them for the wider,
multi-provider view.

## Accounts & authentication (`accounts/`)

Self-service registration and login, on top of DRF's built-in `Token` model:

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/auth/register/` | Create an account — `{username, email?, password}` → `{token, user}` |
| `POST /api/v1/auth/login/` | `{username, password}` → `{token, user}` |
| `GET /api/v1/auth/me/` | Current user + `provider_memberships`, token-authenticated |
| `POST /api/v1/auth/logout/` | Deletes the current token, forcing re-login |

Registering grants **read access only** — no `ProviderMembership` is created.
This is intentional and matches the governed-onboarding design of the
`providers` app: joining the network to *screen or certify* content is an
admin decision, not a signup checkbox. An admin links an account to a
provider afterwards (Django admin, or `ProviderMembership.objects.create(...)`
in a shell) — the frontend picks this up automatically on next login.

**CORS**: `django-cors-headers` is configured (`CORS_ALLOWED_ORIGINS`,
defaulting to the Vite dev server origins) so the browser-based frontend can
actually call this API directly — this is easy to miss if you only test with
server-to-server or Node-based HTTP clients, neither of which enforce CORS
the way a real browser does.

## Why two services

- **Django (`kilimo_daftari/`)** is KALRO's system of record: it stores the
  full advisory content corpus, runs the human **Screen & Classify**
  workflow (scientific accuracy & currency checks, sorting by crop / topic /
  content type — the same workflow originally run in the Screen & Classify
  Excel template), and exposes a certified-content catalog API that a real
  Beckn Adaptor-Provider's client-facing module would call to make KALRO
  discoverable on the network.
- **FastAPI (`kalro_knowledge_brain/`)** is the RAG + LLM engine: it receives certified
  content from Django, chunks and embeds it (via Ollama) into a vector
  database, and answers farmer/extension-officer queries by retrieving
  grounded context and generating an answer with a self-hosted Ollama model
  — with safety-aware prompting that escalates high-risk advisory content
  (e.g. veterinary treatment, drug dosage) rather than answering confidently.

They are deliberately decoupled: Django can run (and be screened against)
independently of whether the AI Layer/Ollama is up, and a resource is only
pushed to the vector index once it's been marked `quality_flag =
ready_to_certify`.

---

## Quick start (Docker Compose)

```bash
docker compose up -d postgres ollama
docker compose run --rm model-puller        # pulls llama3.1 + nomic-embed-text into the shared Ollama volume
docker compose up -d kilimo_daftari kalro_knowledge_brain frontend

# Django: create an admin user + auth token, then import the sample resource
docker compose exec kilimo_daftari python manage.py createsuperuser
docker compose exec kilimo_daftari python manage.py drf_create_token <username>
docker compose exec kilimo_daftari python manage.py import_advisory_json /data/sample_camel_calf_resource.json
```

Open the frontend at **http://localhost:5173** — paste the token from
`drf_create_token` into **Settings**, then screen the imported resource in
the **Corpus Ledger** and mark it *Ready to Certify* to trigger a sync to
the AI Layer. Or drive it all via curl:

```bash
# Mark it certified (via admin UI at http://localhost:8000/admin/, or the API):
curl -X PATCH http://localhost:8000/api/v1/resources/1/screen/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token <token-from-drf_create_token>" \
  -d '{"quality_flag": "ready_to_certify", "currency_status": "current", "scientific_accuracy_check": "verified"}'
# This also triggers a best-effort sync to the AI Layer's /ingest endpoint.

# Ask the AI Layer a question:
curl -X POST http://localhost:8001/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I manage tick paralysis in camel calves?"}'
```

Django admin: http://localhost:8000/admin/
FastAPI interactive docs: http://localhost:8001/docs
Frontend: http://localhost:5173

### Onboarding a second provider (e.g. a tractor-hire FPO)

```bash
docker compose exec kilimo_daftari python manage.py shell -c "
from providers.models import Provider, ServiceCategory, ProviderMembership
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

fpo = Provider.objects.create(provider_id='mavuno.fpo', name='Mavuno Farmers Cooperative', institution_type='cooperative_fpo')
user, _ = User.objects.get_or_create(username='mavuno_reviewer')
ProviderMembership.objects.create(user=user, provider=fpo, role='reviewer')
token, _ = Token.objects.get_or_create(user=user)
print('Mavuno token:', token.key)
"

# Mavuno's own reviewer creates and screens their own listing --
# a KALRO token would get 403 here, and vice versa.
curl -X POST http://localhost:8000/api/v1/catalog-items/ \
  -H "Content-Type: application/json" -H "Authorization: Token <mavuno-token>" \
  -d '{"provider": 2, "category": 3, "title": "Tractor + Plough Hire, Nakuru County",
       "price": "1500.00", "price_unit": "per hour",
       "attributes": {"equipment_type": "tractor + plough", "operator_included": true}}'

curl -X PATCH http://localhost:8000/api/v1/catalog-items/1/screen/ \
  -H "Content-Type: application/json" -H "Authorization: Token <mavuno-token>" \
  -d '{"quality_flag": "ready_to_certify", "risk_level": "low"}'

# Both providers now show up on the network, each with their own certified catalog:
curl http://localhost:8000/beckn/network/providers/
curl http://localhost:8000/beckn/network/mavuno.fpo/catalog/
```

## Quick start (without Docker)

```bash
# Django backend
cd kilimo_daftari
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py import_advisory_json ../data/sample_camel_calf_resource.json
python manage.py runserver 0.0.0.0:8000

# AI Layer (separate terminal; requires Ollama running locally: `ollama serve`,
# then `ollama pull llama3.1` and `ollama pull nomic-embed-text`)
cd kalro_knowledge_brain
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

Both services also run their test suites without a live Ollama server (the
AI Layer's tests mock the Ollama client):

```bash
cd kilimo_daftari && python manage.py test advisory
cd kalro_knowledge_brain && pytest tests/
```

### Frontend (without Docker)

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, talks to Django (8000) + AI Layer (8001) by default
```

Base URLs are configurable at runtime under **Settings** (persisted to
`localStorage`), so one build works against any deployment. See
`frontend/README.md` for the full page-by-page walkthrough, the design
system, and how to obtain an auth token for the screening workflow.

---

## Data model: JSON spec + Screen & Classify, in one table

`kilimo_daftari/advisory/models.py`'s `AdvisoryResource` table is built from
**two** sources, combined:

1. **Advisory Content Import JSON Specification v0.1** (`JSON_Data_Specification.docx`)
   — the wire format for submitting resources. Every top-level field has a
   matching model field (see the mapping table below). Nested objects
   (`geographic_applicability`, `seasonality`, `license`, `advisory_safety`)
   are kept as JSON columns for spec-exact round-tripping; section-level
   `content[]` items are a separate `ContentSection` table (one row per
   chunk — the granularity the AI Layer embeds).

2. **Screen & Classify working template** (the Excel workbook used earlier
   in this project to check scientific accuracy/currency and sort content by
   crop/topic/content type) — reproduced as first-class columns:
   `currency_status`, `scientific_accuracy_check`, `quality_flag`,
   `screening_notes`, `screened_by`, `screened_at`. The Django admin list
   view mirrors the spreadsheet's filter/sort experience (filter by sector,
   value chain, content type, quality flag, risk level).

Only resources with `quality_flag = ready_to_certify` are ever synced to
the AI Layer's vector index or exposed via the `beckn_provider` catalog —
the screening gate is enforced in both `advisory/services.py` (Django side)
and `kalro_knowledge_brain/app/ingestion.py` (AI Layer side, defensively).

### Field mapping (JSON spec → Django model)

| JSON spec field | Django field | Notes |
|---|---|---|
| `title`, `link`, `publication_id`, `thumbnail`, `institution` | same names | `publication_id` is unique (upsert key) |
| `author` | `author` (JSONField) | list of strings |
| `publish_date` | `publish_date` (CharField) | kept as raw string — source dates aren't consistently formatted |
| `modified_date` | `modified_date` (DateTimeField, nullable) | empty string coerced to `null` |
| `content_type` | `content_type` (CharField) | validated leniently (real exports use free text like "PDF brochure") |
| `language`, `available_languages` | same names | |
| `sector`, `value_chain`, `commodity`, `production_system`, `advisory_domain`, `target_users` | same names | first-class + indexed for filtering |
| `geographic_applicability` | `geographic_applicability` (JSONField) | `{country, counties, agro_ecological_zones, notes}` |
| `seasonality` | `seasonality` (JSONField) | `{season, production_stage, timing_notes}` |
| `license` | `license` (JSONField) | open-shaped per spec |
| `validation_status`, `validated_by`, `review_date`, `next_review_date`, `preferred_citation` | same names | |
| `content[]` | `ContentSection` (FK table) | `content_id`, `reading_order`, `content_header`, `content_text`, `page_start/end`, `content_images`, `content_tables`, `content_warnings`, `content_tags` |
| `advisory_safety` | flattened onto the model | `risk_level`, `risk_domains`, `requires_human_review`, `escalation_guidance`, `safety_disclaimer` |
| *(not in spec)* | `currency_status`, `scientific_accuracy_check`, `quality_flag`, `screening_notes`, `screened_by`, `screened_at` | Screen & Classify workbook fields |
| *(not in spec)* | `vector_sync_status`, `vector_synced_at`, `vector_sync_error` | AI Layer sync bookkeeping |

---

## API surface

### Django backend (`kilimo_daftari/`)

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/ingest/` | Bulk import — accepts the JSON spec's array-of-resources payload exactly |
| `GET/POST /api/v1/resources/` | List/create resources; filter by `?sector=&value_chain=&content_type=&quality_flag=&risk_level=` etc. |
| `GET/PUT/PATCH/DELETE /api/v1/resources/{id}/` | Single resource CRUD |
| `PATCH /api/v1/resources/{id}/screen/` | Screen & Classify workflow — update just the review columns |
| `POST /api/v1/resources/{id}/sync-to-ai-layer/` | Manually (re)push one resource to the AI Layer |
| `POST /api/v1/resources/sync-ready/` | Bulk-sync all certified-but-unsynced resources |
| `GET /beckn/provider-profile/` | Static provider identity for network registration |
| `GET /beckn/catalog/` | Certified-content catalog (what a Beckn Adaptor-Provider would read) |
| `GET /beckn/catalog/{publication_id}/` | Full certified resource record |

### AI Layer (`kalro_knowledge_brain/`)

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/ingest` | Accepts spec-shaped resources, chunks + embeds + stores in Chroma |
| `POST /api/v1/chat` | RAG query: `{"query": "...", "top_k": 5, "filters": {"sector": "livestock"}}` |
| `GET /health` | Ollama + vector store reachability, indexed chunk count |

---

## Populating Chroma from the Django database

The Django database is the system of record; Chroma is a **derived index**
built from whatever's currently certified there. Nothing writes to Chroma
directly — everything goes through the AI Layer's `POST /api/v1/ingest`,
which chunks, embeds, and stores. Three ways to trigger it:

**1. Automatic, as content gets certified (the normal path)**
`PATCH /api/v1/resources/{id}/screen/` with `{"quality_flag": "ready_to_certify"}`
(or the equivalent "Save screening decision" button in the frontend, or the
"Mark selected as Ready to Certify" admin action) fires
`advisory/services.py::sync_resource_to_kalro_knowledge_brain()` automatically.

**2. Backfilling everything already certified**
```bash
# Via the API (what the frontend/admin bulk action calls):
curl -X POST http://localhost:8000/api/v1/resources/sync-ready/ \
  -H "Authorization: Token <your-token>"

# Or via the management command (scriptable, no HTTP auth needed locally):
python manage.py sync_to_kalro_knowledge_brain

# Re-embed everything, even already-synced resources (e.g. after changing
# chunking logic or rebuilding the Chroma volume):
python manage.py sync_to_kalro_knowledge_brain --resync-all

# Just one resource:
python manage.py sync_to_kalro_knowledge_brain --publication-id kalro-livestock-camel-calf-management-2017-043
```
Both only ever touch resources with `quality_flag = ready_to_certify` — the
same guard as the automatic path — and `vector_sync_status` on each
resource tells you what happened (`synced`, `failed`, with the error
message in `vector_sync_error` if it failed).

**3. One resource at a time, on demand**
`POST /api/v1/resources/{id}/sync-to-ai-layer/`, the frontend's "Sync to AI
Layer" button, or the "Sync selected..." admin action.

**Checking it worked:**
```bash
curl http://localhost:8001/health   # vector_store.indexed_chunks should increase
```
or query `GET /api/v1/resources/?vector_sync_status=synced` on the Django
side.

**Scope note**: this backfill only covers `AdvisoryResource` — `CatalogItem`
(market prices, equipment rental, etc., from the `providers` app) isn't
wired into the vector index yet. See "Production hardening notes" below.

---

## RAG pipeline (`kalro_knowledge_brain/app/`)

1. **Chunking** (`ingestion.py`) — one chunk per `content[]` section
   (sections in KALRO exports are already coherent, paragraph-length units);
   longer sections are split on paragraph boundaries.
2. **Embedding** — each chunk (prefixed with resource title + section
   header for topical context) is embedded via Ollama's `/api/embeddings`
   (default model: `nomic-embed-text`).
3. **Storage** (`vector_store.py`) — embeddings + documents + rich metadata
   (sector, value_chain, commodity, AEZ, risk_level, quality_flag,
   content_tags, ...) are upserted into a persistent Chroma collection.
   Re-ingesting a resource clears its previous chunks first (idempotent).
4. **Retrieval + generation** (`rag.py`) — a query is embedded, the top-k
   nearest chunks are retrieved (optionally filtered by sector/value_chain),
   and a system prompt is built that:
   - restricts the model to only the retrieved context,
   - forces an explicit "consult a qualified expert" caveat whenever any
     retrieved chunk carries `content_warnings` or `requires_human_review`,
   - asks for source citations.
   The prompt + query go to Ollama's `/api/chat` (default model:
   `llama3.1`). The response includes the answer, ranked source citations,
   and a `risk_level` / `safety_notice` computed from the retrieved
   metadata (independent of what the LLM itself says, so safety flagging
   isn't solely dependent on the model behaving).

---

## Production hardening notes

This is a runnable **reference** implementation. Before real deployment:

- **`CatalogItem.attributes` tradeoff**: storing category-specific fields as
  JSON (rather than a table per category) means fast onboarding but weaker
  DB-level querying/validation on those fields (e.g. filtering by
  `interest_rate_pct < 12` needs Postgres JSON operators, not a plain
  column, and nothing stops a provider submitting the "wrong" shape for
  their category — `schema_hint` is documentation, not enforcement). If a
  specific attribute on a specific category turns out to be heavily
  queried, "graduate" it into a real column or a per-category child table —
  a normal, low-risk evolution, not a redesign.
- **Provider onboarding is staff-only by design** (`IsStaffOrReadOnly` on
  `ProviderViewSet`) — joining the network is treated as a governed
  decision, not self-service signup, matching the Root/Registrar model.
  Relax this deliberately if self-service onboarding is actually wanted.
- **AI Layer sync currently covers `AdvisoryResource` only.** `CatalogItem`
  listings (market prices, equipment rental, etc.) are not indexed into the
  RAG vector store — they're discoverable via `/beckn/network/...` but the
  chat assistant can't yet answer "where can I rent a tractor near me" by
  retrieving them. Extending `kalro_knowledge_brain/app/ingestion.py` to also accept
  `CatalogItem`-shaped payloads (structured, not chunked prose) is a
  natural next step if that's wanted.

- **Sync mechanism**: `advisory/services.py`'s Django→AI Layer sync is a
  synchronous HTTP call for simplicity. Replace with a Celery task (or
  Django signal + outbox pattern) so screening isn't blocked by AI Layer
  availability, and add retries.
- **Vector store**: Chroma needs no separate server, which is why it's the
  default here. For production, consider `pgvector` inside the same
  Postgres instance the Django backend already uses, so the corpus and its
  embeddings share one backup/DR story — `vector_store.py`'s
  `upsert_chunks` / `query` interface is narrow enough to swap.
- **Auth**: `kalro_knowledge_brain_INGEST_API_KEY` is a bare shared secret; swap for
  mTLS or a signed-request scheme when integrating with a real Beckn
  Adaptor.
- **Beckn protocol**: `beckn_provider/` exposes plain REST endpoints for a
  Beckn Adaptor-Provider's client-facing module to call — it does not speak
  the Beckn protocol (`search`/`on_search`/`select`/...) itself. Point an
  actual Beckn Adaptor-Provider instance at these endpoints, or extend
  `beckn_provider/views.py` if you need to speak Beckn callbacks directly.
- **Content images/tables**: kept as JSON on `ContentSection` per the spec's
  own nested shape; the spec notes "images would need extraction and
  storage separately" — wire `content_images[].image_url` to real object
  storage (S3/GCS/MinIO) rather than leaving it as a bare URL string.
- **Multi-language**: `language` / `available_languages` are captured but
  the RAG prompt is English-only; add translation or per-language Ollama
  models for Swahili-first delivery.

---

## Repository layout

```
kilimostack-kalro-backend/
├── docker-compose.yml
├── data/
│   └── sample_camel_calf_resource.json      # real KALRO example, used by both test suites
├── kilimo_daftari/                          # "Provider Platform"
│   ├── config/                              # settings, urls, wsgi/asgi
│   ├── advisory/                            # models, serializers, views, admin, services, tests
│   │   └── management/commands/import_advisory_json.py
│   ├── providers/                           # multi-tenant Provider / ServiceCategory / CatalogItem
│   │   └── management/commands/seed_providers.py
│   ├── accounts/                            # register/login/me/logout (DRF token auth)
│   ├── beckn_provider/                      # certified-content catalog + multi-provider network catalog
│   └── manage.py
├── kalro_knowledge_brain/                                # "AI Layer" (FastAPI + Ollama + Chroma)
│   ├── app/
│   │   ├── main.py, config.py, schemas.py
│   │   ├── ollama_client.py, vector_store.py
│   │   ├── ingestion.py, rag.py
│   │   └── routers/ (ingest.py, chat.py, health.py)
│   └── tests/
└── frontend/                                # React + Vite client
    ├── src/
    │   ├── components/                      # Layout, RequireAuth, PageHeader, Stamp (signature), States
    │   ├── pages/                            # Landing, Login, Register, Dashboard, Resources, ResourceDetail, Import, Advisory, Settings
    │   └── lib/                              # advisoryApi.ts, authApi.ts, aiLayerApi.ts, authStore.ts, settingsStore.ts
    └── README.md                             # design system + page-by-page notes
```
