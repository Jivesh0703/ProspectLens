# ProspectLens

An agentic account research workspace for GTM and revenue teams. Research company websites against your ideal customer profile, inspect the source evidence, and prepare outreach for review. Save customer profiles, research a list of accounts, and attach reviewed briefs to Salesforce accounts.

## Features

- **Evidence-backed account research.** Gemini selects relevant pages and source snippet IDs. Python resolves the IDs to the original text, validates references, and checks common fit categories.
- **Reusable customer profiles.** Save your offering and fit criteria, then apply them to different accounts.
- **Batch research.** Upload up to 20 company URLs in a CSV. Research runs sequentially and shows supported criteria, unknowns, and accounts needing manual review. Open individual briefs or download the batch summary.
- **Saved briefs.** Search and reopen the latest 30 briefs in your browser, with original retrieval timestamps. Download Markdown or JSON for a separate copy.
- **Salesforce integration.** Connect your Salesforce account through OAuth, review a brief, and save it as a completed task linked to an existing Account.
- **Gemini model fallback.** Try configured alternative models after eligible provider failures within the same three-attempt research budget.

## Run locally

Use Python 3.10+ and a Gemini API key with access to the configured models. The deployment selects Python 3.13. Flask and Waitress dependencies are pinned in `requirements.txt` and in `pyproject.toml` for Vercel. Keep both dependency lists in sync; the research core uses Python's standard library. Node.js is only needed for the frontend regression tests.

From the repository root, containing `app.py`:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate with `.venv\Scripts\activate`.

If you don't already have `.env`, copy the template:

```sh
cp .env.example .env
```

Set these values in `.env`:

```dotenv
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_FALLBACK_MODELS=gemini-3.1-flash-lite
GEMINI_RPM=5
MAX_DAILY_RESEARCH=20
APP_ENV=development
```

Model availability and quotas depend on your Google project. Set RPM to your actual allowance. An empty `GEMINI_FALLBACK_MODELS` disables fallback; at most three distinct models can be configured including the primary. Changing models does not increase your project's quota. Existing process environment variables override `.env`; restart after editing configuration.

Start the application:

```sh
python app.py
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). Stop with Ctrl+C. For another port, use `python app.py --port 8766`.

## Research an account

Enter a public company URL, an offering of 20–1200 characters, and 1–5 unique criteria of 3–120 characters each. Build the brief, inspect the fit explanations and source excerpts, and review the discovery question and draft.

For example:

```json
{
  "url": "https://www.atlassian.com/",
  "product": "We help B2B software finance teams reconcile subscription payments, match invoices, and investigate unmatched transactions.",
  "criteria": [
    "B2B software company",
    "Subscription pricing",
    "International customers"
  ]
}
```

Expected output includes a fit entry for each criterion, exact quotations with source URLs and retrieval timestamps, a discovery question, unknowns, an outreach draft when evidence is sufficient, and the research activity. Coverage and wording vary with the website and model response. Subscription terms can support subscription pricing; reconciliation pain still needs discovery with the buyer. Unknown criteria reflect missing support in inspected pages.

To use the CLI, save that JSON as `request.json`:

```sh
python app.py --input request.json --output brief.json
```

For an invalid-input check, use `http://127.0.0.1/private`. The browser reports an input error, the API returns HTTP 400, and the CLI exits with code 2 before contacting Gemini. Provider failures return a research-unavailable result with `service_error`.

## Research a batch

Save a CSV such as:

```csv
url
https://www.atlassian.com/
https://www.hubspot.com/
https://www.gitlab.com/
```

1. Enter or load your offering and criteria.
2. Select the CSV under **Research a list** and click **Run batch**.
3. Keep the tab open. Each account uses the same profile snapshot and runs as a separate request.
4. Open completed briefs to inspect evidence, or download a CSV showing coverage, supported criteria, unknowns, and errors.

The input accepts a `url` column, quoted CSV fields, and up to 20 rows in a file smaller than 100 KB. Duplicate normalized URLs are removed. Private destinations are rejected by the backend. A quota/concurrency rejection leaves the current account queued and pauses the batch. A provider/retrieval failure marks that account unavailable and pauses before the next account. Resume continues queued accounts; failed accounts can be researched individually.

Pause finishes the current account before stopping. Completed briefs stay saved; the active queue stays in the current tab and is lost on reload. A batch of 20 accounts may need more than 20 Gemini requests, so plan for your free-tier request and daily quotas.

## Saved workspace

