# Rate My Systems

Anonymous, credibility-weighted ratings of the **systems** people work inside — training, communication, equipment, cleanliness, safety, scheduling, consistency, recognition, accountability, workload. Rate the system, not the people.

Built to *improve* the systems it measures — not to farm attention. No ads, no trackers, no paid influence on scores, no individual ever exposed, no leaderboards. The math is public; the questions are not.

## Run it locally
```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8080
# open http://localhost:8080
```
Dev uses SQLite and an in-memory pepper; sign-in links print to the console. No secrets needed to try it.

```bash
python -m pytest tests/ -q      # 33 tests: scoring math, auth, privacy gates, security fixes
```

## Deploy it
See **DEPLOY.md** — App Runner + RDS Postgres, ~20 minutes, mostly clicking. The app refuses to boot in prod if any secret is missing, so you can't accidentally ship it insecure.

## Edit it (no code)
- `config/instrument.yaml` — the questions, categories, pillars
- `config/scoring.yaml` — weights, recency, privacy thresholds
- `config/copy.yaml` — every user-facing sentence
- `public/css/style.css` — the look

Push → it redeploys, validates, and publishes the new config. Invalid config is rejected and the old version keeps serving. Full map in **ARCHITECTURE.md** §13.

## The documents
- **ARCHITECTURE.md** — the system: data model, scoring pipeline, security, API, build order
- **FOUNDATIONS.md** — the design reviewed against systems/measurement/communication/org theory
- **DESIGN.md** — the product thinking (two-sided value, credibility model)
- **SECURITY.md** — security posture, threat model, accepted risks
- **DEPLOY.md** — the runbook

## How it's laid out
```
app/         FastAPI modular monolith
  main.py        app factory, static server, fail-closed startup
  config_loader  YAML → validated, versioned runtime config
  models.py      schema (facts immutable, derived rebuildable)
  scoring.py     pure scoring function (weights·decay·shrinkage·k-anon)
  publication.py weekly job: facts → score snapshots
  intake.py      session issue + submit + instant comparison
  auth.py        magic-link auth, identity separation
  public.py      public read API (no leaderboards, by construction)
  admin.py       moderation, config publish, job trigger
  security.py    tokens, headers, rate limits, prod fail-closed
config/      the dials (edit these)
public/      the site (vanilla JS, no build step)
tests/       pytest
```

---

*Composite intelligence: human direction (the Solar Guild) × architecture and build (Claude, Anthropic), 2026. The signature is the charter — see `/colophon`. If the no-ads / no-paid-influence / no-exposure commitments ever leave, the signature leaves with them.*
