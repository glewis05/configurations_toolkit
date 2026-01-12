# Configurations Toolkit

Manages system configurations for clinic onboarding and ongoing updates with inheritance support across Program → Clinic → Location hierarchy.

## Project Purpose

This toolkit:
- Parses clinic specification Word documents to extract configuration settings
- Manages configurations with inheritance (child levels inherit from parents unless overridden)
- Tracks all changes for audit trail (FDA 21 CFR Part 11 compliance)
- Provides easy update methods for common operations (NPIs, phone numbers, test codes)
- Exports configurations to formatted Excel reports

## Owner Context
- Solo developer (no separate front-end/back-end team)
- Familiar with R, learning Python — explain Python concepts with R comparisons where helpful
- Aviation background — aviation analogies work well for complex concepts
- Prefers detailed explanations with heavy inline comments

## Database Architecture

### Unified Database Design

All Propel Health toolkits share a **single unified database**:

| Location | Toolkits | Purpose |
|----------|----------|---------|
| `~/projects/data/client_product_database.db` | All | Requirements, configurations, UAT, access management |

Other toolkits use **symlinks** to access this database:
- `~/projects/requirements_toolkit/data/client_product_database.db` → unified DB
- `~/projects/uat_toolkit/data/client_product_database.db` → unified DB

**Why unified?**
- Programs are the central entity connecting requirements AND configurations
- All programs have requirements (features, user stories)
- All programs have configurations (helpdesk info, settings)
- Some programs have clinics with clinic-specific configurations
- Single source of truth for audit trail

### Configuration Tables (this toolkit manages)
- `clinics`, `locations` - Clinic hierarchy under programs
- `config_definitions`, `config_values` - Configuration settings with inheritance
- `providers`, `appointment_types` - Clinical data
- `users`, `user_access`, `access_reviews` - Access management
- `config_history` - Configuration change tracking

### Shared Tables
- `programs` - All programs (P4M, Px4M, ONB, etc.) - shared with all toolkits
- `clients` - Client organizations
- `audit_history` - Unified audit trail for compliance

### Requirements Tables (requirements_toolkit manages)
- `requirements`, `user_stories` - What to build
- `uat_test_cases`, `uat_cycles` - Testing (UAT toolkit extends)
- `traceability`, `compliance_gaps` - Coverage tracking

### MCP Server Integration
The `propel_mcp` server connects to the unified database for all operations.

## Code Standards

### Python Style
- Heavy inline comments explaining WHY, not just WHAT
- Every function needs a docstring with:
  - PURPOSE: What it does
  - R EQUIVALENT: Comparable R function/approach (when applicable)
  - PARAMETERS: Each param with type and example
  - RETURNS: What comes back, with example
  - WHY THIS APPROACH: Reasoning behind implementation choices
- Use type hints for function signatures
- Prefer explicit over clever — readability beats brevity

### File Organization
```
configurations_toolkit/
├── run.py                      # CLI entry point
├── CLAUDE.md                   # This file
├── config/
│   └── config_definitions.yaml # All configurable fields defined here
├── database/
│   ├── config_schema.sql       # Configuration tables schema
│   └── config_manager.py       # CRUD operations with inheritance
├── parsers/
│   └── word_parser.py          # Parse Word clinic spec documents
├── managers/
│   ├── inheritance_manager.py  # Handle inheritance resolution
│   └── update_manager.py       # Easy updates for providers, tests, etc.
├── formatters/
│   └── config_excel_formatter.py  # Export configs to Excel
├── inputs/                     # Drop Word docs to process
└── outputs/                    # Generated Excel exports
```

## Program Types

- **standalone**: No clinic/location hierarchy (e.g., internal tools)
- **clinic_based**: Full hierarchy Program → Clinic → Location (e.g., Prevention4ME, GenoRx)
- **attached**: Shared service linked to other programs (e.g., Discover eConsent)

## Inheritance Model