Profiles and briefs are stored in browser `localStorage` for this website origin. The workspace keeps up to 20 profiles and the latest 30 completed briefs. Saving the same profile name replaces its offering and criteria. Briefs with unknown findings are retained; service failures are excluded. Search the saved list by account or criterion, reopen a brief, or delete individual entries.

Saved research is a snapshot; run it again to refresh sources. Clearing browser data removes it. Storage failures are shown in the interface and downloads remain available. Data does not sync between devices, browsers, localhost, preview deployments, or production domains. Earlier AccountBrief browser data is read on the same origin when present.

## Connect Salesforce

The integration uses the Salesforce OAuth authorization-code flow with PKCE. Each visitor connects their own Salesforce identity. Saving creates a **completed Task** on the selected Account, containing source quotes and URLs, the discovery question, and the outreach draft. Existing account fields are preserved.

Create a Salesforce External Client App, or an existing Connected App, with OAuth web-server flow and API access (`api`). Set its exact callback URL to:

```text
https://your-project.vercel.app/api/salesforce/callback
```

For local development, register `http://127.0.0.1:8765/api/salesforce/callback` as an additional callback if your Salesforce configuration permits it.

Set these server environment variables:

```dotenv
SALESFORCE_CLIENT_ID=your_consumer_key
SALESFORCE_CLIENT_SECRET=your_consumer_secret
SALESFORCE_LOGIN_URL=https://login.salesforce.com
SESSION_SECRET=your_stable_random_secret_of_at_least_32_characters
```

Generate the session secret locally:

```sh
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Use `https://test.salesforce.com` for a sandbox. In production, set `APP_ORIGIN` to the deployment's exact HTTPS origin, especially for custom domains, and register the matching callback with Salesforce.

1. Click **Connect Salesforce** and authorize the app.
2. Open a completed brief and review its evidence, fit, and draft.
3. Check the review checkbox, enter the existing Salesforce Account ID (15 or 18 characters, starting `001`), and click **Save reviewed brief to Salesforce**.
4. Verify the new activity on that Account. Task visibility in Salesforce may depend on the account activity filters.

Salesforce API access and Task permissions are required. Org-specific validation rules or required custom fields can reject a save. The implementation uses REST API v61.0. Client credentials stay on the server. The user's access token is held in a signed HttpOnly, SameSite cookie, with Secure enabled in production and a one-hour application session. Flask session cookies are signed, not encrypted. Tokens are excluded from JavaScript responses and saved research. Reconnect when the Salesforce session expires. Disconnect clears the local session; revoke the app in Salesforce to remove its authorization.

A successful task ID is recorded on the saved brief to prevent another save through that view. CRM writes have no automatic retry. If a network error leaves the outcome uncertain, check Salesforce before trying again. Simultaneous saves from different tabs/devices are not deduplicated by a shared store.

Without Salesforce configuration, research, profiles, history, and batch downloads remain available. OAuth and task creation have automated mocked tests; a live org must still be used to verify permissions and configuration.

## Deploy on Vercel

The suggested repository name is **`prospectlens`**. Use the directory containing `app.py`, `index.py`, `pyproject.toml`, and `vercel.json` as the repository root.

1. Import the GitHub repository into Vercel.
2. Select **Flask** as the framework. Leave Root Directory empty if the app is at the repository root. If the repository contains the `prospectlens/` folder, select that folder as Root Directory.
3. Keep the framework's default build settings. The WSGI entrypoint is `index:app` in `pyproject.toml`.
4. Add `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS`, `GEMINI_RPM`, `MAX_DAILY_RESEARCH`, and `APP_ENV=production` to the appropriate environment scopes.
5. Add the Salesforce settings above if using CRM integration. Keep `SESSION_SECRET` stable across deployments. Set `APP_ORIGIN` for a custom domain or your canonical production URL.
6. Deploy. Vercel supplies its deployment and production hostnames; the backend validates those hosts and same-origin research requests.
7. Check `/api/health`, run one company, upload a small CSV, reopen a saved brief, test downloads, and complete Salesforce authorization and a reviewed save if configured.

`vercel.json` sets the Python function duration to 300 seconds. The research core checks a 180-second run budget between operations. Enable Fluid compute and verify the project's function duration in Vercel. Network operations can add overhead beyond the core budget.

Research is public and uses the owner's Gemini quota. No visitor Gemini key is needed. Rate limiting, concurrency, and daily allowances are **per process**. Vercel can start multiple instances; these counters do not enforce a project-wide daily cap. Use provider quotas for account-level limits. Persistent, distributed usage enforcement is a remaining scaling task.

