# Deploy Rate My Systems to ratemy.systems

*You run these steps in your AWS account — I can't reach it from here. ~20–30 min. Two supported paths; pick A.*

## What you're deploying
One container: FastAPI serves the API (`/v1/*`) and the static site (`/`) on a single origin. Data lives in Postgres (RDS). A weekly job recomputes public scores.

---

## Path A — App Runner from GitHub (recommended, no Docker)

### 1. Push this folder to a GitHub repo
```bash
cd ratemy-aws
git add -A && git commit -m "Rate My Systems v1"
git remote add origin git@github.com:YOUR_USER/ratemy-systems.git
git push -u origin main
```

### 2. Create the database (RDS Postgres)
AWS Console → RDS → Create database → **PostgreSQL**, smallest size (db.t4g.micro), storage 20 GB.
- Name the DB `ratemy`, note the master username/password.
- Make it publicly accessible **No**; put it in the same VPC you'll give App Runner.
- After it's up, copy the endpoint → your `DATABASE_URL` is:
  `postgresql://USER:PASSWORD@ENDPOINT:5432/ratemy`

### 3. Generate the three secrets
```bash
for k in RMS_PEPPER ADMIN_TOKEN JOB_TOKEN; do echo "$k=$(openssl rand -hex 32)"; done
```
Save these somewhere safe now. **`RMS_PEPPER` can never change without orphaning identities** — treat it like a master key.

### 4. Create the App Runner service
AWS Console → App Runner → Create service → Source: **GitHub** → pick your repo/branch.
- Build: it auto-detects `apprunner.yaml`. (Runtime Python 3.11, it's in the file.)
- Service settings → **Environment variables** (this is where the whole security posture switches on):

| Key | Value |
|---|---|
| `RMS_ENV` | `prod` |
| `BASE_URL` | `https://ratemy.systems` |
| `DATABASE_URL` | from step 2 |
| `RMS_PEPPER` | from step 3 |
| `ADMIN_TOKEN` | from step 3 |
| `JOB_TOKEN` | from step 3 |
| `TRUSTED_PROXY_HOPS` | `1` |
| `MAIL_PROVIDER` | `disabled` (anonymous launch) — or `smtp` + the SMTP_* vars below |

  Store the four secrets as **Secrets Manager** references, not plaintext, if you can.
- Networking → attach a VPC connector that can reach the RDS instance.
- Health check path: `/health`.
- Create. First deploy takes a few minutes.

> If any required var is missing, the app **refuses to boot** (by design) and the deploy fails loudly with the exact list. That's the safety net working — add the missing var and redeploy.

### 5. Point the domain
App Runner → your service → **Custom domains** → add `ratemy.systems` (and `www`).
It gives you CNAME/validation records → add them at your DNS registrar. TLS is issued automatically. Propagation is usually minutes.

### 6. Schedule the weekly publication
The score board updates when a job runs. Create it once:
- AWS Console → EventBridge → Scheduler → Create schedule → rate `cron(0 8 ? * MON *)` (Mondays 08:00 UTC).
- Target: **API destination** → `POST https://ratemy.systems/v1/admin/jobs/publish`, header `X-Job-Token: <JOB_TOKEN>`.
- (No body needed.)

### 7. Verify live
```bash
curl https://ratemy.systems/health                 # {"ok":true,...}
curl https://ratemy.systems/v1/methodology          # the public math + charter
```
Open `https://ratemy.systems` → rate a test workplace → you should see the instant comparison screen.

---

## Path B — Docker (any container host)
```bash
docker build -t ratemy .
docker run -p 8080:8080 \
  -e RMS_ENV=prod -e BASE_URL=https://ratemy.systems \
  -e DATABASE_URL=postgresql://USER:PASS@HOST:5432/ratemy \
  -e RMS_PEPPER=... -e ADMIN_TOKEN=... -e JOB_TOKEN=... \
  -e TRUSTED_PROXY_HOPS=1 -e MAIL_PROVIDER=disabled \
  ratemy
```
Put it behind a TLS-terminating proxy that appends `X-Forwarded-For` (set `TRUSTED_PROXY_HOPS` to the number of proxies). Schedule the weekly `POST /v1/admin/jobs/publish` however your host does cron.

---

## Turning on sign-in later (optional)
The site runs fully anonymous with `MAIL_PROVIDER=disabled`. To enable magic-link accounts (needed for credibility tiers), set up **AWS SES**, verify `ratemy.systems`, create SMTP credentials, then set:
`MAIL_PROVIDER=smtp`, `SMTP_HOST=email-smtp.us-east-1.amazonaws.com`, `SMTP_PORT=587`, `SMTP_USER=...`, `SMTP_PASS=...`, `MAIL_FROM=signin@ratemy.systems`. Redeploy.

## Editing the product after launch (your dials)
1. Edit `config/instrument.yaml` (questions), `config/scoring.yaml` (weights/privacy), `config/copy.yaml` (words), or `public/css/style.css` (look).
2. `git commit && git push` → App Runner redeploys → new config validated and published automatically. Invalid config is rejected and the previous version keeps serving.
3. Full map of what-to-edit is in `ARCHITECTURE.md` §13.

## Admin actions (from your laptop)
```bash
# review pending comments
curl -H "X-Admin-Token: $ADMIN_TOKEN" https://ratemy.systems/v1/admin/moderation
# approve one
curl -X POST -H "X-Admin-Token: $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"comment_id":"...","action":"approve"}' https://ratemy.systems/v1/admin/moderation
# recompute scores now (instead of waiting for Monday)
curl -X POST -H "X-Admin-Token: $ADMIN_TOKEN" https://ratemy.systems/v1/admin/jobs/publish
```

## First-week checklist
- [ ] `/health` green, `/v1/methodology` shows your charter
- [ ] a test rating produces the comparison screen
- [ ] company page says "not enough ratings" below 5 raters (privacy gate working)
- [ ] weekly EventBridge job fires once manually without error
- [ ] `RMS_PEPPER` backed up somewhere you won't lose it
- [ ] RDS automated backups on (7–35 day retention)
