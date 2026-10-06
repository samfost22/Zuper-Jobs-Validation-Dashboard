# Plan — Streamlit Dashboard Quick Wins (Option 1)

**Goal:** Get more value out of the *already-deployed* Zuper Jobs Validation Dashboard
without adding any new infrastructure (no webhook service, no agent). Three additions:

1. **Aging** — show & sort by how long a job has been flagged.
2. **Export** — one-click CSV/Excel of the currently-filtered flagged jobs.
3. **Daily Slack digest** — a once-a-day backlog roll-up via the existing cron.

**Effort:** ~half a day total. **Risk:** low — additive, reversible, no schema changes
required (one optional index). All work stays inside this repo and deploys to the
existing Streamlit Cloud site + the existing GitHub Actions sync.

---

## Context — what's already here (verified)

- **Data layer:** `database/queries.py` — but note `streamlit_dashboard.py` has its **own
  local `get_jobs()`** at `streamlit_dashboard.py:273` that the live page actually uses.
  (The `database/queries.py` copy is partly duplicate. We touch the one the page calls.)
- **Schema** (`database_jobs_schema.sql`) already has every date we need:
  - `jobs.completed_at`, `jobs.created_at` (indexed)
  - `validation_flags.created_at` = when the flag was raised (DEFAULT CURRENT_TIMESTAMP)
  - `validation_flags.is_resolved`, `validation_flags.resolved_at`
- **Export already half-exists:** `streamlit_dashboard.py:856` and `:919` already do
  `display_df.to_csv()` + `st.download_button()`. So export is "extend the pattern to the
  main flagged-jobs view," not "build from scratch."
- **Table rendering:** `components/job_table.py:render_job_row()` (`col1/col2/col3` layout;
  the caption at `:39-43` is where an age badge slots in).
- **Cron already runs:** `.github/workflows/scheduled-sync.yml` → `scheduled_sync.py`
  (`run_sync()` at `:34`). This is where the daily digest hooks in — no new scheduler.
- **Slack already wired:** `notifications/slack_notifier.py` — `SlackNotifier` (Block Kit),
  `send_missing_netsuite_notification()`, and `get_notification_stats()` at `:445`.

---

## Feature 1 — Aging (the highest-value one)

**What:** For every flagged job, compute **days flagged** and surface it as a sortable
column / badge, defaulting worst-first. Turns "40 problems" into "these 5 are oldest."

**Definition of "age":**
`days_flagged = today - DATE(validation_flags.created_at)` (fall back to
`jobs.completed_at`, then `jobs.created_at` if a flag has no timestamp).
Use the flag's `created_at` — it answers "how long has this been a known problem,"
which is the operational question.

**Changes:**
1. `streamlit_dashboard.py:273` `get_jobs()` — add to the SELECT:
   ```sql
   CAST(julianday('now') - julianday(
     COALESCE(vf.created_at, j.completed_at, j.created_at)
   ) AS INTEGER) AS days_flagged
   ```
   and add an `ORDER BY days_flagged DESC` option (keep `created_at DESC` as the
   default for non-flagged views). Gate behind a sort selectbox so existing behavior
   is unchanged unless the user opts in.
2. `components/job_table.py:39-43` — add an age badge to the caption, e.g.
   `🔴 23 days` (≥14), `🟡 7 days` (7–13), plain `3 days` (<7). Thresholds as module
   constants at top of file so they're easy to tune.
3. (Optional, performance) add `idx_flags_created` on
   `validation_flags(created_at, is_resolved)` in `migrations/` — only if the flagged
   list feels slow; current volume likely doesn't need it.

**Acceptance:** Open the "Missing NetSuite ID" filter → oldest job is at top, each row
shows a day count, color matches threshold. No change to passing-jobs view.

**Effort:** S (1–2 hrs).

---

## Feature 2 — Export flagged jobs

**What:** A "⬇ Download (CSV / Excel)" button above the main flagged-jobs table that
exports **exactly what's currently filtered** (respects org/team/date/search/aging sort),
not just the current page.

**Changes:**
1. `streamlit_dashboard.py` — near where `render_job_table` is called (after `:945`),
   add a download button. Reuse the existing `to_csv` pattern from `:856`.
   - Pull the **full filtered set** for export (call `get_jobs(..., limit=10000)` or a
     dedicated `export=True` path) so the download isn't capped at one page of 50.
   - Include the `days_flagged` column from Feature 1 + `flag_type`, `flag_message`,
     job_number, org, team, asset, completed_at, and the Zuper URL.
2. Filename: `flagged_jobs_{filter_type}_{YYYY-MM-DD}.csv`.
3. Excel is optional — CSV covers the parts team's need and adds no dependency
   (`openpyxl` not currently in `requirements.txt`; only add it if Excel is wanted).

