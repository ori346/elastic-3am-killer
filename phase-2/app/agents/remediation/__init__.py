"""
Modular Alert Remediation Specialist package for OpenShift alert remediation.

This package provides a clean modular structure while maintaining
the main agent definition in the original alert_remediation_specialist.py file.
"""

from .context_tools import context_tools
from .deployment_tools import deployment_tools

# Import all tools and utilities
from .pod_tools import pod_tools
from .tool_tracker import MAX_TOOLS, reset_tool_usage_counter
from .utils import compact_output, find_pod_by_name, run_oc_command

# Combine all tools for easy import
all_tools = pod_tools + deployment_tools + context_tools

__all__ = [
    # Tool collections
    "pod_tools",
    "deployment_tools",
    "context_tools",
    "all_tools",
    # Tool tracking
    "MAX_TOOLS",
    "reset_tool_usage_counter",
    # Utilities
    "run_oc_command",
    "find_pod_by_name",
    "compact_output",
]
