# AccountBrief

An AI account research agent for GTM teams. Enter a company website, your offering and ideal customer criteria. AccountBrief researches relevant pages and produces an evidence-backed fit assessment, a discovery question and a reviewable outreach draft.

## Hosted use

Open the prototype link provided with the submission. Visitors need only a browser: no login, installation or personal Gemini API key is required.

The hosted application uses the owner's Gemini key, stored privately in Render's environment settings. Visitor research consumes the owner's shared quota. The key is never sent to the browser. Availability depends on the hosting service and Gemini's capacity and project quotas.

## Requirements and dependencies

For a local copy:

- Python 3.10 or newer. Render is configured for Python 3.13.
- Internet access and a browser.
- A Gemini API key with access to the configured model.

The research core uses Python's standard library. Flask serves the HTTP routes and Waitress runs the server. Exact dependency versions are pinned in `requirements.txt`. No frontend build, database or paid service is required; live research requires available Gemini API quota.

## Local setup

Run these commands from the repository root—the directory containing `app.py`:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.

If `.env` does not already exist, create it from the template:

```sh
cp .env.example .env
```

Do not overwrite an existing `.env` containing your key. Set its values:

```dotenv
GEMINI_API_KEY=YOUR_GEMINI_KEY
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_RPM=5
MAX_DAILY_RESEARCH=20
APP_ENV=development
```

Set `GEMINI_RPM` to your model/project's actual requests-per-minute allowance; `5` is a configuration default, not a universal free-tier quota. The app loads `.env` automatically from the project directory. Existing process environment variables take precedence. Restart after changing settings.

`.env` and `.venv/` are ignored by Git. Never commit your key or place it in frontend code.

Start the application:

```sh
python app.py
```

Open **http://127.0.0.1:8765**. Keep the terminal running; stop with Ctrl+C. To choose another local port:

```sh
python app.py --port 8766
```

## Core workflow

1. Enter a real public company website.
2. Describe your offering in 20–1200 characters.
3. Enter 1–5 unique ideal customer criteria, one per line.
4. Select **Build account brief**.
5. Inspect the fit explanations, exact source quotes, unknowns and discovery question.
6. Review the outreach draft and download the Markdown brief or JSON evidence record.

Evidence coverage measures how many criteria have supporting evidence. It is not buying intent, a lead score or a forecast. **Unknown** means the inspected sources did not establish a criterion, not that the company is unsuitable.

## Example input and expected output

### Representative case

Use the following in the browser, or save it as `request.json`:

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

For the CLI:

```sh
python app.py --input request.json --output brief.json
```

Expected behavior: the agent selects relevant product, pricing/licensing and customer sources, validates its evidence and returns a brief. In observed live runs, Atlassian's project-management tool description, monthly subscription terms and customer reach across 200+ countries supported all three criteria.

An illustrative, shortened output based on those runs is:

```json
{
  "account": "www.atlassian.com",
  "status": "Review draft",
  "coverage": {
    "supported": 3,
    "total": 3,
    "meaning": "Evidence coverage, not win probability or a lead score."
  },
  "fit": [
    {
      "criterion": "B2B software company",
      "status": "Evidence found - review relevance",
      "evidence_ids": ["E1"],
      "reason": "The cited page describes a project-management tool for teams."
    },
    {
      "criterion": "Subscription pricing",
      "status": "Evidence found - review relevance",
      "evidence_ids": ["E2"],
      "reason": "The cited licensing page explicitly describes monthly subscriptions."
    },
    {
      "criterion": "International customers",
      "status": "Evidence found - review relevance",
      "evidence_ids": ["E4"],
      "reason": "The customers page states that companies in 200+ countries and territories use Atlassian."
    }
  ],
  "hypothesis": "Does your team reconcile subscription payments across currencies? If so, is matching those payments to invoices a challenge?",
  "service_error": null
}
```

The full JSON also contains source quotations and URLs, retrieval timestamps, unknowns, the outreach draft, executed-tool trace, attempted model-request count and the rendered Markdown report. The example above omits those fields for readability. Source content, selected evidence IDs, wording, page count and coverage can vary between runs; **3/3 is an observed result, not a guaranteed output**.

A useful result may instead mark criteria unknown. If no criterion has relevant evidence, the expected result is **Needs manual research**, with the outreach draft withheld.

### Invalid-input case

Use the same offering and criteria, but change the URL to:

```text
http://127.0.0.1/private
```

Expected behavior:

- The browser shows an input error and generates no brief.
- The API returns HTTP 400 with:

