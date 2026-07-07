# Rate My Systems — The Giants' Review

*v1.0 · July 2026 · The design (DESIGN.md, ARCHITECTURE.md) put in front of the major thinkers of every relevant field. Each lens gets a verdict and either a concrete amendment or an explicit "no change, here's why" — because a review that only adds features is itself a failure mode.*

**Method notes.** Two rules govern this review. First, anti-dogma cuts both ways: every framework is a lens, not a law, and several beloved ideas get rejected below with reasons. Second, the over-optimization guard is Herbert Simon's: organizations that thrive *satisfice* — they set thresholds and preserve slack — while optimizers overfit their proxies and shatter. So this review has an amendment budget: adopt at most six changes, defer the rest, reject the fashionable.

---

## 1. Systems theory & cybernetics

**Deming (variation, SPC — and the deepest cut in this review).** Deming anchored the product ("rate the system, not the people"), but applied honestly he attacks our own display layer. He spent his life fighting rankings — grading people, ranking plants, merit badges — because ranking misattributes variance: most of the spread between units is the *common* system they share, not local virtue. A league table of companies repeats that sin one level up. A warehouse scoring 2.8 on scheduling in a sector that averages 2.7 isn't a bad actor; it's an ordinary point inside common-cause variation, and shaming it teaches the market nothing except fear. The instrument of honest comparison is the **control chart, not the leaderboard**: show each company against its sector's expected range, flag only true signals (outliers beyond control limits, sustained trends against own baseline), and say "within normal variation for this industry" out loud when it's true.
→ **AMENDMENT A1 — No leaderboards, ever.** Public displays are deviation-from-expected: *your workplace vs. sector expectation vs. its own history*. "Top 50 / Bottom 50" lists are banned from the product. This is the boldest anti-status-quo position available to us — every rating site on earth ranks, because ranking farms attention. We measure signal instead. (It also quietly serves the charter: leaderboards are the engagement optimization we forswore.)

**Beer (POSIWID, algedonic channels).** "The purpose of a system is what it does." If RMS in practice produces shame-clicks, that is its purpose, charter notwithstanding — so audit the *behavior* of the product, not its mission statement (see A6/D4). Beer would also recognize RMS as an algedonic channel: a pain signal that bypasses the middle-management filters that normally absorb it. His warning: a pain signal that reaches the wrong node just causes noise.
→ Fold into design, no new mechanism: employer alerts route to the *claimed site operator* (the node with requisite authority), not a corporate comms inbox, and the POSIWID self-check lands in D4.

**Ashby (requisite variety).** The controller must match the variety of the controlled. Ten public categories is deliberate variety reduction for legibility; the item bank underneath, comment themes, and rotation restore variety where action happens (employer side).
→ **No change.** The two-layer design already satisfies Ashby. Adding public sub-scores would trade legibility for false precision.

**Meadows (leverage points, goal displacement).** New information flows — who gets to see what — are among the highest leverage points, and RMS is precisely that. Her caution: systems fail by "seeking the wrong goal," and an index that becomes the goal displaces the purpose. The north-star metric (verified improvements, not scores or traffic) is the structural defense; A2 below closes the remaining gap.

**Von Foerster (second-order cybernetics).** The observer is inside the system: measuring workplaces changes them, and the measurer itself must be observable and correctable. Who rates Rate My Systems?
→ **DEFERRED D4 — Annual self-audit + transparency report** after year one: RMS rates its own systems on its own instrument, publishes the result, plus an integrity log (astroturf attempts caught, disputes and outcomes, methodology changes). Deferred only because there must be operating history to report on.

## 2. Measurement theory & the economics of metrics

