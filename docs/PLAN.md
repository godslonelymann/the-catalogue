# The Catalogue: implementation and setup plan

This plan has 3 parts:

- **Part A**: what we build, and how it works.
- **Part B**: the code changes. This is my work.
- **Part C**: how to set up each service. This is your work, click by click.

At the end there is **Part D**: the order of all the steps, from start to finish.

---

# Part A: what we build

## A1. The goal

A website that shows every product, size, price and stock status from 10 Indian streetwear brands.

- The data updates **every 3 hours**.
- When a sold-out size comes back, the bot sends a **Telegram message** to the people who track it.
- The total cost is **about $1 per month**.

## A2. The architecture

```
 ┌──────── GitHub Actions (free) ───────────┐       ┌──────── Vercel (free) ─────────┐
 │ every 3 h : products                     │       │ Next.js website                │
 │ daily     : collections                  │       │ + Telegram bot (webhook)       │
 │ daily     : database backup              │       │ region: Singapore (sin1)       │
 └──────┬────────────────┬──────────────────┘       └────────────────┬───────────────┘
        │ upload (OIDC)  │ SSL, user "pipeline"          SSL, user "website" (pooled)
        ▼                ▼                                            ▼
  ┌───────────┐    ┌──────────────────── Neon (free) ─────────────────────────┐
  │  AWS S3   │    │ Postgres, 18 tables, no JSONB                             │
  │ raw/      │    └───────────────────────────────────────────────────────────┘
  │ backups/  │
  └───────────┘    Telegram ◀── "back in stock" messages (sent by GitHub)
```

| Service | Job | Cost |
|---|---|---|
| GitHub Actions | Collects the data, writes to the database, sends alerts, makes backups | free |
| AWS S3 | Keeps every raw response (gzip) and the backups | under $1 |
| Neon | Runs Postgres | free |
| Vercel | Website and bot, with a free HTTPS link | free |
| Telegram | Sends the alerts | free |

## A3. How the data flows

### Every 3 hours: products (GitHub)

```
 For each of the 10 stores:
 1. Download products.json, page by page   ──▶ keep the pages in memory
 2. Save each raw page to S3               (first, as a safety net)
 3. Check the count: far fewer products than the last good run? ──▶ stop this store
 4. Parse the pages from memory ──▶ Postgres (one transaction per store)
 5. Price changed? ──▶ add a history row.  Sold out → in stock? ──▶ remember the size
 6. Wait 1 second. If the store says "wait" (retry-after), wait that long.
 After all stores: send the Telegram alerts for the sizes that came back.
```

### Daily: collections (GitHub)

The same steps for collections. Collections tell us which product is in which category.

### Daily: backup (GitHub)

```
 pg_dump of the database ──▶ S3 backups/   (S3 deletes it after 14 days)
```

### A visitor opens the site (Vercel)

```
 visitor ──▶ Vercel ──▶ Neon (the result is cached for a few minutes) ──▶ page
```

### A user asks for an alert

```
 1. Product page: a size is sold out ──▶ the user clicks "Notify me on Telegram"
 2. Vercel checks the limit (10 per hour per visitor) ──▶ creates a "pending" tracker
 3. The browser opens t.me/<bot>?start=<token> ──▶ the user taps Start
 4. Telegram sends the message to Vercel (/api/telegram) ──▶ tracker = "active"
 5. Later, GitHub sees the size is back ──▶ sends the message ──▶ tracker = "notified"
 6. /stop in the bot ──▶ all trackers of that user stop
```

## A4. The database users

| User | Used by | What it can do |
|---|---|---|
| owner (Neon makes it) | Only you, from your Mac | Everything. We use it only for migrations. It **never** goes into GitHub or Vercel. |
| `pipeline` | GitHub Actions | Read and write the product tables and runs. Read and update trackers. Write notifications. |
| `website` | Vercel | Read the product tables. Create and update trackers and subscribers. |

## A5. Security

