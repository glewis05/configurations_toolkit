"""
Managers package for Configurations Toolkit

Provides specialized managers for:
- Inheritance resolution
- Quick updates
- User access and compliance tracking
- Bulk import from Excel
"""

from .inheritance_manager import InheritanceManager
from .update_manager import QuickUpdateManager
from .access_manager import AccessManager
from .access_import import AccessImporter

__all__ = ['InheritanceManager', 'QuickUpdateManager', 'AccessManager', 'AccessImporter']
