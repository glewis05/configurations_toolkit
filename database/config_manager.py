"""
Configuration Manager - CRUD operations for system configurations

PURPOSE: Manage configuration values with inheritance across
         Program → Clinic → Location hierarchy

R EQUIVALENT: Like a hierarchical environment where child environments
inherit from parents (similar to R's lexical scoping)

AVIATION ANALOGY: Like aircraft configuration management where
modifications at the tail number level override type certificate defaults

AUTHOR: Glen Lewis
DATE: 2024
"""

import sqlite3
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

import yaml


# ============================================================================
# DATABASE PATH CONFIGURATION
# ============================================================================

# Default path to the shared database
# Both Requirements Toolkit and Configurations Toolkit use this database
DEFAULT_DB_PATH = os.path.expanduser("~/projects/data/client_product_database.db")


class ConfigurationManager:
    """
    PURPOSE: Manage configuration values with inheritance

    Handles:
    - Program → Clinic → Location inheritance
    - Override tracking
    - Audit logging for all changes
    - Effective value calculation

    R EQUIVALENT: Like an R6 class that manages nested environments

    PARAMETERS:
        db_path: Path to SQLite database file
                 Default: ~/projects/data/client_product_database.db

    EXAMPLE:
        cm = ConfigurationManager()
        cm.initialize_schema()
        cm.set_config('helpdesk_phone', '503.216.6407',
                      program_id='P4M-001', clinic_id='PORT-001')
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """
        Initialize the ConfigurationManager with database connection.

        WHY THIS APPROACH: We use a single database file shared with
        Requirements Toolkit to maintain referential integrity between
        programs, requirements, and configurations.
        """
        # Expand user path (handles ~/...)
        self.db_path = os.path.expanduser(db_path)

        # Ensure the data directory exists
        data_dir = os.path.dirname(self.db_path)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir)
            print(f"Created data directory: {data_dir}")

        # Connect to database
        # check_same_thread=False allows connection to be used across threads
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)

        # Enable foreign key constraints (off by default in SQLite)
        self.conn.execute("PRAGMA foreign_keys = ON")

        # Return rows as dictionaries for easier access
        self.conn.row_factory = sqlite3.Row

    # ========================================================================
    # SCHEMA INITIALIZATION
    # ========================================================================

    def initialize_schema(self) -> None:
        """
        Run config_schema.sql to add configuration tables.

        PURPOSE: Create all configuration-specific tables if they don't exist

        WHY THIS APPROACH: We keep schema in SQL file for version control
        and documentation, but execute it programmatically for convenience.
        """
        # Get the path to the schema file (in same directory as this module)
        schema_path = Path(__file__).parent / "config_schema.sql"

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        # Read and execute schema
        with open(schema_path, 'r') as f:
            schema_sql = f.read()

        # Execute the schema (CREATE IF NOT EXISTS makes this idempotent)
        self.conn.executescript(schema_sql)
        self.conn.commit()

        # Try to add program_type column to programs table if it doesn't exist
        try:
            self.conn.execute("""
                ALTER TABLE programs ADD COLUMN program_type TEXT DEFAULT 'clinic_based'
            """)
            self.conn.commit()
        except sqlite3.OperationalError:
            # Column already exists, that's fine
            pass

        print("Configuration schema initialized successfully")

    def load_definitions_from_yaml(self, yaml_path: str = None) -> int:
        """
        Load config_definitions.yaml into config_definitions table.

        PURPOSE: Populate the config schema from YAML definition file

        PARAMETERS:
            yaml_path: Path to YAML file. If None, uses default in config/

        RETURNS:
            int: Number of definitions loaded

        WHY THIS APPROACH: YAML is human-readable and easy to edit,
        but we store in SQLite for query performance and validation.
        """
        if yaml_path is None:
            # Default to config/config_definitions.yaml in project root
            yaml_path = Path(__file__).parent.parent / "config" / "config_definitions.yaml"

        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)

        count = 0
        cursor = self.conn.cursor()

        for defn in data.get('definitions', []):
            # Convert allowed_values list to JSON string if present
            allowed_values = defn.get('allowed_values')
            if allowed_values and isinstance(allowed_values, list):
                allowed_values = json.dumps(allowed_values)

            cursor.execute("""
                INSERT OR REPLACE INTO config_definitions
                (config_key, category, display_name, description, data_type,
                 allowed_values, default_value, applies_to, is_required,
                 is_clinic_editable, validation_regex, display_order)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                defn['config_key'],
                defn['category'],
                defn['display_name'],
                defn.get('description'),
                defn['data_type'],
                allowed_values,
                defn.get('default_value'),
                defn['applies_to'],
                defn.get('is_required', False),
                defn.get('is_clinic_editable', False),
                defn.get('validation_regex'),
                defn.get('display_order', 0)
            ))
            count += 1

        self.conn.commit()
        print(f"Loaded {count} configuration definitions from {yaml_path}")
        return count

    # ========================================================================
    # PROGRAM OPERATIONS
    # ========================================================================

    def create_program(self, name: str, prefix: str,
                       program_type: str = 'clinic_based',
                       client_id: str = None,
                       description: str = None) -> str:
        """
        Create a program with specified type.

        PURPOSE: Create a new program entry that configurations can attach to

        PARAMETERS:
            name: Program name (e.g., "Prevention4ME")
            prefix: Short prefix for IDs (e.g., "P4M")
            program_type: One of 'standalone', 'clinic_based', 'attached'
            client_id: Optional parent client ID
            description: Optional description

        RETURNS:
            str: The generated program_id

        WHY THIS APPROACH: Programs are the top of the configuration hierarchy.
        We track type to know if clinic/location levels apply.
        """
        program_id = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO programs (program_id, client_id, name, prefix,
                                  program_type, description, created_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (program_id, client_id, name, prefix, program_type,
              description, datetime.now().isoformat()))

        # Log to audit history
        self._log_audit('program', program_id, 'Created',
                        new_value=json.dumps({
                            'name': name,
                            'prefix': prefix,
                            'program_type': program_type
                        }))

        self.conn.commit()
        print(f"Created program: {name} ({program_id})")
        return program_id

    def get_program_by_prefix(self, identifier: str) -> Optional[Dict]:
        """
        Look up a program by prefix OR name.

        PURPOSE: Flexible program lookup - accepts either the short prefix
                 (e.g., "P4M") or the full name (e.g., "Prevention4ME")

        PARAMETERS:
            identifier: Program prefix or name to search for

        RETURNS: Program record as dict, or None if not found

        WHY THIS APPROACH: Users often remember the full name but not
        the prefix. This makes the CLI more forgiving.

        EXAMPLE:
            get_program_by_prefix("P4M")           # Works
            get_program_by_prefix("Prevention4ME") # Also works
        """
        cursor = self.conn.cursor()

        # First try exact prefix match (most common case)
        cursor.execute("""
            SELECT * FROM programs WHERE prefix = ?
        """, (identifier,))
        row = cursor.fetchone()

        if row:
            return dict(row)

        # Then try exact name match
        cursor.execute("""
            SELECT * FROM programs WHERE name = ?
        """, (identifier,))
        row = cursor.fetchone()

        if row:
            return dict(row)

        # Finally try case-insensitive partial match on name
        cursor.execute("""
            SELECT * FROM programs WHERE LOWER(name) LIKE LOWER(?)
        """, (f"%{identifier}%",))
        row = cursor.fetchone()

        return dict(row) if row else None

    def attach_program(self, parent_program_id: str,
                       attached_program_id: str,
                       relationship_type: str = 'uses') -> int:
        """
        Create relationship between programs.

        PURPOSE: Link an attached program (like Discover) to parent programs

        PARAMETERS:
            parent_program_id: The main program (e.g., Prevention4ME)
            attached_program_id: The shared service program (e.g., Discover)
            relationship_type: 'uses', 'requires', or 'optional'

        RETURNS:
            int: The relationship_id

        EXAMPLE:
            cm.attach_program('P4M-001', 'DISC-001', 'uses')
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO program_relationships
            (parent_program_id, attached_program_id, relationship_type)
            VALUES (?, ?, ?)
        """, (parent_program_id, attached_program_id, relationship_type))

        relationship_id = cursor.lastrowid

        self._log_audit('program_relationship', str(relationship_id), 'Created',
                        new_value=json.dumps({
                            'parent': parent_program_id,
                            'attached': attached_program_id,
                            'type': relationship_type
                        }))

        self.conn.commit()
        return relationship_id

    def get_attached_programs(self, program_id: str) -> List[Dict]:
        """
        Get all programs attached to this program.

        RETURNS: List of attached program records
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT p.*, pr.relationship_type
            FROM programs p
            JOIN program_relationships pr ON p.program_id = pr.attached_program_id
            WHERE pr.parent_program_id = ?
        """, (program_id,))
        return [dict(row) for row in cursor.fetchall()]

    # ========================================================================
    # CLINIC/LOCATION OPERATIONS
    # ========================================================================

    def create_clinic(self, program_id: str, name: str,
                      code: str = None, description: str = None) -> str:
        """
        Create a clinic under a program.

        PURPOSE: Create a clinic that can have location-specific configs

        PARAMETERS:
            program_id: Parent program ID
            name: Clinic name (e.g., "Portland Cancer Institute")
            code: Short code (e.g., "PORT")
            description: Optional description

        RETURNS:
            str: The generated clinic_id
        """
        # Generate clinic_id from code or name
        if code:
            clinic_id = f"{code}-{uuid.uuid4().hex[:6].upper()}"
        else:
            # Use first 4 chars of name
            short = ''.join(c for c in name if c.isalnum())[:4].upper()
            clinic_id = f"{short}-{uuid.uuid4().hex[:6].upper()}"

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO clinics (clinic_id, program_id, name, code, description)
            VALUES (?, ?, ?, ?, ?)
        """, (clinic_id, program_id, name, code, description))

        self._log_audit('clinic', clinic_id, 'Created',
                        new_value=json.dumps({
                            'name': name,
                            'code': code,
                            'program_id': program_id
                        }))

        self.conn.commit()
        print(f"Created clinic: {name} ({clinic_id})")
        return clinic_id

    def create_location(self, clinic_id: str, name: str,
                        code: str = None, address: str = None) -> str:
        """
        Create a location under a clinic.

        PURPOSE: Create a location for location-specific configurations

        PARAMETERS:
            clinic_id: Parent clinic ID
            name: Location name (e.g., "PCI Breast Surgery West")
            code: Service location code (e.g., "4000045001")
            address: Physical address

        RETURNS:
            str: The generated location_id
        """
        location_id = f"LOC-{uuid.uuid4().hex[:8].upper()}"

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO locations (location_id, clinic_id, name, code, address)
            VALUES (?, ?, ?, ?, ?)
        """, (location_id, clinic_id, name, code, address))

        self._log_audit('location', location_id, 'Created',
                        new_value=json.dumps({
                            'name': name,
                            'code': code,
                            'clinic_id': clinic_id
                        }))

        self.conn.commit()
        print(f"Created location: {name} ({location_id})")
        return location_id

    def get_clinic_by_name(self, program_id: str, name: str) -> Optional[Dict]:
        """Look up a clinic by program and name."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM clinics WHERE program_id = ? AND name LIKE ?
        """, (program_id, f"%{name}%"))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_location_by_name(self, clinic_id: str, name: str) -> Optional[Dict]:
        """Look up a location by clinic and name."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM locations WHERE clinic_id = ? AND name LIKE ?
        """, (clinic_id, f"%{name}%"))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_program_hierarchy(self, program_id: str) -> Dict:
        """
        Get full hierarchy: Program → Clinics → Locations.

        PURPOSE: Retrieve the complete organizational structure

        RETURNS: Nested dict with program, clinics, and locations

        EXAMPLE OUTPUT:
        {
            'program_id': 'P4M-001',
            'name': 'Prevention4ME',
            'clinics': [
                {
                    'clinic_id': 'PORT-001',
                    'name': 'Portland',
                    'locations': [
                        {'location_id': 'LOC-001', 'name': 'Breast Surgery West'},
                        {'location_id': 'LOC-002', 'name': 'Franz Breast Care'}
                    ]
                }
            ]
        }
        """
        cursor = self.conn.cursor()

        # Get program
        cursor.execute("SELECT * FROM programs WHERE program_id = ?", (program_id,))
        program = cursor.fetchone()
        if not program:
            return None

        result = dict(program)
        result['clinics'] = []

        # Get clinics
        cursor.execute("""
            SELECT * FROM clinics WHERE program_id = ? ORDER BY name
        """, (program_id,))

        for clinic in cursor.fetchall():
            clinic_dict = dict(clinic)
            clinic_dict['locations'] = []

            # Get locations for this clinic
            cursor.execute("""
                SELECT * FROM locations WHERE clinic_id = ? ORDER BY name
            """, (clinic['clinic_id'],))

            for location in cursor.fetchall():
                clinic_dict['locations'].append(dict(location))

            result['clinics'].append(clinic_dict)

        return result

    # ========================================================================
    # CONFIGURATION OPERATIONS
    # ========================================================================

    def set_config(self, config_key: str, value: str,
                   program_id: str, clinic_id: str = None,
                   location_id: str = None, source: str = 'manual',
                   source_document: str = None, rationale: str = None,
                   changed_by: str = 'system',
                   normalize: bool = True) -> int:
        """
        Set a configuration value at any level.

        PURPOSE: Store a configuration value with full audit trail

        PARAMETERS:
            config_key: The configuration key (e.g., 'helpdesk_phone')
            value: The value to set (always stored as string)
            program_id: Program this config belongs to
            clinic_id: Optional clinic (for clinic-level config)
            location_id: Optional location (for location-level config)
            source: Where value came from ('default', 'import', 'manual', 'clinic_portal')
            source_document: e.g., "Portland_Clinic_Spec.docx"
            rationale: Why this value was set
            changed_by: Who made the change
            normalize: If True, normalizes value based on config type (default True)

        RETURNS:
            int: The value_id

        WHY THIS APPROACH: We store at the most specific level provided.
        The get_config() method handles inheritance when reading.
        Values are normalized (phone formats, booleans, times) for consistency.
        """
        cursor = self.conn.cursor()

        # Normalize the value if requested
        if normalize and value:
            value = self._normalize_config_value(config_key, value)

        # Check if this config key exists in definitions
        cursor.execute("""
            SELECT * FROM config_definitions WHERE config_key = ?
        """, (config_key,))
        definition = cursor.fetchone()

        if not definition:
            print(f"Warning: config_key '{config_key}' not in definitions")

        # Check if value already exists at this level
        cursor.execute("""
            SELECT value_id, value, version FROM config_values
            WHERE config_key = ?
              AND program_id = ?
              AND (clinic_id = ? OR (clinic_id IS NULL AND ? IS NULL))
              AND (location_id = ? OR (location_id IS NULL AND ? IS NULL))
        """, (config_key, program_id, clinic_id, clinic_id, location_id, location_id))

        existing = cursor.fetchone()

        # Determine if this is an override
        is_override = self._is_override(config_key, program_id, clinic_id, location_id, value)

        if existing:
            # Update existing value
            old_value = existing['value']
            new_version = existing['version'] + 1

            cursor.execute("""
                UPDATE config_values
                SET value = ?, is_override = ?, source = ?, source_document = ?,
                    rationale = ?, version = ?, updated_date = ?, created_by = ?
                WHERE value_id = ?
            """, (value, is_override, source, source_document, rationale,
                  new_version, datetime.now().isoformat(), changed_by,
                  existing['value_id']))

            value_id = existing['value_id']

            # Log the change
            self._log_config_history(config_key, program_id, clinic_id, location_id,
                                     old_value, value, changed_by, rationale, source_document)
        else:
            # Insert new value
            cursor.execute("""
                INSERT INTO config_values
                (config_key, program_id, clinic_id, location_id, value, is_override,
                 source, source_document, rationale, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (config_key, program_id, clinic_id, location_id, value, is_override,
                  source, source_document, rationale, changed_by))

            value_id = cursor.lastrowid

            # Log the creation
            self._log_config_history(config_key, program_id, clinic_id, location_id,
                                     None, value, changed_by, rationale, source_document)

        self.conn.commit()
        return value_id

    def get_config(self, config_key: str, program_id: str,
                   clinic_id: str = None, location_id: str = None) -> Dict:
        """
        Get configuration value with inheritance.

        PURPOSE: Retrieve the effective value for a config at any level

        Checks in order:
        1. Location-specific value (if location_id provided)
        2. Clinic-specific value (if clinic_id provided)
        3. Program-specific value
        4. Default from config_definitions

        PARAMETERS:
            config_key: The configuration key to look up
            program_id: The program context
            clinic_id: Optional clinic context
            location_id: Optional location context

        RETURNS:
            Dict with:
            - value: The effective value
            - effective_level: Where value came from ('location', 'clinic', 'program', 'default')
            - is_override: Whether this overrides parent
            - source: How value was set
            - source_document: Document value came from

        AVIATION ANALOGY: Like checking aircraft configuration:
        first check tail-specific, then fleet, then type certificate
        """
        cursor = self.conn.cursor()

        # Try each level in order of specificity
        levels = []

        if location_id:
            levels.append(('location', location_id, clinic_id, program_id))
        if clinic_id:
            levels.append(('clinic', None, clinic_id, program_id))
        levels.append(('program', None, None, program_id))

        for level_name, loc_id, clin_id, prog_id in levels:
            cursor.execute("""
                SELECT * FROM config_values
                WHERE config_key = ?
                  AND program_id = ?
                  AND (clinic_id = ? OR (clinic_id IS NULL AND ? IS NULL))
                  AND (location_id = ? OR (location_id IS NULL AND ? IS NULL))
            """, (config_key, prog_id, clin_id, clin_id, loc_id, loc_id))

            row = cursor.fetchone()
            if row:
                return {
                    'value': row['value'],
                    'effective_level': level_name,
                    'is_override': bool(row['is_override']),
                    'source': row['source'],
                    'source_document': row['source_document'],
                    'rationale': row['rationale']
                }

        # Fall back to default from definitions
        cursor.execute("""
            SELECT default_value FROM config_definitions WHERE config_key = ?
        """, (config_key,))
        row = cursor.fetchone()

        if row and row['default_value']:
            return {
                'value': row['default_value'],
                'effective_level': 'default',
                'is_override': False,
                'source': 'default',
                'source_document': None,
                'rationale': None
            }

        # No value found at any level
        return {
            'value': None,
            'effective_level': None,
            'is_override': False,
            'source': None,
            'source_document': None,
            'rationale': None
        }

    def get_effective_config(self, program_id: str, clinic_id: str = None,
                             location_id: str = None) -> Dict[str, Dict]:
        """
        Get ALL effective configurations for a level.

        PURPOSE: Get complete configuration picture for a specific level

        RETURNS:
            Dict mapping config_key to effective value info

        EXAMPLE:
            configs = cm.get_effective_config('P4M-001', clinic_id='PORT-001')
            print(configs['helpdesk_phone']['value'])  # '503.216.6407'
            print(configs['helpdesk_phone']['effective_level'])  # 'clinic'

        WHY THIS APPROACH: Uses a single query to get all values at all levels,
        then computes inheritance in Python. This is O(1) queries instead of
        O(n) where n is the number of config keys (was 47+ queries, now 1).
        """
        cursor = self.conn.cursor()

        # Get all definitions with defaults in one query
        cursor.execute("""
            SELECT config_key, default_value FROM config_definitions
        """)
        definitions = {row['config_key']: row['default_value'] for row in cursor.fetchall()}

        # Get all relevant config values in ONE query
        # This fetches program, clinic, and location level values together
        cursor.execute("""
            SELECT config_key, value, source, source_document, rationale, is_override,
                   clinic_id, location_id
            FROM config_values
            WHERE program_id = ?
              AND (clinic_id IS NULL OR clinic_id = ?)
              AND (location_id IS NULL OR location_id = ?)
        """, (program_id, clinic_id, location_id))

        # Organize values by level for each config key
        # Structure: {config_key: {'program': row, 'clinic': row, 'location': row}}
        values_by_key = {}
        for row in cursor.fetchall():
            key = row['config_key']
            if key not in values_by_key:
                values_by_key[key] = {}

            # Determine which level this value is at
            if row['location_id']:
                values_by_key[key]['location'] = dict(row)
            elif row['clinic_id']:
                values_by_key[key]['clinic'] = dict(row)
            else:
                values_by_key[key]['program'] = dict(row)

        # Build result with inheritance resolution
        result = {}
        for config_key, default_value in definitions.items():
            key_values = values_by_key.get(config_key, {})

            # Check levels in order of specificity: location > clinic > program > default
            effective_value = None
            effective_level = 'default'
            source = 'default'
            source_document = None
            rationale = None
            is_override = False

            # Check each level
            for level in ['location', 'clinic', 'program']:
                if level in key_values:
                    row = key_values[level]
                    effective_value = row['value']
                    effective_level = level
                    source = row['source']
                    source_document = row['source_document']
                    rationale = row['rationale']
                    is_override = bool(row['is_override'])
                    break  # Found most specific level

            # Fall back to default if no value found
            if effective_value is None:
                effective_value = default_value

            result[config_key] = {
                'value': effective_value,
                'effective_level': effective_level,
                'is_override': is_override,
                'source': source,
                'source_document': source_document,
                'rationale': rationale
            }

        return result

    def get_overrides(self, program_id: str, clinic_id: str = None,
                      location_id: str = None) -> List[Dict]:
        """
        Get only the overridden values at this specific level.

        PURPOSE: See what's explicitly set at a level vs inherited

        RETURNS: List of config values that are overrides
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT cv.*, cd.display_name, cd.category
            FROM config_values cv
            JOIN config_definitions cd ON cv.config_key = cd.config_key
            WHERE cv.program_id = ?
              AND (cv.clinic_id = ? OR (cv.clinic_id IS NULL AND ? IS NULL))
              AND (cv.location_id = ? OR (cv.location_id IS NULL AND ? IS NULL))
              AND cv.is_override = TRUE
            ORDER BY cd.category, cd.display_order
        """, (program_id, clinic_id, clinic_id, location_id, location_id))

        return [dict(row) for row in cursor.fetchall()]

    def compare_to_defaults(self, program_id: str, clinic_id: str = None,
                            location_id: str = None) -> List[Dict]:
        """
        Compare current configs to program defaults.

        PURPOSE: Review what's different from defaults for validation

        RETURNS: List of differences with old/new values
        """
        cursor = self.conn.cursor()

        differences = []
        configs = self.get_effective_config(program_id, clinic_id, location_id)

        for key, info in configs.items():
            if info['effective_level'] not in ['program', 'default']:
                # Get the program/default value
                cursor.execute("""
                    SELECT cd.default_value,
                           cv.value as program_value
                    FROM config_definitions cd
                    LEFT JOIN config_values cv ON cd.config_key = cv.config_key
                                              AND cv.program_id = ?
                                              AND cv.clinic_id IS NULL
                                              AND cv.location_id IS NULL
                    WHERE cd.config_key = ?
                """, (program_id, key))

                row = cursor.fetchone()
                if row:
                    default_val = row['program_value'] or row['default_value']
                    if default_val != info['value']:
                        differences.append({
                            'config_key': key,
                            'default_value': default_val,
                            'current_value': info['value'],
                            'level': info['effective_level'],
                            'source': info['source']
                        })

        return differences

    # ========================================================================
    # PROVIDER OPERATIONS
    # ========================================================================

    def add_provider(self, location_id: str, name: str,
                     npi: str = None, role: str = 'Ordering Provider',
                     specialty: str = None,
                     validate_npi: bool = True,
                     skip_if_exists: bool = True) -> int:
        """
        Add a provider to a location.

        PARAMETERS:
            location_id: Location this provider works at
            name: Provider name (e.g., "Christine Kemp, NP")
            npi: National Provider Identifier
            role: Provider role
            specialty: Medical specialty
            validate_npi: If True, validates NPI format (default True)
            skip_if_exists: If True, silently skips if provider exists at location

        RETURNS:
            int: The provider_id (existing if skip_if_exists, new otherwise)

        RAISES:
            ValueError: If NPI is invalid and validate_npi is True
            sqlite3.IntegrityError: If provider exists and skip_if_exists is False

        WHY THIS APPROACH: NPIs are critical for healthcare billing
        and compliance. Validating on entry prevents bad data.
        Duplicate prevention ensures data quality and prevents
        re-importing the same provider multiple times.
        """
        # Validate and normalize NPI
        normalized_npi = npi
        if npi and validate_npi:
            is_valid, result = self._validate_npi(npi)
            if not is_valid:
                raise ValueError(f"Invalid NPI for {name}: {result}")
            normalized_npi = result

        cursor = self.conn.cursor()

        # Check if provider already exists at this location (active only)
        cursor.execute("""
            SELECT provider_id, npi FROM providers
            WHERE location_id = ? AND name = ? AND is_active = TRUE
        """, (location_id, name))

        existing = cursor.fetchone()

        if existing:
            if skip_if_exists:
                # Update NPI if we have a new one and existing doesn't have one
                if normalized_npi and not existing['npi']:
                    cursor.execute("""
                        UPDATE providers SET npi = ?, updated_date = ?
                        WHERE provider_id = ?
                    """, (normalized_npi, datetime.now().isoformat(), existing['provider_id']))
                    self.conn.commit()
                    print(f"  Updated NPI for existing provider: {name}")
                else:
                    print(f"  Provider already exists: {name} at location {location_id}")
                return existing['provider_id']
            else:
                raise sqlite3.IntegrityError(
                    f"Provider '{name}' already exists at location {location_id}"
                )

        cursor.execute("""
            INSERT INTO providers (location_id, name, npi, role, specialty)
            VALUES (?, ?, ?, ?, ?)
        """, (location_id, name, normalized_npi, role, specialty))

        provider_id = cursor.lastrowid

        self._log_audit('provider', str(provider_id), 'Created',
                        new_value=json.dumps({
                            'name': name,
                            'npi': normalized_npi,
                            'role': role,
                            'location_id': location_id
                        }))

        self.conn.commit()
        print(f"Added provider: {name} (NPI: {normalized_npi})")
        return provider_id

    def update_provider(self, provider_id: int, **updates) -> None:
        """
        Update provider info.

        PARAMETERS:
            provider_id: Provider to update
            **updates: Fields to update (name, npi, role, specialty)

        EXAMPLE:
            cm.update_provider(123, npi='1234567890', role='Supervising')
        """
        cursor = self.conn.cursor()

        # Get current values for audit
        cursor.execute("SELECT * FROM providers WHERE provider_id = ?", (provider_id,))
        old = cursor.fetchone()
        if not old:
            raise ValueError(f"Provider {provider_id} not found")

        # Build update query
        valid_fields = ['name', 'npi', 'role', 'specialty', 'is_active']
        set_clauses = []
        values = []

        for field, value in updates.items():
            if field in valid_fields:
                set_clauses.append(f"{field} = ?")
                values.append(value)

        if not set_clauses:
            return

        values.append(datetime.now().isoformat())
        values.append(provider_id)

        query = f"""
            UPDATE providers
            SET {', '.join(set_clauses)}, updated_date = ?
            WHERE provider_id = ?
        """
        cursor.execute(query, values)

        # Log changes
        self._log_audit('provider', str(provider_id), 'Updated',
                        old_value=json.dumps(dict(old)),
                        new_value=json.dumps(updates))

        self.conn.commit()
        print(f"Updated provider {provider_id}: {updates}")

    def get_providers(self, location_id: str = None,
                      clinic_id: str = None,
                      active_only: bool = True) -> List[Dict]:
        """
        Get providers, optionally filtered by location or clinic.

        PARAMETERS:
            location_id: Filter by specific location
            clinic_id: Filter by clinic (all locations in clinic)
            active_only: Only return active providers
        """
        cursor = self.conn.cursor()

        if location_id:
            query = """
                SELECT p.*, l.name as location_name
                FROM providers p
                JOIN locations l ON p.location_id = l.location_id
                WHERE p.location_id = ?
            """
            params = [location_id]
        elif clinic_id:
            query = """
                SELECT p.*, l.name as location_name
                FROM providers p
                JOIN locations l ON p.location_id = l.location_id
                WHERE l.clinic_id = ?
            """
            params = [clinic_id]
        else:
            query = """
                SELECT p.*, l.name as location_name
                FROM providers p
                JOIN locations l ON p.location_id = l.location_id
            """
            params = []

        if active_only:
            if params:
                query += " AND p.is_active = TRUE"
            else:
                query += " WHERE p.is_active = TRUE"

        query += " ORDER BY p.name"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def deactivate_provider(self, provider_id: int, reason: str = None) -> None:
        """
        Soft delete - set is_active=False.

        WHY THIS APPROACH: We never hard delete for audit trail purposes.
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            UPDATE providers
            SET is_active = FALSE,
                deactivated_date = ?,
                deactivation_reason = ?,
                updated_date = ?
            WHERE provider_id = ?
        """, (datetime.now().isoformat(), reason,
              datetime.now().isoformat(), provider_id))

        self._log_audit('provider', str(provider_id), 'Deactivated',
                        new_value=json.dumps({'reason': reason}))

        self.conn.commit()
        print(f"Deactivated provider {provider_id}")

    # ========================================================================
    # IMPORT OPERATIONS
    # ========================================================================

    def clear_program_data(self, program_id: str, keep_structure: bool = False) -> Dict:
        """
        Clear all config data for a program before reimport.

        PURPOSE: Allow fresh reimport of a clinic spec document without
                 duplicate entries. Used with --reimport flag.

        PARAMETERS:
            program_id: Program to clear data for
            keep_structure: If True, keep clinics/locations but clear configs only
                           If False, clear everything including structure

        RETURNS:
            Dict with counts of deleted entities

        WHY THIS APPROACH: When re-importing after parser fixes, we need a clean
        slate to avoid duplicate values. This method provides controlled deletion
        while preserving audit history (never delete config_history).

        AVIATION ANALOGY: Like a flight plan reset - clear the route points but
        keep the departure/arrival airports (if keep_structure=True).
        """
        cursor = self.conn.cursor()
        counts = {
            'config_values': 0,
            'providers': 0,
            'locations': 0,
            'clinics': 0
        }

        # Get all clinics for this program
        cursor.execute("SELECT clinic_id FROM clinics WHERE program_id = ?", (program_id,))
        clinic_ids = [row['clinic_id'] for row in cursor.fetchall()]

        if not clinic_ids:
            print(f"  No clinics found for program {program_id}")
            return counts

        # Get all locations for these clinics
        location_ids = []
        for clinic_id in clinic_ids:
            cursor.execute("SELECT location_id FROM locations WHERE clinic_id = ?", (clinic_id,))
            location_ids.extend([row['location_id'] for row in cursor.fetchall()])

        # Delete config_values (always - this is the main thing we're clearing)
        cursor.execute("""
            DELETE FROM config_values
            WHERE program_id = ?
        """, (program_id,))
        counts['config_values'] = cursor.rowcount
        print(f"  Deleted {counts['config_values']} config values")

        if not keep_structure:
            # Delete providers at these locations
            for loc_id in location_ids:
                cursor.execute("DELETE FROM providers WHERE location_id = ?", (loc_id,))
                counts['providers'] += cursor.rowcount

            # Delete locations
            for clinic_id in clinic_ids:
                cursor.execute("DELETE FROM locations WHERE clinic_id = ?", (clinic_id,))
                counts['locations'] += cursor.rowcount

            # Delete clinics
            for clinic_id in clinic_ids:
                cursor.execute("DELETE FROM clinics WHERE clinic_id = ?", (clinic_id,))
                counts['clinics'] += cursor.rowcount

            print(f"  Deleted {counts['providers']} providers")
            print(f"  Deleted {counts['locations']} locations")
            print(f"  Deleted {counts['clinics']} clinics")

        self.conn.commit()
        return counts

    def import_from_parsed_doc(self, parsed_data: Dict, program_id: str,
                               source_document: str = None) -> Dict:
        """
        Import parsed document (from Word parser) into database.

        PURPOSE: Take output from word_parser and create all entities.
                 ALL config values are stored at LOCATION level, never clinic level.

        PARAMETERS:
            parsed_data: Output from ClinicSpecParser.parse()
            program_id: Program to import under
            source_document: Original document filename

        RETURNS:
            Dict with counts of created entities

        Creates:
        - Clinic (geographic area container, internal use only)
        - Locations (the actual service locations = "clinics" in business terms)
        - Config values at LOCATION level only
        - Providers (at locations)

        KEY CONCEPT: "Portland" is a geographic AREA, not a clinic.
        The actual clinics ARE the service locations (PCI Breast Surgery West, etc.)
        All config values must be distributed to these location-level entities.

        WHY THIS APPROACH: Every config value must reach the location level:
        - If location-specific in document → parse and distribute to matching locations
        - If shared value → distribute same value to ALL locations
        - NEVER create clinic-level config entries

        AVIATION ANALOGY: Like waypoint-based flight planning - every parameter
        must be specified at each waypoint (location), not just the route level.
        """
        counts = {
            'clinics': 0,
            'locations': 0,
            'configs': 0,
            'location_configs': 0,  # All configs are location-level now
            'providers': 0
        }

        # Get scope locations from parsed document - these are the actual service locations
        scope_locations = parsed_data.get('scope_locations', [])

        if not scope_locations:
            print("  Warning: No scope_locations found in document")
            return counts

        # Create or get clinic (geographic area container)
        # NOTE: This is for database structure only - not shown in exports
        clinic_name = parsed_data.get('clinic_name', 'Unknown Clinic')
        existing_clinic = self.get_clinic_by_name(program_id, clinic_name)

        if existing_clinic:
            clinic_id = existing_clinic['clinic_id']
        else:
            clinic_id = self.create_clinic(program_id, clinic_name)
            counts['clinics'] = 1

        # Create locations from scope and build lookup dicts
        # location_lookup: maps location name (exact) to location_id
        # location_lookup_lower: maps lowercased name to location_id (for matching)
        location_lookup = {}  # Exact name → location_id
        location_lookup_lower = {}  # Lower name → location_id

        for loc_name in scope_locations:
            existing = self.get_location_by_name(clinic_id, loc_name)
            if not existing:
                location_id = self.create_location(clinic_id, loc_name)
                counts['locations'] += 1
            else:
                location_id = existing['location_id']

            location_lookup[loc_name] = location_id
            location_lookup_lower[loc_name.lower()] = location_id

        # =====================================================================
        # IMPORT CONFIGURATIONS - ALL values go to LOCATION level
        # =====================================================================
        # Use mapped_configs from the parser (already processed with distribution logic)

        cursor = self.conn.cursor()

        # Get set of valid config keys from definitions
        cursor.execute("SELECT config_key FROM config_definitions")
        valid_keys = {row['config_key'] for row in cursor.fetchall()}

        # Process mapped_configs - these have location distribution already applied
        location_config_batch = []

        for cfg in parsed_data.get('mapped_configs', []):
            config_key = cfg.get('config_key', '')
            value = cfg.get('value')
            rationale = cfg.get('rationale', '')

            # Skip unmapped or empty configs
            if not config_key or config_key.startswith('unmapped_'):
                continue
            if not value or 'same as default' in str(value).lower():
                continue

            # Check if this is a location-specific key (contains @location suffix)
            # NOTE: Don't check valid_keys here because the full key includes location
            # We check base_key validity inside the @ block
            if '@' in config_key:
                # Format: "helpdesk_phone@PCI BREAST SURGERY WEST"
                base_key, location_name = config_key.split('@', 1)

                if base_key not in valid_keys:
                    continue

                # Find the location_id for this location name
                loc_id = location_lookup.get(location_name)
                if not loc_id:
                    loc_id = location_lookup_lower.get(location_name.lower())

                if loc_id:
                    location_config_batch.append({
                        'config_key': base_key,
                        'value': value,
                        'location_id': loc_id,
                        'rationale': rationale
                    })
            elif '_by_location' in config_key:
                # This is a location distribution dict - process each location
                if isinstance(value, dict):
                    base_key = config_key.replace('_by_location', '')
                    if base_key not in valid_keys:
                        continue

                    for loc_name, loc_value in value.items():
                        loc_id = location_lookup.get(loc_name)
                        if not loc_id:
                            loc_id = location_lookup_lower.get(loc_name.lower())

                        if loc_id:
                            location_config_batch.append({
                                'config_key': base_key,
                                'value': loc_value,
                                'location_id': loc_id,
                                'rationale': rationale
                            })
            else:
                # Regular config - distribute to ALL locations (shared value)
                # Must be a valid config key
                if config_key not in valid_keys:
                    continue

                for loc_name, loc_id in location_lookup.items():
                    location_config_batch.append({
                        'config_key': config_key,
                        'value': value,
                        'location_id': loc_id,
                        'rationale': rationale
                    })

        # =====================================================================
        # INSERT LOCATION-LEVEL CONFIGS
        # =====================================================================
        # NOTE: ALL configs go to location level - no clinic level entries
        history_batch = []

        for cfg in location_config_batch:
            config_key = cfg['config_key']
            location_id = cfg['location_id']

            # Check if exists at this location
            cursor.execute("""
                SELECT value_id, value FROM config_values
                WHERE config_key = ? AND program_id = ? AND location_id = ?
            """, (config_key, program_id, location_id))

            existing = cursor.fetchone()

            if existing:
                old_value = existing['value']
                cursor.execute("""
                    UPDATE config_values
                    SET value = ?, source = 'import', source_document = ?,
                        rationale = ?, updated_date = ?
                    WHERE value_id = ?
                """, (cfg['value'], source_document, cfg['rationale'],
                      datetime.now().isoformat(), existing['value_id']))

                # Only log if value actually changed
                if old_value != cfg['value']:
                    history_batch.append({
                        'config_key': config_key,
                        'program_id': program_id,
                        'clinic_id': clinic_id,
                        'location_id': location_id,
                        'old_value': old_value,
                        'new_value': cfg['value'],
                        'reason': cfg['rationale']
                    })
            else:
                cursor.execute("""
                    INSERT INTO config_values
                    (config_key, program_id, clinic_id, location_id, value, is_override,
                     source, source_document, rationale)
                    VALUES (?, ?, ?, ?, ?, TRUE, 'import', ?, ?)
                """, (config_key, program_id, clinic_id, location_id,
                      cfg['value'], source_document, cfg['rationale']))

                # Log new config creation
                history_batch.append({
                    'config_key': config_key,
                    'program_id': program_id,
                    'clinic_id': clinic_id,
                    'location_id': location_id,
                    'old_value': None,
                    'new_value': cfg['value'],
                    'reason': cfg['rationale']
                })

            counts['location_configs'] += 1

        # Batch insert history entries for audit trail
        # This is critical for FDA 21 CFR Part 11 compliance
        for hist in history_batch:
            cursor.execute("""
                INSERT INTO config_history
                (config_key, program_id, clinic_id, location_id,
                 old_value, new_value, changed_by, change_reason, source_document)
                VALUES (?, ?, ?, ?, ?, ?, 'import', ?, ?)
            """, (hist['config_key'], hist['program_id'], hist['clinic_id'],
                  hist['location_id'], hist['old_value'], hist['new_value'],
                  hist['reason'], source_document))

        # Commit all configs and history at once (batch)
        self.conn.commit()
        print(f"  Logged {len(history_batch)} config history entries")

        # Import providers if present
        for provider_data in parsed_data.get('providers', []):
            # Try to match provider location to our locations
            provider_loc = provider_data.get('location', '')
            location = self._find_matching_location(clinic_id, provider_loc)

            if location:
                self.add_provider(
                    location_id=location['location_id'],
                    name=provider_data.get('name'),
                    npi=provider_data.get('npi'),
                    role=provider_data.get('role', 'Ordering Provider')
                )
                counts['providers'] += 1

        print(f"Import complete: {counts}")
        return counts

    def _is_location_specific_config(self, category: str, parsed_override: Dict) -> bool:
        """
        Determine if a config category should be stored at location level.

        PURPOSE: Identify configs where different locations might have different
                 values (like phone numbers, hours) vs configs that apply to
                 the whole clinic.

        PARAMETERS:
            category: The category name from the Word doc
            parsed_override: Dict of parsed location: value pairs

        RETURNS:
            True if this should be stored at location level

        WHY THIS APPROACH: Some configs naturally vary by location (phone, hours,
        signature blocks) while others apply clinic-wide (branding, algorithms).
        We detect this by:
        1. Checking the category name for location-specific indicators
        2. Checking if the parsed values have multiple location keys
        """
        category_lower = category.lower()

        # Categories that are typically location-specific
        location_specific_categories = [
            'helpdesk phone',
            'help desk phone',
            'phone',
            'hours',
            'operating hours',
            'signature',
            'signature block',
        ]

        for loc_cat in location_specific_categories:
            if loc_cat in category_lower:
                return True

        # Also check if we have multiple distinct location-value pairs
        # This suggests location-specific data even if category doesn't indicate it
        if parsed_override and len(parsed_override) > 1:
            # Check if keys look like location names
            location_keywords = ['surgery', 'clinic', 'center', 'care', 'west', 'east']
            location_like_keys = 0
            for key in parsed_override.keys():
                key_lower = key.lower()
                if any(kw in key_lower for kw in location_keywords):
                    location_like_keys += 1
            # If most keys look like locations, treat as location-specific
            if location_like_keys >= len(parsed_override) * 0.5:
                return True

        return False

    def _get_config_keys_for_category(self, category: str) -> List[str]:
        """
        Get the config keys that correspond to a category.

        PURPOSE: Map category names to the actual config_key values
                 used in the database.

        RETURNS:
            List of config_key strings for this category

        WHY THIS APPROACH: The Word doc uses human-readable category names
        but the database uses normalized keys.
        """
        category_lower = category.lower()

        # Map categories to their config keys
        if 'phone' in category_lower and 'help' in category_lower:
            return ['helpdesk_phone']
        elif 'email' in category_lower and 'help' in category_lower:
            return ['helpdesk_email']
        elif 'hours' in category_lower or 'operation' in category_lower:
            return ['hours_open', 'hours_close']
        elif 'signature' in category_lower:
            return ['signature_block_email', 'signature_block_sms']

        # Default: use the extract method which handles more categories
        return list(self._extract_config_values(category, 'dummy').keys())

    def _extract_config_values(self, category: str, cell_text: str) -> Dict[str, str]:
        """
        Extract individual config values from a cell based on category.

        PURPOSE: Parse complex cells that contain multiple values
                 and return the appropriate value for each config key.

        PARAMETERS:
            category: The category name from the Word doc
            cell_text: The raw cell content

        RETURNS:
            Dict mapping config_key to extracted value

        EXAMPLE:
            category = "Patient Appointment Extract – Filtering"
            cell_text = "Patient Status: New\nService Locations: 4000045001, 405141030005"

            Returns: {
                'extract_patient_status': 'New',
                'extract_service_locations': '4000045001, 405141030005'
            }
        """
        result = {}
        category_lower = category.lower()

        # ---- APPOINTMENT EXTRACT ----
        if 'appointment extract' in category_lower:
            # Parse structured content
            lines = cell_text.split('\n')
            current_key = None
            current_value = []

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if line.lower().startswith('patient status'):
                    if current_key:
                        result[current_key] = ' '.join(current_value).strip()
                    current_key = 'extract_patient_status'
                    # Extract value after colon
                    if ':' in line:
                        current_value = [line.split(':', 1)[1].strip()]
                    else:
                        current_value = []

                elif line.lower().startswith('service location'):
                    if current_key:
                        result[current_key] = ' '.join(current_value).strip()
                    current_key = 'extract_service_locations'
                    if ':' in line:
                        current_value = [line.split(':', 1)[1].strip()]
                    else:
                        current_value = []

                elif line.lower().startswith('location specific') or \
                     line.lower().startswith('appointment type'):
                    if current_key:
                        result[current_key] = ' '.join(current_value).strip()
                    current_key = 'extract_appointment_types'
                    if ':' in line:
                        current_value = [line.split(':', 1)[1].strip()]
                    else:
                        current_value = []

                elif current_key:
                    # Continuation of current section
                    current_value.append(line)

            # Don't forget the last one
            if current_key:
                result[current_key] = ' '.join(current_value).strip()

        # ---- INVITATION SCHEDULE ----
        elif 'invitation schedule' in category_lower:
            result['invitation_days_before'] = cell_text
            result['invitation_channels'] = cell_text

        # ---- EMAIL BRANDING ----
        elif 'email branding' in category_lower or 'branding' in category_lower:
            result['email_branding_template'] = cell_text

        # ---- SIGNATURE ----
        elif 'signature' in category_lower:
            result['signature_block_email'] = cell_text
            result['signature_block_sms'] = cell_text

        # ---- ASSESSMENT LOCKOUT ----
        elif 'lockout' in category_lower or 'assessment' in category_lower:
            result['assessment_lockout_period_months'] = cell_text

        # ---- HELPDESK EMAIL ----
        elif 'help' in category_lower and 'email' in category_lower:
            result['helpdesk_email'] = cell_text
            result['helpdesk_workflow'] = cell_text

        # ---- HELPDESK PHONE ----
        elif 'help' in category_lower and 'phone' in category_lower:
            result['helpdesk_phone'] = cell_text

        # ---- HOURS ----
        elif 'hours' in category_lower or 'operation' in category_lower:
            result['hours_open'] = cell_text
            result['hours_close'] = cell_text

        # ---- TC MODULE ----
        elif 'tc module' in category_lower:
            result['tc_scoring_enabled'] = 'true' if 'enabled' in cell_text.lower() else 'false'

        # ---- TC AGE ----
        elif 'tc age' in category_lower or 'age range' in category_lower:
            result['tc_minimum_age'] = cell_text

        # ---- VERSIONS ----
        elif 'risk assessment' in category_lower and 'version' in category_lower:
            result['version_risk_assessment'] = cell_text
        elif 'tc algorithm' in category_lower:
            result['version_tc_algorithm'] = cell_text
        elif 'nccn' in category_lower:
            result['version_nccn_algorithm'] = cell_text
        elif 'econsent' in category_lower or 'consent' in category_lower:
            result['version_econsent'] = cell_text

        # ---- LAB ORDER ----
        elif 'lab order' in category_lower or 'default lab order' in category_lower:
            # Parse test code and name
            for line in cell_text.split('\n'):
                line = line.strip()
                if line.lower().startswith('test code'):
                    if ':' in line:
                        result['lab_default_test_code'] = line.split(':', 1)[1].strip()
                elif line.lower().startswith('test name'):
                    if ':' in line:
                        result['lab_default_test_name'] = line.split(':', 1)[1].strip()

        # ---- DEFAULT LAB ----
        elif 'default lab' in category_lower and 'order' not in category_lower:
            result['lab_default_name'] = cell_text

        # ---- SAMPLE ----
        elif 'sample' in category_lower:
            if 'optional' in category_lower:
                result['lab_optional_samples'] = cell_text
            else:
                result['lab_default_sample'] = cell_text

        # ---- OPTIONAL TESTS ----
        elif 'optional' in category_lower and 'test' in category_lower:
            result['lab_optional_tests'] = cell_text

        return result

    def _find_matching_location(self, clinic_id: str, provider_location: str) -> Optional[Dict]:
        """
        Find a location that matches the provider's location string.

        PURPOSE: Match provider location names (which may be abbreviated)
                 to actual location records in the database.

        Uses fuzzy matching since provider locations might be:
        - "PCI Breast Care Clinic West" but DB has "PCI BREAST SURGERY WEST"
        - "PCI Franz Breast Care" matching "PCI FRANZ BREAST CARE"
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM locations WHERE clinic_id = ?
        """, (clinic_id,))

        locations = cursor.fetchall()
        provider_loc_lower = provider_location.lower()

        # Try exact match first
        for loc in locations:
            if loc['name'].lower() == provider_loc_lower:
                return dict(loc)

        # Try partial match - find best overlap
        best_match = None
        best_score = 0

        for loc in locations:
            loc_words = set(loc['name'].lower().split())
            prov_words = set(provider_loc_lower.split())

            # Count overlapping words
            overlap = len(loc_words & prov_words)
            if overlap > best_score:
                best_score = overlap
                best_match = loc

        # Require at least 2 words to match
        if best_score >= 2:
            return dict(best_match)

        return None

    # ========================================================================
    # AUDIT OPERATIONS
    # ========================================================================

    def get_config_history(self, config_key: str, program_id: str,
                           clinic_id: str = None, location_id: str = None) -> List[Dict]:
        """
        Get change history for a specific config.

        RETURNS: List of historical changes
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT * FROM config_history
            WHERE config_key = ?
              AND program_id = ?
              AND (clinic_id = ? OR (clinic_id IS NULL AND ? IS NULL))
              AND (location_id = ? OR (location_id IS NULL AND ? IS NULL))
            ORDER BY changed_date DESC
        """, (config_key, program_id, clinic_id, clinic_id, location_id, location_id))

        return [dict(row) for row in cursor.fetchall()]

    def get_all_changes(self, program_id: str,
                        start_date: str = None,
                        end_date: str = None) -> List[Dict]:
        """
        Get all config changes for a program in date range.

        PARAMETERS:
            program_id: Program to query
            start_date: ISO date string for start of range
            end_date: ISO date string for end of range

        RETURNS: List of all changes
        """
        cursor = self.conn.cursor()

        query = """
            SELECT ch.*, cd.display_name, cd.category
            FROM config_history ch
            LEFT JOIN config_definitions cd ON ch.config_key = cd.config_key
            WHERE ch.program_id = ?
        """
        params = [program_id]

        if start_date:
            query += " AND ch.changed_date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND ch.changed_date <= ?"
            params.append(end_date)

        query += " ORDER BY ch.changed_date DESC"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    # ------------------------------------------------------------------------
    # INPUT VALIDATION
    # ------------------------------------------------------------------------

    def _validate_npi(self, npi: str, strict: bool = False) -> Tuple[bool, str]:
        """
        Validate NPI (National Provider Identifier) format.

        PURPOSE: Ensure NPIs meet CMS standards before storing

        PARAMETERS:
            npi: The NPI string to validate
            strict: If True, requires valid Luhn checksum

        RETURNS:
            Tuple of (is_valid: bool, normalized_npi_or_error: str)
            If valid, returns (True, normalized_npi)
            If invalid, returns (False, error_message)

        NPI FORMAT:
        - Must be exactly 10 digits
        - First digit must be 1 or 2 (Individual=1, Organization=2)
        - Last digit is Luhn check digit (ISO standard)

        AVIATION ANALOGY: Like validating a tail number - must follow
        specific format rules (N-number in US must start with N).

        WHY THIS APPROACH: NPIs have a strict format defined by CMS.
        Validating on input prevents bad data from entering the database.
        """
        if not npi:
            return (True, None)  # None is acceptable

        # Strip any non-digit characters
        digits_only = ''.join(c for c in npi if c.isdigit())

        # Check length (allow 9 for known typos, but warn)
        if len(digits_only) == 9:
            # Some docs have typos with 9 digits - accept with warning
            print(f"  Warning: NPI '{npi}' has only 9 digits (expected 10)")
            return (True, digits_only)

        if len(digits_only) != 10:
            return (False, f"NPI must be 10 digits, got {len(digits_only)}")

        # Check first digit (1 = individual, 2 = organization)
        if digits_only[0] not in ('1', '2'):
            return (False, f"NPI must start with 1 or 2, got '{digits_only[0]}'")

        # Validate Luhn checksum if strict mode
        if strict:
            if not self._validate_luhn(digits_only):
                return (False, f"NPI '{digits_only}' failed Luhn checksum validation")

        return (True, digits_only)

    def _validate_luhn(self, digits: str) -> bool:
        """
        Validate a number using the Luhn algorithm (ISO/IEC 7812-1).

        PURPOSE: Verify NPI check digit is valid

        Used for NPIs, credit cards, and other identification numbers.

        ALGORITHM:
        1. Starting from rightmost digit, double every second digit
        2. If doubled digit > 9, subtract 9
        3. Sum all digits
        4. Valid if sum % 10 == 0

        WHY THIS APPROACH: Standard ISO validation used by CMS for NPIs.
        """
        # For NPI, prefix with "80840" before applying Luhn
        # (per CMS NPI standard)
        prefixed = "80840" + digits

        total = 0
        for i, char in enumerate(reversed(prefixed)):
            digit = int(char)
            if i % 2 == 1:  # Every second digit from right
                digit *= 2
                if digit > 9:
                    digit -= 9
            total += digit

        return total % 10 == 0

    def _normalize_phone(self, phone: str) -> str:
        """
        Normalize phone number to consistent format.

        PURPOSE: Store all phone numbers in consistent format for display

        PARAMETERS:
            phone: Raw phone string (various formats accepted)

        RETURNS:
            Normalized phone string in format: XXX.XXX.XXXX

        ACCEPTED INPUTS:
            "5032166407"      → "503.216.6407"
            "(503) 216-6407"  → "503.216.6407"
            "503-216-6407"    → "503.216.6407"
            "1-503-216-6407"  → "503.216.6407"
            "503.216.6407"    → "503.216.6407"

        WHY THIS APPROACH: Consistent storage makes display and comparison
        easier. Using dots is clean and common in healthcare settings.
        """
        if not phone:
            return phone

        # Strip all non-digit characters
        digits = ''.join(c for c in phone if c.isdigit())

        # Remove leading 1 (US country code)
        if len(digits) == 11 and digits[0] == '1':
            digits = digits[1:]

        # Check for valid 10-digit US phone
        if len(digits) == 10:
            return f"{digits[:3]}.{digits[3:6]}.{digits[6:]}"

        # If not 10 digits, return original (might be extension or intl)
        return phone

    def _normalize_config_value(self, config_key: str, value: str) -> str:
        """
        Normalize config value based on its type.

        PURPOSE: Ensure consistent storage format for common value types

        PARAMETERS:
            config_key: The configuration key (determines normalization)
            value: The raw value to normalize

        RETURNS:
            Normalized value string

        WHY THIS APPROACH: Different config types need different treatment.
        Phone numbers should be normalized, booleans lowercase, etc.
        """
        if not value:
            return value

        # Phone number fields
        if 'phone' in config_key.lower():
            return self._normalize_phone(value)

        # Boolean fields
        if 'enabled' in config_key.lower() or config_key.startswith('is_'):
            value_lower = value.lower().strip()
            if value_lower in ('true', 'yes', '1', 'enabled', 'on'):
                return 'true'
            elif value_lower in ('false', 'no', '0', 'disabled', 'off'):
                return 'false'

        # Time fields - normalize to HH:MM format
        if 'hours_' in config_key.lower() or config_key.endswith('_time'):
            # Try to parse various time formats
            import re
            # Match patterns like "8:00 AM", "08:00", "8am"
            time_match = re.match(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', value, re.IGNORECASE)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2) or 0)
                ampm = time_match.group(3)

                if ampm and ampm.lower() == 'pm' and hour < 12:
                    hour += 12
                elif ampm and ampm.lower() == 'am' and hour == 12:
                    hour = 0

                return f"{hour:02d}:{minute:02d}"

        return value

    def _is_override(self, config_key: str, program_id: str,
                     clinic_id: str, location_id: str, value: str) -> bool:
        """
        Determine if a value is an override of the parent level.

        RETURNS: True if value differs from parent level
        """
        # If setting at program level, check against default
        if not clinic_id and not location_id:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT default_value FROM config_definitions WHERE config_key = ?
            """, (config_key,))
            row = cursor.fetchone()
            return row and row['default_value'] != value

        # Otherwise, get parent value and compare
        if location_id:
            parent = self.get_config(config_key, program_id, clinic_id, None)
        else:
            parent = self.get_config(config_key, program_id, None, None)

        return parent['value'] != value

    def _log_audit(self, record_type: str, record_id: str, action: str,
                   old_value: str = None, new_value: str = None,
                   changed_by: str = 'system', reason: str = None) -> None:
        """
        Log to the shared audit_history table.

        This uses the audit table from the Requirements Toolkit schema.
        """
        cursor = self.conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO audit_history
                (record_type, record_id, action, old_value, new_value,
                 changed_by, changed_date, change_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (record_type, record_id, action, old_value, new_value,
                  changed_by, datetime.now().isoformat(), reason))
        except sqlite3.OperationalError:
            # audit_history table might not exist (if running standalone)
            pass

    def _log_config_history(self, config_key: str, program_id: str,
                            clinic_id: str, location_id: str,
                            old_value: str, new_value: str,
                            changed_by: str, reason: str,
                            source_document: str) -> None:
        """Log to config_history table for detailed config tracking."""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO config_history
            (config_key, program_id, clinic_id, location_id,
             old_value, new_value, changed_by, change_reason, source_document)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (config_key, program_id, clinic_id, location_id,
              old_value, new_value, changed_by, reason, source_document))

    def _map_category_to_keys(self, raw_category: str) -> List[str]:
        """
        Map raw category names from Word docs to config keys.

        EXAMPLE:
        'Patient Appointment Extract – Filtering' →
            ['extract_patient_status', 'extract_service_locations']
        """
        # Mapping of common category patterns to config keys
        mappings = {
            'appointment extract': ['extract_patient_status', 'extract_service_locations',
                                    'extract_appointment_types'],
            'invitation': ['invitation_days_before', 'invitation_channels'],
            'reminder': ['reminder_days_before', 'reminder_frequency'],
            'sms': ['sms_aws_approval_destination'],
            'email branding': ['email_branding_template', 'email_branding_logo'],
            'signature': ['signature_block_email', 'signature_block_sms'],
            'assessment': ['assessment_lockout_trigger', 'assessment_lockout_period_months'],
            'helpdesk': ['helpdesk_email', 'helpdesk_phone', 'helpdesk_workflow'],
            'hours': ['hours_open', 'hours_close'],
            'tc scoring': ['tc_scoring_enabled', 'tc_minimum_age'],
            'version': ['version_tc_algorithm', 'version_nccn_algorithm',
                        'version_econsent', 'version_risk_assessment'],
            'lab': ['lab_default_name', 'lab_default_test_code', 'lab_default_sample']
        }

        raw_lower = raw_category.lower()
        for pattern, keys in mappings.items():
            if pattern in raw_lower:
                return keys

        return []

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_config_manager(db_path: str = DEFAULT_DB_PATH) -> ConfigurationManager:
    """
    Get a ConfigurationManager instance.

    PURPOSE: Factory function for getting a manager instance

    R EQUIVALENT: Like a constructor function in R

    EXAMPLE:
        cm = get_config_manager()
        cm.initialize_schema()
    """
    return ConfigurationManager(db_path)


# ============================================================================
# MODULE TEST
# ============================================================================

if __name__ == "__main__":
    # Quick test of the module
    print("Testing ConfigurationManager...")

    cm = ConfigurationManager()
    cm.initialize_schema()
    cm.load_definitions_from_yaml()

    # Test creating a program
    program_id = cm.create_program("Test Program", "TEST", program_type='clinic_based')

    # Test creating a clinic and location
    clinic_id = cm.create_clinic(program_id, "Test Clinic", code="TCLI")
    location_id = cm.create_location(clinic_id, "Test Location", code="1234")

    # Test setting and getting config
    cm.set_config('helpdesk_phone', '555-1234', program_id, clinic_id, location_id)
    result = cm.get_config('helpdesk_phone', program_id, clinic_id, location_id)
    print(f"Config result: {result}")

    # Test hierarchy
    hierarchy = cm.get_program_hierarchy(program_id)
    print(f"Hierarchy: {json.dumps(hierarchy, indent=2)}")

    print("Tests complete!")
