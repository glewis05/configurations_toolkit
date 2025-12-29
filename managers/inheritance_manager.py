"""
Inheritance Manager - Handle Program → Clinic → Location inheritance

PURPOSE: Manage configuration inheritance and override resolution
         across the organizational hierarchy

R EQUIVALENT: Like managing nested environments in R where child
environments inherit from parents but can override specific values

AVIATION ANALOGY: Like aircraft configuration inheritance:
- Type Certificate (Program level) - base configuration
- Fleet-specific (Clinic level) - airline customizations
- Tail number (Location level) - individual aircraft specifics

AUTHOR: Glen Lewis
DATE: 2024
"""

import json
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.config_manager import ConfigurationManager


class InheritanceManager:
    """
    PURPOSE: Handle Program → Clinic → Location inheritance

    Provides methods for:
    - Resolving effective values through inheritance chain
    - Comparing values at different levels
    - Propagating changes down the hierarchy
    - Validating inheritance consistency

    PARAMETERS:
        config_manager: ConfigurationManager instance

    EXAMPLE:
        cm = ConfigurationManager()
        im = InheritanceManager(cm)

        # Get value with full inheritance info
        result = im.resolve_with_inheritance('helpdesk_phone', program_id, clinic_id)
        print(result['value'])  # The effective value
        print(result['inheritance_chain'])  # Where each level got its value
    """

    def __init__(self, config_manager: ConfigurationManager):
        """
        Initialize with a ConfigurationManager.

        WHY THIS APPROACH: We wrap the ConfigurationManager to add
        inheritance-specific operations while keeping CRUD in one place.
        """
        self.cm = config_manager
        self.conn = config_manager.conn

    def resolve_with_inheritance(self, config_key: str, program_id: str,
                                 clinic_id: str = None,
                                 location_id: str = None) -> Dict:
        """
        Resolve a config value and show the full inheritance chain.

        PURPOSE: Get the effective value AND show where each level
                 in the hierarchy gets its value

        PARAMETERS:
            config_key: The configuration key to look up
            program_id: Program context
            clinic_id: Optional clinic context
            location_id: Optional location context

        RETURNS:
            Dict containing:
            - value: The effective value at the requested level
            - effective_level: Where the value came from
            - inheritance_chain: List of dicts showing each level's value

        EXAMPLE OUTPUT:
            {
                'value': '503.216.6407',
                'effective_level': 'clinic',
                'inheritance_chain': [
                    {'level': 'default', 'value': None, 'source': 'definition'},
                    {'level': 'program', 'value': '800.555.0000', 'source': 'manual'},
                    {'level': 'clinic', 'value': '503.216.6407', 'source': 'import', 'is_override': True}
                ]
            }
        """
        cursor = self.conn.cursor()

        # Build the inheritance chain
        chain = []

        # 1. Get default value from definitions
        cursor.execute("""
            SELECT default_value FROM config_definitions WHERE config_key = ?
        """, (config_key,))
        defn = cursor.fetchone()
        default_val = defn['default_value'] if defn else None

        chain.append({
            'level': 'default',
            'value': default_val,
            'source': 'definition',
            'is_override': False
        })

        # 2. Get program-level value
        cursor.execute("""
            SELECT value, source, source_document, is_override
            FROM config_values
            WHERE config_key = ? AND program_id = ?
              AND clinic_id IS NULL AND location_id IS NULL
        """, (config_key, program_id))
        prog_row = cursor.fetchone()

        if prog_row:
            chain.append({
                'level': 'program',
                'value': prog_row['value'],
                'source': prog_row['source'],
                'source_document': prog_row['source_document'],
                'is_override': bool(prog_row['is_override'])
            })

        # 3. Get clinic-level value (if applicable)
        if clinic_id:
            cursor.execute("""
                SELECT value, source, source_document, is_override
                FROM config_values
                WHERE config_key = ? AND program_id = ? AND clinic_id = ?
                  AND location_id IS NULL
            """, (config_key, program_id, clinic_id))
            clinic_row = cursor.fetchone()

            if clinic_row:
                chain.append({
                    'level': 'clinic',
                    'value': clinic_row['value'],
                    'source': clinic_row['source'],
                    'source_document': clinic_row['source_document'],
                    'is_override': bool(clinic_row['is_override'])
                })

        # 4. Get location-level value (if applicable)
        if location_id:
            cursor.execute("""
                SELECT value, source, source_document, is_override
                FROM config_values
                WHERE config_key = ? AND program_id = ?
                  AND clinic_id = ? AND location_id = ?
            """, (config_key, program_id, clinic_id, location_id))
            loc_row = cursor.fetchone()

            if loc_row:
                chain.append({
                    'level': 'location',
                    'value': loc_row['value'],
                    'source': loc_row['source'],
                    'source_document': loc_row['source_document'],
                    'is_override': bool(loc_row['is_override'])
                })

        # Determine effective value (last non-None value in chain)
        effective_value = None
        effective_level = 'default'

        for link in chain:
            if link['value'] is not None:
                effective_value = link['value']
                effective_level = link['level']

        return {
            'value': effective_value,
            'effective_level': effective_level,
            'inheritance_chain': chain
        }

    def compare_levels(self, config_key: str, program_id: str,
                       clinic_id: str = None) -> Dict:
        """
        Compare configuration values across all levels.

        PURPOSE: See how a config differs between program, clinic, and locations

        RETURNS:
            Dict with program value, clinic value, and location values
        """
        result = {
            'config_key': config_key,
            'program_value': None,
            'clinic_value': None,
            'location_values': []
        }

        # Get program value
        prog = self.cm.get_config(config_key, program_id)
        result['program_value'] = {
            'value': prog['value'],
            'source': prog['source']
        }

        if not clinic_id:
            return result

        # Get clinic value
        clinic = self.cm.get_config(config_key, program_id, clinic_id)
        result['clinic_value'] = {
            'value': clinic['value'],
            'source': clinic['source'],
            'is_different': clinic['value'] != prog['value']
        }

        # Get all location values under this clinic
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT l.location_id, l.name,
                   cv.value, cv.source, cv.is_override
            FROM locations l
            LEFT JOIN config_values cv ON l.location_id = cv.location_id
                                       AND cv.config_key = ?
            WHERE l.clinic_id = ?
            ORDER BY l.name
        """, (config_key, clinic_id))

        for row in cursor.fetchall():
            # Get effective value for this location
            effective = self.cm.get_config(config_key, program_id, clinic_id, row['location_id'])

            result['location_values'].append({
                'location_id': row['location_id'],
                'location_name': row['name'],
                'explicit_value': row['value'],  # Value set at this level (may be None)
                'effective_value': effective['value'],  # Inherited or explicit
                'is_override': bool(row['is_override']) if row['is_override'] else False,
                'source': row['source']
            })

        return result

    def get_all_overrides(self, program_id: str) -> List[Dict]:
        """
        Get all overridden values across the entire program hierarchy.

        PURPOSE: Quick view of what's customized vs inherited

        RETURNS:
            List of all override configurations
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT cv.*, cd.display_name, cd.category,
                   c.name as clinic_name, l.name as location_name
            FROM config_values cv
            JOIN config_definitions cd ON cv.config_key = cd.config_key
            LEFT JOIN clinics c ON cv.clinic_id = c.clinic_id
            LEFT JOIN locations l ON cv.location_id = l.location_id
            WHERE cv.program_id = ? AND cv.is_override = TRUE
            ORDER BY cd.category, cd.display_order
        """, (program_id,))

        return [dict(row) for row in cursor.fetchall()]

    def propagate_value(self, config_key: str, value: str,
                        program_id: str, from_level: str,
                        force: bool = False) -> Dict[str, int]:
        """
        Propagate a value down the hierarchy.

        PURPOSE: Push a program value to all clinics, or clinic value to all locations

        PARAMETERS:
            config_key: Config to propagate
            value: New value to set
            program_id: Program context
            from_level: 'program' or 'clinic' - where to propagate from
            force: If True, overwrite existing values; if False, only set where not overridden

        RETURNS:
            Dict with counts of affected entities

        AVIATION ANALOGY: Like an Airworthiness Directive that affects all aircraft
        of a type - sometimes you push changes down to the whole fleet.
        """
        cursor = self.conn.cursor()
        counts = {'updated': 0, 'skipped': 0}

        if from_level == 'program':
            # Propagate to all clinics
            cursor.execute("""
                SELECT clinic_id FROM clinics WHERE program_id = ?
            """, (program_id,))

            for row in cursor.fetchall():
                clinic_id = row['clinic_id']

                if not force:
                    # Check if clinic has explicit value
                    existing = self.cm.get_config(config_key, program_id, clinic_id)
                    if existing['effective_level'] == 'clinic':
                        counts['skipped'] += 1
                        continue

                self.cm.set_config(config_key, value, program_id, clinic_id,
                                   source='propagated',
                                   rationale=f'Propagated from program level')
                counts['updated'] += 1

        return counts

    def validate_inheritance(self, program_id: str) -> List[Dict]:
        """
        Validate inheritance consistency for a program.

        PURPOSE: Find any orphaned values or inconsistencies

        Checks:
        - Config values for non-existent clinics/locations
        - Values set at wrong level (based on applies_to)
        - Missing required configs

        RETURNS:
            List of validation issues found
        """
        issues = []
        cursor = self.conn.cursor()

        # Check for orphaned clinic configs
        cursor.execute("""
            SELECT cv.*
            FROM config_values cv
            WHERE cv.program_id = ?
              AND cv.clinic_id IS NOT NULL
              AND cv.clinic_id NOT IN (SELECT clinic_id FROM clinics WHERE program_id = ?)
        """, (program_id, program_id))

        for row in cursor.fetchall():
            issues.append({
                'type': 'orphaned_clinic_config',
                'config_key': row['config_key'],
                'clinic_id': row['clinic_id'],
                'message': f"Config {row['config_key']} references non-existent clinic {row['clinic_id']}"
            })

        # Check for orphaned location configs
        cursor.execute("""
            SELECT cv.*
            FROM config_values cv
            WHERE cv.program_id = ?
              AND cv.location_id IS NOT NULL
              AND cv.location_id NOT IN (
                  SELECT l.location_id FROM locations l
                  JOIN clinics c ON l.clinic_id = c.clinic_id
                  WHERE c.program_id = ?
              )
        """, (program_id, program_id))

        for row in cursor.fetchall():
            issues.append({
                'type': 'orphaned_location_config',
                'config_key': row['config_key'],
                'location_id': row['location_id'],
                'message': f"Config {row['config_key']} references non-existent location {row['location_id']}"
            })

        # Check for values set at wrong level
        cursor.execute("""
            SELECT cv.*, cd.applies_to
            FROM config_values cv
            JOIN config_definitions cd ON cv.config_key = cd.config_key
            WHERE cv.program_id = ?
        """, (program_id,))

        for row in cursor.fetchall():
            applies_to = row['applies_to']

            # Check if value is at appropriate level
            if applies_to == 'program' and (row['clinic_id'] or row['location_id']):
                issues.append({
                    'type': 'wrong_level',
                    'config_key': row['config_key'],
                    'message': f"Config {row['config_key']} applies to program only but set at lower level"
                })
            elif applies_to == 'clinic' and row['location_id']:
                issues.append({
                    'type': 'wrong_level',
                    'config_key': row['config_key'],
                    'message': f"Config {row['config_key']} applies to clinic only but set at location level"
                })

        # Check for missing required configs at program level
        cursor.execute("""
            SELECT cd.config_key, cd.display_name
            FROM config_definitions cd
            WHERE cd.is_required = TRUE
              AND cd.applies_to IN ('program', 'all')
              AND cd.config_key NOT IN (
                  SELECT config_key FROM config_values
                  WHERE program_id = ? AND clinic_id IS NULL AND location_id IS NULL
              )
              AND cd.default_value IS NULL
        """, (program_id,))

        for row in cursor.fetchall():
            issues.append({
                'type': 'missing_required',
                'config_key': row['config_key'],
                'message': f"Required config {row['display_name']} not set at program level"
            })

        return issues

    def get_inheritance_tree(self, config_key: str, program_id: str) -> Dict:
        """
        Get a visual tree representation of inheritance for a config.

        PURPOSE: Visual representation of how a value flows through hierarchy

        RETURNS:
            Nested dict representing the inheritance tree
        """
        cursor = self.conn.cursor()

        # Get program info
        cursor.execute("SELECT * FROM programs WHERE program_id = ?", (program_id,))
        program = cursor.fetchone()

        if not program:
            return None

        prog_value = self.cm.get_config(config_key, program_id)

        tree = {
            'name': program['name'],
            'level': 'program',
            'value': prog_value['value'],
            'source': prog_value['source'],
            'is_override': False,
            'children': []
        }

        # Get clinics
        cursor.execute("""
            SELECT * FROM clinics WHERE program_id = ? ORDER BY name
        """, (program_id,))

        for clinic in cursor.fetchall():
            clinic_value = self.cm.get_config(config_key, program_id, clinic['clinic_id'])

            clinic_node = {
                'name': clinic['name'],
                'level': 'clinic',
                'value': clinic_value['value'],
                'source': clinic_value['source'],
                'is_override': clinic_value['effective_level'] == 'clinic',
                'children': []
            }

            # Get locations for this clinic
            cursor.execute("""
                SELECT * FROM locations WHERE clinic_id = ? ORDER BY name
            """, (clinic['clinic_id'],))

            for location in cursor.fetchall():
                loc_value = self.cm.get_config(config_key, program_id,
                                                clinic['clinic_id'], location['location_id'])

                loc_node = {
                    'name': location['name'],
                    'level': 'location',
                    'value': loc_value['value'],
                    'source': loc_value['source'],
                    'is_override': loc_value['effective_level'] == 'location'
                }

                clinic_node['children'].append(loc_node)

            tree['children'].append(clinic_node)

        return tree

    def print_inheritance_tree(self, config_key: str, program_id: str) -> str:
        """
        Print a text-based tree of inheritance.

        PURPOSE: Human-readable visualization of inheritance

        RETURNS:
            Formatted string representation of tree
        """
        tree = self.get_inheritance_tree(config_key, program_id)
        if not tree:
            return "Program not found"

        lines = [f"Inheritance Tree for: {config_key}\n"]
        lines.append(self._format_tree_node(tree, 0))

        return '\n'.join(lines)

    def _format_tree_node(self, node: Dict, indent: int) -> str:
        """Format a single node of the inheritance tree."""
        prefix = '  ' * indent

        if indent == 0:
            marker = ''
        elif node.get('children'):
            marker = '├── '
        else:
            marker = '└── '

        override_marker = '*' if node.get('is_override') else ''

        line = f"{prefix}{marker}{node['name']}: {node['value']}{override_marker}"

        if node.get('source') and node['source'] != 'default':
            line += f" ({node['source']})"

        result = [line]

        for child in node.get('children', []):
            result.append(self._format_tree_node(child, indent + 1))

        return '\n'.join(result)


# ============================================================================
# MODULE TEST
# ============================================================================

if __name__ == "__main__":
    print("Testing InheritanceManager...")

    # This would require a database to test properly
    cm = ConfigurationManager()
    cm.initialize_schema()
    cm.load_definitions_from_yaml()

    im = InheritanceManager(cm)

    # Create test data
    program_id = cm.create_program("Test Inheritance", "TINH")
    clinic_id = cm.create_clinic(program_id, "Test Clinic", "TCLI")
    location_id = cm.create_location(clinic_id, "Test Location", "LOC1")

    # Set values at different levels
    cm.set_config('helpdesk_phone', '800-555-0000', program_id)  # Program level
    cm.set_config('helpdesk_phone', '503-555-1234', program_id, clinic_id)  # Clinic override

    # Test inheritance resolution
    result = im.resolve_with_inheritance('helpdesk_phone', program_id, clinic_id, location_id)
    print(f"\nResolve result: {json.dumps(result, indent=2)}")

    # Test tree visualization
    tree_str = im.print_inheritance_tree('helpdesk_phone', program_id)
    print(f"\nTree:\n{tree_str}")

    print("\nTests complete!")
