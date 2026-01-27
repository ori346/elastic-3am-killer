"""
Tool usage tracking for Alert Remediation Specialist.

This module provides centralized tool usage tracking and limit enforcement
to prevent the agent from using too many tools before creating a plan.
"""

from configs import ALERT_REMEDIATION_SPECIALIST

# Tool usage tracking configuration
MAX_TOOLS = ALERT_REMEDIATION_SPECIALIST.max_tools

# Module-level counter for tool usage (resets per agent execution)
_tool_usage_count = 0


def track_tool_usage(func):
    """Decorator to track tool usage and enforce limit."""

    def wrapper(*args, **kwargs):
        global _tool_usage_count

        # Check if limit exceeded BEFORE executing the tool
        if _tool_usage_count >= MAX_TOOLS:
            return f"The tools called more than {MAX_TOOLS} (currently at {_tool_usage_count}). Please consolidate, create remediation plan and use write_remediation_plan - this is MANDATORY."

        # Increment the counter
        _tool_usage_count += 1

        # Call the original function
        result = func(*args, **kwargs)

        return result

    return wrapper


def reset_tool_usage_counter():
    """Reset the tool usage counter. Called at the start of each agent execution."""
    global _tool_usage_count
    _tool_usage_count = 0


def get_current_tool_count():
    """Get the current tool usage count."""
    return _tool_usage_count
