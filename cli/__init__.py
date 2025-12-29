"""
CLI Package for Configurations Toolkit
======================================

This package provides the command-line interface for the Configurations Toolkit.

Structure:
    cli/
    ├── __init__.py     - Main entry point (this file)
    ├── parser.py       - Argument parser definitions
    ├── utils.py        - Shared output formatting utilities
    ├── config_commands.py   - Configuration management commands (TODO)
    ├── access_commands.py   - Access management commands (TODO)
    └── import_commands.py   - Import/export commands (TODO)

Usage:
    from cli import main
    main()

Note: Command handlers are currently in run.py and will be migrated
      to separate modules incrementally.
"""

from .parser import create_parser
from .utils import (
    print_header,
    print_subheader,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_table_row,
    print_list_item,
    print_separator,
    print_blank,
    require_arg,
    require_args,
    format_date,
    format_bool,
    format_count,
)

__all__ = [
    # Parser
    'create_parser',
    # Output utilities
    'print_header',
    'print_subheader',
    'print_success',
    'print_error',
    'print_warning',
    'print_info',
    'print_table_row',
    'print_list_item',
    'print_separator',
    'print_blank',
    # Validation
    'require_arg',
    'require_args',
    # Formatting
    'format_date',
    'format_bool',
    'format_count',
]
