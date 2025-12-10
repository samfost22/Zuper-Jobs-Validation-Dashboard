-- Zuper Jobs Validation Database Schema

-- Jobs table
CREATE TABLE IF NOT EXISTS jobs (
    job_uid TEXT PRIMARY KEY,
    job_number TEXT,
    job_title TEXT,
    job_status TEXT,
    job_category TEXT,
    customer_name TEXT,
    organization_uid TEXT,
    organization_name TEXT,
    service_team TEXT,
    asset_name TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    completed_at TIMESTAMP,
    has_line_items BOOLEAN DEFAULT 0,
    has_checklist_parts BOOLEAN DEFAULT 0,
    has_netsuite_id BOOLEAN DEFAULT 0,
    netsuite_sales_order_id TEXT,
    jira_link TEXT,
    slack_link TEXT,
    job_notes TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_uid) REFERENCES organizations(organization_uid)
);

-- Job line items (parts/products used on job)
CREATE TABLE IF NOT EXISTS job_line_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_uid TEXT NOT NULL,
    item_name TEXT,
    item_code TEXT,
    item_serial TEXT,
    quantity REAL DEFAULT 1,
    price REAL,
    line_item_type TEXT,
    created_at TIMESTAMP,
    FOREIGN KEY (job_uid) REFERENCES jobs(job_uid)
);

-- Job checklist parts (parts mentioned in checklists/status)
CREATE TABLE IF NOT EXISTS job_checklist_parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_uid TEXT NOT NULL,
    checklist_question TEXT,
    part_serial TEXT,
    part_description TEXT,
    status_name TEXT,
    position TEXT,
    updated_at TIMESTAMP,
    FOREIGN KEY (job_uid) REFERENCES jobs(job_uid)
);

-- Job checklist text (full searchable text from all checklist answers)
CREATE TABLE IF NOT EXISTS job_checklist_text (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_uid TEXT NOT NULL,
    checklist_question TEXT,
    checklist_answer TEXT,
    status_name TEXT,
    updated_at TIMESTAMP,
    FOREIGN KEY (job_uid) REFERENCES jobs(job_uid)
);

-- Job custom fields
CREATE TABLE IF NOT EXISTS job_custom_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_uid TEXT NOT NULL,
    field_label TEXT,
    field_value TEXT,
    field_type TEXT,
    FOREIGN KEY (job_uid) REFERENCES jobs(job_uid),
    UNIQUE(job_uid, field_label)
);

-- Validation flags
CREATE TABLE IF NOT EXISTS validation_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_uid TEXT NOT NULL,
    flag_type TEXT,  -- 'missing_netsuite_id', 'line_item_mismatch'
    flag_severity TEXT,  -- 'error', 'warning'
    flag_message TEXT,
    details TEXT,  -- JSON with extra details
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_resolved BOOLEAN DEFAULT 0,
    resolved_at TIMESTAMP,
    FOREIGN KEY (job_uid) REFERENCES jobs(job_uid)
);

-- Organizations table
CREATE TABLE IF NOT EXISTS organizations (
    organization_uid TEXT PRIMARY KEY,
    organization_name TEXT,
    netsuite_customer_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sync log
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_started_at TIMESTAMP,
    sync_completed_at TIMESTAMP,
    jobs_processed INTEGER,
    flags_created INTEGER,
    errors TEXT,
    status TEXT DEFAULT 'in_progress'
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_completed ON jobs(completed_at);
CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(job_category);
CREATE INDEX IF NOT EXISTS idx_jobs_service_team ON jobs(service_team);
CREATE INDEX IF NOT EXISTS idx_jobs_has_line_items ON jobs(has_line_items);
CREATE INDEX IF NOT EXISTS idx_jobs_has_netsuite ON jobs(has_netsuite_id);
CREATE INDEX IF NOT EXISTS idx_jobs_organization ON jobs(organization_uid);
CREATE INDEX IF NOT EXISTS idx_line_items_job ON job_line_items(job_uid);
CREATE INDEX IF NOT EXISTS idx_line_items_serial ON job_line_items(item_serial);
CREATE INDEX IF NOT EXISTS idx_checklist_job ON job_checklist_parts(job_uid);
CREATE INDEX IF NOT EXISTS idx_checklist_serial ON job_checklist_parts(part_serial);
CREATE INDEX IF NOT EXISTS idx_checklist_text_job ON job_checklist_text(job_uid);
CREATE INDEX IF NOT EXISTS idx_flags_job ON validation_flags(job_uid);
CREATE INDEX IF NOT EXISTS idx_flags_type ON validation_flags(flag_type, is_resolved);
CREATE INDEX IF NOT EXISTS idx_organizations_netsuite ON organizations(netsuite_customer_id);

-- Validation summary view
CREATE VIEW IF NOT EXISTS job_validation_summary AS
SELECT
    j.job_uid,
    j.job_number,
    j.job_title,
    j.customer_name,
    j.created_at,
    j.has_line_items,
    j.has_checklist_parts,
    j.has_netsuite_id,
    j.netsuite_sales_order_id,
    j.jira_link,
    j.slack_link,
    COUNT(DISTINCT li.id) as line_items_count,
    COUNT(DISTINCT cp.id) as checklist_parts_count,
    COUNT(DISTINCT CASE WHEN vf.is_resolved = 0 THEN vf.id END) as active_flags_count,
    MAX(CASE WHEN vf.flag_type = 'missing_netsuite_id' AND vf.is_resolved = 0 THEN 1 ELSE 0 END) as has_missing_netsuite_flag,
    MAX(CASE WHEN vf.flag_type = 'line_item_mismatch' AND vf.is_resolved = 0 THEN 1 ELSE 0 END) as has_mismatch_flag,
    GROUP_CONCAT(DISTINCT CASE WHEN vf.is_resolved = 0 THEN vf.flag_message END, ' | ') as flag_messages
FROM jobs j
LEFT JOIN job_line_items li ON j.job_uid = li.job_uid
LEFT JOIN job_checklist_parts cp ON j.job_uid = cp.job_uid
LEFT JOIN validation_flags vf ON j.job_uid = vf.job_uid
GROUP BY j.job_uid;