```
                    ┌─────────────────┐
                    │  config_definitions  │  (default values)
                    └─────────┬───────┘
                              │ inherits
                    ┌─────────▼───────┐
                    │     PROGRAM      │  (program-wide overrides)
                    │   e.g., P4M      │
                    └─────────┬───────┘
                              │ inherits
              ┌───────────────┼───────────────┐
              │               │               │
    ┌─────────▼─────┐ ┌───────▼───────┐ ┌─────▼───────┐
    │    CLINIC     │ │    CLINIC     │ │   CLINIC    │
    │   Portland    │ │   Seattle     │ │  Providence │
    └───────┬───────┘ └───────────────┘ └─────────────┘
            │ inherits
    ┌───────┴───────┐
    │               │
┌───▼─────┐ ┌───────▼──────┐
│ LOCATION│ │   LOCATION   │
│ West    │ │ Franz Care   │
└─────────┘ └──────────────┘
```

**Key Concepts:**
- Values set at Program level apply to all Clinics and Locations unless overridden
- Values set at Clinic level apply to all Locations in that clinic unless overridden
- Override tracking shows what's explicitly set vs inherited
- Audit history tracks all changes with who, what, when, why

## Configuration Categories

| Category | Description | Example Keys |
|----------|-------------|--------------|
| `appointment_extract` | EHR appointment filtering | `extract_patient_status`, `extract_service_locations`, `extract_providers`, `extract_appointment_types` |
| `invitation` | Initial invitation settings | `invitation_days_before`, `invitation_channels` |
| `reminder` | Follow-up reminder settings | `reminder_days_before`, `reminder_frequency` |
| `sms` | SMS campaign settings | `sms_aws_approval_destination` |
| `email_branding` | Email templates and branding | `email_branding_template`, `email_branding_logo` |
| `signature_block` | Location-specific signatures | `signature_block_email`, `signature_block_sms` |
| `assessment` | Risk assessment lockout | `assessment_lockout_trigger`, `assessment_lockout_period_months` |
| `helpdesk` | Help desk contact info | `helpdesk_email`, `helpdesk_phone`, `helpdesk_workflow` |
| `operations` | Operating hours | `hours_open`, `hours_close` |
| `tc_scoring` | Tyrer-Cuzick scoring | `tc_scoring_enabled`, `tc_minimum_age` |
| `versions` | Algorithm/engine versions | `version_tc_algorithm`, `version_nccn_algorithm` |
| `lab_order` | Lab and test defaults | `lab_default_name`, `lab_default_test_code` |

## CLI Commands

### Initialization
```bash
# Initialize database and load definitions (run once)
python3 run.py --init
```

### Import Operations
```bash
# Import from Word clinic spec document
python3 run.py --import "Portland_Clinic_Spec.docx" --program P4M
```

### View Operations
```bash
# List all programs with hierarchy
python3 run.py --list-programs

# View all configs for a program
python3 run.py --view --program P4M

# View configs for a specific clinic
python3 run.py --view --program P4M --clinic Portland

# View configs for a specific location
python3 run.py --view --program P4M --clinic Portland --location "Breast Surgery West"

# View inheritance tree for a config
python3 run.py --tree helpdesk_phone --program P4M

# View audit history for a config
python3 run.py --audit helpdesk_phone --program P4M --clinic Portland
```

### Set/Update Operations
```bash
# Set a config value at program level
python3 run.py --set helpdesk_phone --value "800.555.0000" --program P4M

# Set at clinic level
python3 run.py --set helpdesk_phone --value "503.216.6407" --program P4M --clinic Portland

# Set at location level
python3 run.py --set helpdesk_phone --value "503.216.6500" \
    --program P4M --clinic Portland --location "Breast Surgery West"

# Update provider NPI
python3 run.py --update-provider "Christine Kemp" --npi "1215158639"

# Update provider NPI for specific program
python3 run.py --update-provider "Kemp" --npi "1215158639" --program P4M
```

