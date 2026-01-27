import logging
import os
import sys

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from agents.workflow_agent_executor import WorkflowAgentExecutor

# Configuration from environment
PORT = os.getenv("AGENT_PORT", "5001")
AGENT_HOST = os.getenv("AGENT_HOST", "0.0.0.0")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def create_agent_card() -> AgentCard:
    """Create the AgentCard defining the workflow agent's capabilities."""
    skills = [
        AgentSkill(
            id="remediate_openshift_alert",
            name="Remediate OpenShift Alert",
            description="Analyze and remediate OpenShift cluster alerts by investigating the issue, creating remediation plan, executing fixes, and verifying resolution",
            tags=["remediation", "openshift", "automation", "alerts"],
            examples=[
                "Remediate pod crash alert in namespace",
                "Fix high CPU usage alert for backend server",
                "Resolve OOMKilled container in production namespace",
                "Handle deployment failure alerts",
            ],
        ),
        AgentSkill(
            id="generate_incident_report",
            name="Generate Incident Report",
            description="Generate concise incident report for engineers including root cause analysis, remediation actions taken, and recommendations",
            tags=["reporting", "documentation", "communication"],
            examples=[
                "Create incident report for memory pressure alert",
                "Generate summary report of remediation for engineers",
                "Document root cause and resolution of cluster issue",
            ],
        ),
    ]

    return AgentCard(
        name="OpenShift Remediation Agent",
        description="Autonomous agent for OpenShift cluster alert remediation. Investigates alerts, executes fixes, verifies resolution, and generates concise reports for engineers.",
        url=f"http://{AGENT_HOST}:{PORT}/",
        version="1.0.0",
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["text/markdown", "text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        skills=skills,
    )


"""Main entry point for the Workflow Coordinator."""
agent_card = create_agent_card()
request_handler = DefaultRequestHandler(
    agent_executor=WorkflowAgentExecutor(),
    task_store=InMemoryTaskStore(),
)
server = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=request_handler,
)
logger.info("=" * 70)
logger.info("Workflow Coordinator Ready!")
logger.info("=" * 70)


app = server.build()