```json
{
  "error": "Use a public http(s) website, without credentials or custom ports."
}
```

- The CLI prints that validation error and exits with code `2`.
- No Gemini request is made.

### Provider failure

Unavailable Gemini service, quota exhaustion or a timeout does not become a negative account assessment. The response reports **Research unavailable**, includes `service_error`, and withholds the draft. The interface displays that error so the user can address it or retry later.

## Sample data and automated tests

Test data is included under `tests/fixtures/`:

| File / case | Purpose and expected behavior |
|---|---|
| `request.json` | A fictional account research input used by tests |
| `websites.json`: Meridian Cloud | Fictional software, recurring-billing and international-customer statements; supports the normal workflow |
| `websites.json`: Quiet Company | A sparse coming-soon page; no supported criteria and no outreach draft |
| `websites.json`: Juniper Studio | A pottery workshop without evidence for the software ICP; no relevant fit |

The `.example` URLs in these fixtures are fictional keys, not public websites. **Do not submit them to the live app.** Tests load these files and mock retrieval/provider responses; the application never loads them and has no demo or synthetic fallback mode.

Run all tests with the virtual environment active:

```sh
python -m unittest discover -s tests -v
```

The latest verified suite has **84 passing tests**. Expected summary:

```text
Ran 84 tests

OK
```

The suite does not consume Gemini quota. It covers normal, sparse and invalid inputs; adaptive tool calls; evidence-ID validation; source targeting; outreach safeguards; HTML extraction; request pacing/budgets; TLS and provider errors; bounded HTTP 503 retry; public HTTP routes; HTTPS-origin handling; concurrency; and daily allowances.

Live Atlassian research and local Waitress startup have also been exercised. Automated checks and successful live runs do not establish systematic model accuracy, buying intent or future service availability. Verify the deployed URL separately after each release.

## How the agent works

Python fetches the initial webpage. Gemini receives selected source excerpts and criterion-specific source suggestions, then chooses additional pages through `research_pages`. Python retrieves that batch. Gemini reviews the results and uses `complete_research` to select stable source snippet IDs, explain fit, identify unknowns and propose a discovery question.

Python resolves those IDs to exact stored quotations and validates references before generating the report. The model selects sources and assesses evidence; conventional code controls retrieval, validation, budgets and exports. An invalid completion can be corrected within the remaining request allowance.

The default limits are:

| Resource | Limit |
|---|---|
| Gemini requests | Three total attempts, including any retry |
| Pages | Four total: the initial page plus up to three agent-selected follow-ups |
| Model-facing excerpts | Up to 3000 text characters per page |
| Tool actions | Ten |
| Research time | 180 seconds, checked between operations |
| Individual model request | Up to 90 seconds, reduced by pacing and remaining time |

The representative path can complete in two model requests. Only the first model decision can select additional pages; later decisions complete or correct the brief. One short HTTP 503 retry is allowed within the same three-attempt limit. Long retry delays, repeated 503s, timeouts and quota errors stop the run rather than loop.

Full HTML and locally extracted article text have no byte/character cutoff. Only selected excerpts go to Gemini. The parser does not execute JavaScript. Network/DNS operations can add overhead beyond the checked run budget.

## Evidence and outreach safeguards

- Navigation/menu text, headers/footers, scripts, styles and hidden elements are excluded where identifiable.
- Product descriptions, billing terms and customer-reach statements are prioritized over generic marketing copy.
- The agent selects exact snippets by ID instead of retyping source quotations.
- Each fit finding includes source references and an explanation. Common ICP categories also have conservative lexical checks.
- Unsupported criteria remain unknown. Company statements are not independently verified, and lexical checks are not semantic proof.
- Outreach uses evidence referenced by supported findings, avoids discontinued-product/refund/legal notices and uses a neutral opening when necessary.
- Unverified workflows are phrased as conditional discovery questions. Human review remains necessary.

The app does not send emails or change a CRM.

## Implemented, mocked and deferred

| Status | Scope |
|---|---|
| **Implemented** | Live Gemini tool-calling agent, public-page retrieval, targeted source selection, exact evidence references, fit explanations, unknowns, conditional discovery questions, reviewed outreach drafts, Markdown/JSON exports, CLI/API, production HTTP server and usage controls |
| **Mocked for tests only** | Fictional company webpages and scripted Gemini responses; no production fallback to these mocks |
| **Deferred** | External search-engine discovery, JavaScript rendering, contact enrichment, CRM integrations, email sending, persistent account history, multi-instance quota coordination and systematic accuracy/product validation |