### Export Operations
```bash
# Export all program configs to Excel
python3 run.py --export --program P4M

# Export with custom output path
python3 run.py --export --program P4M --output outputs/p4m_configs.xlsx

# Export specific clinic
python3 run.py --export --program P4M --clinic Portland --output outputs/portland.xlsx
```

### Compare Operations
```bash
# Compare clinic to program defaults
python3 run.py --compare --program P4M --clinic Portland

# Compare location to defaults
python3 run.py --compare --program P4M --clinic Portland --location "Breast Surgery West"
```

### Create Operations
```bash
# Create new program
python3 run.py --create-program "Prevention4ME" --prefix P4M --type clinic_based

# Create attached program
python3 run.py --create-program "Discover" --prefix DISC --type attached --attach-to "P4M,PRE,GRX"

# Create clinic under program
python3 run.py --create-clinic "Portland Cancer Institute" --program P4M --code PORT

# Create location under clinic
python3 run.py --create-location "Breast Surgery West" --program P4M --clinic Portland --code "4000045001"
```

## Programmatic Usage

### Basic Operations
```python
from database import ConfigurationManager, get_config_manager
from managers import InheritanceManager, QuickUpdateManager
from formatters import ConfigExcelFormatter

# Get manager instance
cm = get_config_manager()

# Initialize (first time only)
cm.initialize_schema()
cm.load_definitions_from_yaml()

# Create hierarchy
program_id = cm.create_program("Prevention4ME", "P4M", program_type='clinic_based')
clinic_id = cm.create_clinic(program_id, "Portland", code="PORT")
location_id = cm.create_location(clinic_id, "Breast Surgery West", code="4000045001")

# Add provider
cm.add_provider(location_id, "Christine Kemp, NP", npi="1215158639")

# Set config values
cm.set_config('helpdesk_phone', '503.216.6407', program_id, clinic_id, location_id,
              source='import', source_document='Portland_Spec.docx')

# Get config (with inheritance)
result = cm.get_config('helpdesk_phone', program_id, clinic_id, location_id)
print(result['value'])           # '503.216.6407'
print(result['effective_level']) # 'location'
print(result['is_override'])     # True
```

### Inheritance Operations
```python
im = InheritanceManager(cm)

# Get full inheritance chain
chain = im.resolve_with_inheritance('helpdesk_phone', program_id, clinic_id, location_id)
print(chain['inheritance_chain'])
# [
#   {'level': 'default', 'value': None},
#   {'level': 'program', 'value': '800.555.0000'},
#   {'level': 'clinic', 'value': '503.216.6407', 'is_override': True}
# ]

# Print visual inheritance tree
print(im.print_inheritance_tree('helpdesk_phone', program_id))
# Prevention4ME: 800.555.0000 (manual)
#   └── Portland: 503.216.6407* (import)
#       └── Breast Surgery West: 503.216.6407 (inherited)

# Validate inheritance
issues = im.validate_inheritance(program_id)
```

### Quick Updates
```python
qm = QuickUpdateManager(cm)

# Update provider NPI by name
qm.update_provider_npi("Christine Kemp", "1215158639")

# Update test code for a clinic
qm.update_test_code("Portland", "CAP123", new_name="Custom Panel")

# Update phone by location name
qm.update_phone("Breast Surgery West", "503.216.6500")

# Update hours
qm.update_hours("Breast Surgery West", "08:00", "17:00")

# Bulk update from Excel
qm.bulk_update_from_excel("updates.xlsx", dry_run=False)
```

### Export to Excel (Configuration Matrix)

The Excel export now uses a single **Configuration Matrix** view that shows all config values at all hierarchy levels in one sheet:

```
Columns: Config Key | Display Name | Program Default | Clinic Name | Location1 | Location2 | ...
Rows: Grouped by category with section headers

Values:
- "—" (em dash) = inherited from parent level
- Actual value = explicitly set at that level

Styling:
- Yellow (gold) highlight = override (differs from parent)
- Blue section headers = category groupings
- Frozen panes = config names stay visible when scrolling
```