**Goodhart / Campbell.** "When a measure becomes a target, it ceases to be a good measure" — and Campbell's corollary: the more a social indicator drives decisions, the more it corrupts the process it measures. The moment employers care, gaming begins. Existing defenses (hidden rotating items, weighting, anomaly detection, church/state) are necessary, not sufficient. The robust defense is **triangulation**: perception scores, a small set of behavioral-proxy items (e.g., "I've looked for another job this month"), and measured improvement deltas. Coherent gaming of all three at once approaches the cost of just fixing the system — which is the ideal property: *make gaming more expensive than improving.*
→ Adopt inside the instrument (one behavioral-proxy item per pillar in the bank; no new mechanism). Keep stakes on *deltas*, not levels, which further devalues level-gaming.

**Messick / psychometric validity.** A score used publicly carries a validity burden: internal structure (do 10 categories really factor into 4 pillars?), reliability (alpha, test-retest), and eventually criterion validity (do low safety scores precede incidents? does low workload score predict turnover?). No review site on earth publishes a validity study; an instrument that does becomes *the* citable one — this is how "publicly recognizable as good" is actually earned in the measurement world.
→ **DEFERRED D3 — Validity program**: log everything needed from day one (the item-level schema already does), publish reliability at first adequate volume, pre-register the criterion studies. Deferred for data, designed for now.

**Regression to the mean (the fake-badge bug).** A company measured at its worst will "improve" by pure chance; shrinkage dampens but does not eliminate this. Improvement records as currently specified (before/after within a window) would systematically hand out unearned badges — and sophisticated employers could farm them by acting only after anomalously bad quarters.
→ **AMENDMENT A2 — Sector-adjusted deltas.** An improvement record publishes only if the company's category delta exceeds its sector's delta over the same window (difference-in-differences, kept honest and simple) with the confidence floor. This is a scoring-pipeline change (ARCHITECTURE §5/§8) and it protects the most important number we publish.

## 3. Communication theory

