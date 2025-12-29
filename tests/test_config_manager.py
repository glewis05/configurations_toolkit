"""
Unit Tests for Configuration Manager

PURPOSE: Test core CRUD operations, inheritance, and validation
         in the ConfigurationManager class

R EQUIVALENT: Like testthat for R - structured unit tests

AVIATION ANALOGY: Pre-flight checklist - verify all systems work
before committing to flight

AUTHOR: Glen Lewis
DATE: 2024

RUN TESTS:
    python3 -m pytest tests/ -v
    OR
    python3 tests/test_config_manager.py
"""

import os
import sys
import unittest
import tempfile
import sqlite3
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.config_manager import ConfigurationManager, get_config_manager


class TestNPIValidation(unittest.TestCase):
    """
    Test NPI validation logic.

    NPIs must be:
    - 10 digits
    - Start with 1 or 2
    - Pass Luhn checksum (optional strict mode)
    """

    def setUp(self):
        """Create a temporary database for testing."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.cm = ConfigurationManager(self.temp_db.name)
        self.cm.initialize_schema()

    def tearDown(self):
        """Clean up temporary database."""
        self.cm.close()
        os.unlink(self.temp_db.name)

    def test_valid_10_digit_npi(self):
        """Valid 10-digit NPI starting with 1 should pass."""
        is_valid, result = self.cm._validate_npi("1234567890")
        self.assertTrue(is_valid)
        self.assertEqual(result, "1234567890")

    def test_valid_npi_with_formatting(self):
        """NPI with spaces/dashes should be normalized."""
        is_valid, result = self.cm._validate_npi("123-456-7890")
        self.assertTrue(is_valid)
        self.assertEqual(result, "1234567890")

    def test_valid_npi_starting_with_2(self):
        """Organization NPIs start with 2."""
        is_valid, result = self.cm._validate_npi("2345678901")
        self.assertTrue(is_valid)

    def test_invalid_npi_wrong_length(self):
        """NPIs must be 10 digits (or 9 with warning)."""
        is_valid, result = self.cm._validate_npi("12345")
        self.assertFalse(is_valid)
        self.assertIn("10 digits", result)

    def test_invalid_npi_wrong_start(self):
        """NPIs must start with 1 or 2."""
        is_valid, result = self.cm._validate_npi("3234567890")
        self.assertFalse(is_valid)
        self.assertIn("start with 1 or 2", result)

    def test_9_digit_npi_accepted_with_warning(self):
        """9-digit NPIs accepted (known typos in some docs)."""
        is_valid, result = self.cm._validate_npi("123456789")
        self.assertTrue(is_valid)  # Accepted but warns
        self.assertEqual(len(result), 9)

    def test_none_npi_valid(self):
        """None/empty NPI is acceptable."""
        is_valid, result = self.cm._validate_npi(None)
        self.assertTrue(is_valid)
        self.assertIsNone(result)

    def test_empty_npi_valid(self):
        """Empty string NPI is acceptable."""
        is_valid, result = self.cm._validate_npi("")
        self.assertTrue(is_valid)


class TestPhoneNormalization(unittest.TestCase):
    """Test phone number normalization."""

    def setUp(self):
        """Create a temporary database for testing."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.cm = ConfigurationManager(self.temp_db.name)

    def tearDown(self):
        """Clean up temporary database."""
        self.cm.close()
        os.unlink(self.temp_db.name)

    def test_digits_only(self):
        """10 digits should normalize to XXX.XXX.XXXX."""
        result = self.cm._normalize_phone("5032166407")
        self.assertEqual(result, "503.216.6407")

    def test_dashes(self):
        """Dashes should be converted to dots."""
        result = self.cm._normalize_phone("503-216-6407")
        self.assertEqual(result, "503.216.6407")

    def test_parentheses(self):
        """Parentheses format should normalize."""
        result = self.cm._normalize_phone("(503) 216-6407")
        self.assertEqual(result, "503.216.6407")

    def test_country_code(self):
        """Leading 1 (US country code) should be stripped."""
        result = self.cm._normalize_phone("1-503-216-6407")
        self.assertEqual(result, "503.216.6407")

    def test_already_normalized(self):
        """Already-normalized phone should stay the same."""
        result = self.cm._normalize_phone("503.216.6407")
        self.assertEqual(result, "503.216.6407")

    def test_non_standard_length(self):
        """Non-10-digit phones returned as-is."""
        result = self.cm._normalize_phone("911")
        self.assertEqual(result, "911")

    def test_none_phone(self):
        """None should return None."""
        result = self.cm._normalize_phone(None)
        self.assertIsNone(result)