The website uses the adaptive agent by default. An explicit `workflow: efficient` CLI/API alternative retains a software-directed, single-model-request pipeline; it is not the website's default.

## API

| Endpoint | Behavior |
|---|---|
| `GET /api/health` | Public process health: `{"ok":true}`; no key or configuration values |
| `POST /api/research` | Accepts the JSON input shown above; returns the brief or a structured error |

`mode` can be omitted or set to `gemini`; other modes are rejected. `workflow` defaults to `agent`. Invalid input returns HTTP 400. Non-JSON requests return 415, oversized input returns 413, and concurrency/daily-limit rejections return 429. Provider failures return a structured research result with `status: Research unavailable` and `service_error`.

## Deploy on Render

Use `accountbrief` as the Git repository root, with `render.yaml` alongside `app.py`. For a Blueprint deployment, connect the repository, select `render.yaml`, confirm Free compute and provide `GEMINI_API_KEY` when prompted.

For manual Web Service setup:

| Setting | Value |
|---|---|
| Root Directory | Leave empty |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python app.py` |
| Health Check Path | `/api/health` |

Set these environment variables in Render:

```dotenv
APP_ENV=production
HOST=0.0.0.0
GEMINI_API_KEY=YOUR_PRIVATE_KEY
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_RPM=5
MAX_DAILY_RESEARCH=20
```

Adjust RPM and the daily allowance to your actual quota. Render supplies `PORT` and service-hostname metadata; `.python-version` selects Python 3.13. Do not upload `.env`. No visitor username/password is required. For a custom domain, set `APP_ORIGIN` to its HTTPS origin.

After deployment, check that the public URL loads, `/api/health` returns only `{"ok":true}`, a real research run completes, invalid inputs fail clearly and report downloads work. Render Free can sleep when idle, so the first load may require a startup wait. Hosting startup delays and Gemini errors are separate issues.

Only one research run executes at a time. The default production allowance is 20 research attempts per UTC day. The allowance and rate limiter are in-memory and reset on process restart/redeploy; they are not persistent, account-wide spending caps. Invalid inputs do not consume the research allowance; valid attempts count even if retrieval or the provider fails. Other tools using the same Google project consume its quota independently.

## Project layout

| Path | Purpose |
|---|---|
| `app.py` | Research core, agent, validation, exports and CLI/startup |
| `server.py` | Flask routes, HTTPS/origin handling, usage controls and Waitress |
| `static/` | Browser HTML, CSS and JavaScript |
| `tests/` | Automated tests |
| `tests/fixtures/` | Test-only synthetic inputs and webpages |
| `tools/diagnose_gemini.py` | Optional manual diagnostic; uses the configured key and may consume quota |
| `.env.example` | Shareable configuration template |
| `requirements.txt` | Pinned dependencies |
| `render.yaml` | Render deployment configuration |
| `.python-version` | Hosted Python version selection |

Public retrieval is restricted to the target hostname, public network destinations, verified TLS and robots permission. Cross-host redirects, login/paywall content and JavaScript-only content are not supported. A complete HTML download does not mean the entire website has been researched.

## Time spent

**3 hours total.**

## AI use, checks and prior work

Codex assisted problem framing, implementation, prompt iteration, test design, debugging and documentation. Its output was checked through executable tests, local server checks and live account-research runs. Validation caught and corrected issues including altered source quotations, navigation text being used as evidence, inappropriate outreach assumptions and provider connection failures.

The application was built in an empty workspace; no prior candidate application, proprietary customer dataset or existing candidate codebase was reused. Standard libraries and third-party Flask/Waitress dependencies were used. Official Gemini and Render documentation informed the integrations. Synthetic company content is confined to automated test fixtures. Source provenance checks do not eliminate incorrect inference, so fit judgments and drafts require review.

## What I would investigate next

1. Compare manual research, a checklist and AccountBrief with a small group of SDRs, account executives or founders. Measure preparation plus correction time and whether the resulting briefs are useful.
2. Evaluate evidence relevance and appropriate abstention across varied sites, sparse pages, conflicting statements and adversarial page content. Track incorrect fit associations separately from fabricated quotations.
3. Improve source discovery and extraction for sites requiring redirects or JavaScript, without overstating what was inspected.
4. If demand is demonstrated, add saved customer profiles, account lists and reviewed CRM export. Introduce persistent/shared quota controls before expanding public usage.

These are next investigations, not completed studies or claims of revenue impact.

## References

- [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling)
- [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Gemini troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting)
- [Render web services](https://render.com/docs/web-services)
- [Render free hosting](https://render.com/docs/free)
