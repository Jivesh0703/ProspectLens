# AccountBrief

An account research agent for GTM teams. Provide a company website, your offering and ideal customer criteria. AccountBrief researches relevant pages, checks exact source evidence and returns a fit assessment plus a reviewable outreach draft.

## Requirements

- Python 3.10 or newer
- A browser and internet connection
- Your own Gemini API key with access to the configured model

The research core uses Python's standard library. The HTTP server uses Flask and Waitress, pinned in `requirements.txt`. No frontend build or database is required.

## Setup

Create and activate an isolated environment from this directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Then copy `.env.example` to `.env` if you do not already have `.env`:

```sh
cp .env.example .env
```

Do not replace an existing `.env` containing your key. Edit its values:

```dotenv
GEMINI_API_KEY=YOUR_PERSONAL_KEY
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_RPM=5
```

`GEMINI_RPM` should match your model/project's active requests-per-minute quota, not an assumed universal free-tier limit. Check your actual limits in Google AI Studio. Existing process environment variables take precedence over `.env`. Restart after changing settings.

`.env` is ignored by Git and excluded from the source ZIP. Keep it private. The app reads it server-side; the key is not sent to the browser.

## Run

```sh
python3 app.py
```

Open **http://127.0.0.1:8765**. Keep the terminal running; stop with Ctrl+C. For a different local port:

```sh
python3 app.py --port 8766
```

Local startup defaults to `127.0.0.1:8765`. On Render, the app binds to `0.0.0.0` and the assigned `PORT`, uses Waitress, requires reviewer credentials and trusts only the HTTPS scheme from Render's proxy. Use `render.yaml` in this directory for a Render Blueprint deployment. Make `accountbrief/` your Git repository root and leave Render’s Root Directory empty. The blueprint intentionally has no `rootDir` setting.

## Use

1. Enter a real public company website, such as `https://www.atlassian.com/`.
2. Describe your offering in 20–1200 characters.
3. Enter 1–5 unique ideal customer criteria, one per line.
4. Select **Build account brief**.
5. Review the criteria explanations, source quotes, discovery question and outreach draft. Download Markdown or JSON if useful.

Example offering: “We help B2B software finance teams reconcile subscription payments, match invoices, and investigate unmatched transactions.”

Example criteria: B2B software company; Subscription pricing; International customers.

Evidence coverage counts criteria with supporting evidence. It is not buying intent, a lead score or a forecast. Unknown means the inspected evidence did not establish that criterion; it does not prove the company is unsuitable.

There is no application demo mode or synthetic fallback. Automated tests use isolated fixtures and simulated provider responses only.

## How the agent works

- Python fetches the initial public webpage.
- Gemini receives selected source excerpts and criterion-specific link suggestions, then chooses relevant product, pricing or customer/company pages through `research_pages`.
- Python retrieves that batch. Gemini selects stable source snippet IDs and submits the fit explanations, discovery question and unknowns through `complete_research`.
- Python resolves IDs to exact stored quotes, checks source provenance and references, applies conservative relevance checks and builds the report/draft.
- An invalid completion can be corrected within the remaining request budget. The first model decision can select research pages; later decisions complete or correct the brief.

The default agent is capped at **three total Gemini request attempts**, **four pages including the initial page**, and ten tool actions. The representative path can complete in two model requests. Up to three follow-up pages are fetched in one batch. Model excerpts are limited to 3000 text characters per page; full HTML and local article text have no byte/character cutoff. JavaScript is not executed, so content loaded later by the website may be absent.

The checked run budget is 180 seconds. Each provider request waits at most 90 seconds, less pacing delay and the remaining run budget. Network/DNS overhead can exceed a hard deadline. A shared in-process limiter spaces requests using `GEMINI_RPM`; usage by other applications/processes on the same Google project is not coordinated.

HTTP 503 may be retried once after a short wait, inside the same three-attempt cap. Long Retry-After values, repeated 503s and exhausted budgets stop the run. Timeouts, quota errors and permanent errors are not automatically retried. Gemini availability and free-tier capacity are not guaranteed.