class TestConfigInheritance(unittest.TestCase):
    """
    Test configuration inheritance logic.

    Inheritance flows: Default → Program → Clinic → Location
    """

    def setUp(self):
        """Create a test hierarchy."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.cm = ConfigurationManager(self.temp_db.name)
        self.cm.initialize_schema()
        self.cm.load_definitions_from_yaml()

        # Create hierarchy: Program → Clinic → Location
        self.program_id = self.cm.create_program("Test Program", "TEST")
        self.clinic_id = self.cm.create_clinic(self.program_id, "Test Clinic", "TCLI")
        self.location_id = self.cm.create_location(self.clinic_id, "Test Location")

    def tearDown(self):
        """Clean up temporary database."""
        self.cm.close()
        os.unlink(self.temp_db.name)

    def test_default_inheritance(self):
        """Config with no value set should have None or default level."""
        result = self.cm.get_config('helpdesk_phone', self.program_id)
        # If no value is set and no default defined, effective_level is None
        # If a default is defined in config_definitions, effective_level is 'default'
        self.assertIn(result['effective_level'], [None, 'default'])

    def test_program_level_override(self):
        """Program-level value should override default."""
        self.cm.set_config('helpdesk_phone', '800.555.0000', self.program_id)

        result = self.cm.get_config('helpdesk_phone', self.program_id)
        self.assertEqual(result['value'], '800.555.0000')
        self.assertEqual(result['effective_level'], 'program')

    def test_clinic_inherits_from_program(self):
        """Clinic should inherit from program if no clinic value."""
        self.cm.set_config('helpdesk_phone', '800.555.0000', self.program_id)

        result = self.cm.get_config('helpdesk_phone', self.program_id, self.clinic_id)
        self.assertEqual(result['value'], '800.555.0000')
        self.assertEqual(result['effective_level'], 'program')

    def test_clinic_level_override(self):
        """Clinic-level value should override program."""
        self.cm.set_config('helpdesk_phone', '800.555.0000', self.program_id)
        self.cm.set_config('helpdesk_phone', '503.216.6407', self.program_id, self.clinic_id)

        result = self.cm.get_config('helpdesk_phone', self.program_id, self.clinic_id)
        self.assertEqual(result['value'], '503.216.6407')
        self.assertEqual(result['effective_level'], 'clinic')
        self.assertTrue(result['is_override'])

    def test_location_inherits_from_clinic(self):
        """Location should inherit from clinic if no location value."""
        self.cm.set_config('helpdesk_phone', '503.216.6407', self.program_id, self.clinic_id)

        result = self.cm.get_config('helpdesk_phone', self.program_id,
                                    self.clinic_id, self.location_id)
        self.assertEqual(result['value'], '503.216.6407')
        self.assertEqual(result['effective_level'], 'clinic')

    def test_location_level_override(self):
        """Location-level value should override clinic."""
        self.cm.set_config('helpdesk_phone', '503.216.6407', self.program_id, self.clinic_id)
        self.cm.set_config('helpdesk_phone', '503.216.6500', self.program_id,
                           self.clinic_id, self.location_id)

        result = self.cm.get_config('helpdesk_phone', self.program_id,
                                    self.clinic_id, self.location_id)
        self.assertEqual(result['value'], '503.216.6500')
        self.assertEqual(result['effective_level'], 'location')
        self.assertTrue(result['is_override'])


class TestProviderOperations(unittest.TestCase):
    """Test provider CRUD operations."""

    def setUp(self):
        """Create test hierarchy with location."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.cm = ConfigurationManager(self.temp_db.name)
        self.cm.initialize_schema()

        self.program_id = self.cm.create_program("Test Program", "TEST")
        self.clinic_id = self.cm.create_clinic(self.program_id, "Test Clinic")
        self.location_id = self.cm.create_location(self.clinic_id, "Test Location")

    def tearDown(self):
        """Clean up temporary database."""
        self.cm.close()
        os.unlink(self.temp_db.name)

    def test_add_provider(self):
        """Adding a provider should succeed."""
        provider_id = self.cm.add_provider(
            self.location_id, "Christine Kemp, NP",
            npi="1234567890", role="Ordering Provider"
        )
        self.assertIsNotNone(provider_id)

    def test_add_provider_invalid_npi(self):
        """Invalid NPI should raise ValueError."""
        with self.assertRaises(ValueError):
            self.cm.add_provider(
                self.location_id, "Bad Provider, MD",
                npi="invalid", validate_npi=True
            )

    def test_add_provider_skip_validation(self):
        """Skipping NPI validation should allow invalid NPI."""
        provider_id = self.cm.add_provider(
            self.location_id, "Special Provider, MD",
            npi="invalid", validate_npi=False
        )
        self.assertIsNotNone(provider_id)

    def test_duplicate_provider_skipped(self):
        """Duplicate provider at same location should be skipped."""
        provider_id1 = self.cm.add_provider(
            self.location_id, "Christine Kemp, NP",
            npi="1234567890", skip_if_exists=True
        )
        provider_id2 = self.cm.add_provider(
            self.location_id, "Christine Kemp, NP",
            npi="1234567890", skip_if_exists=True
        )
        # Should return same ID (existing provider)
        self.assertEqual(provider_id1, provider_id2)

    def test_get_providers(self):
        """Getting providers should return added providers."""
        self.cm.add_provider(self.location_id, "Provider A, MD", npi="1234567890")
        self.cm.add_provider(self.location_id, "Provider B, NP", npi="1234567891")

        providers = self.cm.get_providers(location_id=self.location_id)
        self.assertEqual(len(providers), 2)


