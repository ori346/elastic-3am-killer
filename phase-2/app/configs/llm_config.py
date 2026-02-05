"""
Shared LLM configuration module for OpenShift alert remediation agents.

This module provides centralized LLM configuration and eliminates duplicated
code across agent files.
"""

import os
from dataclasses import dataclass
from typing import Optional

from llama_index.llms.openai_like import OpenAILike


@dataclass
class AgentLLMConfig:
    """Configuration for agent-specific LLM settings."""

    api_base: str
    api_key: str
    model: str
    max_tokens: int
    temperature: float
    context_window: int
    default_headers: Optional[dict] = None

    def __post_init__(self):
        """Set default headers if not provided."""
        if self.default_headers is None:
            self.default_headers = {"Content-Type": "application/json"}


def get_agent_api_config(agent_prefix: str) -> tuple[str, str, str, int]:
    """
    Get API configuration for a specific agent with fallback to shared variables.

    Args:
        agent_prefix: Agent prefix (e.g., "WORKFLOW_COORDINATOR", "ALERT_REMEDIATION_SPECIALIST", "INCIDENT_REPORT_GENERATOR")

    Returns:
        Tuple of (api_base, api_key, model, context_window)
    """
    api_base = os.getenv(f"{agent_prefix}_API_BASE", os.getenv("API_BASE"))
    api_key = os.getenv(f"{agent_prefix}_API_KEY", os.getenv("API_KEY"))
    model = os.getenv(f"{agent_prefix}_MODEL", os.getenv("MODEL"))

    # Get context window with fallback to default (8192)
    context_window = int(
        os.getenv(f"{agent_prefix}_CONTEXT_WINDOW", os.getenv("CONTEXT_WINDOW", "8192"))
    )

    return api_base, api_key, model, context_window


def create_agent_llm(
    agent_prefix: str,
    max_tokens: int,
    temperature: float,
    default_headers: dict = {"Content-Type": "application/json"},
    context_window: Optional[int] = None,
) -> OpenAILike:
    """
    Create an OpenAI-like LLM instance for an agent.

    Args:
        agent_prefix: Agent prefix for environment variables (e.g., "WORKFLOW_COORDINATOR")
        max_tokens: Maximum tokens for the agent
        temperature: Temperature for the agent
        default_headers: Optional default headers (uses default if None)
        context_window: Optional context window override (uses env config if None)

    Returns:
        Configured OpenAILike instance
    """
    api_base, api_key, model, env_context_window = get_agent_api_config(agent_prefix)

    # Use provided context_window or fallback to environment configuration
    final_context_window = (
        context_window if context_window is not None else env_context_window
    )

    return OpenAILike(
        api_base=api_base,
        api_key=api_key,
        model=model,
        is_chat_model=True,
        max_tokens=max_tokens,
        temperature=temperature,
        default_headers=default_headers,
        context_window=final_context_window,
    )


def create_workflow_coordinator_llm(
    max_tokens: int, temperature: float, context_window: Optional[int] = None
) -> OpenAILike:
    """
    Create LLM for Workflow Coordinator.

    Args:
        max_tokens: Maximum tokens for the agent
        temperature: Temperature for the agent
        context_window: Optional context window override (uses env config if None)

    Returns:
        Configured OpenAILike instance for Workflow Coordinator
    """

    return create_agent_llm(
        agent_prefix="WORKFLOW_COORDINATOR",
        max_tokens=max_tokens,
        temperature=temperature,
        context_window=context_window,
    )


def create_alert_remediation_specialist_llm(
    max_tokens: int, temperature: float, context_window: Optional[int] = None
) -> OpenAILike:
    """
    Create LLM for Alert Remediation Specialist.

    Args:
        max_tokens: Maximum tokens for the agent
        temperature: Temperature for the agent
        context_window: Optional context window override (uses env config if None)

    Returns:
        Configured OpenAILike instance for Alert Remediation Specialist
    """

    return create_agent_llm(
        agent_prefix="ALERT_REMEDIATION_SPECIALIST",
        max_tokens=max_tokens,
        temperature=temperature,
        context_window=context_window,
    )


def create_incident_report_generator_llm(
    max_tokens: int, temperature: float, context_window: Optional[int] = None
) -> OpenAILike:
    """
    Create LLM for Incident Report Generator.

    Args:
        max_tokens: Maximum tokens for the agent
        temperature: Temperature for the agent
        context_window: Optional context window override (uses env config if None)

    Returns:
        Configured OpenAILike instance for Incident Report Generator
    """
    return create_agent_llm(
        agent_prefix="INCIDENT_REPORT_GENERATOR",
        max_tokens=max_tokens,
        temperature=temperature,
        context_window=context_window,
    )
