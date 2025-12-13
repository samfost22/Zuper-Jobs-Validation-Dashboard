# Performance Analysis Report

This document identifies performance anti-patterns, N+1 queries, unnecessary re-renders, and inefficient algorithms found in the codebase.

## Critical Issues

### 1. N+1 Query Pattern in Bulk Serial Lookup (`streamlit_dashboard.py:675-713`)

**Severity: High**

The bulk serial lookup feature executes a separate database query for each serial number in a loop:

```python
for i, serial in enumerate(serials):
    cursor.execute("""
        SELECT DISTINCT j.job_uid, j.job_number, ...
        FROM jobs j
        LEFT JOIN job_line_items li ON j.job_uid = li.job_uid
            AND (li.item_serial LIKE ? OR li.item_serial LIKE ?)
        ...
    """, (f'%{serial}%', f'%{serial}%', f'%{serial}%', f'%{serial}%'))
```

**Impact**: If a user searches for 100 serial numbers, this executes 100 separate database queries.

**Fix**: Use a single query with `WHERE ... IN (...)` or build a UNION query:

```python
# Option 1: Single query with OR conditions
placeholders = " OR ".join(["(li.item_serial LIKE ? OR cp.part_serial LIKE ?)"] * len(serials))
params = []
for s in serials:
    params.extend([f'%{s}%', f'%{s}%'])
cursor.execute(f"SELECT ... WHERE {placeholders}", params)

# Option 2: Use temp table for large searches
cursor.execute("CREATE TEMP TABLE search_serials (serial TEXT)")
cursor.executemany("INSERT INTO search_serials VALUES (?)", [(s,) for s in serials])
cursor.execute("""
    SELECT ...
    FROM jobs j, search_serials ss
    WHERE j.item_serial LIKE '%' || ss.serial || '%'
""")
```

---

### 2. N+1 Query in `database/queries.py:search_serials_bulk()` (lines 367-420)

**Severity: High**

Same pattern as above - iterates through serials executing a query per item:

```python
for serial in serials:
    cursor.execute("""
        SELECT DISTINCT ...
        FROM jobs j
        LEFT JOIN job_line_items li ON j.job_uid = li.job_uid AND li.item_serial LIKE ?
        ...
    """, (f'%{serial}%', f'%{serial}%'))
```

**Fix**: Same as above - batch the query.

---

### 3. Repeated Database Connections in Sync Loop (`sync_jobs_to_db.py:383-594`)

**Severity: Medium**

The `sync_jobs_to_database()` function commits after every 100 jobs but keeps a single connection open. However, it creates multiple database connections indirectly through notification tracking:

```python
# Line 542-583: For each job with missing_netsuite_id flag
from notifications.slack_notifier import send_missing_netsuite_notification
result = send_missing_netsuite_notification(...)  # This opens its own DB connection
```

Inside `slack_notifier.py`:
- `init_notification_tracking()` - opens connection (line 217)
- `was_notification_sent()` - opens connection (line 245)
- `record_notification()` - opens connection (line 270)

**Impact**: For each job needing notification, 3 additional database connections are opened/closed.

**Fix**: Pass the existing database connection to notification functions or batch notification operations.

---

### 4. SQL Injection Vulnerability via String Interpolation (`streamlit_dashboard.py:172-213`)

**Severity: Critical (Security + Performance)**

The `get_jobs()` function builds SQL queries using f-strings with user input:

```python
if job_number:
    filter_clauses.append(f"j.job_number LIKE '%{job_number}%'")
# ... similar patterns for month, organization, team, asset
```

**Security Risk**: SQL injection attacks possible.
**Performance Risk**: Query plan caching is defeated since query strings change with each input.

**Note**: The `database/queries.py` version uses parameterized queries correctly - the issue is in the legacy `streamlit_dashboard.py` file.

**Fix**: Always use parameterized queries:
```python
filter_clauses.append("j.job_number LIKE ?")
params.append(f"%{job_number}%")
```

---

### 5. Inefficient Line Item Deletion Pattern (`sync_jobs_to_db.py:458-506`)

**Severity: Medium**

For each job, three DELETE operations occur before inserting new data:

```python
cursor.execute("DELETE FROM job_line_items WHERE job_uid = ?", (job_uid,))
# ... insert line items one by one

cursor.execute("DELETE FROM job_checklist_parts WHERE job_uid = ?", (job_uid,))
# ... insert checklist parts one by one

cursor.execute("DELETE FROM job_custom_fields WHERE job_uid = ?", (job_uid,))
# ... insert custom fields one by one
```

**Impact**: For 1000 jobs with an average of 5 line items each: 3000 DELETE statements + 5000 INSERT statements.

**Fix**: Use `executemany()` for batch inserts:

```python
cursor.execute("DELETE FROM job_line_items WHERE job_uid = ?", (job_uid,))
if line_items:
    cursor.executemany("""
        INSERT INTO job_line_items (job_uid, item_name, item_code, item_serial, quantity, price, line_item_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [(job_uid, item['item_name'], item['item_code'], item['item_serial'],
           item['quantity'], item['price'], item['line_item_type'], job.get('created_at', ''))
          for item in line_items])
```

---

## Medium Issues

### 6. Redundant Metrics Queries (`streamlit_dashboard.py:100-144`)

**Severity: Medium**

The `get_metrics()` function runs 4 separate queries that could be combined:

```python
cursor.execute("SELECT COUNT(*) as total FROM jobs")
cursor.execute("SELECT COUNT(DISTINCT job_uid) ... WHERE flag_type = 'parts_replaced_no_line_items'...")
cursor.execute("SELECT COUNT(DISTINCT job_uid) ... WHERE flag_type = 'missing_netsuite_id'...")
cursor.execute("SELECT COUNT(*) ... FROM jobs j LEFT JOIN validation_flags...")
```

**Fix**: Combine into a single query with subqueries or conditional aggregation:

```sql
SELECT
    COUNT(*) as total_jobs,
    COUNT(DISTINCT CASE WHEN vf.flag_type = 'parts_replaced_no_line_items' AND vf.is_resolved = 0 THEN j.job_uid END) as parts_no_items_count,
    COUNT(DISTINCT CASE WHEN vf.flag_type = 'missing_netsuite_id' AND vf.is_resolved = 0 THEN j.job_uid END) as missing_netsuite_count,
    COUNT(DISTINCT CASE WHEN vf.id IS NULL THEN j.job_uid END) as passing_count
FROM jobs j
LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid AND vf.is_resolved = 0
```

---

### 7. Streamlit Re-render on Every Input Change

**Severity: Medium**

In `streamlit_dashboard.py`, filter inputs directly modify session state and trigger re-renders:

```python
with col1:
    job_number_input = st.text_input("Job Number", ...)
    if job_number_input:
        st.session_state.job_number_search = job_number_input
        st.session_state.current_page = 1  # Triggers rerun
```

**Impact**: Typing in a search box triggers a full page re-render on each keystroke.

**Fix**: Use Streamlit's `st.form()` to batch input changes:

```python
with st.form("filter_form"):
    job_number_input = st.text_input("Job Number", ...)
    part_input = st.text_input("Part Name/Code", ...)
    if st.form_submit_button("Apply Filters"):
        st.session_state.job_number_search = job_number_input
        st.session_state.part_search = part_input
        st.rerun()
```

---

### 8. Duplicate Filter Options Queries (`streamlit_dashboard.py:301-328`)

**Severity: Low**

`get_filter_options()` runs two separate queries for organizations and teams:

```python
cursor.execute("SELECT DISTINCT organization_name FROM jobs ...")
cursor.execute("SELECT DISTINCT service_team FROM jobs ...")
```

**Fix**: Combine into one query:

```sql
SELECT DISTINCT organization_name, service_team FROM jobs
WHERE organization_name IS NOT NULL OR service_team IS NOT NULL
```

Then split the results in Python.

---

### 9. Expensive Job Validation Summary View (`database_jobs_schema.sql:117-140`)

**Severity: Medium**

The `job_validation_summary` view performs multiple JOINs and aggregations on every query:

```sql
CREATE VIEW IF NOT EXISTS job_validation_summary AS
SELECT ...
    COUNT(DISTINCT li.id) as line_items_count,
    COUNT(DISTINCT cp.id) as checklist_parts_count,
    COUNT(DISTINCT CASE WHEN vf.is_resolved = 0 THEN vf.id END) as active_flags_count,
    ...
FROM jobs j
LEFT JOIN job_line_items li ON j.job_uid = li.job_uid
LEFT JOIN job_checklist_parts cp ON j.job_uid = cp.job_uid
LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid
GROUP BY j.job_uid;
```

**Impact**: Any query against this view performs full table scans with 3 JOINs.

**Fix**:
1. Don't use this view for listings - query the jobs table directly
2. If summary data is needed, materialize it during sync (store counts in the jobs table)
3. Add indexes to support the view if it must be used

---

### 10. Inefficient API Enrichment Memory Pattern (`streamlit_sync.py:227-367`)

**Severity: Medium**

The `enrich_jobs_with_assets()` function creates a full copy of all jobs in memory:

```python
enriched_jobs = [None] * total  # Pre-allocate full array
job_uid_to_index = {job.get('job_uid'): idx for idx, job in enumerate(jobs)}  # Another full dict
```

For 5000 jobs with rich data, this could use 100MB+ of memory.

**Fix**: Process in batches (which `sync_jobs_in_batches()` already does) and avoid the full pre-allocation:

```python
# Instead of storing all at once, yield results or process in chunks
for batch in batched(jobs, batch_size):
    enriched = enrich_batch(batch)
    sync_batch_to_db(enriched)
```

---

## Minor Issues

### 11. Missing Composite Index for Common Query Pattern

**Location**: `database_jobs_schema.sql`

**Issue**: Queries filtering by `completed_at` or `created_at` combined with `organization_name` lack a composite index:

```sql
-- This query pattern is common but has no supporting composite index:
WHERE date(COALESCE(j.completed_at, j.created_at)) BETWEEN ? AND ?
  AND j.organization_name LIKE ?
```

**Fix**: Add composite indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_jobs_completed_org ON jobs(completed_at, organization_name);
CREATE INDEX IF NOT EXISTS idx_jobs_created_org ON jobs(created_at, organization_name);
```

---

### 12. Unnecessary `ensure_database_exists()` Calls

**Location**: `database/queries.py` - called in every function

**Issue**: Every query function calls `ensure_database_exists()`:

```python
def get_metrics():
    ensure_database_exists()
    with db_session() as conn:
        ...

def get_jobs():
    ensure_database_exists()
    ...
```

**Impact**: Each call checks `os.path.exists(db_path)` - cheap but unnecessary when called repeatedly.

**Fix**: Call once at application startup, not on every query.

---

## Summary Table

| Issue | Severity | Category | Location |
|-------|----------|----------|----------|
| N+1 Query in Bulk Serial Lookup | High | N+1 Query | streamlit_dashboard.py:675 |
| N+1 Query in search_serials_bulk | High | N+1 Query | database/queries.py:384 |
| SQL Injection via String Interpolation | Critical | Security | streamlit_dashboard.py:172 |
| Repeated DB Connections in Notifications | Medium | Connection Management | sync_jobs_to_db.py + slack_notifier.py |
| Inefficient Line Item Insert Pattern | Medium | Batch Operations | sync_jobs_to_db.py:458 |
| Redundant Metrics Queries | Medium | Query Optimization | streamlit_dashboard.py:100 |
| Re-renders on Input Change | Medium | Streamlit UX | streamlit_dashboard.py |
| Expensive View with Multiple JOINs | Medium | Schema Design | database_jobs_schema.sql:117 |
| API Enrichment Memory Usage | Medium | Memory | streamlit_sync.py:227 |
| Missing Composite Indexes | Low | Index Design | database_jobs_schema.sql |
| Redundant ensure_database_exists | Low | Startup | database/queries.py |

---

## Recommended Priority

1. **Immediate**: Fix SQL injection vulnerability (security risk)
2. **High**: Fix N+1 queries in bulk serial lookup (affects user-facing feature)
3. **Medium**: Batch insert operations and combine metrics queries
4. **Low**: Streamlit form optimization and index additions