```python
formatter = ConfigExcelFormatter(cm)

# Export full program with Configuration Matrix view
formatter.export_program("P4M", "outputs/p4m_configs.xlsx")

# Optional: Include/exclude additional sheets
formatter.export_program("P4M", "outputs/p4m_configs.xlsx",
                         include_audit=True,      # Audit History sheet
                         include_providers=True)  # Providers sheet

# Export specific clinic
formatter.export_clinic("P4M", "Portland", "outputs/portland.xlsx")
```

**Example Output:**
| Config Key | Display Name | Program Default | Portland | Breast Surgery West | Franz Breast Care |
|------------|--------------|-----------------|----------|---------------------|-------------------|
| helpdesk_phone | Helpdesk Phone | — | — | 503.216.6407 | 503.216.6800 |
| helpdesk_email | Helpdesk Email | support@p4m.com | — | — | — |
| hours_open | Opening Time | 08:00 | — | **09:00** (yellow) | — |

## Word Document Parsing

The `ClinicSpecParser` expects Word documents with:
- Header with Doc ID, Version, Parent SRS
- Scope section listing locations
- Configuration Matrix table with columns:
  - Category
  - Global Default
  - [Clinic Name] Override/Customization
  - Rationale/Source
- Optional Provider table
- Change Log table

### Category-to-Config-Key Mapping

The parser intelligently maps Word document categories to specific config keys:

| Document Category | Config Keys | Parsing Logic |
|-------------------|-------------|---------------|
| "Patient Appointment Extract – Filtering" | `extract_patient_status`, `extract_service_locations`, `extract_providers`, `extract_appointment_types` | Parses each subsection separately |
| "Invitation Clinical Help Desk Email" | `helpdesk_email`, `helpdesk_workflow` | Separates email (contains @) from workflow text |
| "Invitation Clinical Help Desk Phone Number" | `helpdesk_phone` | Parses "Location: Value" format for location-specific |
| "Invitation Hours of Operation" | `hours_open`, `hours_close` | Parses time ranges like "8am-5pm" |
| "TC Scoring Patient Age" | `tc_minimum_age`, `tc_maximum_age` | Parses age ranges like "35-84" |
| "Lab Order Defaults Test" | `lab_default_test_code`, `lab_default_test_name` | Parses "CODE: Name" format |

### Location-Specific Value Parsing

Values in the format `Location: Value` are automatically parsed as location-specific overrides:
```
Breast Surgery West: 503.216.6407
Franz Breast Care: 503.216.6800
```

### Parser Output

```python
from parsers import ClinicSpecParser

parser = ClinicSpecParser("Portland_Clinic_Spec.docx")
result = parser.parse()

print(result['clinic_name'])       # 'Portland'
print(result['scope_locations'])   # ['Breast Surgery West', 'Franz Breast Care']
print(result['configurations'])    # Raw config dicts from document
print(result['mapped_configs'])    # Processed configs with proper keys
print(result['providers'])         # List of provider dicts

# Import to database
cm.import_from_parsed_doc(result, program_id, source_document="Portland_Spec.docx")
```

## Audit Trail

All changes are logged for FDA 21 CFR Part 11 compliance:

```python
# Get history for specific config
history = cm.get_config_history('helpdesk_phone', program_id, clinic_id)

# Get all changes for a program
all_changes = cm.get_all_changes(program_id, start_date='2024-01-01')

# Each entry contains:
# - changed_date
# - old_value
# - new_value
# - changed_by
# - change_reason
# - source_document
```

## Database Tables

