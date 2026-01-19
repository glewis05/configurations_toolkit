-- ============================================================================
-- CONFIGURATIONS TOOLKIT SCHEMA
-- Extends Client Product Database with configuration tracking
--
-- PURPOSE: Store and manage system configurations with inheritance
--
-- R EQUIVALENT: Like a hierarchical config list where child elements
-- inherit from parents unless explicitly overridden
--
-- AVIATION ANALOGY: Like aircraft configuration sheets that inherit
-- from type certificate defaults but can be overridden per tail number
-- ============================================================================

-- ----------------------------------------------------------------------------
-- BASE TABLES (shared with Requirements Toolkit)
-- These tables are created here if they don't exist, allowing standalone use
-- ----------------------------------------------------------------------------

-- Clients table (top-level organizations)
CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'Active',
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Programs table (projects under clients)
CREATE TABLE IF NOT EXISTS programs (
    program_id TEXT PRIMARY KEY,
    client_id TEXT,
    name TEXT NOT NULL,
    prefix TEXT UNIQUE,
    description TEXT,
    program_type TEXT DEFAULT 'clinic_based',
    status TEXT DEFAULT 'Active',
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(client_id)
);

-- Audit history table (shared audit trail)
CREATE TABLE IF NOT EXISTS audit_history (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    action TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by TEXT DEFAULT 'system',
    changed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    change_reason TEXT
);

-- Index for audit lookups
CREATE INDEX IF NOT EXISTS idx_audit_record ON audit_history(record_type, record_id);
CREATE INDEX IF NOT EXISTS idx_audit_date ON audit_history(changed_date);

-- ----------------------------------------------------------------------------
-- PROGRAM RELATIONSHIPS
-- For attached programs (like Discover eConsent) that link to multiple programs
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS program_relationships (
    relationship_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- The main program (e.g., Prevention4ME)
    parent_program_id TEXT NOT NULL,

    -- The attached/shared program (e.g., Discover eConsent)
    attached_program_id TEXT NOT NULL,

    -- How the programs are related
    -- 'uses': parent uses attached service
    -- 'requires': parent requires attached service
    -- 'optional': attached service is optional for parent
    relationship_type TEXT DEFAULT 'uses',

    -- Audit fields
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT DEFAULT 'system',

    -- Foreign keys to programs table (in shared database)
    FOREIGN KEY (parent_program_id) REFERENCES programs(program_id),
    FOREIGN KEY (attached_program_id) REFERENCES programs(program_id),

    -- Each parent can only have one relationship to each attached program
    UNIQUE(parent_program_id, attached_program_id)
);

-- ----------------------------------------------------------------------------
-- CLINICS
-- Organizations/sites under a program (e.g., Portland, Providence)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS clinics (
    clinic_id TEXT PRIMARY KEY,

    -- Parent program (FK to programs table in shared database)
    program_id TEXT NOT NULL,

    -- Clinic identification
    name TEXT NOT NULL,                    -- Full name: "Portland Cancer Institute"
    code TEXT,                             -- Short code: "PORT" or "PCI"
    description TEXT,                      -- Optional description

    -- Status tracking
    status TEXT DEFAULT 'Active',          -- 'Active', 'Inactive', 'Onboarding', 'Archived'

    -- Audit fields
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT DEFAULT 'system',

    FOREIGN KEY (program_id) REFERENCES programs(program_id)
);

-- ----------------------------------------------------------------------------
-- LOCATIONS
-- Physical locations/service points under a clinic
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS locations (
    location_id TEXT PRIMARY KEY,

    -- Parent clinic
    clinic_id TEXT NOT NULL,

    -- Location identification
    name TEXT NOT NULL,                    -- "PCI Breast Surgery West"
    code TEXT,                             -- Service location code: "4000045001"
    address TEXT,                          -- Physical address

    -- Status tracking
    status TEXT DEFAULT 'Active',          -- 'Active', 'Inactive', 'Archived'

    -- Audit fields
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT DEFAULT 'system',

    FOREIGN KEY (clinic_id) REFERENCES clinics(clinic_id)
);