| Risk | Protection |
|---|---|
| AWS keys leak | No AWS keys exist. GitHub signs in with OIDC. The role can only write to `raw/` and `backups/`, and read `raw/`. It cannot delete. |
| Someone reads database traffic | Neon allows SSL only. Our clients use `sslmode=verify-full`, so they also check the server certificate. |
| A database password leaks | Each user can do only its own job. The owner password stays on your Mac. |
| Secrets in the code | Passwords live only in GitHub secrets, Vercel environment variables, and your local `.env` (git ignores it). |
| Fake Telegram messages | Telegram sends a secret header. Vercel rejects every request without the correct header. |
| Spam on "Notify me" | Only sold-out sizes. A limit of 10 per hour for each visitor (we keep a hash of the IP address, not the address). |
| A store sends broken data | The raw file goes to S3 first. We refuse the update when far fewer products arrive. |
| Data loss | A daily backup to S3, kept 14 days. All raw data stays in S3. |
| Runs fail and nobody sees it | GitHub sends you an email when a scheduled run fails. |
| Two runs at the same time | Each workflow has a lock (`concurrency`). A new run waits for the old run. |
| A surprise AWS bill | An AWS budget alert at $2 per month. |

---

# Part B: the code changes (my work)

I do each task on your Mac, against the local Postgres 18 and a local folder in place of S3. Telegram stays off during the tests, so the code writes the messages to the log.

## B1. Pipeline: parse from memory

**Files:** `pipeline/fetch.py`, `pipeline/parse.py`, `pipeline/jobs.py`

- Now: `fetch_products` saves the pages to S3. Then `parse_products` downloads them again from S3.
- Change: `fetch_products` returns the pages that it has in memory. `parse_products` takes them as an argument.
- `reparse` still reads from S3. That is its job.
- The order stays the same: save to S3 first, then parse.

**Test:** run `python -m pipeline products --store fugazee` locally, and compare the row counts with the old code.

## B2. Pipeline: the count check

**Status:** this check was already in `pipeline/parse.py` (`MIN_SHARE_OF_ACTIVE`). No change was needed.

- Before the parse, compare the new product count with the last successful run of that store.
- If the new count is **less than half**, and the last count was more than 20, mark the run `failed` with a clear message. Do not parse.
- The raw files are already in S3, so we can look at them later.

**Test:** a test with a fake small page. The run must fail and the database must not change.

## B3. Pipeline: obey `retry-after`

**Files:** `pipeline/shopify.py`

- Now: on HTTP 429 the code waits 10, 20, then 30 seconds.
- Change: curl also reports the `retry-after` header. If the store sends it, wait that many seconds (at most 120). If not, keep the current pauses.

**Test:** a unit test for the code that reads the header.

## B4. Pipeline: Neon connection

**Files:** `pipeline/config.py`, `.env.example`

- `CATALOGUE_DB` takes the full Neon address: `postgresql://pipeline:...@<host>/catalogue?sslmode=verify-full&sslrootcert=system`.
- `sslrootcert=system` tells the client to check Neon's certificate with the normal trusted list.
- The OpenSSL inside `psycopg[binary]` cannot find that list by itself. `connect()` sets `SSL_CERT_FILE` to the system file before it connects (found during the first Neon test).
- `.env.example` shows the new format. It has no real values.

## B5. Pipeline: no double alerts

**Files:** `pipeline/alerts.py`

- Now: the code sends the message first, then marks the tracker `notified`. If the run stops between these 2 steps, the next run sends the same message again.
- Change: mark the tracker `notified` **first** (only if it is still `active`), and commit. Then send. If the send fails, set the tracker back to `active`.

**Test:** run the alert step 2 times for the same restock. Only 1 message goes out.

## B6. Database: migration `002_users_and_limits.sql`

**Files:** `db/migrations/002_users_and_limits.sql`, a new command in `pipeline/__main__.py`

- Create the roles `pipeline` and `website` **without** a password and without login.
- Give each role only its grants (see A4).
- Set default grants, so a table in a later migration gets the same grants.
- Add the column `trackers.requester_hash` and an index on (`requester_hash`, `created_at`). The website uses them for the limit.
- A new command, `python -m pipeline set-db-passwords`, makes 2 long random passwords. It turns on login for the 2 roles and writes the 2 Neon addresses to your local `.env`. The passwords never go into git. (Neon accepts only plain-text passwords in `ALTER ROLE`. The password goes over the verified SSL connection, and Postgres stores only its hash.)
- The `pipeline` user can also read `schema_migrations`, because the backup (`pg_dump`) runs as `pipeline` and must read every table.