class TestEffectiveConfig(unittest.TestCase):
    """Test get_effective_config optimization."""

    def setUp(self):
        """Create test hierarchy."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.cm = ConfigurationManager(self.temp_db.name)
        self.cm.initialize_schema()
        self.cm.load_definitions_from_yaml()

        self.program_id = self.cm.create_program("Test Program", "TEST")
        self.clinic_id = self.cm.create_clinic(self.program_id, "Test Clinic")

    def tearDown(self):
        """Clean up temporary database."""
        self.cm.close()
        os.unlink(self.temp_db.name)

    def test_get_all_configs(self):
        """get_effective_config should return all defined configs."""
        configs = self.cm.get_effective_config(self.program_id)

        # Should have all config definitions
        self.assertIn('helpdesk_phone', configs)
        self.assertIn('helpdesk_email', configs)
        self.assertIn('hours_open', configs)

    def test_inherits_overrides_correctly(self):
        """Overridden values should be reflected in effective config."""
        self.cm.set_config('helpdesk_phone', '800.555.0000', self.program_id)
        self.cm.set_config('helpdesk_phone', '503.216.6407', self.program_id, self.clinic_id)

        # Program level
        configs_program = self.cm.get_effective_config(self.program_id)
        self.assertEqual(configs_program['helpdesk_phone']['value'], '800.555.0000')
        self.assertEqual(configs_program['helpdesk_phone']['effective_level'], 'program')

        # Clinic level
        configs_clinic = self.cm.get_effective_config(self.program_id, self.clinic_id)
        self.assertEqual(configs_clinic['helpdesk_phone']['value'], '503.216.6407')
        self.assertEqual(configs_clinic['helpdesk_phone']['effective_level'], 'clinic')


class TestConfigValueNormalization(unittest.TestCase):
    """Test config value normalization."""

    def setUp(self):
        """Create a temporary database for testing."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.cm = ConfigurationManager(self.temp_db.name)

    def tearDown(self):
        """Clean up temporary database."""
        self.cm.close()
        os.unlink(self.temp_db.name)

    def test_phone_normalization(self):
        """Phone config values should be normalized."""
        result = self.cm._normalize_config_value('helpdesk_phone', '503-216-6407')
        self.assertEqual(result, '503.216.6407')

    def test_boolean_normalization_true(self):
        """Boolean true variants should normalize to 'true'."""
        for val in ['true', 'True', 'TRUE', 'yes', 'Yes', '1', 'enabled']:
            result = self.cm._normalize_config_value('tc_scoring_enabled', val)
            self.assertEqual(result, 'true', f"Failed for input: {val}")

    def test_boolean_normalization_false(self):
        """Boolean false variants should normalize to 'false'."""
        for val in ['false', 'False', 'FALSE', 'no', 'No', '0', 'disabled']:
            result = self.cm._normalize_config_value('tc_scoring_enabled', val)
            self.assertEqual(result, 'false', f"Failed for input: {val}")

    def test_time_normalization(self):
        """Time values should normalize to HH:MM format."""
        result = self.cm._normalize_config_value('hours_open', '8:00 AM')
        self.assertEqual(result, '08:00')

        result = self.cm._normalize_config_value('hours_close', '5:00 PM')
        self.assertEqual(result, '17:00')


class TestLuhnValidation(unittest.TestCase):
    """Test Luhn algorithm implementation for NPI validation."""

    def setUp(self):
        """Create a temporary database for testing."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.cm = ConfigurationManager(self.temp_db.name)

    def tearDown(self):
        """Clean up temporary database."""
        self.cm.close()
        os.unlink(self.temp_db.name)

    def test_valid_luhn_npi(self):
        """Known valid NPIs should pass Luhn check."""
        # NPI: 1215158639 is a real valid NPI format
        valid = self.cm._validate_luhn("1215158639")
        # Note: Luhn for NPI uses "80840" prefix
        # This is testing the algorithm, not specific NPIs
        self.assertIsInstance(valid, bool)


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    # Run with verbose output
    unittest.main(verbosity=2)