| Table | Purpose |
|-------|---------|
| `programs` | Top-level programs (shared with Requirements Toolkit) |
| `program_relationships` | Links attached programs to parents |
| `clinics` | Organizations under programs |
| `locations` | Physical sites under clinics |
| `config_definitions` | Schema for all possible configs |
| `config_values` | Actual config values at each level |
| `providers` | Healthcare providers at locations |
| `appointment_types` | Appointment type filters per location |
| `config_history` | Detailed config change log |
| `users` | User accounts for access tracking |
| `user_access` | Access grants (who has access to what) |
| `access_reviews` | Periodic access review history |
| `user_training` | HIPAA workforce training records |
| `role_conflicts` | Segregation of duties rules |

## User Access Module

Track system access for Part 11, HIPAA, and SOC 2 compliance.

### Key Concepts

- **Users**: People who may have system access (user_id is unique per Part 11)
- **Access Grants**: Specific access a user has (program/clinic/location + role)
- **Access Reviews**: Periodic recertification (SOC 2 requirement - quarterly or annual)
- **Training**: HIPAA workforce training tracking
- **Role Conflicts**: Segregation of duties rules (prevents conflicting role combinations)

### File Organization

```
configurations_toolkit/
├── database/
│   └── access_schema.sql           # User access tables schema
├── managers/
│   └── access_manager.py           # User, access, review, training operations
├── reports/
│   └── compliance_reports.py       # Auditor compliance reports
├── formatters/
│   └── access_excel_formatter.py   # Export access data to Excel
```

### Compliance Framework Coverage

| Requirement | Framework | How Tracked |
|-------------|-----------|-------------|
| Unique user IDs | Part 11 | `users.user_id` (e.g., "JSMITH-A1B2C3") |
| Authority checks | Part 11 | `user_access.role` (Admin, Provider, Coordinator, Read-Only, Auditor) |
| Electronic signatures | Part 11 | `audit_history.changed_by` |
| Minimum necessary access | HIPAA | Scoped to program/clinic/location levels |
| Termination procedures | HIPAA | `terminate_user()` automatically revokes all access |
| Workforce training | HIPAA | `user_training` table tracks HIPAA, Cybersecurity, Application Training |
| Business Associates | HIPAA | `users.is_business_associate` flag |
| Access provisioning | SOC 2 | `user_access` with full audit trail |
| Periodic review | SOC 2 | `access_reviews` table, `next_review_due` field |
| Segregation of duties | SOC 2 | `role_conflicts` table (blocks Admin+Auditor) |

### CLI Commands - User Management

```bash
# Initialize access schema (run once)
python3 run.py --init-access

# Create a user
python3 run.py --add-user "John Smith" --email "jsmith@clinic.com" --organization "Portland Clinic"

# Create a Business Associate user (HIPAA)
python3 run.py --add-user "Jane Contractor" --email "jane@vendor.com" --organization "Vendor Inc" --business-associate

# List users
python3 run.py --list-users
python3 run.py --list-users --status "Active"

# Terminate user (auto-revokes all access)
python3 run.py --terminate-user "jsmith@clinic.com" --reason "Employment ended" --by "HR Admin"
```

### CLI Commands - Access Management

```bash
# Grant access to a user
python3 run.py --grant-access --user "jsmith@clinic.com" --program P4M --role Coordinator --by "Manager" --reason "New hire"

# Grant access to specific clinic
python3 run.py --grant-access --user "jsmith@clinic.com" --program P4M --clinic Portland --role Provider --by "Manager"

# Revoke access
python3 run.py --revoke-access --access-id 123 --by "Manager" --reason "Role change"

# List access for a user
python3 run.py --list-access --user "jsmith@clinic.com"

# List access for a scope
python3 run.py --list-access --program P4M --clinic Portland
```

### CLI Commands - Access Reviews

```bash
# Show overdue reviews
python3 run.py --reviews-due
python3 run.py --reviews-due --program P4M

# Conduct a single review
python3 run.py --conduct-review --access-id 123 --by "Compliance Officer" --review-status "Certified" --notes "Confirmed with manager"

# Export review worksheet for batch processing
python3 run.py --export-review-worksheet --program P4M --output outputs/Q4_review.xlsx

# Import completed review worksheet
python3 run.py --import-review-worksheet "outputs/Q4_review_completed.xlsx" --by "Compliance Officer"
```