**Habermas (ideal speech, communicative action).** Legitimate discourse requires speech free of coercion and strategic distortion — the anonymity architecture is, in effect, an engineered approximation of the ideal speech situation for people who cannot safely speak at work. But Habermas would press: broadcast is not discourse. Ratings flow one way; responses flow one way back. Genuine communicative action is iterative.
→ **DEFERRED D1 — The dialogue mechanic.** A claimed employer may attach one clarifying question per category per period (from a vetted template bank, so questions can't fish for identities), appended to that company's future rating sessions and answered only in aggregate. Anonymized, slow, structured dialogue between a workforce and its management — no platform has built this. Deferred because v1 must prove the basic loop first; designed now so the session model reserves room for it.

**Framing (Entman) + Safety-II (Hollnagel) + Appreciative Inquiry (Cooperrider).** Three fields, one convergent finding: systems studied only through their failures produce cynicism and learn nothing from what works. Safety science's Safety-II: understand why things go *right*. The current display (and the "How broken is your workplace" headline) is pure deficit frame.
→ **AMENDMENT A3 — Strength-paired display.** Every public scope shows its strongest system beside its weakest, always, and the post-rating screen does the same. Not toxic positivity — the honest shape of the data, which contains both. (Recommend softening the headline to match: "How broken — and how solid — is your workplace?" Owner's call; it's a copy.yaml edit.)

**Shannon.** Weighting is signal-to-noise engineering; batching is smoothing; k-anonymity is deliberate bandwidth limitation for privacy.
→ **No change.** The pipeline is already an SNR design; formalizing further would be decoration.

## 4. Psychology

**Hirschman (Exit, Voice, Loyalty).** RMS is a voice channel positioned before exit. His core insight — voice atrophies without response — is already the product's spine (the improvement loop). **No change**; noted because it is the theoretical confirmation that the loop, not the ratings, is the product.

**Procedural justice (Thibaut & Walker; Leventhal).** Perceived fairness requires consistency, transparency, voice, and *correctability* — for both sides. Raters have all four. Employers currently have no recourse against suspected brigading except silence, and entities that feel unjustly judged delegitimize the judge (loudly, in public, with lawyers).
→ **AMENDMENT A5 — Due process for the rated.** An employer can flag a scoring window for integrity review; the review runs against the anomaly log; the outcome is published either way ("reviewed — no action" / "anomalous cluster removed"). Correctability without purchasable outcomes; every case lands in the transparency log (D4). This is what lets RMS look a skeptical public in the eye.

**Edmondson (psychological safety).** The uncomfortable mirror: dependence on anonymous external voice can excuse organizations from building internal safety — RMS could become the outsourcing of listening. Position RMS explicitly as *calibration and backstop*, with the employer toolkit pointing inward ("if your people can only say this here, that is itself a finding — your communication score is telling you why").
→ Positioning note folded into employer-facing copy; no mechanism. Watch for it in D4.

**Self-determination theory (Deci & Ryan) + overjustification.** The rater's motivations map cleanly: autonomy (voluntary, pseudonymous), competence (calibration, literacy micro-lessons, earned rank), relatedness ("it's not just you"). The classic failure would be gamifying the intrinsic away with streaks and confetti — already barred by charter §2.4.
→ **No change; explicit rejection recorded below (R2).**

**Kahneman & response-style research.** Peak-end and recency distort recall; acquiescence and extreme-responding distort scales. Frequency-anchored behavioral items (already chosen) are the standard mitigation; calibration scoring (already designed) handles response styles — with the standing rule that calibration measures *discrimination and consistency*, never agreement with the mean.
→ **No change.**

## 5. Organizational theory

**Weick (sensemaking).** Organizations act on stories, not numbers; a score without narrative produces either denial or panic. Theme extraction must preserve *thick description* — anonymize identity, never meaning. Concrete themes ("night shift can't reach maintenance") beat abstractions ("communication: 2.6") for provoking action.
→ Constraint recorded for the moderation/themes module; no new mechanism.

**Meyer & Rowan (decoupling); DiMaggio & Powell (isomorphism).** Once RMS matters, expect ceremonial compliance: declared actions decoupled from real change, adopted because peers adopted. The delta requirement (A2) is the anti-decoupling device. Its edge case: actions whose windows close without measurable change must be visible, or declaration becomes free PR — but punitively framed, and no one will dare declare.
→ **AMENDMENT A6 — Neutral outcome states.** Every declared action resolves publicly to exactly one of: *improved (sector-adjusted)* · *no measurable change yet* · *window extended (re-measuring)*. Stated flatly, ZERO-BS style, without celebration or shame. Honesty that keeps trying safe.

**Ostrom (governing the commons).** The ratings corpus is a commons; her design principles demand that those affected by the rules participate in changing them, with monitoring and graduated sanctions. A measurement platform whose methodology is amended by decree will eventually be captured or distrusted — openness of *process* is as load-bearing as openness of math.
→ **DEFERRED D2 — Methodology RFC.** Scoring/instrument changes post publicly for a comment window (raters and claimed employers both) before publish; the k-anonymity floor remains raise-only, per ARCHITECTURE §13. Deferred until there is a community to consult; the config-versioning machinery it needs already exists.

**Weick & Sutcliffe (high-reliability organizations).** Preoccupation with failure, reluctance to simplify: RMS should track its own near-misses (caught astroturf, false-positive suppressions, deanonymization attempts) the way an HRO tracks incidents.
→ Feeds D4's integrity log; no separate mechanism.

**James C. Scott (Seeing Like a State).** The standing danger of all legibility projects: the map flattens local knowledge (*metis*) and then the map is enforced. Two hard rules follow. The index must never override the narrative — scores start conversations, themes carry the truth. And credentials must only ever *add* weight; the uncredentialed voice is never gated, or the Guild becomes a legibility regime of its own.
→ Second rule promoted to standing principle alongside the charter (it was implicit in DESIGN §4; now it is written).

## 6. Farther fields

**Epidemiology / public health surveillance.** RMS is workplace epidemiology: sentinel surveillance (pulse cohorts), case definitions (category blurbs), and the iron rule — never publish counts without denominators and uncertainty (already ZERO-BS law). Its deepest gift is the evaluation discipline behind A2: uncontrolled before-after comparisons are how fields fool themselves.

**Dekker (just culture).** "Rate the system, not the people" *is* just culture, operationalized for the public. His refinement: forward-looking accountability — the question is never "who scored us low" but "what do we fix next." Employer-facing copy should be written in that grammar throughout. → Copy constraint; no mechanism.

**Auditing theory (independence).** The Guild both sells training and would certify workplaces — a textbook independence conflict (the auditor paid by the auditee's tutor). Managed, not fatal: separate the certification function's personnel and reporting line, disclose the structure on the seal itself, and let D4's transparency report cover certification statistics.
→ Constraint recorded for the Phase-3 seal; the seal does not launch without it.

**Ecology (the meaning of symbiosis).** Mutualism drifts to parasitism edge by edge, so audit each exchange: worker↔platform (voice for signal — mutual), employer↔platform (diagnosis for engagement — mutual), guild↔platform (demand for credibility — mutual, watch auditing independence), **employer↔worker inside pulse invites — the one edge with coercion risk** ("everyone scan this QR and be positive"). Batch codes verify cohorts rather than individuals (already designed); the missing piece is detection.
→ **AMENDMENT A4 — Publish the organic/pulse divergence.** Every scope displays its invited-vs-organic score gap. A persistent large gap is the fingerprint of coerced positivity, visible to everyone — which mostly prevents it from being attempted.

---

## 7. The ledger

**Adopted (the amendment budget: six):**

| # | Amendment | Source lens | Lands in |
|---|---|---|---|
| A1 | No leaderboards — control-chart displays (vs. sector expectation + own history) | Deming/SPC | ARCHITECTURE §5, §7; public pages |
| A2 | Sector-adjusted improvement deltas (DiD + confidence floor) | Epidemiology, RTM | ARCHITECTURE §5, §8 |
| A3 | Strength-paired display everywhere | Safety-II, framing, AI | Public pages, post-rating screen |
| A4 | Organic/pulse divergence published per scope | Ecology/coercion | ARCHITECTURE §5, §8 |
| A5 | Employer integrity-review with published outcomes | Procedural justice | ARCHITECTURE §7, §9; moderation |
| A6 | Neutral action-outcome states (improved / no change yet / re-measuring) | Meyer & Rowan | ARCHITECTURE §8 |

**Deferred (designed-for, not built-yet):** D1 dialogue mechanic (Habermas) · D2 methodology RFC (Ostrom) · D3 validity program (Messick — data collection starts day one) · D4 annual self-audit + transparency report (von Foerster, Beer, HRO).

**Rejected, with reasons (the anti-dogma section):**

- **R1 — The single sacred number (NPS worship).** One number invites one target invites Goodhart. The 0–100 index stays a *summary*, always displayed with pillars, n, and confidence — never alone.
- **R2 — Engagement gamification** (streaks, badges-for-activity, notification farming). Overjustification kills intrinsic motivation, and attention is explicitly not the goal. Rank stays tied to demonstrated judgment only.
- **R3 — Raw public comments** (the Glassdoor model). Maximum drama, maximum deanonymization surface, minimum diagnostic value. Themes preserve meaning with protection.
- **R4 — Rating individual managers.** The founding insight is Deming's: the system produces most of the outcomes. Naming people re-personalizes what we exist to de-personalize. Permanently out of scope.
- **R5 — Post-rating revision windows** (deliberative-polling flavor). Sounds reflective; in practice it's an anchoring-manipulation surface and an employer-pressure window ("go change your rating"). Immutable facts stay immutable.

**The over-optimization guard, stated once:** Simon's satisficing is the operating rule for this document's own output — six amendments adopted, not sixteen; thresholds, not maxima; slack preserved. The next review of this kind should happen only after real data exists to discipline it. Theory proposed; evidence disposes.
