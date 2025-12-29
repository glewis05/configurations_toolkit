"""
Database package for Configurations Toolkit

Provides ConfigurationManager for CRUD operations on
system configurations with inheritance support.
"""

from .config_manager import ConfigurationManager, get_config_manager

__all__ = ['ConfigurationManager', 'get_config_manager']
