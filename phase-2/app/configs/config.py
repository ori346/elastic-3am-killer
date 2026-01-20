"""
Central configuration module for OpenShift alert remediation system.

This module centralizes all configuration values to eliminate hardcoded values
throughout the codebase and provide environment variable support.
"""

import os
from dataclasses import dataclass


@dataclass
class TimeoutConfig:
    """Timeout configuration for various operations."""

    # Command execution timeouts
    command_execution: int = 60  # Host agent command execution timeout
    oc_command_default: int = 30  # Default timeout for oc commands

    # Alert checking timeouts
    alert_status_check: int = 30  # Alertmanager query timeout
    alertmanager_wait: int = 30  # Wait time before checking Alertmanager

    @classmethod
    def from_env(cls) -> "TimeoutConfig":
        """Create TimeoutConfig from environment variables."""
        return cls(
            command_execution=int(os.getenv("COMMAND_EXECUTION_TIMEOUT", "60")),
            oc_command_default=int(os.getenv("OC_COMMAND_DEFAULT_TIMEOUT", "30")),
            alert_status_check=int(os.getenv("ALERT_STATUS_CHECK_TIMEOUT", "30")),
            alertmanager_wait=int(os.getenv("ALERTMANAGER_WAIT_TIMEOUT", "30")),
        )


@dataclass
class AlertManagerConfig:
    """Alertmanager configuration for alert status checking."""

    namespace: str = "openshift-monitoring"
    pod_name: str = "alertmanager-main-0"
    url: str = "http://localhost:9093"

    @classmethod
    def from_env(cls) -> "AlertManagerConfig":
        """Create AlertManagerConfig from environment variables."""
        return cls(
            namespace=os.getenv("ALERTMANAGER_NAMESPACE", "openshift-monitoring"),
            pod_name=os.getenv("ALERTMANAGER_POD_NAME", "alertmanager-main-0"),
            url=os.getenv("ALERTMANAGER_URL", "http://localhost:9093"),
        )


@dataclass
class LogCollectionConfig:
    """Configuration for log collection and event querying."""

    # Default number of events to return
    events_tail_size: int = 10

    # Log tail sizes
    logs_tail_default: int = 5  # Default logs without pattern
    logs_tail_with_pattern: int = 100  # Initial tail when using grep pattern
    logs_tail_final: int = 10  # Final tail after grep

    @classmethod
    def from_env(cls) -> "LogCollectionConfig":
        """Create LogCollectionConfig from environment variables."""
        return cls(
            events_tail_size=int(os.getenv("EVENTS_TAIL_SIZE", "10")),
            logs_tail_default=int(os.getenv("LOGS_TAIL_DEFAULT", "5")),
            logs_tail_with_pattern=int(os.getenv("LOGS_TAIL_WITH_PATTERN", "100")),
            logs_tail_final=int(os.getenv("LOGS_TAIL_FINAL", "10")),
        )


@dataclass
class NetworkConfig:
    """Network configuration for the application."""

    host: str = "0.0.0.0"
    port: int = 5001

    @classmethod
    def from_env(cls) -> "NetworkConfig":
        """Create NetworkConfig from environment variables."""
        return cls(
            host=os.getenv("APP_HOST", "0.0.0.0"),
            port=int(os.getenv("APP_PORT", "5001")),
        )


@dataclass
class DeploymentConfig:
    """Configuration for deployment and cleanup operations."""

    # Default namespace for operations
    default_namespace: str = "default"

    # Default release name for Helm operations
    default_release_name: str = "openshift-alert-remediation"

    # Default container image
    default_image_tag: str = "latest"

    @classmethod
    def from_env(cls) -> "DeploymentConfig":
        """Create DeploymentConfig from environment variables."""
        return cls(
            default_namespace=os.getenv("DEFAULT_NAMESPACE", "default"),
            default_release_name=os.getenv(
                "DEFAULT_RELEASE_NAME", "openshift-alert-remediation"
            ),
            default_image_tag=os.getenv("DEFAULT_IMAGE_TAG", "latest"),
        )