-- ----------------------------------------------------------------------------
-- CONFIGURATION DEFINITIONS
-- Schema for all possible configurations (what CAN be configured)
--
-- AVIATION ANALOGY: Like the aircraft configuration options in the
-- Type Certificate Data Sheet - defines what's configurable
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS config_definitions (
    config_key TEXT PRIMARY KEY,           -- Unique key: "helpdesk_phone"

    -- Categorization
    category TEXT NOT NULL,                -- Group: 'appointment_extract', 'invitation', etc.
    display_name TEXT NOT NULL,            -- Human-readable: "Helpdesk Phone Number"
    description TEXT,                      -- Detailed description

    -- Data type and validation
    data_type TEXT NOT NULL,               -- 'text', 'number', 'boolean', 'json', 'phone', 'email', 'time'
    allowed_values TEXT,                   -- JSON array for dropdowns: '["Saliva", "Blood"]'
    default_value TEXT,                    -- Program global default
    validation_regex TEXT,                 -- Optional regex for validation

    -- Inheritance and editability
    applies_to TEXT NOT NULL,              -- 'program', 'clinic', 'location', 'all'
    is_required BOOLEAN DEFAULT FALSE,     -- Must have a value?
    is_clinic_editable BOOLEAN DEFAULT FALSE,  -- Can clinics edit in future portal?

    -- Display
    display_order INTEGER DEFAULT 0,       -- Order within category

    -- Audit
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- CONFIGURATION VALUES
-- Actual configuration values at each level with inheritance tracking
--
-- KEY CONCEPT: Inheritance flows Program → Clinic → Location
-- A NULL clinic_id means it's a program-level value
-- A NULL location_id means it's a clinic-level value (or program if clinic is also NULL)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS config_values (
    value_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Which config this is for
    config_key TEXT NOT NULL,

    -- Where this value applies (hierarchy)
    program_id TEXT NOT NULL,              -- Always required
    clinic_id TEXT,                        -- NULL = program-level value
    location_id TEXT,                      -- NULL = clinic-level or program-level

    -- The actual value (stored as text, parsed according to data_type)
    value TEXT,

    -- Inheritance tracking
    is_override BOOLEAN DEFAULT FALSE,     -- TRUE if overriding parent level

    -- Provenance tracking (important for audits)
    source TEXT,                           -- 'default', 'import', 'manual', 'clinic_portal'
    source_document TEXT,                  -- e.g., "Portland_Clinic_Spec_Dev_Final.docx"
    rationale TEXT,                        -- Why this value was set

    -- Effective dates (for future-dated configs)
    effective_date DATE,                   -- When this config takes effect
    expiry_date DATE,                      -- Optional expiry date

    -- Version tracking
    version INTEGER DEFAULT 1,

    -- Audit fields
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT DEFAULT 'system',

    -- Foreign keys
    FOREIGN KEY (config_key) REFERENCES config_definitions(config_key),
    FOREIGN KEY (program_id) REFERENCES programs(program_id),
    FOREIGN KEY (clinic_id) REFERENCES clinics(clinic_id),
    FOREIGN KEY (location_id) REFERENCES locations(location_id),

    -- Only one value per config per level (program/clinic/location combination)
    UNIQUE(config_key, program_id, clinic_id, location_id)
);

-- ----------------------------------------------------------------------------
-- PROVIDERS
-- Healthcare providers associated with locations
-- Separate table for easier updates (NPIs change, providers move, etc.)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS providers (
    provider_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Location this provider is associated with
    location_id TEXT NOT NULL,

    -- Provider info
    name TEXT NOT NULL,                    -- "Christine Kemp, NP"
    npi TEXT,                              -- National Provider Identifier
    role TEXT,                             -- 'Ordering Provider', 'Supervising', 'Attending'
    specialty TEXT,                        -- 'Breast Surgery', 'Oncology', etc.

    -- Status
    is_active BOOLEAN DEFAULT TRUE,        -- Soft delete - set to FALSE instead of deleting

    -- Audit fields
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT DEFAULT 'system',
    deactivated_date TIMESTAMP,            -- When provider was deactivated
    deactivation_reason TEXT,              -- Why provider was deactivated

    FOREIGN KEY (location_id) REFERENCES locations(location_id)
);

-- ----------------------------------------------------------------------------
-- APPOINTMENT TYPES
-- Types of appointments for filtering (can vary by location)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS appointment_types (
    appointment_type_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Location this applies to
    location_id TEXT NOT NULL,

    -- Appointment type info
    type_code TEXT,                        -- Code from EHR system
    type_name TEXT NOT NULL,               -- Human-readable name

    -- Whether to include in extract filter
    is_included BOOLEAN DEFAULT TRUE,

    -- Audit fields
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (location_id) REFERENCES locations(location_id)
);

-- ----------------------------------------------------------------------------
-- CONFIG HISTORY
-- Tracks all changes to config_values for audit trail
-- Supplements the generic audit_history table with config-specific detail
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS config_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- What changed
    config_key TEXT NOT NULL,
    program_id TEXT NOT NULL,
    clinic_id TEXT,
    location_id TEXT,

    -- The change
    old_value TEXT,
    new_value TEXT,

    -- Who and when
    changed_by TEXT DEFAULT 'system',
    changed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Why
    change_reason TEXT,
    source_document TEXT,

    FOREIGN KEY (config_key) REFERENCES config_definitions(config_key)
);

-- ============================================================================
-- INDEXES
-- Optimize common query patterns
-- ============================================================================