### CLI Commands - Training

```bash
# Assign training
python3 run.py --assign-training --user "jsmith@clinic.com" --training-type "HIPAA" --by "Compliance"

# Complete training
python3 run.py --complete-training --training-id 456 --date "2025-12-19" --certificate "CERT-12345"

# Check training status
python3 run.py --training-status --user "jsmith@clinic.com"

# Show expired training
python3 run.py --expired-training
```

### CLI Commands - Compliance Reports

```bash
# Access list report (who has access to what)
python3 run.py --compliance-report access_list --program P4M

# Export to Excel
python3 run.py --compliance-report access_list --program P4M --output outputs/access_report.xlsx

# Access changes during a period
python3 run.py --compliance-report access_changes --start-date "2025-10-01" --end-date "2025-12-31"

# Review status (are reviews current?)
python3 run.py --compliance-report review_status

# Training compliance
python3 run.py --compliance-report training_compliance

# CRITICAL: Terminated user audit (should always be empty!)
python3 run.py --compliance-report terminated_audit

# Business Associates report
python3 run.py --compliance-report business_associates

# Segregation of duties violations
python3 run.py --compliance-report segregation_of_duties
```

### Programmatic Usage

```python
from managers import AccessManager
from reports import ComplianceReports
from formatters import AccessExcelFormatter

# Initialize
am = AccessManager()
am.initialize_schema()

# Create user
user_id = am.create_user(
    name="John Smith",
    email="jsmith@clinic.com",
    organization="Portland Clinic"
)

# Grant access
access_id = am.grant_access(
    user_id=user_id,
    program_id="P4M",
    role="Coordinator",
    granted_by="Manager",
    clinic_id="Portland",
    reason="New hire"
)

# Conduct review
am.conduct_review(
    access_id=access_id,
    reviewed_by="Compliance",
    status="Certified",
    notes="Confirmed with manager"
)

# Assign and complete training
# responsibility: 'Client' (client org tracks) or 'Propel Health' (PHP tracks, default)
training_id = am.assign_training(user_id, "HIPAA", "Compliance", responsibility="Client")
am.complete_training(training_id, completed_date="2025-12-19", certificate_reference="CERT-12345")

# Generate compliance reports
reports = ComplianceReports(am)
access_report = reports.access_list_report(program_id="P4M")
print(f"Total users with access: {access_report['summary']['total_users']}")

# Export to Excel
formatter = AccessExcelFormatter(am)
formatter.export_compliance_report(access_report, "outputs/access_report.xlsx")

# Check for compliance issues
terminated = am.get_terminated_with_access()  # Should be empty!
if terminated:
    print("WARNING: Terminated users still have access!")
```

### Access Review Workflow

1. **Quarterly Review Cycle**:
   ```bash
   # Export worksheet of overdue reviews
   python3 run.py --export-review-worksheet --program P4M --output outputs/Q4_review.xlsx
   ```

2. **Manager Reviews in Excel**:
   - Open the worksheet
   - For each row, select Decision: Certified, Revoked, or Modified
   - Add notes explaining the decision

3. **Import Completed Reviews**:
   ```bash
   python3 run.py --import-review-worksheet "outputs/Q4_review_completed.xlsx" --by "Compliance Officer"
   ```

4. **Verify Compliance**:
   ```bash
   python3 run.py --compliance-report review_status
   # Should show: Overdue: 0
   ```

### Audit Trail

All access changes are logged to `audit_history`:

```python
# View audit history for access changes
cursor.execute("""
    SELECT * FROM audit_history
    WHERE entity_type IN ('user', 'user_access', 'access_reviews', 'user_training')
    ORDER BY changed_date DESC
""")
```

