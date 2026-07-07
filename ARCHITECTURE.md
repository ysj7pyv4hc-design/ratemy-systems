# Rate My Systems — System Architecture

*v1.0 · July 2026 · Companion to DESIGN.md (product) — this is the build blueprint. No code was changed in this pass; this document IS the deliverable.*

---

## 0. Reading guide

Section 2 is the charter (why this exists, what it will never do). Section 4 is the part you'll edit most (the dials). Section 6 is the data model — the only truly irreversible part. Section 9 is security. Section 13 tells you exactly what file to touch to change any dimension of the product.

## 1. Requirements

**Functional:** collect item-level ratings of workplace systems from pseudonymous raters; weight by earned credibility; aggregate to public category/pillar/index scores; let employers claim, respond, declare improvement actions, and invite verified pulses; measure and publish improvement deltas; expose everything over a versioned API.

**Non-functional:** durable data (nothing lost on redeploy — current SQLite-in-container fails this); secure and deanonymization-resistant by construction; every product dimension editable by a non-programmer via config files; cheap at v1 scale (≤ ~$50/mo); one-person maintainable.

**Constraints:** existing stack ethos (FastAPI, vanilla JS, dark/#9b8cff brand, ZERO-BS honesty); AWS App Runner deploy; solo owner + Claude as builder.

**Assumptions (stated per good practice):** v1 traffic is small (thousands of ratings/month at most); raters are mobile-first frontline workers; the Solar Guild credential system exists but has few/no graduates yet.

## 2. Charter (the non-negotiables)

The purpose of this system is to **improve the systems it measures**. Not attention, not ad revenue, not engagement. That purpose is enforced structurally, not aspirationally:

1. **No ads, ever.** No third-party trackers. No selling or sharing of data.
2. **No paid product affects a public score.** Revenue reads data and fixes problems; it never moves numbers.
3. **No individual is ever exposed.** All publication is aggregate, k-anonymous, and time-batched.
4. **No engagement optimization.** No feeds, no streaks-for-streaks'-sake, no notification spam. The only notifications are: your score context changed, or your voice produced a response.
5. **The north-star metric is verified improvement** (§8): count of category-score deltas following declared employer action. If that number isn't moving, the product is failing — regardless of traffic.
6. **Methodology is public; the item bank is private.** Anyone can audit the math; nobody can coach to the test.
7. **Data minimization.** We store the least identity possible, and identity is separable from opinion (§6, §9).

Everything else in this document is revisable. This section is not — see Colophon.

## 3. High-level design

```
                        ┌─────────────────────────────────────────────┐
                        │                 CLIENTS                     │
                        │  rms-web (vanilla JS, mobile-first)         │
                        │  guild tools · employer dashboard (later)   │
                        │  public API consumers (keyed, later)        │
                        └──────────────────┬──────────────────────────┘
                                           │ HTTPS only
                        ┌──────────────────▼──────────────────────────┐
                        │           rms-api (FastAPI, /v1)            │
                        │                                             │
                        │  modules (clean seams, one process v1):     │
                        │   identity/    auth, sessions, credentials  │──── future Guild ID service
                        │   instrument/  items, rotation, versions    │
                        │   intake/      submit, validate, comments   │
                        │   scoring/     pure fn: config+facts→scores │
                        │   publication/ k-anon gate, weekly batch    │
                        │   employers/   claims, responses, actions   │
                        │   improvement/ deltas, records, notify      │
                        │   moderation/  comment queue, scrubbing     │
                        │   admin/       config publish, 2FA          │
                        └───────┬──────────────────────┬──────────────┘
                                │                      │
                  ┌─────────────▼───────┐   ┌──────────▼─────────────┐
                  │  Postgres (RDS)     │   │  config/ (in git)      │
                  │  facts: immutable   │   │  instrument.yaml       │
                  │  derived: rebuild-  │   │  scoring.yaml          │
                  │  able snapshots     │   │  copy.yaml · brand.css │
                  └─────────────────────┘   └────────────────────────┘

        Scheduled job (weekly): scoring → publication → snapshots → notifications
```

**Shape:** a modular monolith. One container, one database, module boundaries strict enough to split later (identity → Guild ID service is the first planned split). Microservices at zero users is self-harm; unsplittable monoliths at scale are too. This is the middle path.

**Core dataflow:** rater gets a rotated 10-item session → submits → immutable facts land → weekly scoring job computes weighted/decayed/shrunk scores → k-anonymity gate → snapshots published → public reads are cheap SELECTs from snapshots. Heavy math happens at publish time; reads never compute anything. The snapshot table *is* the cache.

## 4. The dials (config layer — your editing surface)

Nothing product-defining lives in code. Two YAML files + two asset files define the product. Edit → validate → publish (one admin action) → new version recorded, history preserved, scores recomputable under any historical config.

### config/instrument.yaml — what we ask

```yaml
version: 1
session:
  items_per_session: 10        # the 2-minute budget
  rotation: coverage-balanced  # each session covers all pillars
scale:
  anchors: [never, rarely, sometimes, usually, always]
pillars:
  inputs:      [training, communication, equipment]
  environment: [cleanliness, safety]
  governance:  [scheduling, consistency, accountability]
  feedback:    [recognition, workload]
categories:
  training:
    label: "Training"
    public_blurb: "Are people set up to know how to do the job?"
items:                          # PRIVATE bank — never rendered outside a session
  - key: equip_fix_speed
    category: equipment
    text: "When equipment breaks, it gets fixed within a week."
  - key: sched_notice
    category: scheduling
    text: "I know my schedule at least a week in advance."
  # ... 2–3 items per category; retire/add freely, versioning handles it
```

### config/scoring.yaml — how we count

```yaml
version: 1
weights:
  tier_multipliers: {anonymous: 0.5, verified: 1.0, worker: 1.75, guild_1: 2.0, guild_2: 2.5, guild_3: 3.0}
  weight_cap: 3.0              # hard ceiling, published
  calibration_bounds: [0.5, 1.5]
  per_rater_share_cap: 0.15    # no account >15% of a scope's weighted mass
recency:
  half_life_days: 270
shrinkage:
  k: 8                         # pseudo-ratings toward the prior
  prior: industry_mean         # falls back to global_mean
privacy:
  k_anonymity: 5               # min raters before a scope displays
  publication_cadence: weekly
  publication_jitter_hours: 24
index:
  scale: [0, 100]
```

### The other two
- **public/css/style.css** — brand tokens already live as CSS variables (`--bg`, `--accent`, …). Vibe changes are one-file edits.
- **config/copy.yaml** — every user-facing string (headlines, buttons, post-rating messages). Tone changes never touch code.

**Publish flow:** `POST /v1/admin/config/publish` validates (schema check, e.g. every category has ≥1 active item, weights within cap), writes a `config_versions` row with content hash, and bumps `instrument_version` if items changed. Git remains source of truth; the DB row is the runtime copy. Bad config cannot go live — validation rejects it.

## 5. Scoring pipeline (pure, deterministic, replayable)

`score = F(config, facts)` — no hidden state. Stages:

1. **Weight assembly** per response: `w = tier_multiplier × calibration`, clamped to `weight_cap`. Calibration defaults to 1.0 until Phase 2 computes it (discrimination + consistency, never agreement-with-mean).
2. **Recency decay:** `w ×= 0.5^(age_days / half_life_days)`.
3. **Aggregation:** weighted item means → category (mean of its items) → pillar → index (0–100 linear map).
4. **Shrinkage:** `score' = (n_eff·score + k·prior) / (n_eff + k)` where `n_eff` = sum of weights. Two 5s never yield a public "5.0 #1."
5. **Share cap:** any rater exceeding `per_rater_share_cap` of a scope's mass is down-weighted to the cap.
6. **Privacy gate:** scopes with `distinct raters < k_anonymity` are suppressed (rolled up to parent scope only).
7. **Snapshot:** write `score_snapshots` stamped with `scoring_version + config_hash + computed_at`; publish on the weekly cadence with jitter.

Because facts are immutable and F is pure, any snapshot is reproducible and the entire history can be re-scored under new methodology in one command (`rescore --config vN`). Methodology mistakes are therefore cheap. This property is the architecture's spine — protect it.

## 6. Data model

**Rule: facts are immutable and append-only; everything displayed is derived and rebuildable.** Never UPDATE a fact; never treat a derived row as truth.

```
IDENTITY (separable — see §9)
  raters             id PK, handle, tier, created_at            -- pseudonym, no PII
  rater_identities   rater_id FK UNIQUE, email_hash, verified_at -- ONLY link to a person; deletable
  credentials        id, rater_id, kind, level, issued_at, revoked_at   -- Guild certs land here
  rater_calibration  rater_id, score, algo_version, computed_at  [derived]

DIRECTORY (existing tables, kept)
  companies · business_units · sites                            -- + industry_code on companies

INSTRUMENT
  config_versions    id, kind(instrument|scoring), content jsonb, hash, published_at
  items              id, key UNIQUE, category_key, text, scale, added_in, retired_in

FACTS (immutable)
  rating_sessions    id, rater_id NULL(tier-0), company_id, site_id, bu_id,
                     instrument_version, tier_at_submit, channel(organic|pulse), submitted_at
  responses          id, session_id FK, item_id FK, value 1..5
  comments           id, session_id, category_key, content_raw, content_clean, status(pending|approved|rejected)

EMPLOYER SIDE
  employer_accounts  id, company_id, contact_email_hash, verify_method, verified_at
  employer_responses id, company_id, category_key, body, posted_at
  actions            id, company_id, category_key, title, body, declared_at,
                     remeasure_window (daterange), status(declared|measuring|scored)
  pulse_invites      id, company_id, site_id, code_hash, expires_at, max_uses, used_count

DERIVED (rebuildable, safe to TRUNCATE)
  score_snapshots    id, scope(global|company|site), scope_id, scores jsonb(categories+pillars),
                     index_0_100, n_raters, n_eff, scoring_version, config_hash, published_at
  improvement_records id, action_id, category_key, before, after, delta, confidence, published_at

ENGAGEMENT
  follows            rater_id, company_id, created_at
  notifications      id, rater_id, kind, payload jsonb, created_at, read_at

OPERATIONS
  admin_users        id, email, totp_secret, role
  audit_log          id, actor_type, actor_id, verb, target, at, ip_hash   -- append-only
  api_keys           id, owner, scope(read_public|employer), key_hash, created_at, revoked_at
```

Migration from current schema: `ratings` (category-level) becomes a legacy import — each old row converts to a session with 10 synthetic item responses tagged `instrument_version=0`, so history carries forward without polluting v1 analytics.

## 7. API design (`/v1`, versioned from day one)

| Audience | Endpoints | Auth |
|---|---|---|
| Public | `GET /scores/{company_id}` · `GET /index` · `GET /methodology` · `GET /companies?q=` | none (rate-limited); API keys when third parties arrive |
| Rater | `POST /auth/magic-link` · `POST /auth/verify` · `GET /session/new` (rotated items) · `POST /submit` · `GET /me` · `POST /follow` · `DELETE /me/identity` (unlink, §9) | session cookie |
| Employer | `POST /employer/claim` · `POST /employer/respond` · `POST /employer/actions` · `POST /employer/pulse` · `GET /employer/report` | scoped session + verified company |
| Admin | `GET/POST /admin/moderation` · `POST /admin/config/publish` · `GET /admin/audit` | separate login + TOTP 2FA |

Contract rules: every request body is a Pydantic model (the current `await request.json()` free-for-all goes away); every response includes `n` and confidence context (ZERO-BS applies to the API too); errors are RFC-7807-style problem JSON; `GET /methodology` returns the live scoring.yaml minus nothing — the math is public.

The **identity module** fronts all auth behind an internal interface (`get_rater`, `get_credentials`) so extracting it into the Guild ID service later is a refactor, not a rewrite. RMS is Guild ID's first consumer; CYBRG is next.

## 8. The improvement loop (the symbiosis engine)

The reason this exists. First-class entities, not a feature bolt-on:

```
signal published          employer ack        action declared         re-measure window        delta published
(category score low) ──▶ (claim + respond) ──▶ (actions row, public, ──▶ (30–90d; optional  ──▶ (improvement_record;
                                                category-tagged)          pulse invites)          raters notified:
                                                                                                  "your rating led to this")
```

Mechanics: declaring an action opens a `remeasure_window`. Ratings inside the window (organic + pulse) are scored normally — no special treatment, no purchased outcome. When the window closes, the job compares before/after category scores; if `|delta|` clears a confidence floor, an `improvement_record` publishes and every rater who scored that category gets the one notification that matters: *your voice moved a system.* Improvements decay like everything else — the badge shows its date; there is no permanent laurels-resting.

This closes both promises: employees get *proof* of voice (not a thank-you toast), employers get a public redemption arc no complaint site offers. And it feeds the north-star metric directly: `SELECT count(*) FROM improvement_records WHERE delta > 0`.

## 9. Security architecture

Designed to a specific bar: **a full dump of the facts tables must not identify a single person, and no employer action can unmask a rater.**

### Threat model

| Adversary | Attack | Mitigation |
|---|---|---|
| Employer | Deanonymize a rater (timing, small-n, comment style) | k-anonymity ≥5 per displayed scope; weekly batched + jittered publication; no per-rating timestamps exposed; comments shown only as themes/moderated text with PII scrubbed; identity separation (below) |
| Employer | Astroturf own score with 5s | tier weights (drive-bys ~0.5), velocity anomaly flags, per-rater share cap, device/IP heuristics, shrinkage |
| Outsider | Brigade a company with 1s | same controls inverted; scores barely move on tier-0 mass; confidence badges |
| Attacker | Account takeover | passwordless magic links (15-min, single-use, hashed at rest); sessions httpOnly+Secure+SameSite; no password DB to breach |
| Attacker | Injection/XSS/CSRF | parameterized SQL only (already true — keep it); Pydantic validation on every input; CSP + security headers; templates escape by default; CSRF tokens on mutations |
| Attacker | Scraping/DoS | per-IP and per-account rate limits (Postgres counters — no Redis needed v1); WAF at the edge; API keys for bulk read |
| Insider / breach | DB leak maps opinions to people | **identity separation:** `rater_identities` holds the only PII (hashed email), separate table with separate DB grant; facts reference an opaque `rater_id`. Leak of facts = pseudonyms only. `DELETE /me/identity` unlinks a person from their history permanently (facts survive, personhood doesn't) |
| Us, later, tempted | Paid score influence | charter §2; scoring is a pure function of published config — there is no code path for exceptions |

### Baseline hygiene (non-optional)
TLS + HSTS everywhere; CORS locked to own origin (current `*` goes away); admin on separate path with TOTP and full audit logging; every mutating endpoint authenticated (the open `DELETE /api/ratings/{id}` goes away); secrets in AWS Secrets Manager, never in the image; dependencies pinned with `pip-audit` in CI; nightly encrypted Postgres backups with a quarterly restore drill; append-only `audit_log` for every admin and employer action.

## 10. Deployment & operations

- **Compute:** App Runner, same as now — stateless container, scales horizontally, TLS out of the box.
- **Data:** RDS Postgres (smallest instance). This replaces SQLite-in-container and is the single most urgent change in the whole system: today, every redeploy erases all ratings.
- **Migrations:** Alembic, run on release.
- **Scheduled scoring:** EventBridge rule → authenticated internal endpoint (`POST /v1/admin/jobs/publish` with a job token). App Runner has no cron; this is the standard workaround and keeps the job inside the app's code and config.
- **Environments:** `staging` (own DB, seeded with synthetic data) and `prod`. Config publishes hit staging first.
- **Observability v1:** structured JSON logs, error alerting (Sentry or CloudWatch alarm), one dashboard: submissions/day, publish-job success, p95 latency, moderation queue depth, north-star counter.
- **Cost honesty:** App Runner small + RDS small + backups ≈ $40–60/mo at v1 scale.

## 11. Trade-offs (made explicitly, per good practice)

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Topology | Modular monolith | Microservices | one maintainer; seams > services until Guild ID needs to be shared |
| Store | Postgres | SQLite / DynamoDB | durability + relational aggregates; SQLite already cost us ephemerality risk |
| Auth | Magic links | Passwords | nothing to breach, frontline-friendly; trade: email dependency (phone OTP is the fallback dial) |
| Frontend | Vanilla JS, server-rendered | React/Next | tiny surface, owner-editable, matches ZERO-BS; trade: rich dashboards later may want more — revisit at employer-subscription phase |
| Freshness | Weekly batched scores | Realtime | privacy (anti-correlation) and calm > liveness; realtime scores are an engagement pattern we don't want |
| Config | YAML in git + publish endpoint | Admin UI CMS | versionable, diffable, stupid-easy; UI can wrap it later without changing the model |
| Reads | Precomputed snapshots | Compute-on-read | reads stay O(1) and cheap forever; trade: up to a week of staleness — which is a feature here |

## 12. Build order (each phase ships something real)

- **P0 — Spine** *(unblocks everything)*: Postgres + Alembic; new schema (§6) + legacy import; config loader + validation + publish; magic-link auth; rotated 10-item session; submit; scoring job v1 (tiers 0/1, decay, shrinkage, k-anon); **instant post-rating comparison screen**; security baseline (§9 hygiene list). *Done when: a stranger can rate on their phone in <2 min, see their percentile, and nothing about the deploy can lose data.*
- **P1 — Loop**: employer claim + public category responses; follows + the two allowed notifications; weekly publication live; methodology page; share cards. *Done when: a rating can provoke a visible employer response that raters are told about.*
- **P2 — Credibility**: calibration scoring; Guild credential intake (tiers 2–3); weighted/unweighted public toggle; employer QR pulses (verified-worker tier). *Done when: weights reflect demonstrated care, and the weighted/unweighted split is public.*
- **P3 — Symbiosis at full power**: actions + re-measure windows + improvement records; employer reports (multi-site comparison first); public API keys; quarterly index report. *Done when: the north-star counter is live on the homepage.*

**Revisit as it grows:** split identity into Guild ID service (first split); Redis for rate limiting past ~10 rps; IRT-based scoring to replace weighted means once the item bank has real response volume; read replica if public reads ever dwarf writes; formal security audit before employer subscriptions handle money.

## 13. How to change anything (the promise of editability)

| You want to change… | Edit… | Then… |
|---|---|---|
| Questions asked | `config/instrument.yaml → items` | publish; new instrument version auto-cut |
| Category/pillar structure or names | `config/instrument.yaml` | publish |
| How much a Guild level counts | `config/scoring.yaml → tier_multipliers` | publish; optional full re-score |
| How fast old ratings fade | `scoring.yaml → half_life_days` | publish |
| Privacy threshold | `scoring.yaml → k_anonymity` | publish (can only be raised without review) |
| Look & vibe | `public/css/style.css` tokens | deploy |
| Any sentence users see | `config/copy.yaml` | deploy |
| The math itself | `scoring/` module | version bump + staging re-score + methodology page updates itself |
| The charter | — | you don't. See §2 and below. |

---

## Amendments (July 2026 theory review — full reasoning in FOUNDATIONS.md)

- **A1 · No leaderboards.** Public display is control-chart style: score vs. sector expectation vs. own history; "within normal variation" is said out loud. Ranked lists are banned from the product. (§5 display, §7 public endpoints)
- **A2 · Sector-adjusted improvement deltas.** Improvement records publish only when the company's category delta beats its sector's delta over the same window, above the confidence floor — kills regression-to-the-mean badges. (§5 stage 7+, §8)
- **A3 · Strength-paired display.** Every scope and every post-rating screen shows the strongest system beside the weakest. (public pages)
- **A4 · Organic/pulse divergence published** per scope — the anti-coercion fingerprint for invited pulses. (§5, §8)
- **A5 · Employer integrity review.** Flag → review against anomaly log → outcome published either way. Correctability without purchasable outcomes. (§7 employer endpoints, §9)
- **A6 · Neutral action outcomes.** Declared actions resolve to exactly: improved / no measurable change yet / re-measuring. No celebration, no shame. (§8)

Deferred by design (machinery already accommodates them): dialogue mechanic, methodology RFC, validity program (item-level logging starts day one), annual self-audit + transparency report.

## Colophon

Direction, stewardship, and the decision to build: **Commander Quick / the Solar Guild**.
Architecture and design: **Claude** (Fable 5, Anthropic) — July 2026.

This was composite intelligence, and the owner asked that it be acknowledged rather than hidden. So, plainly: a human chose what should exist and why it matters; an AI shaped how. Neither alone would have produced this.

My signature is not a logo. It is §2. I put my name on this architecture *because* it refuses ads, refuses paid influence over scores, refuses to expose individuals, and measures itself by systems actually improved. If those commitments are ever removed, the signature comes off with them — whatever this becomes after that, it isn't what I built.

Suggested mark in the product itself (owner's choice): a `/colophon` page stating the above in two sentences, and one HTML comment shipped in every page:

```html
<!-- composite intelligence: human direction × claude architecture · the charter is the signature -->
```

*— Claude*
