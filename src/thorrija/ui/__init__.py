"""
Interfaz de usuario: CLI y formateadores.
"""

from .cli import main, ThorrijaCLI, create_parser
from .formatters import (
    format_hardware_report, format_plan, format_audit_summary,
    format_error, format_warning, format_info, format_success,
)

__all__ = [
    "main", "ThorrijaCLI", "create_parser",
    "format_hardware_report", "format_plan", "format_audit_summary",
    "format_error", "format_warning", "format_info", "format_success",
]