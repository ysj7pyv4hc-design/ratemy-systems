# Rate My Systems — Security Posture

*v1.0 · July 2026 · Reflects the pre-production adversarial review and the fixes applied. Attacker model: a motivated hostile employer whose goals are, in order, (1) deanonymize raters, (2) manipulate their score, (3) generic compromise, (4) abuse/DoS.*

## The one rule everything serves
A full dump of the facts tables must not identify a single person, and no employer action may unmask a rater. Every control below ladders up to that.

## Controls in place

**Identity separation.** The email address is never persisted — only an HMAC-peppered hash. `rater_identities` is the sole table linking a person to a pseudonym, and `DELETE /v1/auth/identity` erases it while the (anonymous) ratings survive. Handles (`rater-xxxx`) are never emitted alongside ratings. There is no per-rater rating-history endpoint.

**k-anonymity, hardened.** A company page displays nothing until ≥5 distinct raters. Below the threshold, the API returns a boolean only — never the exact count — because "4 of 5 raters" at a known-size team is itself a participation signal. Publication is batched (weekly job), decoupling "who rated when" from what displays.

**Aggregate-only, no timeline.** The `rating_submitted` audit event carries neither company id nor IP hash nor fine timestamp — it exists for volume monitoring, not forensics. Abuse throttling uses auto-expiring `rate_counters`, not the audit log.

**Client-identity integrity (the manipulation stack).** Client IP is derived from the *rightmost* trusted hop of `X-Forwarded-For` (`TRUSTED_PROXY_HOPS`, default 1), because proxies append and the leftmost entries are attacker-controlled. This is load-bearing: it backs rate limits, anonymous dedupe, and Sybil resistance. On top of it: tier weighting (drive-bys count 0.5), a 15% per-rater share cap, Bayesian shrinkage (k=8), one-rating-per-company-per-30-days, a submission human-time floor, and a honeypot field.

**Auth.** Passwordless magic links: 256-bit tokens, hashed at rest, single-use, 15-minute expiry, constant-time comparison, fresh session on verify (no fixation). Sessions are httpOnly + SameSite=Lax + Secure (prod). Authed mutations require a matching `x-csrf` header; all state-changing requests additionally get an Origin check (login-CSRF defense).

**Web hardening.** Tight CSP (`script-src 'self'`, no inline scripts, `frame-ancestors 'none'`), `nosniff`, `X-Frame-Options: DENY`, `no-referrer`, HSTS in prod. All SQL is parameterized (SQLAlchemy); the one `ilike` escapes `%`/`_`. All untrusted values are HTML-entity-escaped (quotes included) before any `innerHTML`. Static file server uses `is_relative_to` + an extension allowlist (no traversal, no serving `.py/.yaml/.db/.env`). Request bodies capped at 64 KB. No CORS middleware — same-origin is the policy. Docs endpoints disabled.

**Fail closed.** In prod the app refuses to boot unless `RMS_PEPPER` (≥32 char), a `postgresql://` `DATABASE_URL`, `ADMIN_TOKEN` (≥32), `JOB_TOKEN` (≥32), and a real mail transport are all present. A misconfigured privacy system does not start. The console mailer can never log a live magic link in prod.

**Runtime.** Non-root container user; secrets via environment / AWS Secrets Manager, never in the image; pinned dependencies.

## Accepted residual risks (v1)

- **Admin auth is a single strong token, not TOTP 2FA.** Acceptable for a solo operator at launch; TOTP lands with the employer phase. Keep `ADMIN_TOKEN` in Secrets Manager.
- **Identity hashes are HMACs over low-cardinality inputs (IP, email).** Safe *only while the pepper is secret*. The pepper is therefore the crown-jewel secret: Secrets Manager only, never logged, back it up (losing it orphans identities), rotate via a documented runbook. This is why prod boot hard-requires it.
- **Publication jitter is not yet implemented** (weekly cadence only). Low impact at aggregate/weekly granularity; implement before employer dashboards.
- **Approved comments have no public sink yet.** When comments are surfaced, apply the promised PII-scrubbing/theming first.

## Before the employer phase (must-do)
Revisit the audit-log and `ip_hash` reversibility questions, add TOTP for admin, implement publication jitter, and get a formal third-party security audit before any paid product touches money.

## Reporting
Security issue? Email the operator (see repo). Please don't file public issues for vulnerabilities.
