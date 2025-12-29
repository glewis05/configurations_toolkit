"""
CLI Utility Functions
=====================

Shared utility functions for CLI output formatting and common operations.

WHY SEPARATE FILE: DRY principle - these helpers are used across all
command handlers. Centralizing them makes styling changes easy.
"""

import sys
from typing import Optional


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================
# Consistent styling for CLI output. Using simple print with formatting
# rather than rich/click to keep dependencies minimal.

def print_header(title: str, width: int = 60) -> None:
    """
    Print a section header with separator lines.

    EXAMPLE:
        print_header("User Access Report")
        # ============================================================
        # USER ACCESS REPORT
        # ============================================================
    """
    print()
    print("=" * width)
    print(title.upper())
    print("=" * width)


def print_subheader(title: str, width: int = 40) -> None:
    """Print a subsection header."""
    print()
    print(title)
    print("-" * width)


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"✓ {message}")


def print_error(message: str) -> None:
    """Print an error message to stderr."""
    print(f"Error: {message}", file=sys.stderr)


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"Warning: {message}")


def print_info(message: str) -> None:
    """Print an informational message."""
    print(message)


def print_table_row(label: str, value: str, indent: int = 0) -> None:
    """
    Print a label: value row with optional indentation.

    EXAMPLE:
        print_table_row("Name", "John Smith")
        print_table_row("Email", "jsmith@example.com", indent=2)
    """
    prefix = "  " * indent
    print(f"{prefix}{label}: {value}")


def print_list_item(item: str, indent: int = 0, bullet: str = "•") -> None:
    """
    Print a bulleted list item.

    EXAMPLE:
        print_list_item("First item")
        print_list_item("Sub item", indent=1)
    """
    prefix = "  " * indent
    print(f"{prefix}{bullet} {item}")


def print_separator(char: str = "-", width: int = 60) -> None:
    """Print a separator line."""
    print(char * width)


def print_blank() -> None:
    """Print a blank line."""
    print()


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def require_arg(args, arg_name: str, friendly_name: str = None) -> bool:
    """
    Check if a required argument is present.

    Returns True if present, False (with error message) if not.

    EXAMPLE:
        if not require_arg(args, 'program', '--program'):
            return
    """
    value = getattr(args, arg_name, None)
    if not value:
        display_name = friendly_name or f"--{arg_name.replace('_', '-')}"
        print_error(f"{display_name} required")
        return False
    return True


def require_args(args, *arg_specs) -> bool:
    """
    Check multiple required arguments.

    EXAMPLE:
        if not require_args(args, ('program', '--program'), ('clinic', '--clinic')):
            return
    """
    for spec in arg_specs:
        if isinstance(spec, tuple):
            arg_name, friendly_name = spec
        else:
            arg_name = spec
            friendly_name = None
        if not require_arg(args, arg_name, friendly_name):
            return False
    return True


# =============================================================================
# FORMATTING HELPERS
# =============================================================================

def format_date(date_str: Optional[str]) -> str:
    """Format a date string for display, or return placeholder if None."""
    return date_str if date_str else "—"


def format_bool(value: bool) -> str:
    """Format a boolean for display."""
    return "Yes" if value else "No"


def format_count(count: int, singular: str, plural: str = None) -> str:
    """
    Format a count with proper singular/plural form.

    EXAMPLE:
        format_count(1, "user")  # "1 user"
        format_count(5, "user")  # "5 users"
    """
    if plural is None:
        plural = singular + "s"
    word = singular if count == 1 else plural
    return f"{count} {word}"
