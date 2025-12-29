"""
COMPLIANCE REPORTS MODULE
=========================
Generate compliance reports for Part 11, HIPAA, and SOC 2 audits.

This module provides ready-to-use reports that auditors commonly request:
- Access list: Who has access to what?
- Access changes: What changed during a period?
- Review status: Are access reviews current?
- Training compliance: Is workforce training current?
- Terminated user audit: Any terminated users with access?
- Business associates: External users with PHI access?
- Segregation of duties: Any role conflicts?

Aviation Analogy:
    Think of these as pre-flight checklists and safety audits:
    - Access list = crew manifest (who's authorized to be on this flight)
    - Review status = recurrent training status (everyone current?)
    - Terminated audit = revoked certificates (no one flying who shouldn't be)
    Each report is designed to answer specific regulatory questions.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, date, timedelta
from pathlib import Path
import json

# Import AccessManager - we'll use it for data access
from managers.access_manager import AccessManager


class ComplianceReports:
    """
    PURPOSE: Generate compliance reports for Part 11, HIPAA, and SOC 2 audits

    This class provides formatted reports that answer common auditor questions.
    Each report method returns structured data that can be displayed in the CLI,
    exported to Excel, or used programmatically.

    R EQUIVALENT:
        In R, you might create a package of functions that query the database
        and return tibbles. This class does the same with Python dicts.

    ATTRIBUTES:
        am: AccessManager instance for data access

    EXAMPLE:
        reports = ComplianceReports()

        # Get all users with access to Portland clinic
        access_list = reports.access_list_report(
            program_id="P4M",
            clinic_id="Portland"
        )

        # Export to Excel for auditor
        reports.export_to_excel("access_list", "audit_report.xlsx",
                               program_id="P4M")
    """

    def __init__(self, access_manager: AccessManager = None):
        """
        Initialize ComplianceReports.

        PURPOSE: Set up the reports generator with database access

        PARAMETERS:
            access_manager: Optional AccessManager instance. If not provided,
                           creates a new one using the default database path.

        WHY THIS APPROACH:
            We accept an existing AccessManager so we can share connections
            and avoid opening multiple database handles. This also makes
            testing easier since we can inject a mock.
        """
        # Use provided AccessManager or create new one
        self.am = access_manager if access_manager else AccessManager()

    def access_list_report(
        self,
        program_id: str = None,
        clinic_id: str = None,
        location_id: str = None,
        as_of_date: str = None,
        include_training: bool = True
    ) -> Dict[str, Any]:
        """
        Generate a report of who has access to what.

        PURPOSE: Answer the auditor question "Who has access to this system?"

        R EQUIVALENT:
            user_access %>%
              left_join(users) %>%
              left_join(programs) %>%
              filter(is_active == TRUE)

        PARAMETERS:
            program_id: Filter to specific program (optional)
            clinic_id: Filter to specific clinic (optional)
            location_id: Filter to specific location (optional)
            as_of_date: Report as of this date (default: today)
            include_training: Include training status for each user

        RETURNS:
            Dict containing:
            - report_date: When report was generated
            - filters: What filters were applied
            - summary: Counts by role and scope
            - access_list: Detailed list of each access grant

        WHY THIS APPROACH:
            This is the most common auditor request. We include training
            status so they can see the full compliance picture at once.

        EXAMPLE:
            report = reports.access_list_report(program_id="P4M")
            print(f"Total with access: {report['summary']['total_users']}")
            for access in report['access_list']:
                print(f"  {access['user_name']}: {access['role']}")
        """
        cursor = self.am.conn.cursor()

        if as_of_date is None:
            as_of_date = date.today().isoformat()

        # Resolve IDs from names/prefixes
        resolved_program_id = None
        resolved_clinic_id = None
        resolved_location_id = None

        if program_id:
            resolved_program_id = self.am._resolve_program_id(program_id)
        if clinic_id and resolved_program_id:
            resolved_clinic_id = self.am._resolve_clinic_id(clinic_id, resolved_program_id)
        if location_id and resolved_clinic_id:
            resolved_location_id = self.am._resolve_location_id(location_id, resolved_clinic_id)

        # Build the main query
        query = """
            SELECT
                u.user_id,
                u.name as user_name,
                u.email,
                u.organization,
                u.is_business_associate,
                u.status as user_status,
                ua.access_id,
                ua.role,
                ua.granted_date,
                ua.granted_by,
                ua.grant_reason,
                ua.review_cycle,
                ua.next_review_due,
                p.name as program_name,
                p.prefix as program_prefix,
                c.name as clinic_name,
                l.name as location_name,
                (SELECT MAX(ar.review_date)
                 FROM access_reviews ar
                 WHERE ar.access_id = ua.access_id) as last_review_date
            FROM user_access ua
            JOIN users u ON ua.user_id = u.user_id
            JOIN programs p ON ua.program_id = p.program_id
            LEFT JOIN clinics c ON ua.clinic_id = c.clinic_id
            LEFT JOIN locations l ON ua.location_id = l.location_id
            WHERE ua.is_active = TRUE
              AND u.status = 'Active'
        """

        params = []

        if resolved_program_id:
            query += " AND ua.program_id = ?"
            params.append(resolved_program_id)

        if resolved_clinic_id:
            query += " AND (ua.clinic_id = ? OR ua.clinic_id IS NULL)"
            params.append(resolved_clinic_id)

        if resolved_location_id:
            query += " AND (ua.location_id = ? OR ua.location_id IS NULL)"
            params.append(resolved_location_id)

        query += " ORDER BY u.name, p.name"

        cursor.execute(query, params)
        access_records = [dict(row) for row in cursor.fetchall()]

        # Add training status if requested
        if include_training:
            for record in access_records:
                training = self.am.get_training_status(record['user_id'])
                record['training_status'] = self._summarize_training(training)

        # Calculate summary statistics
        summary = self._calculate_access_summary(access_records)

        return {
            'report_type': 'access_list',
            'report_date': datetime.now().isoformat(),
            'as_of_date': as_of_date,
            'filters': {
                'program_id': program_id,
                'clinic_id': clinic_id,
                'location_id': location_id
            },
            'summary': summary,
            'access_list': access_records
        }

    def access_changes_report(
        self,
        start_date: str,
        end_date: str = None,
        program_id: str = None
    ) -> Dict[str, Any]:
        """
        Report on access changes during a period.

        PURPOSE: Answer "What access changes happened during this period?"

        PARAMETERS:
            start_date: Start of period (ISO format: YYYY-MM-DD)
            end_date: End of period (default: today)
            program_id: Filter to specific program (optional)

        RETURNS:
            Dict containing:
            - grants: New access grants during period
            - revocations: Access revoked during period
            - modifications: Access changes during period
            - summary: Counts of each type

        WHY THIS APPROACH:
            Auditors often ask for a change log for a specific period
            (e.g., last quarter). This pulls all relevant changes from
            the audit_history table.

        EXAMPLE:
            changes = reports.access_changes_report(
                start_date="2025-10-01",
                end_date="2025-12-31"
            )
            print(f"New grants: {changes['summary']['grants']}")
        """
        cursor = self.am.conn.cursor()

        if end_date is None:
            end_date = date.today().isoformat()

        # Get grants during period
        query_grants = """
            SELECT
                ua.*,
                u.name as user_name,
                u.email,
                p.name as program_name,
                c.name as clinic_name,
                l.name as location_name
            FROM user_access ua
            JOIN users u ON ua.user_id = u.user_id
            JOIN programs p ON ua.program_id = p.program_id
            LEFT JOIN clinics c ON ua.clinic_id = c.clinic_id
            LEFT JOIN locations l ON ua.location_id = l.location_id
            WHERE ua.granted_date BETWEEN ? AND ?
        """

        params = [start_date, end_date]

        if program_id:
            resolved_program_id = self.am._resolve_program_id(program_id)
            query_grants += " AND ua.program_id = ?"
            params.append(resolved_program_id)

        query_grants += " ORDER BY ua.granted_date DESC"

        cursor.execute(query_grants, params)
        grants = [dict(row) for row in cursor.fetchall()]

        # Get revocations during period
        query_revokes = """
            SELECT
                ua.*,
                u.name as user_name,
                u.email,
                p.name as program_name,
                c.name as clinic_name,
                l.name as location_name
            FROM user_access ua
            JOIN users u ON ua.user_id = u.user_id
            JOIN programs p ON ua.program_id = p.program_id
            LEFT JOIN clinics c ON ua.clinic_id = c.clinic_id
            LEFT JOIN locations l ON ua.location_id = l.location_id
            WHERE ua.revoked_date BETWEEN ? AND ?
        """

        params = [start_date, end_date]

        if program_id:
            query_revokes += " AND ua.program_id = ?"
            params.append(resolved_program_id)

        query_revokes += " ORDER BY ua.revoked_date DESC"

        cursor.execute(query_revokes, params)
        revocations = [dict(row) for row in cursor.fetchall()]

        # Get modifications from audit_history
        query_mods = """
            SELECT *
            FROM audit_history
            WHERE entity_type = 'user_access'
              AND action = 'MODIFY'
              AND changed_date BETWEEN ? AND ?
            ORDER BY changed_date DESC
        """

        cursor.execute(query_mods, (start_date, end_date))
        modifications = [dict(row) for row in cursor.fetchall()]

        return {
            'report_type': 'access_changes',
            'report_date': datetime.now().isoformat(),
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'filters': {
                'program_id': program_id
            },
            'summary': {
                'grants': len(grants),
                'revocations': len(revocations),
                'modifications': len(modifications),
                'total_changes': len(grants) + len(revocations) + len(modifications)
            },
            'grants': grants,
            'revocations': revocations,
            'modifications': modifications
        }

    def review_status_report(self, program_id: str = None) -> Dict[str, Any]:
        """
        Report on access review status.

        PURPOSE: Answer "Are access reviews current?"

        R EQUIVALENT:
            user_access %>%
              mutate(status = case_when(
                next_review_due <= today() ~ "Overdue",
                next_review_due <= today() + 30 ~ "Due Soon",
                TRUE ~ "Current"
              ))

        PARAMETERS:
            program_id: Filter to specific program (optional)

        RETURNS:
            Dict containing:
            - total_access: Total active access grants
            - current: Reviews current (not yet due)
            - due_soon: Reviews due in next 30 days
            - overdue: Reviews past due
            - details: List of access grants needing review

        WHY THIS APPROACH:
            SOC 2 requires periodic access reviews. This report shows
            at a glance whether the organization is keeping up.

        EXAMPLE:
            status = reports.review_status_report(program_id="P4M")
            if status['summary']['overdue'] > 0:
                print(f"WARNING: {status['summary']['overdue']} overdue reviews!")
        """
        cursor = self.am.conn.cursor()

        today = date.today()
        due_soon_date = (today + timedelta(days=30)).isoformat()
        today_str = today.isoformat()

        # Build base query
        base_query = """
            SELECT
                ua.access_id,
                ua.user_id,
                u.name as user_name,
                u.email,
                ua.role,
                ua.program_id,
                p.name as program_name,
                c.name as clinic_name,
                l.name as location_name,
                ua.granted_date,
                ua.review_cycle,
                ua.next_review_due,
                (SELECT MAX(ar.review_date)
                 FROM access_reviews ar
                 WHERE ar.access_id = ua.access_id) as last_review_date
            FROM user_access ua
            JOIN users u ON ua.user_id = u.user_id
            JOIN programs p ON ua.program_id = p.program_id
            LEFT JOIN clinics c ON ua.clinic_id = c.clinic_id
            LEFT JOIN locations l ON ua.location_id = l.location_id
            WHERE ua.is_active = TRUE
              AND u.status = 'Active'
        """

        params = []

        if program_id:
            resolved_program_id = self.am._resolve_program_id(program_id)
            base_query += " AND ua.program_id = ?"
            params.append(resolved_program_id)

        # Get all active access
        cursor.execute(base_query + " ORDER BY ua.next_review_due", params)
        all_access = [dict(row) for row in cursor.fetchall()]

        # Categorize by review status
        current = []
        due_soon = []
        overdue = []

        for access in all_access:
            if access['next_review_due'] is None:
                # No review scheduled - treat as due
                due_soon.append(access)
            elif access['next_review_due'] <= today_str:
                overdue.append(access)
            elif access['next_review_due'] <= due_soon_date:
                due_soon.append(access)
            else:
                current.append(access)

        return {
            'report_type': 'review_status',
            'report_date': datetime.now().isoformat(),
            'filters': {
                'program_id': program_id
            },
            'summary': {
                'total_access': len(all_access),
                'current': len(current),
                'due_soon': len(due_soon),
                'overdue': len(overdue),
                'compliance_percentage': (
                    round(len(current) / len(all_access) * 100, 1)
                    if all_access else 100
                )
            },
            'current': current,
            'due_soon': due_soon,
            'overdue': overdue
        }

    def overdue_reviews_report(self) -> Dict[str, Any]:
        """
        List all overdue access reviews.

        PURPOSE: Prioritized list of reviews that need immediate attention

        RETURNS:
            Dict with overdue reviews sorted by urgency (most overdue first)

        WHY THIS APPROACH:
            This is a focused report for compliance officers to work through.
            It's essentially a to-do list for catching up on reviews.
        """
        overdue = self.am.get_reviews_due()

        return {
            'report_type': 'overdue_reviews',
            'report_date': datetime.now().isoformat(),
            'summary': {
                'total_overdue': len(overdue),
                'oldest_overdue': overdue[0]['next_review_due'] if overdue else None,
                'max_days_overdue': int(overdue[0]['days_overdue']) if overdue else 0
            },
            'overdue_reviews': overdue
        }

    def training_compliance_report(self, program_id: str = None) -> Dict[str, Any]:
        """
        Report on training compliance for all users.

        PURPOSE: Answer "Is workforce training current?"

        PARAMETERS:
            program_id: Filter to users with access to this program (optional)

        RETURNS:
            Dict containing:
            - summary: Counts by training status
            - current: Users with all training current
            - expired: Users with expired training
            - missing: Users missing required training

        WHY THIS APPROACH:
            HIPAA requires workforce training. This report shows training
            status across the organization so gaps can be addressed.

        EXAMPLE:
            training = reports.training_compliance_report()
            if training['summary']['expired'] > 0:
                print(f"WARNING: {training['summary']['expired']} users need training renewal!")
        """
        cursor = self.am.conn.cursor()

        # Get all active users (optionally filtered by program access)
        if program_id:
            resolved_program_id = self.am._resolve_program_id(program_id)
            query = """
                SELECT DISTINCT u.*
                FROM users u
                JOIN user_access ua ON u.user_id = ua.user_id
                WHERE u.status = 'Active'
                  AND ua.is_active = TRUE
                  AND ua.program_id = ?
                ORDER BY u.name
            """
            cursor.execute(query, (resolved_program_id,))
        else:
            query = """
                SELECT * FROM users
                WHERE status = 'Active'
                ORDER BY name
            """
            cursor.execute(query)

        users = [dict(row) for row in cursor.fetchall()]

        # Check training for each user
        current_users = []
        expired_users = []
        missing_users = []

        # Required training types
        required_training = ['HIPAA Privacy', 'HIPAA Security']

        for user in users:
            training = self.am.get_training_status(user['user_id'])
            user_training = self._summarize_training(training)
            user['training_summary'] = user_training

            # Determine compliance status
            if user_training['expired_count'] > 0:
                expired_users.append(user)
            elif user_training['missing_count'] > 0:
                missing_users.append(user)
            else:
                current_users.append(user)

        return {
            'report_type': 'training_compliance',
            'report_date': datetime.now().isoformat(),
            'filters': {
                'program_id': program_id
            },
            'summary': {
                'total_users': len(users),
                'current': len(current_users),
                'expired': len(expired_users),
                'missing': len(missing_users),
                'compliance_percentage': (
                    round(len(current_users) / len(users) * 100, 1)
                    if users else 100
                )
            },
            'current_users': current_users,
            'expired_users': expired_users,
            'missing_users': missing_users
        }

    def terminated_user_audit(self) -> Dict[str, Any]:
        """
        CRITICAL: Find terminated users who still have active access.

        PURPOSE: This should ALWAYS return empty if compliant!
                 Any results indicate a serious compliance issue.

        RETURNS:
            Dict with any terminated users still having access

        WHY THIS APPROACH:
            HIPAA requires timely termination of access. This audit
            catches any gaps where the termination process failed.
            Run this regularly as part of compliance monitoring.

        AVIATION ANALOGY:
            Like checking that no one with a revoked medical certificate
            is still on the flight schedule. This should never happen,
            but we check to be absolutely sure.
        """
        terminated_with_access = self.am.get_terminated_with_access()

        # This is a critical finding if not empty
        is_compliant = len(terminated_with_access) == 0

        return {
            'report_type': 'terminated_audit',
            'report_date': datetime.now().isoformat(),
            'is_compliant': is_compliant,
            'summary': {
                'terminated_with_access': len(terminated_with_access),
                'status': 'PASS' if is_compliant else 'FAIL - IMMEDIATE ACTION REQUIRED'
            },
            'findings': terminated_with_access
        }

    def business_associate_report(self) -> Dict[str, Any]:
        """
        Report on external users (Business Associates) with access.

        PURPOSE: HIPAA BAA tracking - who outside the organization has access?

        RETURNS:
            Dict with all external users and their access scope

        WHY THIS APPROACH:
            HIPAA requires tracking Business Associates (external parties)
            who handle PHI. This report shows all external access for
            BAA compliance review.
        """
        external_users = self.am.get_external_users()

        # Group by organization
        by_org = {}
        for user in external_users:
            org = user['organization']
            if org not in by_org:
                by_org[org] = []
            by_org[org].append(user)

        return {
            'report_type': 'business_associates',
            'report_date': datetime.now().isoformat(),
            'summary': {
                'total_external_users': len(external_users),
                'organizations': len(by_org),
                'total_access_grants': sum(u['access_count'] for u in external_users)
            },
            'by_organization': by_org,
            'all_external_users': external_users
        }

    def segregation_of_duties_report(self, program_id: str = None) -> Dict[str, Any]:
        """
        Check all users for role conflicts.

        PURPOSE: SOC 2 segregation of duties verification

        PARAMETERS:
            program_id: Filter to specific program (optional)

        RETURNS:
            Dict with any users who have conflicting roles

        WHY THIS APPROACH:
            Segregation of duties is a key SOC 2 control. This report
            scans all access grants to find any combinations that violate
            the role_conflicts table.
        """
        cursor = self.am.conn.cursor()

        # Get all active access grouped by user and program
        query = """
            SELECT
                u.user_id,
                u.name as user_name,
                u.email,
                ua.program_id,
                p.name as program_name,
                GROUP_CONCAT(DISTINCT ua.role) as roles
            FROM user_access ua
            JOIN users u ON ua.user_id = u.user_id
            JOIN programs p ON ua.program_id = p.program_id
            WHERE ua.is_active = TRUE
              AND u.status = 'Active'
        """

        params = []

        if program_id:
            resolved_program_id = self.am._resolve_program_id(program_id)
            query += " AND ua.program_id = ?"
            params.append(resolved_program_id)

        query += " GROUP BY u.user_id, ua.program_id"

        cursor.execute(query, params)
        user_roles = [dict(row) for row in cursor.fetchall()]

        # Check each user for conflicts
        violations = []
        warnings = []

        for user_role in user_roles:
            roles = user_role['roles'].split(',') if user_role['roles'] else []

            # Check each role pair
            for i, role_a in enumerate(roles):
                for role_b in roles[i+1:]:
                    # Check for conflict
                    cursor.execute("""
                        SELECT * FROM role_conflicts
                        WHERE (role_a = ? AND role_b = ?)
                           OR (role_a = ? AND role_b = ?)
                    """, (role_a, role_b, role_b, role_a))

                    conflict = cursor.fetchone()
                    if conflict:
                        finding = {
                            'user_id': user_role['user_id'],
                            'user_name': user_role['user_name'],
                            'email': user_role['email'],
                            'program_name': user_role['program_name'],
                            'conflicting_roles': [role_a, role_b],
                            'severity': conflict['severity'],
                            'reason': conflict['conflict_reason']
                        }

                        if conflict['severity'] == 'Block':
                            violations.append(finding)
                        else:
                            warnings.append(finding)

        is_compliant = len(violations) == 0

        return {
            'report_type': 'segregation_of_duties',
            'report_date': datetime.now().isoformat(),
            'filters': {
                'program_id': program_id
            },
            'is_compliant': is_compliant,
            'summary': {
                'users_checked': len(user_roles),
                'blocking_violations': len(violations),
                'warnings': len(warnings),
                'status': 'PASS' if is_compliant else 'FAIL - BLOCKING VIOLATIONS FOUND'
            },
            'violations': violations,
            'warnings': warnings
        }

    def export_to_excel(
        self,
        report_type: str,
        output_path: str,
        **filters
    ) -> str:
        """
        Export any report to Excel for auditor review.

        PURPOSE: Create formatted Excel files for auditor handoff

        PARAMETERS:
            report_type: Which report to generate. Options:
                         'access_list', 'access_changes', 'review_status',
                         'overdue_reviews', 'training_compliance',
                         'terminated_audit', 'business_associates',
                         'segregation_of_duties'
            output_path: Where to save the Excel file
            **filters: Additional filters passed to the report method

        RETURNS:
            str: Path to the generated Excel file

        WHY THIS APPROACH:
            Auditors typically want Excel files they can review and annotate.
            We delegate to AccessExcelFormatter for the actual formatting.

        EXAMPLE:
            path = reports.export_to_excel(
                "access_list",
                "audit/q4_access_report.xlsx",
                program_id="P4M"
            )
        """
        # Import here to avoid circular import
        from formatters.access_excel_formatter import AccessExcelFormatter

        # Generate the report data
        report_methods = {
            'access_list': self.access_list_report,
            'access_changes': self.access_changes_report,
            'review_status': self.review_status_report,
            'overdue_reviews': self.overdue_reviews_report,
            'training_compliance': self.training_compliance_report,
            'terminated_audit': self.terminated_user_audit,
            'business_associates': self.business_associate_report,
            'segregation_of_duties': self.segregation_of_duties_report
        }

        if report_type not in report_methods:
            raise ValueError(
                f"Unknown report type: {report_type}. "
                f"Valid types: {list(report_methods.keys())}"
            )

        report_data = report_methods[report_type](**filters)

        # Export to Excel
        formatter = AccessExcelFormatter(self.am)
        return formatter.export_compliance_report(report_data, output_path)

    def _summarize_training(self, training_records: List[Dict]) -> Dict[str, Any]:
        """
        Summarize training records for a user.

        PURPOSE: Create a quick summary of training status

        PARAMETERS:
            training_records: List of training dicts from get_training_status

        RETURNS:
            Dict with counts and status by training type
        """
        summary = {
            'current_count': 0,
            'pending_count': 0,
            'expired_count': 0,
            'missing_count': 0,
            'by_type': {}
        }

        # Required training types
        required_types = {'HIPAA Privacy', 'HIPAA Security'}
        found_types = set()

        for record in training_records:
            training_type = record['training_type']
            status = record['status']
            found_types.add(training_type)

            summary['by_type'][training_type] = status

            if status == 'Current':
                summary['current_count'] += 1
            elif status == 'Pending':
                summary['pending_count'] += 1
            elif status == 'Expired':
                summary['expired_count'] += 1

        # Check for missing required training
        missing = required_types - found_types
        summary['missing_count'] = len(missing)
        summary['missing_types'] = list(missing)

        return summary

    def _calculate_access_summary(self, access_records: List[Dict]) -> Dict[str, Any]:
        """
        Calculate summary statistics for access list.

        PURPOSE: Provide high-level stats for report header

        PARAMETERS:
            access_records: List of access dicts

        RETURNS:
            Dict with counts by role, organization, etc.
        """
        # Count unique users
        unique_users = set(r['user_id'] for r in access_records)

        # Count by role
        by_role = {}
        for record in access_records:
            role = record['role']
            by_role[role] = by_role.get(role, 0) + 1

        # Count by organization
        by_org = {}
        for record in access_records:
            org = record['organization']
            by_org[org] = by_org.get(org, 0) + 1

        # Count external (business associates)
        external_count = sum(1 for r in access_records if r['is_business_associate'])

        return {
            'total_users': len(unique_users),
            'total_access_grants': len(access_records),
            'by_role': by_role,
            'by_organization': by_org,
            'external_users': external_count
        }


# =============================================================================
# MODULE TEST
# =============================================================================

if __name__ == "__main__":
    print("Testing ComplianceReports...")

    reports = ComplianceReports()

    # Show available reports
    print("\nAvailable reports:")
    print("  - access_list")
    print("  - access_changes")
    print("  - review_status")
    print("  - overdue_reviews")
    print("  - training_compliance")
    print("  - terminated_audit")
    print("  - business_associates")
    print("  - segregation_of_duties")

    print("\nUse: python -m reports.compliance_reports")