**Test:** run the migration locally. Then connect as `website` and try to change a product. It must fail.

## B7. Backup in GitHub

**Files:** `pipeline/backup.py`, `.github/workflows/backup.yml`

- `pipeline/backup.py` stays the same. It runs `pg_dump` and uploads the file to `backups/`.
- The workflow installs the `pg_dump` version that matches Neon's Postgres version.

**Test:** run a backup against the local database into a local folder, then restore it into a new empty database.

## B8. GitHub workflows

**Files:** `.github/workflows/products.yml`, `collections.yml`, `backup.yml`, `reparse.yml`

| Workflow | When (UTC) | When (IST) |
|---|---|---|
| `products.yml` | `0 */3 * * *` | 05:30, 08:30, 11:30 and so on |
| `collections.yml` | `30 21 * * *` | 03:00 |
| `backup.yml` | `30 22 * * *` | 04:00 |
| `reparse.yml` | only by hand, with a run ID | — |

Each workflow:

1. Has `workflow_dispatch`, so you can start it by hand.
2. Has a `concurrency` lock. A new run waits. It does not cancel the old run.
3. Has `permissions: id-token: write, contents: read`. OIDC needs `id-token`.
4. Gets AWS access with `aws-actions/configure-aws-credentials` and `AWS_ROLE_ARN`.
5. Installs Python 3.12 and `requirements.txt`.
6. Runs one `python -m pipeline ...` command.
7. Has a time limit (products 30 minutes, collections 30 minutes, backup 10 minutes).

I remove `fetch-test.yml` after the first good run.

## B9. Website: Neon connection

**Files:** `web/src/lib/db.ts`, `web/.env.example`

- The pool reads `DATABASE_URL` (the pooled Neon address of the `website` user).
- The pool size is small (`max: 3`), because each Vercel function opens its own pool. Neon's pooler handles the rest.

**Test:** `npm run build` and `npm run dev`, against the local database.

## B10. Website: the limit on "Notify me"

**Files:** `web/src/app/api/track/route.ts`

- Get the visitor IP address from the `x-forwarded-for` header that Vercel sets.
- Make a hash: sha256 of (IP address + `RATE_LIMIT_SALT`). We keep only the hash.
- Count the trackers with this hash from the last hour. At 10 or more, reply with HTTP 429: "Too many requests. Try again in an hour."
- Save the hash in the new tracker row.

**Test:** send 11 requests from one address. The 11th must fail.

## B11. Bot: move it to Vercel

**Files:** new `web/src/app/api/telegram/route.ts` and `web/src/lib/bot.ts`. Remove `pipeline/bot.py`.

- Telegram sends each message to `https://<site>/api/telegram`.
- First, check the header `X-Telegram-Bot-Api-Secret-Token`. If it is not equal to `TELEGRAM_WEBHOOK_SECRET`, reply 401 and stop.
- Then do the same work as the Python bot: `/start <token>`, `/start`, `/list`, `/stop`. The texts stay the same.
- Send the reply in the HTTP response. Telegram supports this, so we make no extra call.
- Always reply 200 after the secret check, also on an error. If not, Telegram sends the same message again and again.
- The `bot_state` table is no longer used. I leave it in place, because we never delete.

**Test:** send fake Telegram requests with `curl` to the local site: one with the correct header and one without it.

## B12. Clean-up

- Remove `deploy/run.sh` and `deploy/crontab`.
- Remove the `bot` command from `pipeline/__main__.py`.
- Update `.env.example` and `web/.env.example`.

## B13. README (at the end)

- What it is, with a screenshot.
- The architecture diagram.
- The main decisions and why: GitHub in place of AWS for fetching, raw-first, no JSONB, change-only history.
- How to run it locally.
- The security list.

---

# Part C: set up the services (your work)

Do the steps in the order of **Part D**. Each section here is one service.

**Two rules for all steps:**

- Never paste a password, a token or a connection address in the chat. Put it only where the step says.
- When a step shows a value only one time, copy it at once.

## C1. Neon (about 5 minutes)

