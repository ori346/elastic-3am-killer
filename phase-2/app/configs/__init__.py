"""
Configuration package for OpenShift alert remediation system.

This package provides centralized configuration management with environment variable support.
"""

from .config import (
    ALERTMANAGER,
    DEPLOYMENT,
    HOST_AGENT_LLM,
    LOG_COLLECTION,
    MAX_TOOLS,
    NETWORK,
    REMEDIATION_AGENT,
    REMEDIATION_AGENT_LLM,
    REPORT_MAKER_AGENT_LLM,
    TIMEOUTS,
    WORKFLOW,
    config,
)
from .llm_config import (
    create_host_agent_llm,
    create_remediation_agent_llm,
    create_report_maker_agent_llm,
)

__all__ = [
    # Configuration objects
    "config",
    "TIMEOUTS",
    "ALERTMANAGER",
    "LOG_COLLECTION",
    "NETWORK",
    "DEPLOYMENT",
    "REMEDIATION_AGENT",
    "WORKFLOW",
    "HOST_AGENT_LLM",
    "REMEDIATION_AGENT_LLM",
    "REPORT_MAKER_AGENT_LLM",
    "MAX_TOOLS",
    # LLM factory functions
    "create_host_agent_llm",
    "create_remediation_agent_llm",
    "create_report_maker_agent_llm",
]
