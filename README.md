# Configurations Toolkit

Python toolkit for managing clinic configurations with inheritance support across Program → Clinic → Location hierarchy.

## Overview

This toolkit:
- Parses clinic specification Word documents to extract configuration settings
- Manages configurations with inheritance (child levels inherit from parents unless overridden)
- Tracks all changes for audit trail (FDA 21 CFR Part 11 compliance)
- Provides easy update methods for common operations (NPIs, phone numbers, test codes)
- Exports configurations to formatted Excel reports
- Manages user access, training, and compliance for HIPAA and SOC 2

## Installation

```bash
# Clone the repository
git clone https://github.com/glewis05/configurations_toolkit.git
cd configurations_toolkit

# Install dependencies
pip install -e .
# Or: pip install pyyaml openpyxl python-docx

# Initialize database
python3 run.py --init
```

## Quick Start

```bash
# Initialize database with config definitions
python3 run.py --init

# Import from Word clinic spec document
python3 run.py --import "Portland_Clinic_Spec.docx" --program P4M

# View configurations
python3 run.py --view --program P4M --clinic Portland

# Set a configuration value
python3 run.py --set helpdesk_phone --value "503.216.6407" --program P4M --clinic Portland

# Export to Excel
python3 run.py --export --program P4M --output outputs/p4m_configs.xlsx
```

## Project Structure

```
configurations_toolkit/
├── run.py                  # CLI entry point
├── CLAUDE.md               # AI assistant context
├── pyproject.toml          # Package configuration
├── database/
│   ├── config_schema.sql   # Configuration tables schema
│   ├── access_schema.sql   # User access tables schema
│   └── config_manager.py   # CRUD operations with inheritance
├── parsers/
│   └── word_parser.py      # Parse Word clinic spec documents
├── managers/
│   ├── inheritance_manager.py  # Handle inheritance resolution
│   ├── update_manager.py       # Easy updates for providers, tests, etc.
│   └── access_manager.py       # User and access management
├── formatters/
│   ├── config_excel_formatter.py   # Export configs to Excel
│   └── access_excel_formatter.py   # Export access data to Excel
├── reports/
│   └── compliance_reports.py       # Auditor compliance reports
├── config/
│   └── config_definitions.yaml     # All configurable fields defined here
├── inputs/                 # Drop Word docs to process
└── outputs/                # Generated Excel exports
```

## Inheritance Model

```
              ┌─────────────────┐
              │ config_definitions │  (default values)
              └─────────┬───────┘
                        │ inherits
              ┌─────────▼───────┐
              │     PROGRAM      │  (program-wide overrides)
              │   e.g., P4M      │
              └─────────┬───────┘
                        │ inherits
        ┌───────────────┼───────────────┐
        │               │               │
  ┌─────▼─────┐ ┌───────▼───────┐ ┌─────▼───────┐
  │  CLINIC   │ │    CLINIC     │ │   CLINIC    │
  │  Portland │ │   Seattle     │ │ Providence  │
  └─────┬─────┘ └───────────────┘ └─────────────┘
        │ inherits
  ┌─────┴─────────┐
  │               │
┌─▼───────┐ ┌─────▼──────┐
│LOCATION │ │  LOCATION  │
│  West   │ │Franz Care  │
└─────────┘ └────────────┘
```

- Values set at Program level apply to all Clinics and Locations unless overridden
- Values set at Clinic level apply to all Locations in that clinic unless overridden
- Override tracking shows what's explicitly set vs inherited
- Audit history tracks all changes with who, what, when, why

## Configuration Categories

| Category | Description | Example Keys |
|----------|-------------|--------------|
| `appointment_extract` | EHR appointment filtering | `extract_patient_status`, `extract_providers` |
| `invitation` | Initial invitation settings | `invitation_days_before`, `invitation_channels` |
| `reminder` | Follow-up reminder settings | `reminder_days_before`, `reminder_frequency` |
| `helpdesk` | Help desk contact info | `helpdesk_email`, `helpdesk_phone` |
| `lab_order` | Lab and test defaults | `lab_default_name`, `lab_default_test_code` |

## User Access Management

Track system access for Part 11, HIPAA, and SOC 2 compliance:

```bash
# Add a user
python3 run.py --add-user "John Smith" --email "jsmith@clinic.com" --organization "Portland Clinic"

# Grant access
python3 run.py --grant-access --user "jsmith@clinic.com" --program P4M --role Coordinator --by "Manager"

# Show overdue reviews
python3 run.py --reviews-due

# Generate compliance report
python3 run.py --compliance-report access_list --program P4M
```

## Database Architecture

Part of the unified Propel Health database ecosystem:

| Location | Purpose |
|----------|---------|
| `~/projects/data/client_product_database.db` | Shared database for all toolkits |

### Tables Managed by This Toolkit
- `clinics`, `locations` - Clinic hierarchy under programs
- `config_definitions`, `config_values` - Configuration settings with inheritance
- `providers`, `appointment_types` - Clinical data
- `users`, `user_access`, `access_reviews` - Access management
- `user_training` - HIPAA workforce training records

## Related Projects

- **[requirements_toolkit](https://github.com/glewis05/requirements_toolkit)** - Generates user stories and test cases
- **[uat_toolkit](https://github.com/glewis05/uat_toolkit)** - Manages UAT execution cycles
- **[propel_mcp](https://github.com/glewis05/propel_mcp)** - MCP server connecting all toolkits

## License

Proprietary - Propel Health