## Agent and fallback behavior

Python retrieves the initial webpage. Gemini chooses up to three same-host follow-up pages through `research_pages`, then calls `complete_research` using IDs from the retrieved snippets. Python resolves those IDs, validates references and common-category evidence checks, and builds the brief and exports.

The agent has at most four pages, ten tool actions, three model attempts, and a checked 180-second research budget. Model-facing excerpts are limited to 3000 characters per page. The normal agent path can finish in two model requests.

Fallback tries configured models in order on model-not-found, rate-limit, transient server errors, or timeout when time and request budget remain. It rebuilds agent context from retrieved snippets to avoid transferring model-specific thought signatures. Authentication failures stop the run. A configured fallback can also be used by the `workflow: efficient` CLI/API path. All attempts share the three-request limit. Without a fallback, the agent retains its bounded short HTTP 503 retry. Long provider retry delays stop the run. JSON exports include `models_used` and fallback warnings.

## Evidence quality and limitations

Source IDs establish quote provenance; relevance still needs review. The common-category guard rejects weak matches such as an annual company event used to support subscription pricing. The regression suite includes strong, weak, missing, unrelated-industry, and malformed evidence, plus a check that subscription evidence does not become an assertion of reconciliation pain.

These are synthetic regression tests, not a benchmark of live model accuracy. An evaluation across real companies, independently labeled evidence, and seller correction time remains to be done. Custom criteria rely more heavily on the model's judgment. Website statements are not independently verified.

The retriever reads HTML and checks public destinations, same-host boundaries, TLS, and robots permission. It does not execute JavaScript, access authenticated content, or research an entire website. Full HTML downloads are read without a byte cutoff; the model receives selected excerpts. JavaScript-heavy pages and sparse sites can produce unknown findings. Website text is treated as untrusted input by the agent prompt; source validation cannot eliminate prompt injection or incorrect inference.

## Tests

With the virtual environment active:

```sh
python -m unittest discover -s tests -v
node --test tests/test_frontend.cjs
```

Python tests mock provider/retrieval traffic and Salesforce requests. They exercise research, abstention, URL validation, snippet provenance, relevance guards, routing budgets, Vercel hosts, OAuth state, reviewed Task creation, and uncertain CRM outcomes. Frontend tests exercise CSV parsing, batch sequencing and pause behavior, saved state, and exports without consuming live quota.

`tests/fixtures/` contains synthetic company webpages and request data. Its `.example` URLs are fixture keys for tests. Use real company URLs in the live application.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Process health |
| `POST /api/research` | Research `{url, product, criteria}`; agent workflow by default |
| `GET /api/salesforce/status` | Whether OAuth is configured and this browser is connected |
| `GET /api/salesforce/connect` | Start Salesforce authorization |
| `GET /api/salesforce/callback` | Validate OAuth state and exchange the authorization code |
| `POST /api/salesforce/disconnect` | Clear this browser's Salesforce session |
| `POST /api/salesforce/save` | Create a reviewed account task for the connected user |

Research input errors return 400, non-JSON returns 415, oversized requests return 413, and usage rejections return 429. Provider failures return `service_error` in the research result. CRM writes require same-origin requests, an authorized session, an Account ID, a brief, and `reviewed: true`.

## Project layout

| Path | Purpose |
|---|---|
| `app.py` | Research agent, model routing, validation, report exports, and CLI |
| `server.py` | Flask application factory, routes, host/origin checks, and usage controls |
| `salesforce.py` | Salesforce OAuth and reviewed Task integration |
| `index.py` | Vercel WSGI entrypoint |
| `pyproject.toml`, `vercel.json` | Vercel entrypoint and function configuration |
| `static/` | Research UI, profiles, browser history, CSV batches, and CRM review |
| `tests/` | Python and frontend regression tests and synthetic fixtures |
| `tools/diagnose_gemini.py` | Manual provider diagnostic that can consume quota |
| `.env.example` | Configuration template |

`.env`, `.venv/`, and `.vercel/` are ignored by Git. The Vercel function bundle excludes local environment files, tests, tools, and virtual environments.

## Roadmap

- Validate research quality and preparation time with sellers across varied accounts.
- Add durable, authenticated workspace storage and shared usage enforcement.
- Persist batch queues so work can resume after closing the browser.
- Add account lookup and org-specific field mapping for Salesforce.
- Improve source discovery for JavaScript-heavy sites and conflicting statements.