**Acceptance:** Filter to one org → download → CSV row count matches the on-screen
total count (not the page size), columns include age + Zuper link.

**Effort:** S (~30–45 min).

---

## Feature 3 — Daily Slack digest

**What:** Once a day, post a single backlog summary to the existing Slack/Zapier webhook:

> 📋 *Daily Validation Digest — Jun 3*
> • 12 open issues (3 missing SO ID, 9 parts-no-line-items)
> • 2 new since yesterday · 1 resolved
> • ⏳ Oldest open: Job #18742 (Willoughby) — 19 days
> _<link to dashboard>_

This complements (doesn't replace) the existing per-job real-time alerts.

**Where it runs:** inside the existing cron, **not** the Streamlit app (Streamlit Cloud
sleeps and can't self-schedule). Two clean options:

- **3a (recommended):** add a `--digest` mode to `scheduled_sync.py` and a second
  schedule entry in `.github/workflows/scheduled-sync.yml` (e.g. one `cron: '0 14 * * *'`
  = 7am Pacific) that runs `python scheduled_sync.py --mode digest`. Reuses the
  `SLACK_WEBHOOK_URL` secret already configured in the workflow.
- **3b (alt):** standalone `daily_digest.py` invoked by its own tiny workflow. Same
  effect; slightly more files.

**Changes (3a):**
1. New `queries.py` (or local) function `get_digest_stats()`:
   ```sql
   -- open by type
   SELECT flag_type, COUNT(DISTINCT job_uid) FROM validation_flags
     WHERE is_resolved = 0 GROUP BY flag_type;
   -- new in last 24h
   SELECT COUNT(*) FROM validation_flags
     WHERE is_resolved = 0 AND created_at > datetime('now','-24 hours');
   -- resolved in last 24h
   SELECT COUNT(*) FROM validation_flags
     WHERE is_resolved = 1 AND resolved_at > datetime('now','-24 hours');
   -- oldest open (join jobs for number/org)
   SELECT j.job_number, j.organization_name,
     CAST(julianday('now')-julianday(vf.created_at) AS INT) AS days
     FROM validation_flags vf JOIN jobs j ON j.job_uid=vf.job_uid
     WHERE vf.is_resolved=0 ORDER BY vf.created_at ASC LIMIT 1;
   ```
2. New `slack_notifier.py` method `send_daily_digest(stats)` — Block Kit, mirrors the
   style of `send_missing_netsuite_alert` (`:138`). Add a "Open Dashboard" button to the
   Streamlit URL.
3. `scheduled_sync.py` — add `"digest"` to the argparse choices (`:86`) and a branch in
   `run_sync()`/`main()` that calls `get_digest_stats()` → `send_daily_digest()` and exits
   (no API pull needed for digest).
4. `.github/workflows/scheduled-sync.yml` — add the daily digest cron + a job step that
   runs `--mode digest`.

> ⚠️ **State caveat:** the SQLite DB on GitHub Actions is ephemeral unless the workflow
> already persists it (commit-back, artifact, or external DB). Check how
> `scheduled-sync.yml` handles `jobs_validation.db` today — the digest reads whatever the
> sync just wrote, so run digest **in the same job after a sync**, or point both at the
> same persisted DB. This is a "verify before building" item, not a blocker.

**Acceptance:** Manually trigger the workflow with `--mode digest` → one well-formatted
Slack message with correct open/new/resolved counts and the oldest job. Re-running
doesn't double-post for the same day (optional: guard via `notification_log` with type
`daily_digest` + date).

**Effort:** M (2–3 hrs, mostly the workflow/DB-persistence verification).

---

## Suggested order

1. **Aging** — biggest value, lowest risk, unlocks the export column too.
2. **Export** — trivial once aging adds the column; immediately useful to the parts team.
3. **Daily digest** — do last; needs the GitHub Actions DB-persistence check first.

Stop after #1+#2 if that's "enough" — they're self-contained and need no cron changes.

## Out of scope (these are Options 2 & 3, not this plan)
- Real-time **webhook** receiver (needs an always-on companion service).
- Backend **triage agent** (Claude API drafting follow-ups).
- Consolidating this app's `jobs_validation.db` with Module Audit / Supabase stores.

## Pre-flight checks before coding
- [ ] Confirm `streamlit_dashboard.py:273 get_jobs()` is the function the live page calls
      (vs `database/queries.py`) — patch the one in use, consider de-duping later.
- [ ] Confirm how `.github/workflows/scheduled-sync.yml` persists `jobs_validation.db`
      between runs (drives Feature 3 design).
- [ ] Confirm `SLACK_WEBHOOK_URL` is set as an Actions secret (it's referenced at
      `scheduled_sync.py:44`).
