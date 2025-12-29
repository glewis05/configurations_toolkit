"""
CLI Argument Parser
===================

Defines all command-line arguments for the Configurations Toolkit.

WHY SEPARATE FILE: Keeps argument definitions organized and makes
it easy to see all available commands at a glance.
"""

import argparse


def create_parser() -> argparse.ArgumentParser:
    """
    Create the argument parser.

    WHY THIS APPROACH: argparse provides robust command-line parsing
    with automatic help generation and type checking.
    """
    parser = argparse.ArgumentParser(
        description="Configurations Toolkit - Manage system configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Initialize database:
    python3 run.py --init

  Import from Word doc:
    python3 run.py --import "spec.docx" --program P4M

  View clinic configs:
    python3 run.py --view --program P4M --clinic Portland

  Export to Excel:
    python3 run.py --export --program P4M --output outputs/configs.xlsx

  Update provider NPI:
    python3 run.py --update-provider "Jane Doe" --npi "1234567890"
        """
    )

    # ==== GLOBAL OPTIONS ====
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Enable verbose output")
    parser.add_argument('--db', type=str,
                        default="~/projects/data/client_product_database.db",
                        help="Path to database file")

    # ==== INITIALIZATION ====
    parser.add_argument('--init', action='store_true',
                        help="Initialize database schema and load definitions")

    # ==== IMPORT OPERATIONS ====
    parser.add_argument('--import', dest='import_file', type=str,
                        help="Import configurations from Word document")
    parser.add_argument('--reimport', action='store_true',
                        help="Clear existing program data before import (use with --import)")

    # ==== VIEW OPERATIONS ====
    parser.add_argument('--view', action='store_true',
                        help="View configurations")
    parser.add_argument('--list-programs', action='store_true',
                        help="List all programs with hierarchy")
    parser.add_argument('--audit', type=str, metavar='CONFIG_KEY',
                        help="View audit history for a config key")

    # ==== SET OPERATIONS ====
    parser.add_argument('--set', type=str, metavar='CONFIG_KEY',
                        help="Set a configuration value")
    parser.add_argument('--value', type=str,
                        help="Value to set (use with --set)")

    # ==== UPDATE OPERATIONS ====
    parser.add_argument('--update-provider', type=str, metavar='NAME',
                        help="Update provider by name")
    parser.add_argument('--npi', type=str,
                        help="NPI number (use with --update-provider)")
    parser.add_argument('--update-phone', type=str, metavar='PHONE',
                        help="Update helpdesk phone for location")
    parser.add_argument('--update-hours', type=str, nargs=2,
                        metavar=('OPEN', 'CLOSE'),
                        help="Update hours for location (e.g., '08:00' '17:00')")

    # ==== EXPORT OPERATIONS ====
    parser.add_argument('--export', action='store_true',
                        help="Export configurations to Excel")
    parser.add_argument('--output', '-o', type=str,
                        help="Output file path")

    # ==== COMPARE OPERATIONS ====
    parser.add_argument('--compare', action='store_true',
                        help="Compare clinic/location to defaults")
    parser.add_argument('--tree', type=str, metavar='CONFIG_KEY',
                        help="Show inheritance tree for a config")

    # ==== CREATE OPERATIONS ====
    parser.add_argument('--create-program', type=str, metavar='NAME',
                        help="Create new program")
    parser.add_argument('--prefix', type=str,
                        help="Program prefix (e.g., P4M)")
    parser.add_argument('--type', type=str,
                        choices=['standalone', 'clinic_based', 'attached'],
                        default='clinic_based',
                        help="Program type")
    parser.add_argument('--attach-to', type=str,
                        help="Comma-separated list of program prefixes to attach to")

    parser.add_argument('--create-clinic', type=str, metavar='NAME',
                        help="Create new clinic")
    parser.add_argument('--create-location', type=str, metavar='NAME',
                        help="Create new location")
    parser.add_argument('--code', type=str,
                        help="Optional code for clinic/location")

    # ==== CONTEXT FILTERS ====
    parser.add_argument('--program', '-p', type=str,
                        help="Program prefix to operate on")
    parser.add_argument('--clinic', '-c', type=str,
                        help="Clinic name")
    parser.add_argument('--location', '-l', type=str,
                        help="Location name")

    # =========================================================================
    # USER ACCESS MANAGEMENT
    # =========================================================================

    # ==== USER OPERATIONS ====
    parser.add_argument('--add-user', type=str, metavar='NAME',
                        help="Create a new user")
    parser.add_argument('--email', type=str,
                        help="User email (use with --add-user)")
    parser.add_argument('--organization', type=str, default='Internal',
                        help="User organization (use with --add-user)")
    parser.add_argument('--business-associate', action='store_true',
                        help="Mark user as Business Associate (HIPAA)")

    parser.add_argument('--list-users', action='store_true',
                        help="List all users")
    parser.add_argument('--status', type=str,
                        choices=['Active', 'Inactive', 'Terminated'],
                        help="Filter users by status")

    parser.add_argument('--terminate-user', type=str, metavar='EMAIL',
                        help="Terminate a user and revoke all access")
    parser.add_argument('--reason', type=str,
                        help="Reason for action (use with --terminate-user, --revoke-access)")
    parser.add_argument('--by', type=str,
                        help="Who is performing the action")

    # ==== ACCESS OPERATIONS ====
    parser.add_argument('--grant-access', action='store_true',
                        help="Grant access to a user")
    parser.add_argument('--user', type=str,
                        help="User email (use with --grant-access)")
    parser.add_argument('--role', type=str,
                        choices=['Read-Only', 'Read-Write', 'Read-Write-Order',
                                 'Clinic-Manager', 'Analytics-Only', 'Admin', 'Auditor'],
                        help="Access role")

    parser.add_argument('--revoke-access', action='store_true',
                        help="Revoke an access grant")
    parser.add_argument('--access-id', type=int,
                        help="Access grant ID (use with --revoke-access)")

    parser.add_argument('--list-access', action='store_true',
                        help="List access grants")

    # ==== ACCESS REVIEW OPERATIONS ====
    parser.add_argument('--reviews-due', action='store_true',
                        help="Show access reviews that are overdue or due soon")

    parser.add_argument('--conduct-review', action='store_true',
                        help="Conduct an access review")
    parser.add_argument('--review-status', type=str,
                        choices=['Certified', 'Revoked', 'Modified'],
                        help="Review decision (use with --conduct-review)")
    parser.add_argument('--notes', type=str,
                        help="Reviewer notes (use with --conduct-review)")

    parser.add_argument('--export-review-worksheet', action='store_true',
                        help="Export review worksheet to Excel")
    parser.add_argument('--import-review-worksheet', type=str,
                        metavar='FILE',
                        help="Import completed review worksheet from Excel")

    # ==== TRAINING OPERATIONS ====
    parser.add_argument('--assign-training', action='store_true',
                        help="Assign training to a user")
    parser.add_argument('--training-type', type=str,
                        choices=['HIPAA', 'Cybersecurity', 'Application Training',
                                 'SOC 2', 'HITRUST', 'Part 11'],
                        help="Type of training")

    parser.add_argument('--complete-training', action='store_true',
                        help="Mark training as completed")
    parser.add_argument('--training-id', type=int,
                        help="Training record ID")
    parser.add_argument('--date', type=str,
                        help="Completion date (YYYY-MM-DD)")
    parser.add_argument('--certificate', type=str,
                        help="Certificate reference")

    parser.add_argument('--training-status', action='store_true',
                        help="Show training status for a user")

    parser.add_argument('--expired-training', action='store_true',
                        help="Show users with expired training")

    # ==== COMPLIANCE REPORTS ====
    parser.add_argument('--compliance-report', type=str,
                        choices=['access_list', 'access_changes', 'review_status',
                                 'overdue_reviews', 'training_compliance',
                                 'terminated_audit', 'business_associates',
                                 'segregation_of_duties'],
                        help="Generate a compliance report")
    parser.add_argument('--start-date', type=str,
                        help="Start date for reports (YYYY-MM-DD)")
    parser.add_argument('--end-date', type=str,
                        help="End date for reports (YYYY-MM-DD)")

    # ==== ACCESS SCHEMA INIT ====
    parser.add_argument('--init-access', action='store_true',
                        help="Initialize access management schema")

    # ==== ACCESS IMPORT OPERATIONS ====
    parser.add_argument('--import-users', type=str, metavar='FILE',
                        help="Import users from Excel file")
    parser.add_argument('--import-access', type=str, metavar='FILE',
                        help="Import access grants from Excel file")
    parser.add_argument('--import-training', type=str, metavar='FILE',
                        help="Import training records from Excel file")
    parser.add_argument('--import-access-template', type=str, metavar='FILE',
                        help="Import from multi-tab template (Users, Access, Training)")
    parser.add_argument('--generate-access-template', action='store_true',
                        help="Generate blank import template")
    parser.add_argument('--dry-run', action='store_true',
                        help="Validate import without making changes")

    return parser