1. Go to **https://neon.com** and click **Sign up**. Sign in with GitHub. That is the easiest way.
2. Click **New project**.
3. Fill in the form:
   - **Project name:** `the-catalogue`
   - **Postgres version:** **18** if Neon offers it. If not, the newest version on the list.
   - **Region:** **AWS Asia Pacific (Singapore)**. If you see **Mumbai**, choose Mumbai.
   - **Database name:** `catalogue`
4. Click **Create project**.
5. On the project page, click **Connect**.
6. In the box that opens:
   - Role: the owner role (the default, for example `neondb_owner`)
   - Database: `catalogue`
   - **Connection pooling: OFF**
7. Copy the address. It starts with `postgresql://`.
8. Open the file `.env` in the project folder on your Mac. If it does not exist, copy `.env.example` to `.env`.
9. Add this line at the end, with your address after the `=`:

   ```
   NEON_OWNER_URL=postgresql://...
   ```

10. Tell me in the chat: "Neon is ready." Do not paste the address.

**Done (2026-10-22):** I ran the migrations and `set-db-passwords`. Your `.env` now has 4 new lines: `PIPELINE_DB_URL`, `WEBSITE_DB_URL` (pooled), `TELEGRAM_WEBHOOK_SECRET` and `RATE_LIMIT_SALT`. You copy them into GitHub and Vercel in C3 and C4.

## C2. AWS (about 15 minutes)

Sign in to the AWS console. Check that the region at the top right is **Asia Pacific (Mumbai) ap-south-1**.

### C2.1 Trust GitHub (the OIDC provider)

1. Open **IAM** (type "IAM" in the search bar).
2. In the left menu, click **Identity providers**, then **Add provider**.
3. **Provider type:** OpenID Connect.
4. **Provider URL:** `https://token.actions.githubusercontent.com`
5. **Audience:** `sts.amazonaws.com`
6. Click **Add provider**.

### C2.2 Create the role `catalogue-github`

1. In IAM, click **Roles**, then **Create role**.
2. **Trusted entity type:** Web identity.
3. **Identity provider:** `token.actions.githubusercontent.com`
4. **Audience:** `sts.amazonaws.com`
5. **GitHub organization:** `godslonelymann`
6. **GitHub repository:** `the-catalogue`
7. **GitHub branch:** `main`
8. Click **Next**. Do not choose a policy on this page. Click **Next** again.
9. **Role name:** `catalogue-github`. Click **Create role**.

### C2.3 Give the role its permission

1. Open the role `catalogue-github`.
2. Click **Add permissions**, then **Create inline policy**.
3. Click **JSON**. Delete the text in the box and paste this:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "WriteRawAndBackups",
         "Effect": "Allow",
         "Action": "s3:PutObject",
         "Resource": [
           "arn:aws:s3:::the-catalogue-raw-anurag/raw/*",
           "arn:aws:s3:::the-catalogue-raw-anurag/backups/*"
         ]
       },
       {
         "Sid": "ReadRawForReparse",
         "Effect": "Allow",
         "Action": "s3:GetObject",
         "Resource": "arn:aws:s3:::the-catalogue-raw-anurag/raw/*"
       }
     ]
   }
   ```

4. Click **Next**. **Policy name:** `catalogue-github-s3`. Click **Create policy**.
5. On the role page, copy the **ARN**. It looks like `arn:aws:iam::123456789012:role/catalogue-github`. You need it in C3. The ARN is not a secret.

### C2.4 Check the trust policy

1. On the role page, click the **Trust relationships** tab.
2. The condition must contain this line:

   ```
   "token.actions.githubusercontent.com:sub": "repo:godslonelymann/the-catalogue:ref:refs/heads/main"
   ```

3. If it shows `*` or something else, click **Edit trust policy** and change it to the line above.

This line means: only workflows from the `main` branch of your repo can use the role.

### C2.5 Budget alert

1. Search for **Budgets** and open it.
2. Click **Create budget**, then **Use a template**, then **Monthly cost budget**.
3. **Budget amount:** `2` (USD).
4. **Email:** your email address.
5. Click **Create budget**.

AWS now sends you an email if the bill goes above $2 in a month.

## C3. GitHub (about 10 minutes)

### C3.1 Make the repo public (recommended)

A public repo is better for your resume, and Actions minutes are free and unlimited.

1. Before this step, I check the git history for secrets. Wait for my "OK".
2. Open the repo on GitHub: `godslonelymann/the-catalogue`.
3. Click **Settings**, then **General**. Scroll to **Danger Zone**.
4. Click **Change visibility**, then **Make public**, and confirm.

### C3.2 Add the secrets

1. In the repo, click **Settings**, then **Secrets and variables**, then **Actions**.
2. On the **Secrets** tab, click **New repository secret** for each row:

| Name | Value |
|---|---|
| `CATALOGUE_DB` | `PIPELINE_DB_URL` from your `.env` |
| `TELEGRAM_BOT_TOKEN` | the token from @BotFather (add it in C5) |

3. On the **Variables** tab, click **New repository variable** for each row:

| Name | Value |
|---|---|
| `AWS_ROLE_ARN` | the ARN from C2.3 |
| `CATALOGUE_STORAGE` | `s3://the-catalogue-raw-anurag` |
| `AWS_REGION` | `ap-south-1` |
| `TELEGRAM_BOT_USERNAME` | the bot name without `@` (add it in C5) |

