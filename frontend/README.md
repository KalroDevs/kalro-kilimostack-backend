# KALRO Advisory Corpus — Frontend

React + Vite client for the `django_backend/` (Provider Platform) and
`ai_layer/` (FastAPI + Ollama) services in this repo. Screens and certifies
KALRO's advisory content, then lets you query the AI advisory service it
powers — directly from the browser.

## Design

Visual identity is deliberately not a generic admin-dashboard look: it takes
its cues from herbarium specimen sheets and scientific accession
records — a genuine nod to KALRO's role *certifying* content before it
reaches farmers. The signature element is the **stamp badge**
(`src/components/Stamp.tsx`), a rotated ink-stamp treatment used for
`quality_flag`, `risk_level`, `currency_status` and `scientific_accuracy_check`
throughout the app. Typography: Fraunces (display), Inter (body/UI), IBM Plex
Mono (IDs, codes, data values) — see `tailwind.config.js` for the full token
system (`herbarium`, `moss`, `ochre`, `rust`, `wire`, `paper`, `canvas`).

## Pages

| Route | Auth | Purpose |
|---|---|---|
| `/` | Public | Landing page — what the platform does, links to log in / register |
| `/login` | Public | Log in; redirects to `/dashboard` (or wherever you were headed) |
| `/register` | Public | Self-service account creation — grants read access immediately; provider/screening access is linked by an admin afterwards |
| `/dashboard` | Required | Corpus totals by quality flag and sector, AI Layer health |
| `/resources` | Required | Corpus ledger — filterable/searchable table (sector, quality flag, risk level, search) |
| `/resources/:id` | Required | Resource detail — full metadata, content sections, the Screen & Classify form, AI Layer sync |
| `/import` | Required | Paste or upload a JSON file matching the Advisory Content Import JSON Specification v0.1 |
| `/advisory` | Required | Chat interface against the AI Layer's `/api/v1/chat` (RAG + Ollama), with source citations and safety notices |
| `/settings` | Required | Current session info, plus Django/AI Layer base URLs with live reachability checks |

"Required" routes redirect to `/login` if there's no session (`src/components/RequireAuth.tsx`), and remember where you were headed so login sends you back.

## Authentication

Real accounts, not a pasted token: `/register` and `/login` call the
Django backend's `accounts` app (`/api/v1/auth/register/`, `/login/`,
`/me/`, `/logout/`) and store the returned token + user in
`src/lib/authStore.ts` (persisted to `localStorage`). Every subsequent API
call reads the token from there automatically.

Registering does **not** grant provider access — it mirrors the backend's
governed-onboarding design (see the root README's "Multi-provider,
multi-service network" section). A new account can browse certified
content immediately; an admin has to create a `ProviderMembership` (via
Django admin or the API) before that account can screen/certify anything.
The sidebar and Settings page both show "No provider access yet" until
that happens.


## Quick start

```bash
npm install
npm run dev       # http://localhost:5173
```

By default the app talks to `http://localhost:8000` (Django) and
`http://localhost:8001` (AI Layer) — the same ports `docker-compose.yml` at
the repo root exposes. Change them any time under **Settings**; they're
stored in `localStorage`, not build-time env vars, so the same build works
against any backend.

### Getting screening access after you register

Log in normally through `/login` — that's enough to browse everything. To
actually **save** a screening decision (`PATCH /resources/{id}/screen/`) or
`/catalog-items/{id}/screen/`, your account needs a `ProviderMembership`.
An admin grants this via Django admin (`/admin/providers/providermembership/`)
or the shell:

```bash
cd ../django_backend
python manage.py shell -c "
from django.contrib.auth.models import User
from providers.models import Provider, ProviderMembership
user = User.objects.get(username='<your-username>')
provider = Provider.objects.get(provider_id='kalro.kilimostack')
ProviderMembership.objects.create(user=user, provider=provider, role='reviewer')
"
```

Log out and back in (or refresh) afterwards — the sidebar and Settings page
pull `provider_memberships` fresh from `/api/v1/auth/me/` on login.

### Production build

```bash
npm run build      # type-checks (tsc -b) then bundles with vite
npm run preview     # serve the production build locally
```

## Project layout

```
frontend/
├── src/
│   ├── components/       Layout, PageHeader, RequireAuth, Stamp (signature), SectorChip, States
│   ├── pages/             Landing, Login, Register, Dashboard, Resources, ResourceDetail, Import, Advisory, Settings
│   ├── lib/
│   │   ├── advisoryApi.ts   Django backend client (advisory + providers endpoints)
│   │   ├── authApi.ts       Django accounts client (register/login/me/logout)
│   │   ├── aiLayerApi.ts    FastAPI AI Layer client
│   │   ├── authStore.ts     Zustand store for the session (token + user, persisted)
│   │   ├── settingsStore.ts Zustand store for API base URLs (persisted)
│   │   └── format.ts        date/label formatting helpers
│   ├── types.ts           TS types mirroring the Django/FastAPI schemas
│   ├── App.tsx             routes (public: /, /login, /register — protected: everything else)
│   └── main.tsx            React Query + Router providers
├── tailwind.config.js     design tokens
└── vite.config.ts
```

## Verified against the live backend

This client was built and smoke-tested against a real, running instance of
`django_backend/` in the same environment (not just type-checked): listing
resources, filtering by sector, fetching a single resource, saving a
screening decision, and triggering an AI Layer sync all round-tripped
correctly using the project's real sample data
(`data/sample_camel_calf_resource.json`).

The auth flow specifically was verified end-to-end against the live
`accounts` app: register → login → `/me` → authenticated read → logout
(confirmed the same token stops working afterwards) → a wrong-password
login attempt correctly rejected. A fresh registration was confirmed to
come back with an empty `provider_memberships` array, matching the
backend's governed-onboarding design. CORS was also verified directly
(preflight `OPTIONS` request from the Vite dev origin returns the expected
`access-control-allow-origin` header) — this matters because Node-based
testing doesn't enforce CORS the way a real browser does, so it's an easy
gap to miss.
