# Rate My Systems — Product Design

*Design session, July 2026. Companion to server.py / public/. ZERO-BS voice throughout.*

---

## 1. What this is

Employees don't rate their company or their boss. They rate the **systems** they work inside: training, communication, equipment, cleanliness, safety, scheduling, consistency, recognition, accountability, workload.

The intellectual anchor is Deming: ~94% of workplace failure is systemic, not individual. That single idea separates RMS from Glassdoor (brand grievance) and rate-my-manager clones (personal blame). RMS is a **diagnostic instrument, not a gripe site**. Everything downstream — tone, moderation policy, employer pitch, Guild funnel — flows from "rate the system, not the people."

Positioning line: Glassdoor tells you if people are angry. RMS tells you **why**, and what to fix first.

## 2. The two flywheels

**Rating loop:** ratings → benchmark index → employers care → employers claim + respond → employees see response ("voice heard," proven) → more ratings.

**Credibility loop:** weighted ratings → higher-trust index than any competitor → certification is worth earning → Guild training demand → more certified raters → even better data.

The credibility loop is the moat. Anyone can clone a 10-question survey. Nobody else has a certification body feeding calibrated raters into the instrument. Glassdoor's fatal weakness is that all opinions weigh the same; RMS's answer is *weighted, credentialed, structured* signal.

The loops intersect at the business model (§5): RMS diagnoses, the Solar Guild treats. Low scores aren't a PR problem for RMS — they're Guild demand. This aligns incentives in a way no standalone review site can match.

## 3. Employee value

The stated draws — voice heard, novelty of comparison — are real but decay after one use. Design for episodic return (people rate a workplace monthly/quarterly at most, so retention = return triggers, not daily habit):

1. **Instant comparison at submission.** The moment you submit, you see your workplace vs. industry percentile per pillar. The comparison IS the reward. Today the flow just says thanks — this is the single highest-leverage UX change, and it works even at low n (compare against all warehouse ratings nationally, not just your employer).
2. **"It's not just you."** Show consensus after rating: "78% of raters at similar sites also flag scheduling." Costs nothing, delivers the core emotional payoff — validation that the problem is structural, not personal.
3. **Follow the needle.** Follow your company; get notified when its score moves or the employer responds. This is the return trigger.
4. **Employer response = proof of voice.** When a claimed employer posts "replaced both fryers, retrained shift leads," every rater of that category gets notified. The systems frame keeps responses concrete instead of PR-speak.
5. **Systems literacy on-ramp.** After rating: "You scored consistency low — in systems terms that's process variance. People who can diagnose this get paid to fix it →" The rating flow is Guild lead-gen. Every rater is a prospective trainee.
6. **Earned rank.** Profile shows calibration score, guild level, "your ratings moved N index updates." Ranks with teeth, not gamification candy — nobody gets handed a level (§4).

## 4. Credibility & weighting

### Tiers

| Tier | Who | Weight | Notes |
|---|---|---|---|
| 0 | Anonymous drive-by | ~0.5 | Keep — frictionless capture matters for cold start; anomaly-filtered |
| 1 | Verified account (email/phone) | 1.0 | Baseline "anyone" |
| 2 | Verified worker at rated company | 1.5–2.0 | Payslip hash, work-email, or employer QR pulse (§5). Phase 2 — hard for frontline, but this is what kills the "fake reviews" attack |
| 3+ | Solar Guild certified, by level | up to ~2.5–3.0× cap | Earned via training + assessment. Levels proportional to commitment; never granted |

### Two multiplied factors, not one

`weight = tier_multiplier × calibration_score`, capped.

Credentials say you *trained*; calibration says you're *currently careful*. Calibration is earned in-app: does the rater discriminate between categories (not straight-lining 1s or 5s), stay consistent over time, write comments others at the same site validate? This keeps certified raters honest and gives uncredentialed-but-thoughtful raters a path up — important so baseline users don't feel like second-class citizens. Score on discrimination patterns and consistency, **not** agreement with the mean — honest outliers must not be punished.

### Guardrails

- Tight, **published** multiplier band (max ~3×). At 10× you've built an oligarchy and "voice heard" dies for baseline users; at 1.1× certification is pointless.
- Per-rater cap: no single account > X% of a site's score in a window.
- One rating per company per period per account.
- Always display the unweighted number alongside the weighted one. Framing: "calibrated instruments," never "better people."

### Anti-gaming