@dataclass
class RemediationAgentConfig:
    """Configuration specific to the Remediation Agent."""

    # Maximum number of tools the remediation agent can use before forced to create plan
    max_tools: int = 5

    @classmethod
    def from_env(cls) -> "RemediationAgentConfig":
        """Create RemediationAgentConfig from environment variables."""
        return cls(max_tools=int(os.getenv("REMEDIATION_AGENT_MAX_TOOLS", "5")))


@dataclass
class HostAgentLLMConfig:
    """LLM configuration for Host Agent."""

    max_tokens: int = 1024
    temperature: float = 0.4

    @classmethod
    def from_env(cls) -> "HostAgentLLMConfig":
        """Create HostAgentLLMConfig from environment variables."""
        return cls(
            max_tokens=int(os.getenv("HOST_AGENT_MAX_TOKENS", "1024")),
            temperature=float(os.getenv("HOST_AGENT_TEMPERATURE", "0.4")),
        )


@dataclass
class RemediationAgentLLMConfig:
    """LLM configuration for Remediation Agent."""

    max_tokens: int = 1024
    temperature: float = 0.4

    @classmethod
    def from_env(cls) -> "RemediationAgentLLMConfig":
        """Create RemediationAgentLLMConfig from environment variables."""
        return cls(
            max_tokens=int(os.getenv("REMEDIATION_AGENT_LLM_MAX_TOKENS", "1024")),
            temperature=float(os.getenv("REMEDIATION_AGENT_LLM_TEMPERATURE", "0.4")),
        )


@dataclass
class ReportMakerAgentLLMConfig:
    """LLM configuration for Report Maker Agent."""

    max_tokens: int = 2048
    temperature: float = 0.7

    @classmethod
    def from_env(cls) -> "ReportMakerAgentLLMConfig":
        """Create ReportMakerAgentLLMConfig from environment variables."""
        return cls(
            max_tokens=int(os.getenv("REPORT_MAKER_AGENT_MAX_TOKENS", "2048")),
            temperature=float(os.getenv("REPORT_MAKER_AGENT_TEMPERATURE", "0.7")),
        )


@dataclass
class WorkflowConfig:
    """Configuration for Workflow Agent Executor."""

    # Maximum number of retries for report generation
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> "WorkflowConfig":
        """Create WorkflowConfig from environment variables."""
        return cls(max_retries=int(os.getenv("WORKFLOW_MAX_RETRIES", "3")))


@dataclass
class AppConfig:
    """Main application configuration that combines all config sections."""

    timeouts: TimeoutConfig
    alertmanager: AlertManagerConfig
    log_collection: LogCollectionConfig
    network: NetworkConfig
    deployment: DeploymentConfig
    remediation_agent: RemediationAgentConfig
    workflow: WorkflowConfig
    host_agent_llm: HostAgentLLMConfig
    remediation_agent_llm: RemediationAgentLLMConfig
    report_maker_agent_llm: ReportMakerAgentLLMConfig

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Create complete AppConfig from environment variables."""
        return cls(
            timeouts=TimeoutConfig.from_env(),
            alertmanager=AlertManagerConfig.from_env(),
            log_collection=LogCollectionConfig.from_env(),
            network=NetworkConfig.from_env(),
            deployment=DeploymentConfig.from_env(),
            remediation_agent=RemediationAgentConfig.from_env(),
            workflow=WorkflowConfig.from_env(),
            host_agent_llm=HostAgentLLMConfig.from_env(),
            remediation_agent_llm=RemediationAgentLLMConfig.from_env(),
            report_maker_agent_llm=ReportMakerAgentLLMConfig.from_env(),
        )


# Global configuration instance
config = AppConfig.from_env()

# Convenience exports for common values
TIMEOUTS = config.timeouts
ALERTMANAGER = config.alertmanager
LOG_COLLECTION = config.log_collection
NETWORK = config.network
DEPLOYMENT = config.deployment
REMEDIATION_AGENT = config.remediation_agent
WORKFLOW = config.workflow
HOST_AGENT_LLM = config.host_agent_llm
REMEDIATION_AGENT_LLM = config.remediation_agent_llm
REPORT_MAKER_AGENT_LLM = config.report_maker_agent_llm

# Backwards compatibility exports (can be removed after refactoring)
MAX_TOOLS = REMEDIATION_AGENT.max_tools
