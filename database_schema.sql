-- Zuper-NetSuite Monitoring Database Schema

-- Organizations table
CREATE TABLE IF NOT EXISTS organizations (
    organization_uid TEXT PRIMARY KEY,
    organization_name TEXT NOT NULL,
    organization_email TEXT,
    organization_description TEXT,
    no_of_customers INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    is_portal_enabled BOOLEAN DEFAULT 0,
    is_deleted BOOLEAN DEFAULT 0,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Custom fields table
CREATE TABLE IF NOT EXISTS organization_custom_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_uid TEXT NOT NULL,
    field_label TEXT NOT NULL,
    field_value TEXT,
    field_type TEXT,
    hide_to_fe BOOLEAN DEFAULT 0,
    hide_field BOOLEAN DEFAULT 0,
    read_only BOOLEAN DEFAULT 0,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_uid) REFERENCES organizations(organization_uid),
    UNIQUE(organization_uid, field_label)
);

-- NetSuite mapping view (convenience view)
CREATE VIEW IF NOT EXISTS netsuite_mapping AS
SELECT
    o.organization_uid,
    o.organization_name,
    o.organization_email,
    o.no_of_customers,
    o.is_active,
    o.created_at,
    o.updated_at,
    MAX(CASE WHEN cf.field_label = 'Netsuite Customer ID' THEN cf.field_value END) as netsuite_customer_id,
    MAX(CASE WHEN cf.field_label = 'External ID' THEN cf.field_value END) as external_id,
    MAX(CASE WHEN cf.field_label = 'HubSpot Company ID' THEN cf.field_value END) as hubspot_company_id,
    MAX(CASE WHEN cf.field_label = 'Netsuite Internal ID' THEN cf.field_value END) as netsuite_internal_id,
    CASE
        WHEN MAX(CASE WHEN cf.field_label = 'Netsuite Customer ID' THEN cf.field_value END) IS NOT NULL
        AND LENGTH(TRIM(MAX(CASE WHEN cf.field_label = 'Netsuite Customer ID' THEN cf.field_value END))) > 0
        THEN 1
        ELSE 0
    END as has_netsuite_id
FROM organizations o
LEFT JOIN organization_custom_fields cf ON o.organization_uid = cf.organization_uid
GROUP BY o.organization_uid;

-- Sync log table to track API syncs
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_started_at TIMESTAMP,
    sync_completed_at TIMESTAMP,
    organizations_fetched INTEGER,
    organizations_updated INTEGER,
    organizations_created INTEGER,
    errors TEXT,
    status TEXT DEFAULT 'in_progress'
);

-- Alerts table for tracking missing NetSuite IDs
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_uid TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    alert_message TEXT,
    is_resolved BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    FOREIGN KEY (organization_uid) REFERENCES organizations(organization_uid)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_org_active ON organizations(is_active);
CREATE INDEX IF NOT EXISTS idx_org_created ON organizations(created_at);
CREATE INDEX IF NOT EXISTS idx_custom_field_label ON organization_custom_fields(field_label);
CREATE INDEX IF NOT EXISTS idx_custom_field_value ON organization_custom_fields(field_value);
CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON alerts(is_resolved);
CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type);