-- Hierarchy traversal
CREATE INDEX IF NOT EXISTS idx_clinics_program ON clinics(program_id);
CREATE INDEX IF NOT EXISTS idx_locations_clinic ON locations(clinic_id);
CREATE INDEX IF NOT EXISTS idx_providers_location ON providers(location_id);
CREATE INDEX IF NOT EXISTS idx_appointment_types_location ON appointment_types(location_id);

-- Config lookups
CREATE INDEX IF NOT EXISTS idx_config_values_key ON config_values(config_key);
CREATE INDEX IF NOT EXISTS idx_config_values_program ON config_values(program_id);
CREATE INDEX IF NOT EXISTS idx_config_values_clinic ON config_values(clinic_id);
CREATE INDEX IF NOT EXISTS idx_config_values_location ON config_values(location_id);
CREATE INDEX IF NOT EXISTS idx_config_defs_category ON config_definitions(category);

-- Composite index for inheritance queries (covers WHERE program_id=? AND clinic_id=? AND location_id=?)
-- AVIATION ANALOGY: Like a multi-column flight log index - faster to look up by
-- aircraft + date + route than three separate indexes
CREATE INDEX IF NOT EXISTS idx_config_values_hierarchy
ON config_values(program_id, clinic_id, location_id, config_key);

-- Program relationships
CREATE INDEX IF NOT EXISTS idx_program_rel_parent ON program_relationships(parent_program_id);
CREATE INDEX IF NOT EXISTS idx_program_rel_attached ON program_relationships(attached_program_id);

-- History lookups
CREATE INDEX IF NOT EXISTS idx_config_history_key ON config_history(config_key);
CREATE INDEX IF NOT EXISTS idx_config_history_date ON config_history(changed_date);

-- Status filters
CREATE INDEX IF NOT EXISTS idx_clinics_status ON clinics(status);
CREATE INDEX IF NOT EXISTS idx_locations_status ON locations(status);
CREATE INDEX IF NOT EXISTS idx_providers_active ON providers(is_active);

-- Provider uniqueness - prevent duplicate providers at same location
-- A provider should only appear once per location (based on name + location)
-- Note: NPI alone isn't sufficient since same provider can work at multiple locations
CREATE UNIQUE INDEX IF NOT EXISTS idx_providers_unique_name_location
ON providers(location_id, name) WHERE is_active = TRUE;

-- ============================================================================
-- VIEWS
-- Common query patterns as reusable views
-- ============================================================================

-- View: Full hierarchy with counts
CREATE VIEW IF NOT EXISTS v_program_hierarchy AS
SELECT
    p.program_id,
    p.name AS program_name,
    p.prefix,
    p.program_type,
    c.clinic_id,
    c.name AS clinic_name,
    c.status AS clinic_status,
    l.location_id,
    l.name AS location_name,
    l.code AS location_code,
    l.status AS location_status,
    (SELECT COUNT(*) FROM providers pr WHERE pr.location_id = l.location_id AND pr.is_active = TRUE) AS active_providers
FROM programs p
LEFT JOIN clinics c ON c.program_id = p.program_id
LEFT JOIN locations l ON l.clinic_id = c.clinic_id;

-- View: Config values with inheritance info
CREATE VIEW IF NOT EXISTS v_config_effective AS
SELECT
    cd.config_key,
    cd.category,
    cd.display_name,
    cd.data_type,
    cd.default_value,
    cd.applies_to,
    cv.program_id,
    cv.clinic_id,
    cv.location_id,
    cv.value,
    cv.is_override,
    cv.source,
    cv.source_document,
    CASE
        WHEN cv.location_id IS NOT NULL THEN 'location'
        WHEN cv.clinic_id IS NOT NULL THEN 'clinic'
        WHEN cv.program_id IS NOT NULL THEN 'program'
        ELSE 'default'
    END AS value_level
FROM config_definitions cd
LEFT JOIN config_values cv ON cd.config_key = cv.config_key;

-- View: Attached programs summary
CREATE VIEW IF NOT EXISTS v_attached_programs AS
SELECT
    pr.relationship_id,
    parent.program_id AS parent_id,
    parent.name AS parent_name,
    parent.prefix AS parent_prefix,
    attached.program_id AS attached_id,
    attached.name AS attached_name,
    attached.prefix AS attached_prefix,
    pr.relationship_type,
    pr.created_date
FROM program_relationships pr
JOIN programs parent ON parent.program_id = pr.parent_program_id
JOIN programs attached ON attached.program_id = pr.attached_program_id;

-- View: Provider roster by location
CREATE VIEW IF NOT EXISTS v_provider_roster AS
SELECT
    p.name AS program_name,
    c.name AS clinic_name,
    l.name AS location_name,
    pr.name AS provider_name,
    pr.npi,
    pr.role,
    pr.specialty,
    pr.is_active
FROM providers pr
JOIN locations l ON l.location_id = pr.location_id
JOIN clinics c ON c.clinic_id = l.clinic_id
JOIN programs p ON p.program_id = c.program_id
ORDER BY p.name, c.name, l.name, pr.name;
