"""
Config package for Configurations Toolkit

Contains YAML configuration files:
- config_definitions.yaml: All configurable fields with metadata
"""

import os
from pathlib import Path

# Path to config directory
CONFIG_DIR = Path(__file__).parent

def get_config_path(filename: str) -> str:
    """
    Get absolute path to a config file.

    Args:
        filename: Name of config file (e.g., 'config_definitions.yaml')

    Returns:
        Absolute path to the config file
    """
    return str(CONFIG_DIR / filename)
