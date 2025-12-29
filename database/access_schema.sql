-- ============================================================================
-- ACCESS MANAGEMENT SCHEMA
-- ============================================================================
-- Purpose: Track user access for Part 11, HIPAA, and SOC 2 compliance
--
-- Compliance Framework Coverage:
--   Part 11:  Unique user IDs, authority checks, electronic signatures
--   HIPAA:    Minimum necessary access, termination procedures, workforce training, BAA tracking
--   SOC 2:    Access provisioning, periodic reviews, segregation of duties
--
-- Tables:
--   users          - People who may have system access
--   user_access    - Specific access grants (who has access to what)
--   access_reviews - Periodic recertification history (SOC 2)
--   user_training  - HIPAA workforce training records
--   role_conflicts - Segregation of duties rules
--
-- Aviation Analogy:
--   Think of this like aviation crew certification tracking:
--   - users = crew members with their ratings
--   - user_access = type ratings (what aircraft they can fly)
--   - access_reviews = recurrent training/check rides
--   - user_training = ground school certificates
--   - role_conflicts = crew resource management rules (captain can't also be ATC)
-- ============================================================================


-- ============================================================================
-- USERS TABLE
-- ============================================================================
-- Who may have system access. Every person gets a unique user_id (Part 11).
-- Business associates are flagged for HIPAA BAA tracking.
--
-- Note: user_id is TEXT to allow meaningful IDs like "JSMITH-A1B2C3"
-- rather than opaque integers. This helps with audit log readability.
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    -- Primary identifier - must be unique per Part 11
    -- Format: First initial + last name + random suffix, e.g., "JSMITH-A1B2C3"
    user_id TEXT PRIMARY KEY,

    -- Full name for display and audit trails
    name TEXT NOT NULL,

    -- Email address - unique identifier for login
    -- Can be NULL for users without email (rare, but possible for external BA contacts)
    email TEXT UNIQUE,

    -- Organization name
    -- 'Internal' for employees, company name for external users (Business Associates)
    organization TEXT DEFAULT 'Internal',

    -- HIPAA: Flag for Business Associate Agreement tracking
    -- TRUE = external party with BAA, needs heightened monitoring
    is_business_associate BOOLEAN DEFAULT FALSE,

    -- User status for lifecycle management
    -- Active = current employee/contractor with access rights
    -- Inactive = temporarily disabled (leave of absence, investigation)
    -- Terminated = permanently disabled, all access should be revoked
    status TEXT DEFAULT 'Active' CHECK (status IN ('Active', 'Inactive', 'Terminated')),

    -- Audit timestamps
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Free-text notes for context (e.g., "Contractor through 2025-06-30")
    notes TEXT
);