Employer astroturf (burst of 5s): velocity anomaly detection, device/IP heuristics, tier-weight means drive-bys can't move a score much. Brigading (mass 1s from non-workers): same tools inverted, plus scores don't move materially on tier-0 volume. Both: confidence badges at low n, Bayesian shrinkage (§7).

## 5. Employer value ladder

1. **Unclaimed** — public page appears once n ≥ threshold. They see what everyone sees. The mirror exists whether they engage or not; that's the pressure.
2. **Claimed (free)** — verify business/domain → respond publicly per category, receive alerts. Free because responses power the employee loop.
3. **Subscribed (paid)** —
   - Benchmarks: percentile vs. industry / size / region (the dataset moat).
   - Trends over time; **site-vs-site comparison for multi-site operators** — lead with this, not single-site vanity. A regional operator seeing "Store 12 is a training outlier under the same playbook" is the systems thesis made undeniable, and it's where ops leaders actually feel pain.
   - LLM-extracted comment *themes* (never raw individual comments — anonymity preserved by construction).
   - Weighted vs. unweighted split: "certified raters score your safety 0.8 lower than baseline" is a premium expert read no one else can sell.
   - **Pulse invitations:** employer buys QR-code invites for their own workforce → verified-worker (tier 2) ratings that feed the same public score. This converts RMS from adversarial (Glassdoor) to invited (Culture Amp) without forking the data. Employers accept it because the alternative is being rated anyway, blind.
4. **Remediation funnel** — score low on training? The Guild sells the fix: training, certification, consulting, CYBRG tooling. Then **re-score publicly**: improvement badges ("Most Improved Systems, Q3"). Glassdoor offers only damage control; RMS offers a visible redemption arc. This is the family synergy and the real business.
5. **Guild Certified Workplace** — audited seal when scores + practices clear the bar. Recurring revenue, recruiting asset, makes the index aspirational rather than purely punitive.

### Church/state rule

No paid product ever affects the public score. Written policy, published. One suspected exception and the index dies the Yelp-suspicion death. Revenue comes from *reading* the data and *fixing* the problems — never from moving the number.

## 6. The instrument (questions → groups)