### C3.3 Turn on emails for failed runs

1. Click your photo at the top right, then **Settings**, then **Notifications**.
2. Under **Actions**, choose **Email** and **Only notify for failed workflows**.

### C3.4 Push the code

When I say the code is ready, run this in the project folder:

```bash
git push origin main
```

### C3.5 The first run (by hand)

1. Open the **Actions** tab of the repo.
2. Click **Products** in the left list.
3. Click **Run workflow**, then the green **Run workflow** button.
4. Wait about 5 to 10 minutes. Then click the run and read the log. Each store must show `products=...`.
5. Tell me the result. I check the data in Neon.
6. Do the same for **Collections** and **Backup**.
7. In the AWS console, open **S3**, then the bucket. Check that new files are in `raw/` and `backups/`.

## C4. Vercel (about 10 minutes)

### C4.1 Create the project

1. Go to **https://vercel.com** and click **Sign up**. Choose **Hobby** and sign in with GitHub.
2. Click **Add New**, then **Project**.
3. Find `the-catalogue` and click **Import**. If you do not see it, click **Adjust GitHub App Permissions** and give Vercel access to this repo.
4. **Root Directory:** click **Edit** and choose `web`.
5. **Framework Preset:** Next.js (Vercel finds it).
6. Open **Environment Variables** and add these rows:

| Name | Value |
|---|---|
| `DATABASE_URL` | `WEBSITE_DB_URL` from your `.env` (the pooled one) |
| `RATE_LIMIT_SALT` | `RATE_LIMIT_SALT` from your `.env` |
| `TELEGRAM_BOT_USERNAME` | add it in C5 |
| `TELEGRAM_WEBHOOK_SECRET` | `TELEGRAM_WEBHOOK_SECRET` from your `.env` |

Vercel does **not** need the bot token. The bot replies inside the webhook response.

7. Click **Deploy**. Wait about 2 minutes.
8. Open the link that Vercel shows, for example `https://the-catalogue.vercel.app`. Write it down.

### C4.2 Set the region

1. In the project, click **Settings**, then **Functions**.
2. **Function Region:** choose **Singapore (sin1)**. This is close to Neon.
3. Click **Save**.
4. Click **Deployments**. On the newest deployment, click **...**, then **Redeploy**.

### C4.3 When you add or change a variable

Vercel uses a new value only after a new deployment. After each change, do the **Redeploy** in C4.2 step 4.

## C5. Telegram (about 5 minutes)

### C5.1 Create the bot

1. Open Telegram and search for **@BotFather**. Check that it has the blue tick.
2. Send `/newbot`.
3. Send the bot display name, for example `The Catalogue Alerts`.
4. Send the bot username. It must end in `bot`, for example `thecatalogue_alerts_bot`.
5. BotFather sends the **token**. Copy it. Treat it like a password.
6. Send `/setdescription`, choose your bot, and send: `I tell you when a product you track on The Catalogue is back in stock.`

### C5.2 Put the values in their places

1. **Vercel**: add `TELEGRAM_BOT_USERNAME` (without `@`). Then redeploy (C4.3).
2. **GitHub** (C3.2): add the secret `TELEGRAM_BOT_TOKEN` and the variable `TELEGRAM_BOT_USERNAME`.

### C5.3 Connect the bot to Vercel