## Evidence and outreach checks

Extraction excludes navigation/menu text, headers/footers, scripts, styles and hidden content, while retaining useful links. Targeted passages and short pricing/country-count statements are prioritized. Exact source quotes are selected by ID rather than retyped by the model.

Common ICP categories have conservative lexical relevance guards in addition to model explanations. These are heuristics, not semantic proof. Company statements are not independently verified. Outreach uses evidence referenced by supported criteria, avoids discontinued-product/refund/legal notices, and uses a neutral opening if no appropriate quote remains. Unverified workflows are phrased as conditional discovery questions. No email is sent and no CRM is changed.

## CLI and HTTP API

Save an input file such as `request.json`:

```json
{
  "url": "https://www.atlassian.com/",
  "product": "We help B2B software finance teams reconcile subscription payments and investigate unmatched transactions.",
  "criteria": ["B2B software company", "Subscription pricing", "International customers"]
}
```

Run it with your configured key:

```sh
python3 app.py --input request.json --output brief.json
```

Expected output: JSON containing `status`, `coverage`, explained `fit` entries, source `evidence`, `hypothesis`, `unknowns`, `outreach_draft`, `warnings`, `trace`, `model_requests` and a rendered `markdown` report. Live evidence and coverage vary by site and model response. Invalid input exits with code 2.

- `GET /api/health`: public, minimal process health (`{"ok": true}`); reveals no key/configuration values. Other routes require credentials when access protection is enabled.
- `POST /api/research`: accepts the same JSON input. `mode` may be omitted or set to `gemini`; other modes are rejected.
- `workflow` defaults to `agent`. An explicit `efficient` backend alternative performs local source selection and one AI assessment; the website uses the agent.
- Malformed input returns HTTP 400. Provider failures return a structured result with `status: Research unavailable` and `service_error`; the UI shows the error instead of a fit assessment.

## Project layout

| Path | Purpose |
|---|---|
| `app.py` | CLI/startup, retrieval, agent, validation and exports |
| `server.py` | Flask routes, reviewer authentication, request controls and Waitress serving |
| `static/` | Browser interface: HTML, CSS and JavaScript |
| `tests/` | Automated tests |
| `tests/fixtures/` | Test-only fictional webpages and request data; never loaded by the application |
| `tools/diagnose_gemini.py` | Opt-in model metadata/minimal inference diagnostic; uses your key and may consume quota |
| `.env.example` | Shareable configuration template |
| `requirements.txt` | Runtime dependency information |

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests mock webpage retrieval/provider responses; running the suite does not consume Gemini quota. Coverage includes normal/sparse/invalid cases, adaptive tool calls, exact evidence IDs, targeted source selection, outreach safeguards, request budgets/pacing, TLS errors, quota/provider failures and bounded 503 retry. The application has also completed approved live Atlassian research runs; that does not establish future model availability or output accuracy.

Public retrieval requires same-host HTTP(S) URLs, public DNS destinations, verified TLS and robots permission. Cross-host redirects, login/paywall pages and JavaScript-only content are not supported. Render production mode requires a 12+ character `ACCESS_PASSWORD` and the Gemini key. A single in-process research gate prevents concurrent model runs; `MAX_DAILY_RESEARCH` defaults to 20 research attempts per UTC day in production. This allowance is in-memory and resets on server restart, redeploy or free-service sleep/restart; it is not an account-wide or persistent spending cap. Invalid input is rejected before allowance consumption. Valid research attempts count even if provider/retrieval fails. A multi-instance deployment would require shared quota storage. No deployment or push is performed by these configuration files.

## References

- [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling)
- [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Gemini troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting)

## Deployment verification

84 tests pass, including authenticated/unauthenticated routes, Render HTTPS-origin handling, host validation, cross-site rejection, payload limits, concurrency and daily allowances, failure cleanup and environment-based binding. An actual local Waitress smoke test verified readiness, password gating, HTTPS headers and the static UI with a fake API key and no Gemini calls. The Render service itself has not yet been created or tested.