Your instinct — ask ~10 concrete questions, publish only grouped constructs — is psychometrically correct (it's how Gallup Q12 / SUS work). Formalize it as three layers:

```
item bank (private, rotating)  →  10 categories (public)  →  4 pillars  →  RMS Index (0–100)
```

- **Items are concrete and behavioral:** "When equipment breaks, is it usually fixed within a week?" beats "Rate equipment 1–5." Easier to answer honestly, harder to game, less mood-driven. Use frequency anchors (never/rarely/sometimes/usually/always) for behavioral items.
- **Hard 2-minute budget:** ~10 items per session, mobile. Every item fights for its slot.
- **Rotation / planned missingness:** no rater answers every item; across the population you cover a 20–30 item bank while each person answers 10. Categories stay comparable.
- **Versioned instrument** (v1, v2…) with score equating, so the index survives question changes. This is why hiding items matters: you can rotate and A/B them without breaking the public construct, and employers can't coach to the test.
- **Opposite instinct, same system: hide the items, publish the math.** Methodology page shows weighting, decay, shrinkage, sample sizes in plain language. Radical methodological transparency is the anti-Glassdoor differentiator; item secrecy protects the instrument. Both, deliberately.
- Headline number: keep 1–5 per category for honesty, add a 0–100 composite **RMS Index** for legibility and press ("credit score for workplaces").

Current schema change: today ratings store category scores directly. Move to item-level responses (`items`, `instrument_versions`, `responses`) with category scores computed. Do this before scale — retrofitting item-level data is impossible.

## 7. Trust architecture (the anonymity ↔ credibility tension)

Credibility weighting needs persistent identity; honest rating needs protection from retaliation. Resolution: **pseudonymous accounts carrying verified credentials, with aggregate-only publication.**

- Credentials raise your *weight*, never your *visibility*. Employers never see who rated — only weighted aggregates and moderated themes.
- **k-anonymity:** no company/site breakdown displayed below n≥5 in the window.
- **Batched publication:** scores update weekly, not on submit, so an employer can't correlate "who rated Tuesday" with a schedule.
- **Recency decay** (half-life ~9 months): workplaces change; eternal 2019 reviews are Glassdoor's known failure. Decay also gives employers a reason to keep improving — the score is always *current*.
- **Bayesian shrinkage** toward the industry prior at low n, IMDB-style, so two 5-star ratings don't produce a "5.0, #1 workplace."
- Comments: PII/name-scrubbed, systems-focused moderation ("rate the system, not the people" as policy, not just brand), surfaced to employers only as themes.

Weights, decay, shrinkage, k-anonymity are each a few lines of code, but they define the API contract — design them together, now.

## 8. API-first: the Guild ID layer

"RMS as API" is the right founding instinct, with one reframe: the durable platform primitive isn't the ratings API — it's the **credibility layer**.

- **Guild ID** (conceptually separate service): one account across the family — auth, certification level, calibration score, reputation. RMS is its *first consumer*; CYBRG and future properties are next. Portable earned rank is what makes this a family of companies rather than a shared logo.
- **RMS API**: instrument delivery, submission, scores, aggregates, benchmarks — consumed by rms-web (just the first client), Guild curriculum tools, employer dashboards.
- **Public read API** (keyed): scores + index for journalists, researchers, job boards. An embeddable "RMS Score" on job postings — Rotten Tomatoes for workplaces — is the long-game distribution play.
- v1 pragmatism: keep it one FastAPI app with cleanly separated modules/tables (`auth/credentials` vs. `instrument/scores`). Don't microservice at zero users; do keep the seam clean enough to split.

## 9. Cold start

Chicken-egg: no scores → no employees; no volume → no employers. Wedges, in order:

1. **The Guild is the seed.** Trainees rate their own workplace as part of the curriculum — "your first systems audit is the place you work." Seed data + skills practice + calibration bootstrapping, all in one.
2. **One vertical first.** A ranked index of 50 named companies in one industry/region is newsworthy; 5 ratings across 40 industries is nothing. (If Solar Guild is literally solar/trades, the wedge picks itself: the ops index for solar installers/contractors.)
3. **Give-to-get lite:** headline scores free; unlock full pillar breakdowns by contributing a rating. Glassdoor proved the mechanic; keep it lighter.
4. **Quarterly "State of Workplace Systems" report** from aggregates — the PR engine, even at modest n.

## 10. Risks & riskiest assumptions

1. **Riskiest: unprompted employees won't rate.** Cheapest test: current site + ~50 workers in one vertical; measure completion and share rate of the post-rating comparison card. Run this before building accounts, weighting, or dashboards.
2. **Legal/retaliation:** aggregate-only display, k-anonymity, batching, comment scrubbing are the defense. Terms already exist; keep individual statements unpublishable at low n.
3. **Weighting optics** ("experts count more" reads elitist): tight published band, unweighted number always visible, "calibrated instrument" framing.
4. **Guild dependency:** tiers 2–3 are empty until the Guild has graduates. Launch with tiers 0/1 + calibration; add credential tiers when real. Don't block RMS on Guild maturity.
5. **Selection bias** (angry people rate more): weighting, employer pulse invites, monthly-checkup framing, and honest display of response mix.
6. **Known infra debt** (from prior review): SQLite on App Runner ephemeral storage loses all data on redeploy; unauthenticated DELETE /api/ratings; comments stuck 'pending' with no moderation path. All Phase 0.

## 11. Roadmap (mapped to current code)

**Phase 0 — Foundation (fix before anything):** Postgres (or at minimum durable volume); auth on mutating endpoints; moderation path for comments; item-level schema (§6); pseudonymous accounts; weights v1 (tier 0/1) + recency decay + shrinkage; **instant post-rating comparison screen**.

**Phase 1 — The loop:** claimed employer pages + public category responses; follow/notify; k-anonymity + weekly batching; methodology page; shareable comparison cards.

**Phase 2 — Credibility:** calibration scoring; Guild ID integration + certified tiers; weighted/unweighted views; employer QR pulse invites (tier-2 verification).

**Phase 3 — Business:** employer subscriptions (benchmarks, trends, multi-site, themes); remediation funnel to Guild + re-score badges; Certified Workplace program; public API keys; quarterly report.

## 12. Open decisions (owner's call)

1. Is Solar Guild literally the solar/trades industry, or industry-agnostic? Determines the wedge vertical and item wording.
2. Guild rank ladder: how many levels, named what, earned by what? Needed before tier weights ship. (Guild-flavored: Initiate → Operator → Journeyman → Master?)
3. Church/state on paid score influence — recommend absolute, in writing, on the methodology page.
4. Identity floor: allow anonymous tier-0 forever, or require an account after the first rating?
5. CYBRG vibe reference: the current dark/#9b8cff/terse aesthetic reads right — confirm what specifically should carry over (type, rank iconography, tone?).
