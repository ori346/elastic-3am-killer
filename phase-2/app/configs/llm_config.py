"""
Shared LLM configuration module for OpenShift alert remediation agents.

This module provides centralized LLM configuration and eliminates duplicated
code across agent files.
"""

import os
from dataclasses import dataclass
from typing import Optional

from llama_index.llms.openai_like import OpenAILike

# Try to import Ollama - only available in development environments
try:
    from llama_index.llms.ollama import Ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    Ollama = None  # Prevent NameError


@dataclass
class AgentLLMConfig:
    """Configuration for agent-specific LLM settings."""

    api_base: str
    api_key: str
    model: str
    max_tokens: int
    temperature: float
    system_prompt: str
    default_headers: Optional[dict] = None

    def __post_init__(self):
        """Set default headers if not provided."""
        if self.default_headers is None:
            self.default_headers = {"Content-Type": "application/json"}


def is_ollama_endpoint(api_base: str) -> bool:
    if not api_base:
        return False

    api_base_lower = api_base.lower()
    return (
        ":11434" in api_base_lower or
        "ollama" in api_base_lower or
        api_base_lower.endswith("/v1") and "11434" in api_base_lower
    )


def get_agent_api_config(agent_prefix: str) -> tuple[str, str, str]:
    """
    Get API configuration for a specific agent with fallback to shared variables.

    Args:
        agent_prefix: Agent prefix (e.g., "WORKFLOW_COORDINATOR", "ALERT_REMEDIATION_SPECIALIST", "INCIDENT_REPORT_GENERATOR")

    Returns:
        Tuple of (api_base, api_key, model)
    """
    api_base = os.getenv(f"{agent_prefix}_API_BASE", os.getenv("API_BASE"))
    api_key = os.getenv(f"{agent_prefix}_API_KEY", os.getenv("API_KEY"))
    model = os.getenv(f"{agent_prefix}_MODEL", os.getenv("MODEL"))

    return api_base, api_key, model


def create_agent_llm(
    agent_prefix: str,
    max_tokens: int,
    temperature: float,
    system_prompt: str | None = None,
    default_headers: dict = {"Content-Type": "application/json"},
):
    """
    Create an LLM instance for an agent (either Ollama or OpenAI-like).

    Args:
        agent_prefix: Agent prefix for environment variables (e.g., "WORKFLOW_COORDINATOR")
        max_tokens: Maximum tokens for the agent
        temperature: Temperature for the agent
        system_prompt: System prompt for the agent
        default_headers: Optional default headers (uses default if None)

    Returns:
        Configured LLM instance (Ollama or OpenAILike)
    """
    api_base, api_key, model = get_agent_api_config(agent_prefix)

    # Check if this is an Ollama endpoint and if Ollama package is available
    if is_ollama_endpoint(api_base) and OLLAMA_AVAILABLE:
        # Development: Use native Ollama LLM client
        # Remove both /v1 and /api suffixes as Ollama client adds these automatically
        base_url = api_base.replace("/v1", "").replace("/api", "").rstrip("/")

        return Ollama(
            model=model,
            base_url=base_url,
            temperature=temperature,
            # Note: Ollama handles max tokens internally, but we can set context_window
            context_window=8192,  # Llama3.2 context window
            request_timeout=90.0,
            additional_kwargs={
                "num_predict": max_tokens,  # Ollama's parameter for max tokens
            },
        )
    else:
        # Production OR non-Ollama: Use OpenAI-like LLM for all endpoints
        # In production, even Ollama URLs are treated as OpenAI-compatible endpoints
        return OpenAILike(
            api_base=api_base,
            api_key=api_key,
            model=model,
            is_chat_model=True,
            max_tokens=max_tokens,
            temperature=temperature,
            default_headers=default_headers,
            system_prompt=system_prompt,
        )


def create_workflow_coordinator_llm(max_tokens: int, temperature: float):
    """
    Create LLM for Workflow Coordinator with predefined system prompt.

    Args:
        max_tokens: Maximum tokens for the agent
        temperature: Temperature for the agent

    Returns:
        Configured LLM instance for Workflow Coordinator (Ollama or OpenAILike)
    """
    system_prompt = (
        "You are helping the AI Orchestrator Agent to remediate alerts in OpenShift cluster. "
        "The agent is not allowed to execute commands that do not modify the cluster state such as get, describe, status, logs, etc. "
        "The agent's role is only orchestrating the workflow and not investigating by itself. The agent uses other agents for investigation."
    )

    return create_agent_llm(
        agent_prefix="WORKFLOW_COORDINATOR",
        max_tokens=max_tokens,
        temperature=temperature,
        system_prompt=system_prompt,
    )


def create_alert_remediation_specialist_llm(
    max_tokens: int, temperature: float
):
    """
    Create LLM for Alert Remediation Specialist with predefined system prompt.

    Args:
        max_tokens: Maximum tokens for the agent
        temperature: Temperature for the agent

    Returns:
        Configured LLM instance for Alert Remediation Specialist (Ollama or OpenAILike)
    """
    system_prompt = (
        "You are helping the AI Remediate Agent to remediate alerts in OpenShift cluster. "
        "The agent is not allowed to execute commands that modify the cluster state such as set, rollout, create, apply, edit, delete, expose, etc. "
        "The agent's role is to create commands that will resolve the alert in the cluster and handoff these commands back to Workflow Coordinator agent."
    )

    return create_agent_llm(
        agent_prefix="ALERT_REMEDIATION_SPECIALIST",
        max_tokens=max_tokens,
        temperature=temperature,
        system_prompt=system_prompt,
    )


def create_incident_report_generator_llm(
    max_tokens: int, temperature: float
):
    """
    Create LLM for Incident Report Generator (no system prompt needed as it's set in ReActAgent).

    Args:
        max_tokens: Maximum tokens for the agent
        temperature: Temperature for the agent

    Returns:
        Configured LLM instance for Incident Report Generator (Ollama or OpenAILike)
    """
    # Incident Report Generator doesn't use system_prompt in LLM config
    # The system prompt is handled by the ReActAgent itself
    return create_agent_llm(
        agent_prefix="INCIDENT_REPORT_GENERATOR",
        max_tokens=max_tokens,
        temperature=temperature,
    )
