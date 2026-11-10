# ProspectLens

An agentic AI account research workspace for GTM and revenue teams. Turn company websites into source-backed account briefs, evaluate ideal customer profile (ICP) fit, and prepare outreach with LLM-as-a-judge evaluation and human-in-the-loop review before saving research to Salesforce CRM.

[Try ProspectLens](https://prospect-lens-jet.vercel.app/)

## What it does

- Uses Gemini tool calling to choose relevant company pages and assess account fit.
- Links findings to exact source excerpts and keeps unsupported criteria unknown.
- Uses LLM-as-a-judge for agent evaluation, checking evidence relevance and unsupported outreach claims.
- Requires human-in-the-loop review before saving research to Salesforce.
- Researches CSV lists of up to 20 accounts, with pause and resume.
- Saves customer profiles and the latest 30 briefs in your browser.
- Searches Salesforce accounts and saves reviewed briefs as completed tasks.
- Routes eligible Gemini failures to a fallback model within a shared request budget.

## Try it

Enter these values in the app:

| Field | Example |
|---|---|
| Company website | `https://www.atlassian.com/` |
| Your offering | We help B2B software finance teams reconcile subscription payments, match invoices, and investigate unmatched transactions. |
| Ideal customer criteria | B2B software company · Subscription pricing · International customers |

Enter each criterion on a separate line. Build the brief, inspect its sources, and review the discovery question and outreach draft. For batch research, upload a CSV with a `url` column and up to 20 company websites.

## Quick start

Requires Python 3.10+ and a Gemini API key.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

If you already have `.env`, keep your existing file. Add your key and model settings:

```dotenv
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_FALLBACK_MODELS=gemini-3.1-flash-lite
GEMINI_RPM=5
```

Choose models available to your Google project and set RPM to your actual allowance. Then run:

```sh
python app.py
```

Open [localhost:8765](http://127.0.0.1:8765). Restart after changing environment variables. Keep `.env` private.

## Deploy on Vercel

Import the GitHub repository, select **Flask**, and use the directory containing `app.py` as the root. Keep the default build settings. Add your Gemini environment variables plus `APP_ENV=production` and `MAX_DAILY_RESEARCH=20`, then deploy. The included configuration sets the entrypoint and a 300-second function duration.

## Salesforce setup

Create a Salesforce External Client App with the `api` scope, authorization-code flow, client-secret requirement, and PKCE. Set its callback to `https://YOUR-DOMAIN/api/salesforce/callback`.

Add these environment variables locally or in Vercel, then restart or redeploy:

```dotenv
SALESFORCE_CLIENT_ID=your_consumer_key
SALESFORCE_CLIENT_SECRET=your_consumer_secret
SALESFORCE_LOGIN_URL=https://login.salesforce.com
SESSION_SECRET=your_random_secret_of_at_least_32_characters
APP_ORIGIN=https://YOUR-DOMAIN
```

Generate a session secret with `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`. Keep it stable across deployments. For local use, register the localhost callback and omit `APP_ORIGIN`.

Click **Connect Salesforce**, open a brief, search and select an account, confirm your review, and save. The selected account receives a completed task containing the evidence, discovery question, and outreach draft.

The CRM workflow is demonstrated in the owner's demo org. Other Salesforce orgs require app distribution setup and administrator approval. Research and exports work without Salesforce.

## Limits

- Public HTML research is limited to four pages on the same website to keep requests manageable within Gemini’s free-tier quotas. JavaScript rendering and logged-in content are outside the current scope.
- Salesforce integration is demonstrated in the owner’s demo org. Cross-org distribution is outside the current release and requires additional Salesforce setup and administrator approval. Research and exports work without Salesforce.
- Exact quotes establish source provenance; fit inferences and outreach still need human review.
- Gemini quota and availability affect research. Research fallback shares the same three-attempt budget. Automatic quality review normally adds one request; research and evaluation share a five-request total cap; neither increases quota.
- Profiles and briefs stay in the current browser. Batch queues require the tab to remain open.
- Hosted research uses the owner's Gemini quota. Usage counters are per process and can reset or run separately across Vercel instances.
- Salesforce sessions expire. If a save has an uncertain outcome, check Salesforce before retrying.

## LLM-as-a-judge Evaluation

Every completed research run includes an LLM-as-a-judge step before the brief is returned. This applies to single accounts, CSV batches, and CLI research. The judge evaluates whether cited excerpts support each fit criterion, checks for unsupported outreach claims, and reviews the discovery question.

Research normally takes two model requests, leaving up to three evaluation attempts within a shared **five-request total cap**. A third research request is reserved for recovery when needed, leaving two evaluation attempts. The judge rotates configured models on eligible failures. Actual attempts depend on remaining quota. Invalid judge responses trigger a correction attempt with the specific validation feedback, within the same request cap. 

If research fails, evaluation is skipped. If the judge fails, times out, or returns invalid feedback, the completed brief remains available with **AI quality review unavailable**. Findings remain unchanged; users review any quality flags before using outreach or saving to Salesforce.

The judge assesses the evidence retrieved by research. Feedback needs human review. Tests use mocked judge responses and do not establish live judge accuracy.

To re-evaluate a downloaded JSON brief separately, the same evaluator is also available from the terminal:

```sh
python tools/evaluate_brief.py --input brief.json --output evaluation.json
```

Use `--model YOUR_GEMINI_MODEL` to select another model for that manual run. No additional API key or setup is needed for automatic evaluation.

## Development

Built with Python, Flask, Gemini API, Salesforce REST API, and vanilla JavaScript. Runtime dependencies are pinned in `requirements.txt` and `pyproject.toml`; keep them in sync.

```sh
python -m unittest discover -s tests -v
node --test tests/test_frontend.cjs
```

Tests use synthetic website fixtures and mocked provider, CRM, and LLM judge responses.