Run this one command in your Mac terminal. First put your 3 values in place of the `<...>` parts:

```bash
curl -s "https://api.telegram.org/bot<TOKEN>/setWebhook" -d "url=https://<your-site>.vercel.app/api/telegram" -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>" -d 'allowed_updates=["message"]'
```

The reply must contain `"ok":true`.

To check it later:

```bash
curl -s "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

`last_error_message` must be empty.

## C6. The final check (about 10 minutes)

1. Open the site. Click each brand tab. Open some products.
2. Find a product with a sold-out size. Click **Notify me on Telegram**.
3. Telegram opens. Tap **Start**. The bot must answer "Tracking ...".
4. Send `/list` to the bot. The product must be on the list.
5. To test the alert, I mark that size as sold out in the database. Then you start **Products** by hand. If the size is in stock at the store, you get the message.
6. Send `/stop`. The bot must say how many alerts it stopped.

## C7. Shut down the old AWS server (about 5 minutes)

Do this **only after C6 works**.

1. Open **EC2**, then **Instances**. Select `catalogue-server`. Click **Instance state**, then **Terminate instance**, and confirm.
2. In EC2, open **Elastic IPs**. Select `15.207.36.233`. Click **Actions**, then **Release Elastic IP addresses**.
   **This is important:** AWS charges for an Elastic IP that is not in use.
3. In EC2, open **Security Groups**. Select `catalogue-sg`. Click **Actions**, then **Delete security groups**. (Wait until the instance shows "Terminated".)
4. In EC2, open **Key Pairs**. Delete `catalogue-key`. On your Mac, delete `~/.ssh/catalogue-key.pem`.
5. Open **IAM**, then **Roles**. Delete `catalogue-ec2-role`.
6. **Keep** the S3 bucket `the-catalogue-raw-anurag`. We still use it.

---

# Part D: the order of all steps

| # | Step | Who | Part | Time |
|---|---|---|---|---|
| 1 | Create the Neon project, put the owner address in `.env` | You | C1 | 5 min |
| 2 | Code changes and local tests | Me | B1 to B12 | — |
| 3 | Run the migration on Neon, make the 2 users and the secrets in `.env` | Me | B6 | 5 min |
| 4 | AWS: OIDC provider, role, policy, budget | You | C2 | 15 min |
| 5 | I check the git history. You make the repo public. | Me, then you | C3.1 | 5 min |
| 6 | GitHub: secrets, variables, emails, push | You | C3.2 to C3.4 | 10 min |
| 7 | First runs by hand, check the data | You and me | C3.5 | 20 min |
| 8 | Vercel: import, variables, region, deploy | You | C4 | 10 min |
| 9 | Telegram: create the bot, add the values, connect the webhook | You | C5 | 10 min |
| 10 | Final check on the live site | You and me | C6 | 10 min |
| 11 | Shut down the old EC2 server | You | C7 | 5 min |
| 12 | README and clean-up | Me | B13 | — |

You can do steps 1 and 4 while I do step 2.

---

# Things to know

- **The pipeline uses the direct address. The website uses the pooled address.** The pooler stops Vercel from opening too many connections.
- **Neon sleeps after 5 minutes without queries.** The first page view after that is about half a second slower. This is normal.
- **Neon free restores data only from the last few hours.** Our daily backup in S3 covers older data.
- **GitHub can start a scheduled run a few minutes late.** That is fine for us.
- **GitHub pauses schedules in a public repo after 60 days without commits.** You get an email. Open the Actions tab and click **Enable workflow**.
- **No domain yet.** The link is `https://the-catalogue.vercel.app` or a similar free name. You can add your own domain later in Vercel, under **Settings**, then **Domains**.
- **To load a stored run again** (for example after a parser fix), start the **Reparse** workflow by hand with the run ID, for example `RUN-7KQ2M`.

# Your resume story

> "Built a data platform that tracks 3,400+ products across 10 brands. Scheduled ingestion runs on GitHub Actions (moved off AWS after I found Cloudflare rate limits on cloud IPs). Raw-first storage in S3, a normalized Postgres model on Neon with change-only history, a Next.js frontend on Vercel, and Telegram restock alerts through a webhook. Secured with OIDC (no static keys), least-privilege database roles, and verified SSL. Runs for about $1 per month."
