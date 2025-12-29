"""
Configurations Toolkit
======================

Manages system configurations for clinic onboarding and ongoing updates
with inheritance support across Program → Clinic → Location hierarchy.

This package provides:
- ConfigurationManager: CRUD operations with inheritance
- InheritanceManager: Resolve effective values across hierarchy
- AccessManager: User access, training, and compliance
- AccessImporter: Bulk import from Excel
- QuickUpdateManager: Common update operations
- ComplianceReports: Audit and compliance reporting
- ConfigExcelFormatter: Export configurations to Excel
- AccessExcelFormatter: Export access data to Excel

Example:
    from configurations_toolkit.database import ConfigurationManager
    from configurations_toolkit.managers import AccessManager, InheritanceManager
    from configurations_toolkit.formatters import ConfigExcelFormatter
    from configurations_toolkit.reports import ComplianceReports
"""

# Version
__version__ = '0.1.0'

# Expose key classes at package level for convenience
from .database import ConfigurationManager, get_config_manager
from .managers import (
    InheritanceManager,
    QuickUpdateManager,
    AccessManager,
    AccessImporter
)
from .formatters import ConfigExcelFormatter, AccessExcelFormatter
from .reports import ComplianceReports
from .parsers import ClinicSpecParser

__all__ = [
    # Database
    'ConfigurationManager',
    'get_config_manager',
    # Managers
    'InheritanceManager',
    'QuickUpdateManager',
    'AccessManager',
    'AccessImporter',
    # Formatters
    'ConfigExcelFormatter',
    'AccessExcelFormatter',
    # Reports
    'ComplianceReports',
    # Parsers
    'ClinicSpecParser',
]