Each entry contains:
- `entity_type`: What changed (user, user_access, etc.)
- `entity_id`: ID of the affected record
- `action`: What happened (CREATE, GRANT, REVOKE, REVIEW, etc.)
- `old_value`: Previous state (JSON)
- `new_value`: New state (JSON)
- `changed_by`: Who made the change
- `changed_date`: When it happened
- `change_reason`: Why it was changed

### Role Definitions

| Role | Description | Typical Use |
|------|-------------|-------------|
| Admin | Full control over configurations and access | IT administrators |
| Provider | Clinical access for patient-related configs | Healthcare providers |
| Coordinator | Operational access for scheduling/contact info | Clinic coordinators |
| Read-Only | View configurations but cannot modify | Reporting users |
| Auditor | Special access for compliance audits | Internal/external auditors |

### Role Conflicts (Segregation of Duties)

Pre-defined conflicts in `role_conflicts` table:

| Role A | Role B | Severity | Reason |
|--------|--------|----------|--------|
| Admin | Auditor | Block | Admin should not audit their own work |
| Data Entry | Approver | Warning | Segregation of data entry and approval |
| Provider | Admin | Warning | Clinical users should not have admin privileges |

- **Block**: System prevents the access grant
- **Warning**: System allows but logs the conflict for review

### Importing Existing Data

Use the import functionality when onboarding clinics with existing user lists or migrating from other tracking systems.

#### Generate Import Template

```bash
# Generate blank template with example data and validation dropdowns
python3 run.py --generate-access-template --output "Access_Import_Template.xlsx"
```

The template includes:
- **Users tab**: User information columns
- **Access tab**: Access grant columns
- **Training tab**: Training record columns
- **Instructions tab**: Field definitions and valid values

#### Import from Template

```bash
# Import from multi-tab template (processes Users, Access, Training in order)
python3 run.py --import-access-template "clinic_data.xlsx"

# Dry run to validate without importing
python3 run.py --import-access-template "clinic_data.xlsx" --dry-run
```

#### Import Individual Files

```bash
# Import users first (must exist before access/training)
python3 run.py --import-users "users.xlsx"

# Import access grants
python3 run.py --import-access "access_grants.xlsx"

# Import training records
python3 run.py --import-training "training_records.xlsx"
```

#### Column Matching

The importer uses flexible column matching - multiple column names map to each field:

| Field | Accepted Column Names |
|-------|----------------------|
| Name | Name, Full Name, User Name, Employee Name |
| Email | Email, Email Address, User Email, E-mail |
| Organization | Organization, Company, Org, Department |
| Role | Role, Access Level, Permission, User Role |
| Training Type | Training Type, Training, Course, Course Name |
| Completed Date | Completed Date, Date Completed, Completion Date |

#### Import Order

When importing from a template, order matters:
1. **Users first** - must exist before granting access
2. **Access grants second** - references users and programs
3. **Training records third** - references users

#### Programmatic Usage

```python
from managers import AccessManager, AccessImporter

am = AccessManager()
importer = AccessImporter(am)

# Generate template
importer.generate_import_template("outputs/template.xlsx")

# Import from template
results = importer.import_from_template("filled_template.xlsx")
print(f"Users imported: {results['users']['imported']}")
print(f"Access imported: {results['access']['imported']}")
print(f"Training imported: {results['training']['imported']}")

# Import individual files
user_results = importer.import_users("users.xlsx")
access_results = importer.import_access("access.xlsx", dry_run=True)
training_results = importer.import_training("training.xlsx")
```

## Dependencies

```bash
pip install pyyaml openpyxl python-docx
```

- `pyyaml`: Parse config_definitions.yaml
- `openpyxl`: Read/write Excel files
- `python-docx`: Parse Word documents

## Do NOT
- Use overly clever one-liners without explanation
- Skip error handling
- Assume I know Python idioms — explain them
- Modify shared tables without understanding Requirements Toolkit implications