-- ============================================================================
-- USER ACCESS TABLE
-- ============================================================================
-- Specific access grants: who has access to what scope with what role.
-- This is the core table for access control and SOC 2 provisioning audits.
--
-- Scope Hierarchy:
--   program_id only         = Access to entire program (all clinics, all locations)
--   program_id + clinic_id  = Access to one clinic (all locations within)
--   program_id + clinic_id + location_id = Access to one specific location
--
-- Role Hierarchy (from most to least privileged):
--   Admin      = Full control, can modify configs and grant access
--   Provider   = Clinical access, can view patient-related configs
--   Coordinator = Operational access, can update scheduling/contact info
--   Read-Only  = View only, cannot modify anything
--   Auditor    = Special access for compliance audits
--
-- Note: is_active allows soft-delete pattern - we never hard-delete access records
-- because audit trails require knowing what access was revoked and when.
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_access (
    -- Auto-generated primary key
    access_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Foreign key to users table
    -- NOT NULL because every access grant must be associated with a user
    user_id TEXT NOT NULL,

    -- Scope: What can this user access?
    -- program_id is always required (minimum scope)
    program_id TEXT NOT NULL,

    -- clinic_id NULL = all clinics in program
    -- clinic_id set = only that clinic (and locations within if location_id is NULL)
    clinic_id TEXT,

    -- location_id NULL = all locations in clinic (or program if clinic is also NULL)
    -- location_id set = only that specific location
    location_id TEXT,

    -- Role defines what the user can DO within their scope
    -- Read-Only: View only, single clinic scope
    -- Read-Write: View + Edit, single clinic scope
    -- Read-Write-Order: View + Edit + Order Tests, single clinic scope
    -- Clinic-Manager: View + Edit + Order Tests + Analytics, single clinic scope
    -- Analytics-Only: Aggregated analytics only, cross-clinic scope (no patient data)
    -- Admin: View + Edit + Analytics, cross-clinic scope (system-level)
    -- Auditor: Audit/compliance access
    role TEXT NOT NULL CHECK (role IN (
        'Read-Only', 'Read-Write', 'Read-Write-Order', 'Clinic-Manager',
        'Analytics-Only', 'Admin', 'Auditor'
    )),

    -- JSON array of specific permissions if granular control needed
    -- Example: ["view_configs", "edit_providers", "run_reports"]
    -- NULL means use default permissions for the role
    permissions TEXT,

    -- Grant metadata (required for SOC 2 provisioning audit)
    granted_date DATE NOT NULL,
    granted_by TEXT NOT NULL,
    grant_reason TEXT,
    grant_ticket TEXT,  -- Reference to approval ticket, email, or ServiceNow ID

    -- Revocation metadata (populated when access is revoked)
    revoked_date DATE,
    revoked_by TEXT,
    revoke_reason TEXT,

    -- Soft-delete flag - FALSE means access was revoked
    -- We keep revoked records for audit trail
    is_active BOOLEAN DEFAULT TRUE,

    -- SOC 2: Periodic review schedule
    -- Quarterly = review every 90 days (higher risk roles)
    -- Annual = review once per year (lower risk roles)
    review_cycle TEXT DEFAULT 'Quarterly' CHECK (review_cycle IN ('Quarterly', 'Annual')),

    -- Next scheduled review date (calculated from review_cycle)
    -- Compliance reports flag overdue reviews
    next_review_due DATE,

    -- Audit timestamps
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key constraints
    -- Note: These reference tables from the main config_schema.sql
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (program_id) REFERENCES programs(program_id),
    FOREIGN KEY (clinic_id) REFERENCES clinics(clinic_id),
    FOREIGN KEY (location_id) REFERENCES locations(location_id)
);


-- ============================================================================
-- ACCESS REVIEWS TABLE
-- ============================================================================
-- History of periodic access reviews (SOC 2 recertification).
-- Every access grant should be reviewed on schedule (quarterly or annual).
--
-- Review Workflow:
-- 1. Compliance officer exports worksheet of access due for review
-- 2. Managers review each access grant with their direct reports
-- 3. For each grant, decide: Certified (keep), Revoked (remove), or Modified (change)
-- 4. Import completed worksheet to record reviews
--
-- This creates an audit trail proving access is reviewed regularly.
-- ============================================================================

CREATE TABLE IF NOT EXISTS access_reviews (
    -- Auto-generated primary key
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Foreign key to the access grant being reviewed
    access_id INTEGER NOT NULL,

    -- When the review was conducted
    review_date DATE NOT NULL,

    -- Who conducted the review (usually manager or compliance officer)
    reviewed_by TEXT NOT NULL,

    -- Review decision
    -- Certified = Access confirmed as still needed, schedule next review
    -- Revoked = Access no longer needed, revoke immediately
    -- Modified = Access scope or role changed, update accordingly
    status TEXT NOT NULL CHECK (status IN ('Certified', 'Revoked', 'Modified')),

    -- Reviewer notes explaining the decision
    -- Important for audit: "Confirmed with manager Jane Doe" or "User transferred to new dept"
    notes TEXT,

    -- Next review date (calculated based on review_cycle when Certified)
    -- NULL if Revoked (no future review needed)
    next_review_due DATE,

    -- Audit timestamp
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key constraint
    FOREIGN KEY (access_id) REFERENCES user_access(access_id)
);


