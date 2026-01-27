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
    command_execution: int = 60  # Workflow coordinator command execution timeout
    oc_command_default: int = 30  # Default timeout for oc commands

    @classmethod
    def from_env(cls) -> "TimeoutConfig":
        """Create TimeoutConfig from environment variables."""
        return cls(
            command_execution=int(os.getenv("COMMAND_EXECUTION_TIMEOUT", "60")),
            oc_command_default=int(os.getenv("OC_COMMAND_DEFAULT_TIMEOUT", "30")),
        )


@dataclass
class LogCollectionConfig:
    """Configuration for log collection and event querying."""

    # Default number of events to return
    events_tail_size: int = 10

    # Pod describe events tail size
    pod_events_tail_size: int = 5

    # Log tail sizes
    logs_tail_default: int = 5  # Default logs without pattern
    logs_tail_with_pattern: int = 100  # Initial tail when using grep pattern
    logs_tail_final: int = 10  # Final tail after grep

    @classmethod
    def from_env(cls) -> "LogCollectionConfig":
        """Create LogCollectionConfig from environment variables."""
        return cls(
            events_tail_size=int(os.getenv("EVENTS_TAIL_SIZE", "10")),
            pod_events_tail_size=int(os.getenv("POD_EVENTS_TAIL_SIZE", "5")),
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
class AlertRemediationSpecialistConfig:
    """Configuration specific to the Alert Remediation Specialist."""

    # Maximum number of tools the Alert Remediation Specialist can use before forced to create plan
    max_tools: int = 10

    @classmethod
    def from_env(cls) -> "AlertRemediationSpecialistConfig":
        """Create AlertRemediationSpecialistConfig from environment variables."""
        return cls(
            max_tools=int(os.getenv("ALERT_REMEDIATION_SPECIALIST_MAX_TOOLS", "10"))
        )


@dataclass
class WorkflowCoordinatorLLMConfig:
    """LLM configuration for Workflow Coordinator."""

    max_tokens: int = 1024
    temperature: float = 0.4

    @classmethod
    def from_env(cls) -> "WorkflowCoordinatorLLMConfig":
        """Create WorkflowCoordinatorLLMConfig from environment variables."""
        return cls(
            max_tokens=int(os.getenv("WORKFLOW_COORDINATOR_MAX_TOKENS", "1024")),
            temperature=float(os.getenv("WORKFLOW_COORDINATOR_TEMPERATURE", "0.4")),
        )


@dataclass
class AlertRemediationSpecialistLLMConfig:
    """LLM configuration for Alert Remediation Specialist."""

    max_tokens: int = 1024
    temperature: float = 0.4

    @classmethod
    def from_env(cls) -> "AlertRemediationSpecialistLLMConfig":
        """Create AlertRemediationSpecialistLLMConfig from environment variables."""
        return cls(
            max_tokens=int(
                os.getenv("ALERT_REMEDIATION_SPECIALIST_LLM_MAX_TOKENS", "1024")
            ),
            temperature=float(
                os.getenv("ALERT_REMEDIATION_SPECIALIST_LLM_TEMPERATURE", "0.4")
            ),
        )


@dataclass
class IncidentReportGeneratorLLMConfig:
    """LLM configuration for Incident Report Generator."""

    max_tokens: int = 2048
    temperature: float = 0.7

    @classmethod
    def from_env(cls) -> "IncidentReportGeneratorLLMConfig":
        """Create IncidentReportGeneratorLLMConfig from environment variables."""
        return cls(
            max_tokens=int(os.getenv("INCIDENT_REPORT_GENERATOR_MAX_TOKENS", "2048")),
            temperature=float(
                os.getenv("INCIDENT_REPORT_GENERATOR_TEMPERATURE", "0.7")
            ),
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
    log_collection: LogCollectionConfig
    network: NetworkConfig
    deployment: DeploymentConfig
    alert_remediation_specialist: AlertRemediationSpecialistConfig
    workflow: WorkflowConfig
    workflow_coordinator_llm: WorkflowCoordinatorLLMConfig
    alert_remediation_specialist_llm: AlertRemediationSpecialistLLMConfig
    incident_report_generator_llm: IncidentReportGeneratorLLMConfig

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Create complete AppConfig from environment variables."""
        return cls(
            timeouts=TimeoutConfig.from_env(),
            log_collection=LogCollectionConfig.from_env(),
            network=NetworkConfig.from_env(),
            deployment=DeploymentConfig.from_env(),
            alert_remediation_specialist=AlertRemediationSpecialistConfig.from_env(),
            workflow=WorkflowConfig.from_env(),
            workflow_coordinator_llm=WorkflowCoordinatorLLMConfig.from_env(),
            alert_remediation_specialist_llm=AlertRemediationSpecialistLLMConfig.from_env(),
            incident_report_generator_llm=IncidentReportGeneratorLLMConfig.from_env(),
        )


# Global configuration instance
config = AppConfig.from_env()

# Convenience exports for common values
TIMEOUTS = config.timeouts
LOG_COLLECTION = config.log_collection
NETWORK = config.network
DEPLOYMENT = config.deployment
ALERT_REMEDIATION_SPECIALIST = config.alert_remediation_specialist
WORKFLOW = config.workflow
WORKFLOW_COORDINATOR_LLM = config.workflow_coordinator_llm
ALERT_REMEDIATION_SPECIALIST_LLM = config.alert_remediation_specialist_llm
INCIDENT_REPORT_GENERATOR_LLM = config.incident_report_generator_llm

# Backwards compatibility exports (can be removed after refactoring)
MAX_TOOLS = ALERT_REMEDIATION_SPECIALIST.max_tools
