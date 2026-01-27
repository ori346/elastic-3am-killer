"""
Configuration package for OpenShift alert remediation system.

This package provides centralized configuration management with environment variable support.
"""

from .config import (
    ALERT_REMEDIATION_SPECIALIST,
    ALERT_REMEDIATION_SPECIALIST_LLM,
    DEPLOYMENT,
    INCIDENT_REPORT_GENERATOR_LLM,
    LOG_COLLECTION,
    MAX_TOOLS,
    NETWORK,
    TIMEOUTS,
    WORKFLOW,
    WORKFLOW_COORDINATOR_LLM,
    config,
)
from .llm_config import (
    create_alert_remediation_specialist_llm,
    create_incident_report_generator_llm,
    create_workflow_coordinator_llm,
)

__all__ = [
    # Configuration objects
    "config",
    "TIMEOUTS",
    "LOG_COLLECTION",
    "NETWORK",
    "DEPLOYMENT",
    "ALERT_REMEDIATION_SPECIALIST",
    "WORKFLOW",
    "WORKFLOW_COORDINATOR_LLM",
    "ALERT_REMEDIATION_SPECIALIST_LLM",
    "INCIDENT_REPORT_GENERATOR_LLM",
    "MAX_TOOLS",
    # LLM factory functions
    "create_workflow_coordinator_llm",
    "create_alert_remediation_specialist_llm",
    "create_incident_report_generator_llm",
]