-- ============================================================================
-- USER TRAINING TABLE
-- ============================================================================
-- Track HIPAA workforce training and other required compliance training.
--
-- Training Types:
--   ACTIVE (currently in use):
--     HIPAA               - Consolidated annual HIPAA Privacy & Security training
--     Cybersecurity       - Annual cybersecurity awareness training
--     Application Training - Product-specific application training
--
--   RESERVED (for future use):
--     SOC 2    - SOC 2 compliance training
--     HITRUST  - HITRUST certification training
--     Part 11  - FDA 21 CFR Part 11 training
--
-- Training Responsibility:
--   Client       - Client organization maintains their own training records
--   Propel Health - PHP maintains training records internally
--
-- Lifecycle:
--   Pending  = Training assigned but not yet completed
--   Current  = Training completed and not expired
--   Expired  = Training completion date has passed (needs renewal)
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_training (
    -- Auto-generated primary key
    training_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Foreign key to users table
    user_id TEXT NOT NULL,

    -- Type of training
    -- Active: HIPAA, Cybersecurity, Application Training
    -- Reserved: SOC 2, HITRUST, Part 11
    training_type TEXT NOT NULL CHECK (
        training_type IN ('HIPAA', 'Cybersecurity', 'Application Training',
                          'SOC 2', 'HITRUST', 'Part 11')
    ),

    -- Who maintains the training records
    -- Client = Client organization tracks their own employee training
    -- Propel Health = PHP maintains training records internally
    responsibility TEXT DEFAULT 'Propel Health' CHECK (
        responsibility IN ('Client', 'Propel Health')
    ),

    -- When training was completed (NULL if still pending)
    completed_date DATE,

    -- When training expires (typically 1 year from completion for HIPAA)
    expires_date DATE,

    -- Reference to certificate or LMS completion record
    -- Could be: LMS course ID, certificate number, or document path
    certificate_reference TEXT,

    -- Training status
    -- Pending = assigned but not completed
    -- Current = completed and not expired
    -- Expired = past expires_date, needs renewal
    status TEXT DEFAULT 'Pending' CHECK (status IN ('Pending', 'Current', 'Expired')),

    -- Assignment metadata
    assigned_date DATE,
    assigned_by TEXT,

    -- Audit timestamps
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key constraint
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);


-- ============================================================================
-- ROLE CONFLICTS TABLE
-- ============================================================================
-- Segregation of Duties rules (SOC 2 requirement).
-- Defines which role combinations are prohibited or flagged.
--
-- Severity Levels:
--   Block   = Cannot grant this combination, system will reject
--   Warning = Can grant but flags for compliance review
--
-- Example Conflicts:
--   Admin + Auditor    = Block - Can't audit your own admin actions
--   Data Entry + Approver = Warning - Ideally separate, but may be necessary
--
-- Aviation Analogy:
--   Like how a pilot can't also be the mechanic signing off their own aircraft,
--   or how ATC and flight crew must be separate roles for safety.
-- ============================================================================

