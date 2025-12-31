"""
ACCESS MANAGER MODULE
====================
Manages user access for Part 11, HIPAA, and SOC 2 compliance tracking.

This module handles:
- User lifecycle management (create, update, terminate)
- Access provisioning and revocation with full audit trail
- Periodic access reviews (SOC 2 recertification)
- Training status tracking (HIPAA workforce training)
- Segregation of duties checks

Aviation Analogy:
    Think of this like managing crew certifications and authorizations:
    - Users are crew members with their ratings and medical certificates
    - Access grants are type ratings (what aircraft they can fly)
    - Reviews are recurrent training checks (proficiency checks)
    - Training records are ground school certificates
    - Role conflicts are crew pairing rules (can't be captain and mechanic)

Compliance Framework Coverage:
    Part 11:  Unique user IDs (user_id), authority checks (roles), audit trail
    HIPAA:    Minimum necessary (scoped access), termination procedures,
              workforce training, business associate tracking
    SOC 2:    Access provisioning, periodic reviews, segregation of duties
"""

from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path
from datetime import datetime, date, timedelta
import sqlite3
import json
import uuid
import os
import re


class AccessManager:
    """
    PURPOSE: Manage user access for Part 11, HIPAA, and SOC 2 compliance

    This class provides a complete access management system including:
    - User CRUD operations with status lifecycle
    - Access grant/revoke with scope hierarchy (program > clinic > location)
    - Periodic access review workflow
    - Training assignment and completion tracking
    - Segregation of duties validation
    - Full audit trail for all changes

    R EQUIVALENT:
        In R, you might use a combination of dplyr and custom functions
        with a SQLite backend. This class wraps all that into methods
        like create_user(), grant_access(), conduct_review(), etc.

    ATTRIBUTES:
        db_path: Path to the shared SQLite database
        conn: Active database connection

    EXAMPLE:
        am = AccessManager()
        am.initialize_schema()

        # Create user and grant access
        user_id = am.create_user("John Smith", "jsmith@clinic.com")
        access_id = am.grant_access(user_id, "P4M", "Coordinator",
                                     granted_by="Manager")

        # Conduct periodic review
        am.conduct_review(access_id, reviewed_by="Compliance",
                          status="Certified")
    """

    def __init__(self, db_path: str = None):
        """
        Initialize AccessManager with database connection.

        PURPOSE: Connect to the shared client product database

        R EQUIVALENT:
            con <- DBI::dbConnect(RSQLite::SQLite(), dbname = db_path)

        PARAMETERS:
            db_path: Path to SQLite database file. Defaults to the shared
                     location at ~/projects/data/client_product_database.db

        WHY THIS APPROACH:
            We use the same database as ConfigurationManager to maintain
            referential integrity with programs, clinics, and locations.
            The check_same_thread=False allows multi-threaded access which
            is important for concurrent CLI operations.
        """
        # Default to shared database location
        if db_path is None:
            db_path = "~/projects/data/client_product_database.db"

        # Always expand ~ in path (handles both default and user-provided paths)
        self.db_path = os.path.expanduser(db_path)

        # Ensure the data directory exists
        # This handles first-time setup gracefully
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Connect with row_factory for dict-like access
        # check_same_thread=False allows multi-threaded access
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Enable foreign key enforcement
        # Critical for referential integrity with programs/clinics/locations
        self.conn.execute("PRAGMA foreign_keys = ON")

    def initialize_schema(self) -> None:
        """
        Create access management tables from access_schema.sql.

        PURPOSE: Set up database tables for user access tracking

        R EQUIVALENT:
            DBI::dbExecute(con, readLines("access_schema.sql"))

        WHY THIS APPROACH:
            We read the SQL file rather than hardcoding CREATE statements
            because it keeps the schema definition in one place and makes
            it easier to review during audits.

        RAISES:
            FileNotFoundError: If access_schema.sql doesn't exist
        """
        # Find the schema file relative to this module
        schema_path = Path(__file__).parent.parent / "database" / "access_schema.sql"

        if not schema_path.exists():
            raise FileNotFoundError(
                f"Schema file not found: {schema_path}\n"
                "Make sure access_schema.sql is in the database/ directory."
            )

        # Read and execute the schema
        with open(schema_path, 'r') as f:
            schema_sql = f.read()

        # Execute the full schema (multiple statements)
        self.conn.executescript(schema_sql)
        self.conn.commit()

        print(f"Access schema initialized at {self.db_path}")

    # =========================================================================
    # USER OPERATIONS
    # =========================================================================
    # These methods manage the user lifecycle: create, read, update, terminate.
    # Every user gets a unique ID (Part 11 requirement) and all changes are
    # logged to the audit_history table.
    # =========================================================================

    def create_user(
        self,
        name: str,
        email: str,
        organization: str = 'Internal',
        is_business_associate: bool = False,
        notes: str = None
    ) -> str:
        """
        Create a new user record.

        PURPOSE: Add a new user to the system with a unique ID

        R EQUIVALENT:
            In R, you'd do:
            user_id <- paste0(substr(name, 1, 6), "-", uuid::UUIDgenerate())
            DBI::dbExecute(con, "INSERT INTO users ...")

        PARAMETERS:
            name: Full name (e.g., "John Smith")
            email: Email address (must be unique)
            organization: Company name. 'Internal' for employees,
                          company name for external users.
            is_business_associate: True if external party with HIPAA BAA
            notes: Optional free-text notes

        RETURNS:
            str: The generated user_id (e.g., "JSMITH-A1B2C3")

        WHY THIS APPROACH:
            We generate a readable user_id from the name plus a random suffix.
            This makes audit logs easier to read than opaque integers while
            still guaranteeing uniqueness.

        RAISES:
            ValueError: If email already exists

        EXAMPLE:
            user_id = am.create_user(
                "John Smith",
                "jsmith@clinic.com",
                organization="Portland Clinic"
            )
            # Returns: "JSMITH-A1B2C3"
        """
        cursor = self.conn.cursor()

        # Check for duplicate email
        cursor.execute("SELECT user_id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            raise ValueError(f"User with email '{email}' already exists")

        # Generate readable user_id from name
        # Take first initial + last name (up to 6 chars) + random suffix
        name_parts = name.upper().split()
        if len(name_parts) >= 2:
            # "John Smith" -> "JSMITH"
            prefix = name_parts[0][0] + name_parts[-1][:5]
        else:
            # Single name: take first 6 chars
            prefix = name_parts[0][:6]

        # Add random suffix for uniqueness
        suffix = uuid.uuid4().hex[:6].upper()
        user_id = f"{prefix}-{suffix}"

        # Insert the user record
        cursor.execute("""
            INSERT INTO users (user_id, name, email, organization,
                               is_business_associate, status, notes)
            VALUES (?, ?, ?, ?, ?, 'Active', ?)
        """, (user_id, name, email, organization, is_business_associate, notes))

        # Log to audit_history for Part 11 compliance
        self._log_audit(
            entity_type='user',
            entity_id=user_id,
            action='CREATE',
            new_value=json.dumps({
                'name': name,
                'email': email,
                'organization': organization,
                'is_business_associate': is_business_associate
            }),
            changed_by='system',
            reason='User created'
        )

        self.conn.commit()
        return user_id

    def update_user(
        self,
        user_id: str,
        changed_by: str,
        reason: str = None,
        **updates
    ) -> Dict[str, Any]:
        """
        Update user information.

        PURPOSE: Modify user details with full audit logging

        R EQUIVALENT:
            DBI::dbExecute(con, "UPDATE users SET ... WHERE user_id = ?")

        PARAMETERS:
            user_id: The user to update
            changed_by: Who is making the change (for audit)
            reason: Why the change is being made (for audit)
            **updates: Field=value pairs to update. Valid fields:
                       name, email, organization, is_business_associate,
                       status, notes

        RETURNS:
            Dict with old and new values for each changed field

        WHY THIS APPROACH:
            We capture old values before updating so the audit trail
            shows exactly what changed. This is required for Part 11.

        RAISES:
            ValueError: If user doesn't exist or invalid field specified

        EXAMPLE:
            am.update_user(
                "JSMITH-A1B2C3",
                changed_by="HR Admin",
                reason="Name change after marriage",
                name="Jane Doe-Smith"
            )
        """
        cursor = self.conn.cursor()

        # Get current values for audit comparison
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"User '{user_id}' not found")

        old_values = dict(row)

        # Validate update fields
        valid_fields = {'name', 'email', 'organization', 'is_business_associate',
                        'status', 'notes'}
        invalid_fields = set(updates.keys()) - valid_fields
        if invalid_fields:
            raise ValueError(f"Invalid fields: {invalid_fields}. Valid: {valid_fields}")

        if not updates:
            return {'message': 'No updates specified'}

        # Build and execute UPDATE statement
        set_clauses = [f"{field} = ?" for field in updates.keys()]
        set_clauses.append("updated_date = CURRENT_TIMESTAMP")

        values = list(updates.values()) + [user_id]

        cursor.execute(f"""
            UPDATE users
            SET {', '.join(set_clauses)}
            WHERE user_id = ?
        """, values)

        # Track changes for return and audit
        changes = {}
        for field, new_value in updates.items():
            old_value = old_values.get(field)
            if old_value != new_value:
                changes[field] = {'old': old_value, 'new': new_value}

        # Log to audit_history
        if changes:
            self._log_audit(
                entity_type='user',
                entity_id=user_id,
                action='UPDATE',
                old_value=json.dumps({k: v['old'] for k, v in changes.items()}),
                new_value=json.dumps({k: v['new'] for k, v in changes.items()}),
                changed_by=changed_by,
                reason=reason
            )

        self.conn.commit()
        return {'user_id': user_id, 'changes': changes}

    def terminate_user(
        self,
        user_id: str,
        reason: str,
        terminated_by: str
    ) -> Dict[str, Any]:
        """
        Terminate a user and revoke all their access.

        PURPOSE: Complete offboarding - mark user as Terminated and revoke
                 all active access grants. HIPAA requires timely termination
                 procedures.

        R EQUIVALENT:
            In R, you'd wrap these in a transaction:
            DBI::dbWithTransaction(con, {
              UPDATE users SET status = 'Terminated'
              UPDATE user_access SET is_active = FALSE
            })

        PARAMETERS:
            user_id: The user to terminate (ID or email)
            reason: Why the user is being terminated
            terminated_by: Who initiated the termination

        RETURNS:
            Dict with termination details and list of revoked access

        WHY THIS APPROACH:
            Termination is a critical compliance action. We automatically
            revoke all access to ensure no orphaned permissions remain.
            This is a HIPAA requirement for workforce termination.

        AVIATION ANALOGY:
            Like when a pilot retires - all type ratings are surrendered,
            medical certificate is cancelled, and badge access is revoked.
            Everything happens together to prevent gaps.

        RAISES:
            ValueError: If user not found

        EXAMPLE:
            result = am.terminate_user(
                "jsmith@clinic.com",
                reason="Employment ended",
                terminated_by="HR Admin"
            )
        """
        cursor = self.conn.cursor()

        # Support lookup by email or user_id
        if '@' in user_id:
            cursor.execute("SELECT user_id FROM users WHERE email = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"User with email '{user_id}' not found")
            user_id = row['user_id']
        else:
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not cursor.fetchone():
                raise ValueError(f"User '{user_id}' not found")

        # Get count of active access to revoke
        cursor.execute("""
            SELECT access_id, program_id, clinic_id, location_id, role
            FROM user_access
            WHERE user_id = ? AND is_active = TRUE
        """, (user_id,))
        active_access = [dict(row) for row in cursor.fetchall()]

        # Revoke all active access
        revoked_ids = []
        for access in active_access:
            cursor.execute("""
                UPDATE user_access
                SET is_active = FALSE,
                    revoked_date = date('now'),
                    revoked_by = ?,
                    revoke_reason = ?,
                    updated_date = CURRENT_TIMESTAMP
                WHERE access_id = ?
            """, (terminated_by, f"User terminated: {reason}", access['access_id']))
            revoked_ids.append(access['access_id'])

            # Log each revocation
            self._log_audit(
                entity_type='user_access',
                entity_id=str(access['access_id']),
                action='REVOKE',
                old_value=json.dumps({'is_active': True}),
                new_value=json.dumps({
                    'is_active': False,
                    'revoked_by': terminated_by,
                    'revoke_reason': f"User terminated: {reason}"
                }),
                changed_by=terminated_by,
                reason=f"Auto-revoked due to user termination"
            )

        # Mark user as Terminated
        cursor.execute("""
            UPDATE users
            SET status = 'Terminated',
                updated_date = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (user_id,))

        # Log termination
        self._log_audit(
            entity_type='user',
            entity_id=user_id,
            action='TERMINATE',
            old_value=json.dumps({'status': 'Active'}),
            new_value=json.dumps({'status': 'Terminated'}),
            changed_by=terminated_by,
            reason=reason
        )

        self.conn.commit()

        return {
            'user_id': user_id,
            'status': 'Terminated',
            'terminated_by': terminated_by,
            'reason': reason,
            'access_revoked': len(revoked_ids),
            'revoked_access_ids': revoked_ids
        }

    def get_user(
        self,
        user_id: str = None,
        email: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get user by ID or email.

        PURPOSE: Retrieve a single user's information

        R EQUIVALENT:
            DBI::dbGetQuery(con, "SELECT * FROM users WHERE ...")

        PARAMETERS:
            user_id: User ID to look up (optional if email provided)
            email: Email to look up (optional if user_id provided)

        RETURNS:
            Dict with user fields, or None if not found

        EXAMPLE:
            user = am.get_user(email="jsmith@clinic.com")
            print(user['name'])  # "John Smith"
        """
        cursor = self.conn.cursor()

        if user_id:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        elif email:
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        else:
            raise ValueError("Must provide either user_id or email")

        row = cursor.fetchone()
        return dict(row) if row else None

    def list_users(
        self,
        status_filter: str = None,
        organization_filter: str = None,
        program_filter: str = None,
        include_access_count: bool = True
    ) -> List[Dict[str, Any]]:
        """
        List users with optional filters.

        PURPOSE: Get a filtered list of users for display or reporting

        R EQUIVALENT:
            users %>%
              filter(status == status_filter) %>%
              left_join(access_counts)

        PARAMETERS:
            status_filter: Only show users with this status
                          ('Active', 'Inactive', 'Terminated')
            organization_filter: Only show users from this organization
            program_filter: Only show users with access to this program
                           (e.g., 'Prevention4ME', 'Precision4ME')
            include_access_count: If True, include count of active access grants

        RETURNS:
            List of user dicts, optionally with active_access_count

        EXAMPLE:
            active_users = am.list_users(status_filter='Active')
            external = am.list_users(organization_filter='Portland Clinic')
            prevention_users = am.list_users(program_filter='Prevention4ME')
        """
        cursor = self.conn.cursor()

        # Build query with optional joins and filters
        if include_access_count:
            query = """
                SELECT u.*,
                       COUNT(CASE WHEN ua.is_active = 1 THEN 1 END) as active_access_count
                FROM users u
                LEFT JOIN user_access ua ON u.user_id = ua.user_id
            """
        else:
            query = "SELECT * FROM users u"
            # If filtering by program, we need the join even without access count
            if program_filter:
                query = """
                    SELECT DISTINCT u.*
                    FROM users u
                    JOIN user_access ua ON u.user_id = ua.user_id
                """

        # Add program join if filtering by program
        if program_filter:
            query = query.rstrip()  # Remove trailing whitespace
            if "JOIN user_access" in query:
                query += """
                JOIN programs p ON ua.program_id = p.program_id
                """
            else:
                # Need to add both joins
                query = """
                    SELECT DISTINCT u.*
                    FROM users u
                    JOIN user_access ua ON u.user_id = ua.user_id
                    JOIN programs p ON ua.program_id = p.program_id
                """

        # Build WHERE clause
        conditions = []
        params = []

        if status_filter:
            conditions.append("u.status = ?")
            params.append(status_filter)

        if organization_filter:
            conditions.append("u.organization = ?")
            params.append(organization_filter)

        if program_filter:
            conditions.append("p.name = ?")
            params.append(program_filter)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        if include_access_count and not program_filter:
            query += " GROUP BY u.user_id"
        elif include_access_count and program_filter:
            query += " GROUP BY u.user_id"

        query += " ORDER BY u.name"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # ACCESS OPERATIONS
    # =========================================================================
    # These methods manage access grants: who has access to what scope with
    # what role. Every grant/revoke is logged for SOC 2 compliance.
    # =========================================================================

    def grant_access(
        self,
        user_id: str,
        program_id: str,
        role: str,
        granted_by: str,
        clinic_id: str = None,
        location_id: str = None,
        reason: str = None,
        ticket: str = None,
        review_cycle: str = 'Quarterly',
        permissions: List[str] = None
    ) -> int:
        """
        Grant access to a user.

        PURPOSE: Create a new access grant for a user at a specific scope

        R EQUIVALENT:
            DBI::dbExecute(con, "INSERT INTO user_access ...")

        PARAMETERS:
            user_id: Who is getting access (user_id or email)
            program_id: Which program (required - minimum scope)
            role: What role ('Admin', 'Provider', 'Coordinator',
                  'Read-Only', 'Auditor')
            granted_by: Who is granting the access
            clinic_id: Limit to specific clinic (optional)
            location_id: Limit to specific location (optional)
            reason: Why access is being granted
            ticket: Reference to approval ticket/email
            review_cycle: 'Quarterly' or 'Annual'
            permissions: Optional list of specific permissions

        RETURNS:
            int: The access_id of the new grant

        WHY THIS APPROACH:
            We check for segregation of duties conflicts before granting.
            If a blocking conflict exists, we reject the grant entirely.
            Warning conflicts allow the grant but flag it for review.

        AVIATION ANALOGY:
            Like assigning a type rating - we check prerequisites first
            (does the pilot have the base license?), then issue the rating
            with an expiration date for recurrent training.

        RAISES:
            ValueError: If user or program not found, or blocking conflict

        EXAMPLE:
            access_id = am.grant_access(
                user_id="jsmith@clinic.com",
                program_id="P4M",
                role="Coordinator",
                granted_by="Manager",
                clinic_id="Portland",
                reason="New hire"
            )
        """
        cursor = self.conn.cursor()

        # Resolve user_id from email if needed
        if '@' in user_id:
            cursor.execute("SELECT user_id FROM users WHERE email = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"User with email '{user_id}' not found")
            user_id = row['user_id']

        # Verify user exists and is active
        cursor.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            raise ValueError(f"User '{user_id}' not found")
        if user['status'] == 'Terminated':
            raise ValueError(f"Cannot grant access to terminated user '{user_id}'")

        # Resolve program_id from prefix if needed
        program_id = self._resolve_program_id(program_id)

        # Resolve clinic_id from name if needed
        if clinic_id:
            clinic_id = self._resolve_clinic_id(clinic_id, program_id)

        # Resolve location_id from name if needed
        if location_id:
            if not clinic_id:
                raise ValueError("Cannot specify location without clinic")
            location_id = self._resolve_location_id(location_id, clinic_id)

        # Check segregation of duties
        conflict_check = self.check_segregation_of_duties(user_id, role, program_id)
        if conflict_check['has_conflict']:
            for conflict in conflict_check['conflicts']:
                if conflict['severity'] == 'Block':
                    raise ValueError(
                        f"Segregation of duties violation: Cannot grant '{role}' "
                        f"to user with '{conflict['existing_role']}' role. "
                        f"Reason: {conflict['reason']}"
                    )

        # Calculate next review due date
        today = date.today()
        if review_cycle == 'Quarterly':
            next_review = today + timedelta(days=90)
        else:  # Annual
            next_review = today + timedelta(days=365)

        # Serialize permissions if provided
        permissions_json = json.dumps(permissions) if permissions else None

        # Insert the access grant
        cursor.execute("""
            INSERT INTO user_access (
                user_id, program_id, clinic_id, location_id, role,
                permissions, granted_date, granted_by, grant_reason,
                grant_ticket, is_active, review_cycle, next_review_due
            ) VALUES (?, ?, ?, ?, ?, ?, date('now'), ?, ?, ?, TRUE, ?, ?)
        """, (user_id, program_id, clinic_id, location_id, role,
              permissions_json, granted_by, reason, ticket, review_cycle,
              next_review.isoformat()))

        access_id = cursor.lastrowid

        # Log to audit_history
        self._log_audit(
            entity_type='user_access',
            entity_id=str(access_id),
            action='GRANT',
            new_value=json.dumps({
                'user_id': user_id,
                'program_id': program_id,
                'clinic_id': clinic_id,
                'location_id': location_id,
                'role': role,
                'granted_by': granted_by
            }),
            changed_by=granted_by,
            reason=reason
        )

        # If there were warning-level conflicts, log them too
        if conflict_check['has_conflict']:
            for conflict in conflict_check['conflicts']:
                if conflict['severity'] == 'Warning':
                    self._log_audit(
                        entity_type='user_access',
                        entity_id=str(access_id),
                        action='WARNING',
                        new_value=json.dumps(conflict),
                        changed_by='system',
                        reason=f"Segregation of duties warning: {conflict['reason']}"
                    )

        self.conn.commit()
        return access_id

    def revoke_access(
        self,
        access_id: int,
        revoked_by: str,
        reason: str
    ) -> Dict[str, Any]:
        """
        Revoke an access grant.

        PURPOSE: Remove access from a user with full audit trail

        R EQUIVALENT:
            DBI::dbExecute(con,
              "UPDATE user_access SET is_active=FALSE WHERE access_id=?")

        PARAMETERS:
            access_id: The access grant to revoke
            revoked_by: Who is revoking the access
            reason: Why access is being revoked

        RETURNS:
            Dict with revocation details

        WHY THIS APPROACH:
            We use soft-delete (is_active=FALSE) rather than hard delete
            so the audit trail shows what access existed and when it was
            revoked. This is required for SOC 2 and Part 11.

        RAISES:
            ValueError: If access_id not found or already revoked

        EXAMPLE:
            am.revoke_access(
                access_id=123,
                revoked_by="Manager",
                reason="Role change - no longer needs access"
            )
        """
        cursor = self.conn.cursor()

        # Get current access details
        cursor.execute("""
            SELECT ua.*, u.name as user_name, u.email
            FROM user_access ua
            JOIN users u ON ua.user_id = u.user_id
            WHERE ua.access_id = ?
        """, (access_id,))
        access = cursor.fetchone()

        if not access:
            raise ValueError(f"Access grant {access_id} not found")

        if not access['is_active']:
            raise ValueError(f"Access grant {access_id} is already revoked")

        # Revoke the access
        cursor.execute("""
            UPDATE user_access
            SET is_active = FALSE,
                revoked_date = date('now'),
                revoked_by = ?,
                revoke_reason = ?,
                updated_date = CURRENT_TIMESTAMP
            WHERE access_id = ?
        """, (revoked_by, reason, access_id))

        # Log to audit_history
        self._log_audit(
            entity_type='user_access',
            entity_id=str(access_id),
            action='REVOKE',
            old_value=json.dumps({
                'is_active': True,
                'role': access['role'],
                'program_id': access['program_id'],
                'clinic_id': access['clinic_id'],
                'location_id': access['location_id']
            }),
            new_value=json.dumps({
                'is_active': False,
                'revoked_by': revoked_by,
                'revoke_reason': reason
            }),
            changed_by=revoked_by,
            reason=reason
        )

        self.conn.commit()

        return {
            'access_id': access_id,
            'user_id': access['user_id'],
            'user_name': access['user_name'],
            'role': access['role'],
            'revoked_by': revoked_by,
            'reason': reason
        }

    def modify_access(
        self,
        access_id: int,
        modified_by: str,
        reason: str,
        **updates
    ) -> Dict[str, Any]:
        """
        Modify an existing access grant.

        PURPOSE: Change role, scope, or review cycle of an access grant

        PARAMETERS:
            access_id: The access grant to modify
            modified_by: Who is making the change
            reason: Why the change is being made
            **updates: Field=value pairs. Valid fields:
                       role, clinic_id, location_id, review_cycle, permissions

        RETURNS:
            Dict with old and new values

        WHY THIS APPROACH:
            Sometimes access needs to be adjusted rather than fully revoked
            and re-granted. We track all changes for audit purposes.

        RAISES:
            ValueError: If access_id not found or invalid field
        """
        cursor = self.conn.cursor()

        # Get current access details
        cursor.execute("SELECT * FROM user_access WHERE access_id = ?", (access_id,))
        access = cursor.fetchone()

        if not access:
            raise ValueError(f"Access grant {access_id} not found")

        if not access['is_active']:
            raise ValueError(f"Cannot modify revoked access grant {access_id}")

        old_values = dict(access)

        # Validate update fields
        valid_fields = {'role', 'clinic_id', 'location_id', 'review_cycle', 'permissions'}
        invalid_fields = set(updates.keys()) - valid_fields
        if invalid_fields:
            raise ValueError(f"Invalid fields: {invalid_fields}. Valid: {valid_fields}")

        if not updates:
            return {'message': 'No updates specified'}

        # Handle permissions serialization
        if 'permissions' in updates and updates['permissions'] is not None:
            updates['permissions'] = json.dumps(updates['permissions'])

        # Build and execute UPDATE
        set_clauses = [f"{field} = ?" for field in updates.keys()]
        set_clauses.append("updated_date = CURRENT_TIMESTAMP")

        values = list(updates.values()) + [access_id]

        cursor.execute(f"""
            UPDATE user_access
            SET {', '.join(set_clauses)}
            WHERE access_id = ?
        """, values)

        # Track changes
        changes = {}
        for field, new_value in updates.items():
            old_value = old_values.get(field)
            if old_value != new_value:
                changes[field] = {'old': old_value, 'new': new_value}

        # Log to audit_history
        if changes:
            self._log_audit(
                entity_type='user_access',
                entity_id=str(access_id),
                action='MODIFY',
                old_value=json.dumps({k: v['old'] for k, v in changes.items()}),
                new_value=json.dumps({k: v['new'] for k, v in changes.items()}),
                changed_by=modified_by,
                reason=reason
            )

        self.conn.commit()
        return {'access_id': access_id, 'changes': changes}

    def get_user_access(
        self,
        user_id: str,
        active_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all access grants for a user.

        PURPOSE: See what access a user has (or had)

        PARAMETERS:
            user_id: User to look up (user_id or email)
            active_only: If True, only show active access

        RETURNS:
            List of access grant dicts with program/clinic/location names

        EXAMPLE:
            access_list = am.get_user_access("jsmith@clinic.com")
            for access in access_list:
                print(f"{access['role']} on {access['program_name']}")
        """
        cursor = self.conn.cursor()

        # Resolve user_id from email if needed
        if '@' in user_id:
            cursor.execute("SELECT user_id FROM users WHERE email = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"User with email '{user_id}' not found")
            user_id = row['user_id']

        query = """
            SELECT
                ua.*,
                p.name as program_name,
                p.prefix as program_prefix,
                c.name as clinic_name,
                l.name as location_name
            FROM user_access ua
            JOIN programs p ON ua.program_id = p.program_id
            LEFT JOIN clinics c ON ua.clinic_id = c.clinic_id
            LEFT JOIN locations l ON ua.location_id = l.location_id
            WHERE ua.user_id = ?
        """

        if active_only:
            query += " AND ua.is_active = TRUE"

        query += " ORDER BY ua.granted_date DESC"

        cursor.execute(query, (user_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_access_by_scope(
        self,
        program_id: str = None,
        clinic_id: str = None,
        location_id: str = None,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all users with access to a specific scope.

        PURPOSE: See who has access to a program/clinic/location

        PARAMETERS:
            program_id: Filter by program (prefix or ID)
            clinic_id: Filter by clinic (name or ID)
            location_id: Filter by location (name or ID)
            active_only: If True, only show active access

        RETURNS:
            List of access grants with user details

        EXAMPLE:
            # Who has access to Portland clinic?
            portland_access = am.get_access_by_scope(
                program_id="P4M",
                clinic_id="Portland"
            )
        """
        cursor = self.conn.cursor()

        # Resolve IDs from names/prefixes
        if program_id:
            program_id = self._resolve_program_id(program_id)
        if clinic_id and program_id:
            clinic_id = self._resolve_clinic_id(clinic_id, program_id)
        if location_id and clinic_id:
            location_id = self._resolve_location_id(location_id, clinic_id)

        query = """
            SELECT
                ua.*,
                u.name as user_name,
                u.email,
                u.organization,
                p.name as program_name,
                c.name as clinic_name,
                l.name as location_name
            FROM user_access ua
            JOIN users u ON ua.user_id = u.user_id
            JOIN programs p ON ua.program_id = p.program_id
            LEFT JOIN clinics c ON ua.clinic_id = c.clinic_id
            LEFT JOIN locations l ON ua.location_id = l.location_id
            WHERE 1=1
        """

        params = []

        if program_id:
            query += " AND ua.program_id = ?"
            params.append(program_id)

        if clinic_id:
            query += " AND (ua.clinic_id = ? OR ua.clinic_id IS NULL)"
            params.append(clinic_id)

        if location_id:
            query += " AND (ua.location_id = ? OR ua.location_id IS NULL)"
            params.append(location_id)

        if active_only:
            query += " AND ua.is_active = TRUE"

        query += " ORDER BY u.name, ua.granted_date DESC"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # ACCESS REVIEW OPERATIONS
    # =========================================================================
    # SOC 2 requires periodic review of access grants. These methods support
    # the review workflow: find what's due, conduct reviews, track history.
    # =========================================================================

    def get_reviews_due(
        self,
        as_of_date: str = None,
        program_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get access grants with overdue or upcoming reviews.

        PURPOSE: Find access that needs recertification

        R EQUIVALENT:
            user_access %>%
              filter(next_review_due <= as_of_date, is_active == TRUE)

        PARAMETERS:
            as_of_date: Date to check against (default: today)
            program_id: Filter to specific program

        RETURNS:
            List of access grants needing review, sorted by most overdue first

        WHY THIS APPROACH:
            Quarterly reviews are a SOC 2 requirement. This method makes it
            easy to generate a review worksheet or compliance dashboard.

        EXAMPLE:
            overdue = am.get_reviews_due()
            for access in overdue:
                print(f"{access['user_name']} - {access['days_overdue']} days overdue")
        """
        cursor = self.conn.cursor()

        if as_of_date is None:
            as_of_date = date.today().isoformat()

        # Resolve program_id if provided
        if program_id:
            program_id = self._resolve_program_id(program_id)

        query = """
            SELECT
                ua.*,
                u.name as user_name,
                u.email,
                p.name as program_name,
                p.prefix as program_prefix,
                c.name as clinic_name,
                l.name as location_name,
                julianday(?) - julianday(ua.next_review_due) as days_overdue,
                (SELECT MAX(ar.review_date)
                 FROM access_reviews ar
                 WHERE ar.access_id = ua.access_id) as last_review_date
            FROM user_access ua
            JOIN users u ON ua.user_id = u.user_id
            JOIN programs p ON ua.program_id = p.program_id
            LEFT JOIN clinics c ON ua.clinic_id = c.clinic_id
            LEFT JOIN locations l ON ua.location_id = l.location_id
            WHERE ua.is_active = TRUE
              AND ua.next_review_due <= ?
        """

        params = [as_of_date, as_of_date]

        if program_id:
            query += " AND ua.program_id = ?"
            params.append(program_id)

        query += " ORDER BY ua.next_review_due ASC"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def conduct_review(
        self,
        access_id: int,
        reviewed_by: str,
        status: str,
        notes: str = None
    ) -> Dict[str, Any]:
        """
        Record an access review.

        PURPOSE: Document periodic access recertification

        R EQUIVALENT:
            DBI::dbExecute(con, "INSERT INTO access_reviews ...")

        PARAMETERS:
            access_id: The access grant being reviewed
            reviewed_by: Who conducted the review
            status: Review decision:
                    'Certified' = Access confirmed, schedule next review
                    'Revoked' = Access no longer needed, revoke it
                    'Modified' = Access will be changed (call modify_access next)
            notes: Reviewer's notes explaining the decision

        RETURNS:
            Dict with review details

        WHY THIS APPROACH:
            Each review is recorded in access_reviews table with its own ID.
            This creates an immutable audit trail showing when each access
            grant was reviewed and by whom.

        AVIATION ANALOGY:
            Like logging a proficiency check in a pilot's records.
            The check ride examiner signs off, the date is recorded,
            and the next check ride date is calculated.

        RAISES:
            ValueError: If access_id not found or invalid status

        EXAMPLE:
            am.conduct_review(
                access_id=123,
                reviewed_by="Compliance Officer",
                status="Certified",
                notes="Confirmed with dept manager, still needs access"
            )
        """
        cursor = self.conn.cursor()

        if status not in ('Certified', 'Revoked', 'Modified'):
            raise ValueError(f"Invalid status: {status}. Must be Certified, Revoked, or Modified")

        # Get current access details
        cursor.execute("""
            SELECT ua.*, u.name as user_name
            FROM user_access ua
            JOIN users u ON ua.user_id = u.user_id
            WHERE ua.access_id = ?
        """, (access_id,))
        access = cursor.fetchone()

        if not access:
            raise ValueError(f"Access grant {access_id} not found")

        if not access['is_active']:
            raise ValueError(f"Cannot review revoked access grant {access_id}")

        # Calculate next review due (only for Certified status)
        next_review_due = None
        if status == 'Certified':
            today = date.today()
            if access['review_cycle'] == 'Quarterly':
                next_review_due = today + timedelta(days=90)
            else:
                next_review_due = today + timedelta(days=365)

        # Insert review record
        cursor.execute("""
            INSERT INTO access_reviews (
                access_id, review_date, reviewed_by, status, notes, next_review_due
            ) VALUES (?, date('now'), ?, ?, ?, ?)
        """, (access_id, reviewed_by, status, notes,
              next_review_due.isoformat() if next_review_due else None))

        review_id = cursor.lastrowid

        # Update the access grant's next_review_due
        if status == 'Certified':
            cursor.execute("""
                UPDATE user_access
                SET next_review_due = ?,
                    updated_date = CURRENT_TIMESTAMP
                WHERE access_id = ?
            """, (next_review_due.isoformat(), access_id))

        # If Revoked, actually revoke the access
        if status == 'Revoked':
            self.conn.commit()  # Commit review first
            self.revoke_access(access_id, reviewed_by,
                               f"Revoked during access review: {notes or 'No longer needed'}")

        # Log to audit_history
        self._log_audit(
            entity_type='access_reviews',
            entity_id=str(review_id),
            action='REVIEW',
            new_value=json.dumps({
                'access_id': access_id,
                'user_name': access['user_name'],
                'status': status,
                'reviewed_by': reviewed_by
            }),
            changed_by=reviewed_by,
            reason=notes or f"Access review: {status}"
        )

        self.conn.commit()

        return {
            'review_id': review_id,
            'access_id': access_id,
            'user_name': access['user_name'],
            'status': status,
            'reviewed_by': reviewed_by,
            'notes': notes,
            'next_review_due': next_review_due.isoformat() if next_review_due else None
        }

    def get_review_history(self, access_id: int) -> List[Dict[str, Any]]:
        """
        Get all reviews for an access grant.

        PURPOSE: Show the review history for audit purposes

        PARAMETERS:
            access_id: The access grant to look up

        RETURNS:
            List of review records, newest first
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT *
            FROM access_reviews
            WHERE access_id = ?
            ORDER BY review_date DESC
        """, (access_id,))

        return [dict(row) for row in cursor.fetchall()]

    def bulk_review(
        self,
        access_ids: List[int],
        reviewed_by: str,
        status: str,
        notes: str = None
    ) -> Dict[str, Any]:
        """
        Conduct review for multiple access grants at once.

        PURPOSE: Efficiently process batch reviews during quarterly review sessions

        PARAMETERS:
            access_ids: List of access grants to review
            reviewed_by: Who conducted the reviews
            status: Review decision (same for all)
            notes: Reviewer notes (same for all)

        RETURNS:
            Dict with success/failure counts

        EXAMPLE:
            result = am.bulk_review(
                access_ids=[1, 2, 3, 4],
                reviewed_by="Compliance",
                status="Certified",
                notes="Quarterly review - all confirmed"
            )
        """
        results = {'success': 0, 'failed': 0, 'errors': []}

        for access_id in access_ids:
            try:
                self.conduct_review(access_id, reviewed_by, status, notes)
                results['success'] += 1
            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'access_id': access_id,
                    'error': str(e)
                })

        return results

    def process_review_response(
        self,
        file_path: str,
        reviewed_by: str,
        preview_only: bool = True
    ) -> Dict[str, Any]:
        """
        Process a completed annual access review response file.

        PURPOSE: Import clinic manager's review decisions (keep/terminate/update).

        PARAMETERS:
            file_path: Path to completed Excel review file
            reviewed_by: Who completed the review (clinic manager name)
            preview_only: If True, show what would happen without making changes

        RETURNS:
            Dict with preview actions, summary counts, and any errors

        ACTION LOGIC:
            - Blank/empty → Recertify (mark as reviewed, set next review date)
            - "Terminate" → Revoke access with reason from Manager Notes
            - "Update" → Change role to New Role value, then mark as reviewed

        EXAMPLE:
            result = am.process_review_response(
                file_path="~/Downloads/Franz_Review_Completed.xlsx",
                reviewed_by="Jerry Cain",
                preview_only=True
            )
        """
        import pandas as pd

        # Valid role values
        VALID_ROLES = ['Read-Write-Order', 'Read-Write', 'Read-Only', 'Admin', 'Provider', 'Coordinator', 'Auditor']

        # Expand path and read Excel
        file_path = os.path.expanduser(file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        df = pd.read_excel(file_path)

        # Normalize column names
        df.columns = [col.strip() for col in df.columns]

        # Check for required columns
        required_cols = ['Email', 'Action']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}. Is this a review status export file?")

        results = {
            'preview': [],
            'summary': {
                'total_rows': len(df),
                'recertified': 0,
                'terminated': 0,
                'updated': 0,
                'skipped': 0,
                'errors': 0
            },
            'errors': [],
            'preview_only': preview_only
        }

        cursor = self.conn.cursor()
        today = date.today()

        for idx, row in df.iterrows():
            row_num = idx + 2  # Excel row number

            try:
                email = str(row.get('Email', '')).strip().lower()
                action = str(row.get('Action', '')).strip()
                new_role = str(row.get('New Role', '')).strip()
                manager_notes = str(row.get('Manager Notes', '')).strip()
                program = str(row.get('Program', '')).strip()
                clinic = str(row.get('Clinic', '')).strip()
                current_role = str(row.get('Role', '')).strip()

                # Skip rows without email
                if not email or email == 'nan' or '@' not in email:
                    results['summary']['skipped'] += 1
                    continue

                # Clean up nan values
                if action.lower() == 'nan':
                    action = ''
                if new_role.lower() == 'nan':
                    new_role = ''
                if manager_notes.lower() == 'nan':
                    manager_notes = ''

                # Find the user
                cursor.execute("SELECT user_id, name FROM users WHERE LOWER(email) = ?", (email,))
                user_row = cursor.fetchone()

                if not user_row:
                    results['errors'].append({
                        'row': row_num,
                        'email': email,
                        'error': 'User not found in database'
                    })
                    results['summary']['errors'] += 1
                    continue

                user_id = user_row['user_id']
                user_name = user_row['name']

                # Find the access grant for this program/clinic
                # We need to match on program and clinic from the review file
                query = """
                    SELECT ua.access_id, ua.role, ua.program_id, ua.clinic_id,
                           p.name as program_name, c.name as clinic_name
                    FROM user_access ua
                    JOIN programs p ON ua.program_id = p.program_id
                    LEFT JOIN clinics c ON ua.clinic_id = c.clinic_id
                    WHERE ua.user_id = ? AND ua.is_active = TRUE
                """
                params = [user_id]

                cursor.execute(query, params)
                access_grants = cursor.fetchall()

                # Find matching access grant
                matching_access = None
                for grant in access_grants:
                    grant_program = grant['program_name'] or ''
                    grant_clinic = grant['clinic_name'] or ''

                    # Match on program and clinic (clinic may be empty)
                    if program and grant_program.lower() == program.lower():
                        if clinic and clinic.lower() != 'nan':
                            if grant_clinic.lower() == clinic.lower():
                                matching_access = grant
                                break
                        else:
                            # No clinic specified, match on program only
                            matching_access = grant
                            break

                if not matching_access:
                    results['errors'].append({
                        'row': row_num,
                        'email': email,
                        'error': f'No active access found for program: {program}, clinic: {clinic}'
                    })
                    results['summary']['errors'] += 1
                    continue

                access_id = matching_access['access_id']

                # Build action record
                action_record = {
                    'row': row_num,
                    'name': user_name,
                    'email': email,
                    'program': program,
                    'clinic': clinic or '(Program-wide)',
                    'current_role': matching_access['role'],
                    'action': None,
                    'details': None
                }

                # Process based on action value
                action_upper = action.upper().strip()

                if action_upper == '' or action_upper == 'KEEP':
                    # Recertify - mark as reviewed
                    action_record['action'] = 'RECERTIFY'
                    action_record['details'] = 'Access confirmed, next review scheduled'

                    if not preview_only:
                        self.conduct_review(
                            access_id=access_id,
                            reviewed_by=reviewed_by,
                            status='Certified',
                            notes=manager_notes if manager_notes else 'Annual review - access confirmed'
                        )

                    results['summary']['recertified'] += 1

                elif action_upper == 'TERMINATE':
                    # Revoke access
                    if not manager_notes:
                        results['errors'].append({
                            'row': row_num,
                            'email': email,
                            'error': 'Manager Notes required for Terminate action'
                        })
                        results['summary']['errors'] += 1
                        continue

                    action_record['action'] = 'TERMINATE'
                    action_record['details'] = f'Revoke access. Reason: {manager_notes}'

                    if not preview_only:
                        self.revoke_access(
                            access_id=access_id,
                            revoked_by=reviewed_by,
                            reason=manager_notes
                        )

                    results['summary']['terminated'] += 1

                elif action_upper == 'UPDATE':
                    # Update role
                    if not new_role:
                        results['errors'].append({
                            'row': row_num,
                            'email': email,
                            'error': 'New Role required for Update action'
                        })
                        results['summary']['errors'] += 1
                        continue

                    # Normalize role value
                    role_map = {
                        'READ-WRITE-ORDER': 'Read-Write-Order',
                        'READ + WRITE + ORDER': 'Read-Write-Order',
                        'READ-WRITE': 'Read-Write',
                        'READ + WRITE': 'Read-Write',
                        'READ-ONLY': 'Read-Only',
                        'READ ONLY': 'Read-Only',
                        'ADMIN': 'Admin',
                        'PROVIDER': 'Provider',
                        'COORDINATOR': 'Coordinator',
                        'AUDITOR': 'Auditor',
                    }
                    normalized_role = role_map.get(new_role.upper(), new_role)

                    if normalized_role not in VALID_ROLES:
                        results['errors'].append({
                            'row': row_num,
                            'email': email,
                            'error': f'Invalid New Role: {new_role}. Must be one of: {VALID_ROLES}'
                        })
                        results['summary']['errors'] += 1
                        continue

                    action_record['action'] = 'UPDATE'
                    action_record['new_role'] = normalized_role
                    action_record['details'] = f'Change role from {matching_access["role"]} to {normalized_role}'
                    if manager_notes:
                        action_record['details'] += f'. Reason: {manager_notes}'

                    if not preview_only:
                        # Update the role
                        cursor.execute("""
                            UPDATE user_access
                            SET role = ?, updated_date = CURRENT_TIMESTAMP
                            WHERE access_id = ?
                        """, (normalized_role, access_id))

                        # Log audit
                        self._log_audit(
                            entity_type='user_access',
                            entity_id=str(access_id),
                            action='UPDATE',
                            old_value=json.dumps({'role': matching_access['role']}),
                            new_value=json.dumps({'role': normalized_role}),
                            changed_by=reviewed_by,
                            reason=manager_notes if manager_notes else 'Annual review - role updated'
                        )

                        # Complete the review
                        self.conduct_review(
                            access_id=access_id,
                            reviewed_by=reviewed_by,
                            status='Modified',
                            notes=f"Role changed from {matching_access['role']} to {normalized_role}. {manager_notes}"
                        )

                    results['summary']['updated'] += 1

                else:
                    results['errors'].append({
                        'row': row_num,
                        'email': email,
                        'error': f'Invalid Action: {action}. Must be blank, Terminate, or Update'
                    })
                    results['summary']['errors'] += 1
                    continue

                results['preview'].append(action_record)

            except Exception as e:
                results['errors'].append({
                    'row': row_num,
                    'email': str(row.get('Email', 'unknown')),
                    'error': str(e)
                })
                results['summary']['errors'] += 1

        if not preview_only:
            self.conn.commit()

        return results

    # =========================================================================
    # TRAINING OPERATIONS
    # =========================================================================
    # HIPAA requires workforce training. These methods track training
    # assignments, completions, and expirations.
    # =========================================================================

    def assign_training(
        self,
        user_id: str,
        training_type: str,
        assigned_by: str,
        expires_in_days: int = 365,
        responsibility: str = 'Propel Health'
    ) -> int:
        """
        Assign training to a user.

        PURPOSE: Record that a user needs to complete specific training

        R EQUIVALENT:
            DBI::dbExecute(con, "INSERT INTO user_training ...")

        PARAMETERS:
            user_id: User to assign training to (user_id or email)
            training_type: Type of training. Active types: 'HIPAA', 'Cybersecurity',
                          'Application Training'. Reserved: 'SOC 2', 'HITRUST', 'Part 11'
            assigned_by: Who assigned the training
            expires_in_days: Days after completion before training expires
            responsibility: Who maintains training records:
                          - 'Client': Client organization maintains records
                          - 'Propel Health': PHP maintains records internally (default)

        RETURNS:
            int: The training_id

        EXAMPLE:
            training_id = am.assign_training(
                user_id="jsmith@clinic.com",
                training_type="HIPAA",
                assigned_by="Compliance",
                responsibility="Client"  # Client tracks their own training
            )
        """
        cursor = self.conn.cursor()

        # Resolve user_id from email if needed
        if '@' in user_id:
            cursor.execute("SELECT user_id FROM users WHERE email = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"User with email '{user_id}' not found")
            user_id = row['user_id']

        # Check if user already has this training type pending
        cursor.execute("""
            SELECT training_id FROM user_training
            WHERE user_id = ? AND training_type = ? AND status = 'Pending'
        """, (user_id, training_type))

        if cursor.fetchone():
            raise ValueError(f"User already has pending {training_type} training")

        # Insert training assignment with responsibility tracking
        cursor.execute("""
            INSERT INTO user_training (
                user_id, training_type, responsibility, status, assigned_date, assigned_by
            ) VALUES (?, ?, ?, 'Pending', date('now'), ?)
        """, (user_id, training_type, responsibility, assigned_by))

        training_id = cursor.lastrowid

        # Log to audit_history
        self._log_audit(
            entity_type='user_training',
            entity_id=str(training_id),
            action='ASSIGN',
            new_value=json.dumps({
                'user_id': user_id,
                'training_type': training_type,
                'responsibility': responsibility,
                'assigned_by': assigned_by
            }),
            changed_by=assigned_by,
            reason=f"Training assigned: {training_type}"
        )

        self.conn.commit()
        return training_id

    def complete_training(
        self,
        training_id: int,
        completed_date: str = None,
        certificate_reference: str = None,
        expires_in_days: int = 365
    ) -> Dict[str, Any]:
        """
        Mark training as completed.

        PURPOSE: Record that a user has completed required training

        PARAMETERS:
            training_id: The training assignment to complete
            completed_date: When training was completed (default: today)
            certificate_reference: Link or ID of completion certificate
            expires_in_days: Days until training expires

        RETURNS:
            Dict with completion details

        EXAMPLE:
            am.complete_training(
                training_id=456,
                completed_date="2025-12-19",
                certificate_reference="CERT-12345"
            )
        """
        cursor = self.conn.cursor()

        if completed_date is None:
            completed_date = date.today().isoformat()

        # Parse completion date and calculate expiration
        completion = datetime.fromisoformat(completed_date).date()
        expires_date = completion + timedelta(days=expires_in_days)

        # Get current training details
        cursor.execute("""
            SELECT ut.*, u.name as user_name
            FROM user_training ut
            JOIN users u ON ut.user_id = u.user_id
            WHERE ut.training_id = ?
        """, (training_id,))
        training = cursor.fetchone()

        if not training:
            raise ValueError(f"Training {training_id} not found")

        # Update training record
        cursor.execute("""
            UPDATE user_training
            SET status = 'Current',
                completed_date = ?,
                expires_date = ?,
                certificate_reference = ?,
                updated_date = CURRENT_TIMESTAMP
            WHERE training_id = ?
        """, (completed_date, expires_date.isoformat(), certificate_reference, training_id))

        # Log to audit_history
        self._log_audit(
            entity_type='user_training',
            entity_id=str(training_id),
            action='COMPLETE',
            old_value=json.dumps({'status': training['status']}),
            new_value=json.dumps({
                'status': 'Current',
                'completed_date': completed_date,
                'expires_date': expires_date.isoformat()
            }),
            changed_by='system',
            reason=f"Training completed: {training['training_type']}"
        )

        self.conn.commit()

        return {
            'training_id': training_id,
            'user_id': training['user_id'],
            'user_name': training['user_name'],
            'training_type': training['training_type'],
            'completed_date': completed_date,
            'expires_date': expires_date.isoformat(),
            'certificate_reference': certificate_reference
        }

    def get_training_status(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all training records for a user.

        PURPOSE: See what training a user has completed or needs

        PARAMETERS:
            user_id: User to look up (user_id or email)

        RETURNS:
            List of training records with status
        """
        cursor = self.conn.cursor()

        # Resolve user_id from email if needed
        if '@' in user_id:
            cursor.execute("SELECT user_id FROM users WHERE email = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"User with email '{user_id}' not found")
            user_id = row['user_id']

        # Update expired training status first
        self._update_expired_training()

        cursor.execute("""
            SELECT *
            FROM user_training
            WHERE user_id = ?
            ORDER BY training_type, completed_date DESC
        """, (user_id,))

        return [dict(row) for row in cursor.fetchall()]

    def get_expired_training(self, as_of_date: str = None) -> List[Dict[str, Any]]:
        """
        Get all users with expired or expiring training.

        PURPOSE: Find training that needs renewal

        PARAMETERS:
            as_of_date: Date to check against (default: today)

        RETURNS:
            List of expired/expiring training records
        """
        cursor = self.conn.cursor()

        if as_of_date is None:
            as_of_date = date.today().isoformat()

        # Update expired status first
        self._update_expired_training()

        # Get expired or soon-to-expire training (within 30 days)
        check_date = (date.fromisoformat(as_of_date) + timedelta(days=30)).isoformat()

        cursor.execute("""
            SELECT
                ut.*,
                u.name as user_name,
                u.email,
                julianday(ut.expires_date) - julianday(?) as days_until_expiry
            FROM user_training ut
            JOIN users u ON ut.user_id = u.user_id
            WHERE u.status = 'Active'
              AND ut.expires_date IS NOT NULL
              AND ut.expires_date <= ?
            ORDER BY ut.expires_date ASC
        """, (as_of_date, check_date))

        return [dict(row) for row in cursor.fetchall()]

    def get_users_missing_training(self, training_type: str) -> List[Dict[str, Any]]:
        """
        Get active users who don't have current training of this type.

        PURPOSE: Find users who need to be assigned specific training

        PARAMETERS:
            training_type: The training type to check for

        RETURNS:
            List of users missing this training
        """
        cursor = self.conn.cursor()

        # Update expired status first
        self._update_expired_training()

        cursor.execute("""
            SELECT u.*
            FROM users u
            WHERE u.status = 'Active'
              AND u.user_id NOT IN (
                  SELECT ut.user_id
                  FROM user_training ut
                  WHERE ut.training_type = ?
                    AND ut.status = 'Current'
              )
            ORDER BY u.name
        """, (training_type,))

        return [dict(row) for row in cursor.fetchall()]

    def _update_expired_training(self) -> None:
        """
        Update status of expired training records.

        PURPOSE: Ensure training status reflects current expiration state

        WHY THIS APPROACH:
            Rather than recalculating status on every query, we update
            the status field when records actually expire. This runs
            automatically before training queries.
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            UPDATE user_training
            SET status = 'Expired',
                updated_date = CURRENT_TIMESTAMP
            WHERE status = 'Current'
              AND expires_date < date('now')
        """)

        if cursor.rowcount > 0:
            self.conn.commit()

    # =========================================================================
    # COMPLIANCE CHECKS
    # =========================================================================
    # These methods support compliance audits by identifying potential issues.
    # =========================================================================

    def check_segregation_of_duties(
        self,
        user_id: str,
        new_role: str,
        program_id: str
    ) -> Dict[str, Any]:
        """
        Check if granting new_role would violate segregation of duties.

        PURPOSE: Prevent conflicting role combinations

        R EQUIVALENT:
            In R, you'd do a join between user's existing roles and
            the role_conflicts table to find matches.

        PARAMETERS:
            user_id: User who would receive the new role
            new_role: The role being considered
            program_id: The program context (roles are scoped by program)

        RETURNS:
            Dict with:
            - has_conflict: True if any conflicts found
            - conflicts: List of conflict details

        WHY THIS APPROACH:
            Segregation of duties is a key SOC 2 control. By checking
            at grant time, we prevent violations rather than just
            detecting them later.

        AVIATION ANALOGY:
            Like checking that a pilot isn't also the mechanic signing
            off their own aircraft's maintenance. Some combinations of
            roles are prohibited for safety reasons.
        """
        cursor = self.conn.cursor()

        # Get user's existing roles in this program
        cursor.execute("""
            SELECT DISTINCT role
            FROM user_access
            WHERE user_id = ? AND program_id = ? AND is_active = TRUE
        """, (user_id, program_id))

        existing_roles = [row['role'] for row in cursor.fetchall()]

        conflicts = []

        for existing_role in existing_roles:
            # Check for conflicts in both directions
            cursor.execute("""
                SELECT * FROM role_conflicts
                WHERE (role_a = ? AND role_b = ?)
                   OR (role_a = ? AND role_b = ?)
            """, (existing_role, new_role, new_role, existing_role))

            for conflict in cursor.fetchall():
                conflicts.append({
                    'existing_role': existing_role,
                    'new_role': new_role,
                    'severity': conflict['severity'],
                    'reason': conflict['conflict_reason']
                })

        return {
            'has_conflict': len(conflicts) > 0,
            'conflicts': conflicts
        }

    def get_terminated_with_access(self) -> List[Dict[str, Any]]:
        """
        CRITICAL: Find terminated users who still have active access.

        PURPOSE: Identify compliance violations - no terminated user should
                 have active access.

        RETURNS:
            List of terminated users with active access (should be empty!)

        WHY THIS APPROACH:
            This is a critical compliance check. HIPAA requires timely
            termination of access. If this returns any results, it's an
            immediate compliance issue that needs remediation.

        AVIATION ANALOGY:
            Like checking that no one with a revoked medical certificate
            still has active flight privileges. This should never happen,
            but we check anyway to be sure.
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                u.user_id,
                u.name,
                u.email,
                u.status,
                ua.access_id,
                ua.role,
                p.name as program_name,
                c.name as clinic_name,
                l.name as location_name,
                ua.granted_date
            FROM users u
            JOIN user_access ua ON u.user_id = ua.user_id
            JOIN programs p ON ua.program_id = p.program_id
            LEFT JOIN clinics c ON ua.clinic_id = c.clinic_id
            LEFT JOIN locations l ON ua.location_id = l.location_id
            WHERE u.status = 'Terminated'
              AND ua.is_active = TRUE
            ORDER BY u.name
        """)

        return [dict(row) for row in cursor.fetchall()]

    def get_all_terminated_users(
        self,
        include_access_history: bool = True,
        since_date: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get ALL terminated users with their access history.

        PURPOSE: Full terminated user audit - shows everyone who was terminated,
                 when they were terminated, and confirms their access was revoked.

        PARAMETERS:
            include_access_history: If True, include all access grants (active and revoked)
            since_date: Only include users terminated on or after this date (ISO format)

        RETURNS:
            List of terminated user dicts with compliance status
        """
        cursor = self.conn.cursor()

        query = """
            SELECT
                u.user_id,
                u.name,
                u.email,
                u.organization,
                u.status,
                u.is_business_associate,
                u.created_date,
                u.updated_date as status_changed_date
            FROM users u
            WHERE u.status = 'Terminated'
        """

        params = []

        if since_date:
            query += " AND u.updated_date >= ?"
            params.append(since_date)

        query += " ORDER BY u.updated_date DESC"

        cursor.execute(query, params)
        terminated_users = [dict(row) for row in cursor.fetchall()]

        for user in terminated_users:
            user_id = user['user_id']

            # Get termination details from audit_history
            cursor.execute("""
                SELECT
                    changed_by,
                    change_reason,
                    changed_date
                FROM audit_history
                WHERE record_type = 'user'
                  AND record_id = ?
                  AND action = 'TERMINATE'
                ORDER BY changed_date DESC
                LIMIT 1
            """, (user_id,))

            termination_record = cursor.fetchone()
            if termination_record:
                user['termination_date'] = termination_record['changed_date']
                user['terminated_by'] = termination_record['changed_by']
                user['termination_reason'] = termination_record['change_reason']
            else:
                user['termination_date'] = user['status_changed_date']
                user['terminated_by'] = 'Unknown (pre-audit)'
                user['termination_reason'] = 'No audit record'

            if include_access_history:
                cursor.execute("""
                    SELECT
                        ua.access_id,
                        ua.role,
                        ua.is_active,
                        ua.granted_date,
                        ua.granted_by,
                        ua.revoked_date,
                        ua.revoked_by,
                        ua.revoke_reason,
                        p.name as program_name,
                        p.prefix as program_prefix,
                        c.name as clinic_name,
                        l.name as location_name
                    FROM user_access ua
                    JOIN programs p ON ua.program_id = p.program_id
                    LEFT JOIN clinics c ON ua.clinic_id = c.clinic_id
                    LEFT JOIN locations l ON ua.location_id = l.location_id
                    WHERE ua.user_id = ?
                    ORDER BY ua.granted_date DESC
                """, (user_id,))

                access_history = [dict(row) for row in cursor.fetchall()]
                user['access_history'] = access_history

                active_grants = [a for a in access_history if a['is_active']]
                user['active_access_count'] = len(active_grants)
                user['total_access_count'] = len(access_history)
                user['revoked_access_count'] = len(access_history) - len(active_grants)

                if active_grants:
                    user['compliance_status'] = 'VIOLATION'
                    user['compliance_detail'] = f"{len(active_grants)} access grant(s) still active"
                else:
                    user['compliance_status'] = 'Compliant'
                    user['compliance_detail'] = 'All access properly revoked'
            else:
                cursor.execute("""
                    SELECT COUNT(*) as active_count
                    FROM user_access
                    WHERE user_id = ? AND is_active = TRUE
                """, (user_id,))

                active_count = cursor.fetchone()['active_count']
                user['active_access_count'] = active_count
                user['compliance_status'] = 'VIOLATION' if active_count > 0 else 'Compliant'

        return terminated_users

    def get_review_status_detail(
        self,
        program_id: str = None,
        include_current: bool = False
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get detailed access review status grouped by urgency.

        PURPOSE: Provide detailed data for access review Excel export.

        PARAMETERS:
            program_id: Filter to specific program (optional)
            include_current: If True, include access grants that are current

        RETURNS:
            Dict with keys: 'overdue', 'due_soon', 'current', 'summary'
        """
        cursor = self.conn.cursor()

        today = date.today()
        due_soon_cutoff = (today + timedelta(days=30)).isoformat()
        today_str = today.isoformat()

        resolved_program_id = None
        if program_id:
            resolved_program_id = self._resolve_program_id(program_id)

        query = """
            SELECT
                ua.access_id,
                ua.user_id,
                u.name as user_name,
                u.email,
                u.organization,
                ua.role,
                ua.granted_date,
                ua.granted_by,
                ua.review_cycle,
                ua.next_review_due,
                p.name as program_name,
                p.prefix as program_prefix,
                c.name as clinic_name,
                l.name as location_name,
                (SELECT MAX(ar.review_date)
                 FROM access_reviews ar
                 WHERE ar.access_id = ua.access_id) as last_review_date,
                (SELECT ar.reviewed_by
                 FROM access_reviews ar
                 WHERE ar.access_id = ua.access_id
                 ORDER BY ar.review_date DESC
                 LIMIT 1) as last_reviewed_by
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

        query += " ORDER BY ua.next_review_due ASC NULLS FIRST"

        cursor.execute(query, params)
        all_access = [dict(row) for row in cursor.fetchall()]

        result = {
            'overdue': [],
            'due_soon': [],
            'current': []
        }

        for access in all_access:
            next_due = access['next_review_due']

            if next_due:
                next_due_date = date.fromisoformat(next_due)
                days_diff = (next_due_date - today).days
                access['days_until_due'] = days_diff
                access['days_overdue'] = -days_diff if days_diff < 0 else 0
            else:
                access['days_until_due'] = None
                access['days_overdue'] = None
                access['review_status'] = 'No Review Scheduled'

            if next_due is None or next_due <= today_str:
                access['review_status'] = 'Overdue'
                result['overdue'].append(access)
            elif next_due <= due_soon_cutoff:
                access['review_status'] = 'Due Soon'
                result['due_soon'].append(access)
            else:
                access['review_status'] = 'Current'
                if include_current:
                    result['current'].append(access)

        result['summary'] = {
            'total_active_access': len(all_access),
            'overdue_count': len(result['overdue']),
            'due_soon_count': len(result['due_soon']),
            'current_count': len(all_access) - len(result['overdue']) - len(result['due_soon']),
            'as_of_date': today_str
        }

        return result

    def get_external_users(self, program_id: str = None) -> List[Dict[str, Any]]:
        """
        Get all Business Associate users (HIPAA tracking).

        PURPOSE: List external users who have access for HIPAA BAA tracking

        PARAMETERS:
            program_id: Filter to specific program (optional)

        RETURNS:
            List of external users with their access scope
        """
        cursor = self.conn.cursor()

        query = """
            SELECT DISTINCT
                u.user_id,
                u.name,
                u.email,
                u.organization,
                u.is_business_associate,
                GROUP_CONCAT(DISTINCT p.name) as programs,
                COUNT(DISTINCT ua.access_id) as access_count
            FROM users u
            JOIN user_access ua ON u.user_id = ua.user_id
            JOIN programs p ON ua.program_id = p.program_id
            WHERE u.is_business_associate = TRUE
              AND ua.is_active = TRUE
              AND u.status = 'Active'
        """

        params = []

        if program_id:
            program_id = self._resolve_program_id(program_id)
            query += " AND ua.program_id = ?"
            params.append(program_id)

        query += " GROUP BY u.user_id ORDER BY u.organization, u.name"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _resolve_program_id(self, identifier: str) -> str:
        """
        Resolve program ID from prefix or name.

        PURPOSE: Accept flexible program identifiers

        PARAMETERS:
            identifier: Program ID, prefix, or name

        RETURNS:
            The actual program_id

        RAISES:
            ValueError: If program not found
        """
        cursor = self.conn.cursor()

        # Try exact ID match first
        cursor.execute(
            "SELECT program_id FROM programs WHERE program_id = ?",
            (identifier,)
        )
        row = cursor.fetchone()
        if row:
            return row['program_id']

        # Try prefix match
        cursor.execute(
            "SELECT program_id FROM programs WHERE prefix = ?",
            (identifier.upper(),)
        )
        row = cursor.fetchone()
        if row:
            return row['program_id']

        # Try name match (case-insensitive)
        cursor.execute(
            "SELECT program_id FROM programs WHERE LOWER(name) = LOWER(?)",
            (identifier,)
        )
        row = cursor.fetchone()
        if row:
            return row['program_id']

        raise ValueError(f"Program '{identifier}' not found")

    def _resolve_clinic_id(self, identifier: str, program_id: str) -> str:
        """
        Resolve clinic ID from name or code.

        PURPOSE: Accept flexible clinic identifiers
        """
        cursor = self.conn.cursor()

        # Try exact ID match first
        cursor.execute(
            "SELECT clinic_id FROM clinics WHERE clinic_id = ? AND program_id = ?",
            (identifier, program_id)
        )
        row = cursor.fetchone()
        if row:
            return row['clinic_id']

        # Try name match (case-insensitive)
        cursor.execute(
            "SELECT clinic_id FROM clinics WHERE LOWER(name) = LOWER(?) AND program_id = ?",
            (identifier, program_id)
        )
        row = cursor.fetchone()
        if row:
            return row['clinic_id']

        # Try partial name match
        cursor.execute(
            "SELECT clinic_id FROM clinics WHERE LOWER(name) LIKE ? AND program_id = ?",
            (f"%{identifier.lower()}%", program_id)
        )
        row = cursor.fetchone()
        if row:
            return row['clinic_id']

        raise ValueError(f"Clinic '{identifier}' not found in program")

    def _resolve_location_id(self, identifier: str, clinic_id: str) -> str:
        """
        Resolve location ID from name or code.

        PURPOSE: Accept flexible location identifiers
        """
        cursor = self.conn.cursor()

        # Try exact ID match first
        cursor.execute(
            "SELECT location_id FROM locations WHERE location_id = ? AND clinic_id = ?",
            (identifier, clinic_id)
        )
        row = cursor.fetchone()
        if row:
            return row['location_id']

        # Try name match (case-insensitive)
        cursor.execute(
            "SELECT location_id FROM locations WHERE LOWER(name) = LOWER(?) AND clinic_id = ?",
            (identifier, clinic_id)
        )
        row = cursor.fetchone()
        if row:
            return row['location_id']

        # Try partial name match
        cursor.execute(
            "SELECT location_id FROM locations WHERE LOWER(name) LIKE ? AND clinic_id = ?",
            (f"%{identifier.lower()}%", clinic_id)
        )
        row = cursor.fetchone()
        if row:
            return row['location_id']

        raise ValueError(f"Location '{identifier}' not found in clinic")

    def _log_audit(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        changed_by: str,
        reason: str = None,
        old_value: str = None,
        new_value: str = None
    ) -> None:
        """
        Log an action to the audit_history table.

        PURPOSE: Create immutable audit trail for Part 11 compliance

        PARAMETERS:
            entity_type: What kind of entity changed ('user', 'user_access', etc.)
            entity_id: ID of the entity that changed
            action: What happened ('CREATE', 'UPDATE', 'REVOKE', etc.)
            changed_by: Who made the change
            reason: Why the change was made
            old_value: JSON string of old values
            new_value: JSON string of new values

        WHY THIS APPROACH:
            We use the shared audit_history table (from ConfigurationManager)
            to keep all audit records in one place. This makes compliance
            reporting easier. We use record_type/record_id to match the
            existing schema from config_schema.sql.
        """
        cursor = self.conn.cursor()

        # Check if audit_history table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='audit_history'
        """)

        if not cursor.fetchone():
            # Create audit_history table if it doesn't exist
            # Uses record_type/record_id to match config_schema.sql
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_history (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_type TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    changed_by TEXT,
                    changed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    change_reason TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_record
                ON audit_history(record_type, record_id)
            """)

        # Insert using record_type/record_id (matches config_schema.sql)
        cursor.execute("""
            INSERT INTO audit_history (
                record_type, record_id, action, old_value, new_value,
                changed_by, change_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (entity_type, entity_id, action, old_value, new_value,
              changed_by, reason))

    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Get all data needed for the compliance dashboard.

        PURPOSE: Single method to gather all dashboard metrics in one query batch.

        RETURNS:
            Dict with keys:
            - immediate_attention: overdue reviews, violations, expired training
            - upcoming: reviews due in next 30 days
            - users_by_program: count per program
            - users_by_clinic: count per clinic
            - role_distribution: count per role
            - recent_activity: last 30 days of access grants
            - totals: overall counts
            - as_of: timestamp
        """
        cursor = self.conn.cursor()
        today = date.today()
        thirty_days_ago = (today - timedelta(days=30)).isoformat()
        thirty_days_ahead = (today + timedelta(days=30)).isoformat()
        today_str = today.isoformat()

        result = {
            'immediate_attention': {},
            'upcoming': {},
            'users_by_program': [],
            'users_by_clinic': [],
            'role_distribution': [],
            'recent_activity': [],
            'totals': {},
            'as_of': datetime.now().isoformat()
        }

        # --- IMMEDIATE ATTENTION ---

        # Overdue reviews
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM user_access ua
            JOIN users u ON ua.user_id = u.user_id
            WHERE ua.is_active = TRUE
              AND u.status = 'Active'
              AND (ua.next_review_due IS NULL OR ua.next_review_due <= ?)
        """, (today_str,))
        result['immediate_attention']['reviews_overdue'] = cursor.fetchone()['count']

        # Terminated with active access (violations)
        cursor.execute("""
            SELECT COUNT(DISTINCT u.user_id) as count
            FROM users u
            JOIN user_access ua ON u.user_id = ua.user_id
            WHERE u.status = 'Terminated'
              AND ua.is_active = TRUE
        """)
        result['immediate_attention']['terminated_violations'] = cursor.fetchone()['count']

        # Expired training
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM user_training ut
            JOIN users u ON ut.user_id = u.user_id
            WHERE u.status = 'Active'
              AND ut.status = 'Expired'
        """)
        result['immediate_attention']['training_expired'] = cursor.fetchone()['count']

        # --- UPCOMING ---

        # Reviews due in next 30 days
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM user_access ua
            JOIN users u ON ua.user_id = u.user_id
            WHERE ua.is_active = TRUE
              AND u.status = 'Active'
              AND ua.next_review_due > ?
              AND ua.next_review_due <= ?
        """, (today_str, thirty_days_ahead))
        result['upcoming']['reviews_due_soon'] = cursor.fetchone()['count']

        # --- USERS BY PROGRAM ---

        cursor.execute("""
            SELECT
                p.name as program_name,
                p.prefix as program_prefix,
                COUNT(DISTINCT ua.user_id) as user_count,
                COUNT(DISTINCT ua.clinic_id) as clinic_count
            FROM user_access ua
            JOIN programs p ON ua.program_id = p.program_id
            JOIN users u ON ua.user_id = u.user_id
            WHERE ua.is_active = TRUE
              AND u.status = 'Active'
            GROUP BY p.program_id, p.name, p.prefix
            ORDER BY user_count DESC
        """)
        result['users_by_program'] = [dict(row) for row in cursor.fetchall()]

        # --- USERS BY CLINIC ---

        cursor.execute("""
            SELECT
                COALESCE(c.name, '(Program-wide)') as clinic_name,
                p.name as program_name,
                COUNT(DISTINCT ua.user_id) as user_count
            FROM user_access ua
            JOIN programs p ON ua.program_id = p.program_id
            LEFT JOIN clinics c ON ua.clinic_id = c.clinic_id
            JOIN users u ON ua.user_id = u.user_id
            WHERE ua.is_active = TRUE
              AND u.status = 'Active'
            GROUP BY c.clinic_id, c.name, p.name
            ORDER BY user_count DESC
        """)
        result['users_by_clinic'] = [dict(row) for row in cursor.fetchall()]

        # --- ROLE DISTRIBUTION ---

        cursor.execute("""
            SELECT
                ua.role,
                COUNT(*) as count
            FROM user_access ua
            JOIN users u ON ua.user_id = u.user_id
            WHERE ua.is_active = TRUE
              AND u.status = 'Active'
            GROUP BY ua.role
            ORDER BY count DESC
        """)
        roles = [dict(row) for row in cursor.fetchall()]
        total_roles = sum(r['count'] for r in roles)
        for r in roles:
            r['percentage'] = round((r['count'] / total_roles * 100), 1) if total_roles > 0 else 0
        result['role_distribution'] = roles

        # --- RECENT ACTIVITY ---

        cursor.execute("""
            SELECT
                ua.granted_date,
                u.name as user_name,
                u.email,
                ua.role,
                p.name as program_name,
                COALESCE(c.name, '(Program-wide)') as clinic_name,
                ua.granted_by
            FROM user_access ua
            JOIN users u ON ua.user_id = u.user_id
            JOIN programs p ON ua.program_id = p.program_id
            LEFT JOIN clinics c ON ua.clinic_id = c.clinic_id
            WHERE ua.granted_date >= ?
            ORDER BY ua.granted_date DESC
            LIMIT 20
        """, (thirty_days_ago,))
        result['recent_activity'] = [dict(row) for row in cursor.fetchall()]

        # Recent activity count (all, not just top 20)
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM user_access
            WHERE granted_date >= ?
        """, (thirty_days_ago,))
        result['totals']['recent_grants_count'] = cursor.fetchone()['count']

        # --- TOTALS ---

        cursor.execute("""
            SELECT COUNT(DISTINCT user_id) as count
            FROM users
            WHERE status = 'Active'
        """)
        result['totals']['active_users'] = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM programs")
        result['totals']['total_programs'] = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM clinics")
        result['totals']['total_clinics'] = cursor.fetchone()['count']

        return result

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()


# =============================================================================
# MODULE TEST
# =============================================================================
# Quick test when running this file directly

if __name__ == "__main__":
    print("Testing AccessManager...")

    am = AccessManager()
    am.initialize_schema()

    print("\nSchema initialized successfully!")
    print(f"Database: {am.db_path}")

    # Show table counts
    cursor = am.conn.cursor()
    for table in ['users', 'user_access', 'access_reviews', 'user_training', 'role_conflicts']:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"  {table}: {count} rows")

    am.close()