CREATE TABLE IF NOT EXISTS role_conflicts (
    -- Auto-generated primary key
    conflict_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- The two roles that conflict
    role_a TEXT NOT NULL,
    role_b TEXT NOT NULL,

    -- Why this combination is problematic
    conflict_reason TEXT,

    -- How to handle the conflict
    -- Block = Prevent the grant entirely
    -- Warning = Allow but flag for review
    severity TEXT DEFAULT 'Warning' CHECK (severity IN ('Warning', 'Block')),

    -- Audit timestamp
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================================
-- DEFAULT ROLE CONFLICTS
-- ============================================================================
-- Insert standard segregation of duties rules.
-- OR IGNORE prevents duplicates on re-runs.
-- ============================================================================

INSERT OR IGNORE INTO role_conflicts (role_a, role_b, conflict_reason, severity) VALUES
    -- Admin should not audit their own work (fundamental SOC 2 requirement)
    ('Admin', 'Auditor', 'Administrator should not audit their own administrative actions', 'Block'),

    -- Data entry and approval should be separate when possible
    ('Data Entry', 'Approver', 'Segregation of data entry and approval functions', 'Warning'),

    -- Provider and Admin is a common conflict in healthcare IT
    -- Providers shouldn't be admins for systems containing their own records
    ('Provider', 'Admin', 'Clinical users should not have administrative privileges on clinical systems', 'Warning');


-- ============================================================================
-- INDEXES
-- ============================================================================
-- Indexes for common query patterns to improve performance.
-- Named with idx_ prefix for consistency with existing schema.
-- ============================================================================

-- User lookups by status and email
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_organization ON users(organization);

-- Access lookups by user, scope, and status
CREATE INDEX IF NOT EXISTS idx_user_access_user ON user_access(user_id);
CREATE INDEX IF NOT EXISTS idx_user_access_program ON user_access(program_id);
CREATE INDEX IF NOT EXISTS idx_user_access_clinic ON user_access(clinic_id);
CREATE INDEX IF NOT EXISTS idx_user_access_location ON user_access(location_id);
CREATE INDEX IF NOT EXISTS idx_user_access_active ON user_access(is_active);
CREATE INDEX IF NOT EXISTS idx_user_access_role ON user_access(role);

-- Critical: Index for finding overdue reviews quickly
-- This query runs frequently for compliance dashboards
CREATE INDEX IF NOT EXISTS idx_user_access_review_due ON user_access(next_review_due);

-- Review history lookup by access grant
CREATE INDEX IF NOT EXISTS idx_access_reviews_access ON access_reviews(access_id);
CREATE INDEX IF NOT EXISTS idx_access_reviews_date ON access_reviews(review_date);

-- Training lookups by user and status
CREATE INDEX IF NOT EXISTS idx_user_training_user ON user_training(user_id);
CREATE INDEX IF NOT EXISTS idx_user_training_status ON user_training(status);
CREATE INDEX IF NOT EXISTS idx_user_training_type ON user_training(training_type);
CREATE INDEX IF NOT EXISTS idx_user_training_expires ON user_training(expires_date);


-- ============================================================================
-- VIEWS (Optional - for common queries)
-- ============================================================================

-- Active users with their access count
CREATE VIEW IF NOT EXISTS v_user_access_summary AS
SELECT
    u.user_id,
    u.name,
    u.email,
    u.organization,
    u.is_business_associate,
    u.status,
    COUNT(CASE WHEN ua.is_active = 1 THEN 1 END) as active_access_count,
    MIN(ua.next_review_due) as next_review_due
FROM users u
LEFT JOIN user_access ua ON u.user_id = ua.user_id
GROUP BY u.user_id;


-- Access grants due for review
CREATE VIEW IF NOT EXISTS v_reviews_due AS
SELECT
    ua.access_id,
    u.user_id,
    u.name as user_name,
    u.email,
    ua.program_id,
    c.name as clinic_name,
    l.name as location_name,
    ua.role,
    ua.granted_date,
    ua.next_review_due,
    julianday('now') - julianday(ua.next_review_due) as days_overdue
FROM user_access ua
JOIN users u ON ua.user_id = u.user_id
LEFT JOIN clinics c ON ua.clinic_id = c.clinic_id
LEFT JOIN locations l ON ua.location_id = l.location_id
WHERE ua.is_active = 1
  AND ua.next_review_due <= date('now')
ORDER BY ua.next_review_due ASC;


-- Expired or expiring training
CREATE VIEW IF NOT EXISTS v_training_status AS
SELECT
    ut.training_id,
    u.user_id,
    u.name as user_name,
    u.email,
    ut.training_type,
    ut.status,
    ut.completed_date,
    ut.expires_date,
    CASE
        WHEN ut.expires_date IS NULL THEN NULL
        WHEN ut.expires_date < date('now') THEN 'Expired'
        WHEN ut.expires_date < date('now', '+30 days') THEN 'Expiring Soon'
        ELSE 'Current'
    END as expiry_status,
    julianday(ut.expires_date) - julianday('now') as days_until_expiry
FROM user_training ut
JOIN users u ON ut.user_id = u.user_id
WHERE u.status = 'Active'
ORDER BY ut.expires_date ASC;
