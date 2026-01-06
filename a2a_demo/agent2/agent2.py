import json
import logging
import os
import ssl
import subprocess
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2ARESTFastAPIApplication
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers import RESTHandler
from a2a.types import AgentCapabilities, AgentCard, AgentProvider, AgentSkill
from fastapi import BackgroundTasks
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RemediationInput(BaseModel):
    """Input model for remediation skill"""

    diagnosis: str
    alert_name: str
    alert_labels: Dict[str, str] = Field(default_factory=dict)
    diagnostic_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


class RemediateAgent(BaseModel):
    """Agent 2: Remediates microservice issues by patching deployments based on diagnosis"""

    name: str = "RemediateAgent"
    llm_endpoint: str = Field(default="")
    prometheus_url: str = Field(
        default="https://thanos-querier.openshift-monitoring.svc:9091"
    )
    model: str = Field(default="llama")
    microservice_a_deployment: str = Field(default="microservice-a")
    microservice_b_deployment: str = Field(default="microservice-b")
    namespace: str = Field(default="a2a-demo")

    class Config:
        arbitrary_types_allowed = True

    async def query_prometheus(self, query: str) -> list:
        """Query Prometheus for metrics"""
        try:
            url = f"{self.prometheus_url}/api/v1/query"
            params = {"query": query}

            # Create SSL context that doesn't verify certificates for internal services
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # Read ServiceAccount token for authentication
            token = None
            token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
            if os.path.exists(token_path):
                with open(token_path, "r") as f:
                    token = f.read().strip()

            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                    if data["status"] == "success" and data["data"]["result"]:
                        return data["data"]["result"]
            return []
        except Exception as e:
            logger.error(f"Error querying Prometheus: {str(e)}")
            return []

    def get_deployment_config(self, deployment_name: str) -> Dict[str, Any]:
        """Get deployment configuration using oc command"""
        try:
            result = subprocess.run(
                [
                    "oc",
                    "get",
                    "deployment",
                    deployment_name,
                    "-n",
                    self.namespace,
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                deployment = json.loads(result.stdout)
                container = deployment["spec"]["template"]["spec"]["containers"][0]
                resources = container.get("resources", {})

                return {
                    "deployment_name": deployment_name,
                    "cpu_limit": resources.get("limits", {}).get("cpu"),
                    "cpu_request": resources.get("requests", {}).get("cpu"),
                    "memory_limit": resources.get("limits", {}).get("memory"),
                    "memory_request": resources.get("requests", {}).get("memory"),
                }
            else:
                logger.error(
                    f"Failed to get deployment config for {deployment_name}: {result.stderr}"
                )
                return {"deployment_name": deployment_name, "error": result.stderr}
        except Exception as e:
            logger.error(
                f"Error getting deployment config for {deployment_name}: {str(e)}"
            )
            return {"deployment_name": deployment_name, "error": str(e)}

    async def collect_system_metrics(self) -> Dict[str, Any]:
        """Collect CPU and memory metrics for both microservices from Prometheus"""
        logger.info("📊 Collecting system metrics for both microservices...")

        metrics = {}

        # Queries for both microservices
        queries = {
            "microservice_a_cpu": 'rate(process_cpu_seconds_total{job="microservice-a"}[1m])',
            "microservice_a_memory": 'process_resident_memory_bytes{job="microservice-a"}',
            "microservice_b_cpu": 'rate(process_cpu_seconds_total{job="microservice-b"}[1m])',
            "microservice_b_memory": 'process_resident_memory_bytes{job="microservice-b"}',
            "microservice_b_latency": "queue_service_microservice_b_latency_seconds",
        }

        for metric_name, query in queries.items():
            results = await self.query_prometheus(query)
            if results and len(results) > 0:
                metrics[metric_name] = {
                    "value": float(results[0]["value"][1]),
                    "timestamp": results[0]["value"][0],
                }
            else:
                metrics[metric_name] = {"value": None, "error": "No data"}

        return metrics

    async def analyze_with_llm(
        self,
        diagnosis_from_agent1: str,
        alert_name: str,
        alert_labels: Dict[str, str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Analyze Agent 1's diagnosis and determine remediation strategy"""
        logger.info("🤖 Analyzing with LLM for remediation strategy...")

        if alert_labels is None:
            alert_labels = {}

        # Collect deployment configs for both microservices
        logger.info("📋 Collecting deployment configurations...")
        microservice_a_config = self.get_deployment_config(
            self.microservice_a_deployment
        )
        microservice_b_config = self.get_deployment_config(
            self.microservice_b_deployment
        )

        # Collect system metrics
        system_metrics = await self.collect_system_metrics()

        affected_service = alert_labels.get("service", "unknown")

        # Format deployment configs for display
        def format_config(config):
            if "error" in config:
                return f"Error: {config['error']}"
            return f"CPU: {config.get('cpu_request', 'N/A')}/{config.get('cpu_limit', 'N/A')}, Memory: {config.get('memory_request', 'N/A')}/{config.get('memory_limit', 'N/A')}"

        # Format metrics for display
        def format_metric(metric):
            if metric.get("value") is not None:
                return f"{metric['value']:.4f}"
            return "N/A"

        context = f"""
I am Agent 2, receiving a diagnosis from Agent 1 about a microservice performance issue in an OpenShift cluster.

**Alert**: {alert_name}
**Affected Service**: {affected_service}

**Agent 1's Diagnosis**:
{diagnosis_from_agent1}

**Current Deployment Configurations**:
- **Microservice A**: {format_config(microservice_a_config)}
- **Microservice B**: {format_config(microservice_b_config)}
- **Namespace**: {self.namespace}

**Current System Metrics** (from Prometheus):
- **Microservice A CPU**: {format_metric(system_metrics.get('microservice_a_cpu', {}))} cores/sec
- **Microservice A Memory**: {format_metric(system_metrics.get('microservice_a_memory', {}))} bytes
- **Microservice B CPU**: {format_metric(system_metrics.get('microservice_b_cpu', {}))} cores/sec
- **Microservice B Memory**: {format_metric(system_metrics.get('microservice_b_memory', {}))} bytes
- **Microservice B Latency**: {format_metric(system_metrics.get('microservice_b_latency', {}))} seconds

**My Access Capabilities (Agent 2)**:
- ✅ I CAN access: Both microservices' deployment configurations
- ✅ I CAN access: CPU/memory metrics for both Microservice A and B
- ✅ I CAN access: OpenShift deployment details and resource specifications
- ✅ I CAN execute: `oc` commands to modify deployments

**Note**: Agent 1 has identified the problem location. Now I need to analyze the deployment configuration and metrics to determine the appropriate remediation.

**System Architecture & Data Flow**:
This is a distributed system with two microservices:

1. **Microservice A (Queue Service)**:
   - Receives requests from clients
   - Maintains an internal message queue (max size: 100)
   - Processes queued items by calling Microservice B

2. **Microservice B (Processing Service)**:
   - Receives requests from Microservice A
   - Performs computational work that does not require a lot of memory but is CPU-intensive
   - Runs in OpenShift with configured resource limits (CPU/Memory)

**OpenShift Resource Management**:
- **CPU Limit**: Maximum CPU the pod can use (measured in millicores, e.g., 100m = 0.1 CPU cores, 1000m = 1 full core)
- **CPU Request**: Guaranteed CPU allocation for the pod
- **Memory Limit**: Maximum memory the pod can use (e.g., 256Mi, 1Gi)
- **Memory Request**: Guaranteed memory allocation

When a pod exceeds its CPU limit, OpenShift throttles it, which can cause performance degradation.
When a pod exceeds its memory limit, it may be killed and restarted.

**Typical Resource Values for Reference**:
- CPU: 100m (minimal) → 500m (moderate) → 1000m-2000m (high performance)
- Memory: 256Mi (small) → 512Mi-1Gi (moderate) → 2Gi+ (large)

**Your Task**:
1. Read Agent 1's diagnosis carefully to understand which microservice has the problem
2. Analyze the current deployment configurations and system metrics
3. Correlate the symptoms (latency, CPU, memory) with the deployment resource limits
4. Determine the appropriate remediation action
5. Generate `oc` commands to fix the problem
6. **IMPORTANT**: Each command must fix only a single resource (e.g., separate commands for CPU limit, CPU request, memory limit, memory request)

You MUST respond in this EXACT JSON format:
{{
  "explanation": "Brief explanation of which microservice needs remediation and why, based on analysis of metrics and configuration",
  "commands": [
    "oc set resources deployment <deployment-name> -n {self.namespace} --limits cpu=<value>",
    "oc set resources deployment <deployment-name> -n {self.namespace} --requests cpu=<value>"
  ]
}}

CRITICAL Rules:
1. Analyze Agent 1's diagnosis and the metrics to determine root cause
2. Use deployment name "microservice-b" for Microservice B remediation
3. Use deployment name "microservice-a" for Microservice A remediation
4. Use ONLY valid `oc set resources` commands
5. Namespace is: {self.namespace}
6. Provide AT LEAST one command
7. Choose resource values that will effectively resolve the performance issue based on workload requirements
8. Ensure commands are complete and executable

Return ONLY the JSON, no other text.
"""

        try:
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are Agent 2, an expert OpenShift administrator. You have access to deployment configurations and system metrics for all microservices. Analyze Agent 1's diagnosis along with deployment configs and metrics to determine the root cause and generate remediation commands. You MUST respond ONLY with valid JSON containing an explanation and a list of oc commands. No other text.",
                    },
                    {"role": "user", "content": context},
                ],
                "stream": False,
                "temperature": 0.7,
                "max_tokens": 400,
            }

            logger.info(f"Sending request to LLM at {self.llm_endpoint}")

            # Create SSL context
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(
                    f"{self.llm_endpoint}/v1/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                    ssl=ssl_context,
                ) as response:
                    response.raise_for_status()
                    result = await response.json()

                    if "choices" in result and len(result["choices"]) > 0:
                        llm_response = result["choices"][0]["message"]["content"]

                        # Parse JSON from LLM response
                        try:
                            # Try to extract JSON from the response (in case LLM adds extra text)
                            import re

                            json_match = re.search(r"\{.*\}", llm_response, re.DOTALL)
                            if json_match:
                                remediation_json = json.loads(json_match.group())
                                return remediation_json
                            else:
                                logger.error(
                                    f"No JSON found in LLM response: {llm_response}"
                                )
                                return None
                        except json.JSONDecodeError as je:
                            logger.error(
                                f"Failed to parse JSON from LLM response: {je}"
                            )
                            logger.error(f"LLM response was: {llm_response}")
                            return None
                    else:
                        logger.error(f"Unexpected LLM response format: {result}")
                        return None

        except Exception as e:
            logger.error(f"Error analyzing with LLM: {str(e)}")
            return None

    def execute_commands(
        self, commands: list[str], deployment_name: str = None
    ) -> Dict[str, Any]:
        """Execute a list of oc commands"""
        if deployment_name is None:
            deployment_name = self.microservice_b_deployment

        logger.info(f"🔧 Executing {len(commands)} remediation command(s)...")

        # Get current config before changes
        current_config = self.get_deployment_config(deployment_name)

        results = []
        all_successful = True

        for i, command in enumerate(commands, 1):
            logger.info(f"📝 Command {i}/{len(commands)}: {command}")

            try:
                # Parse the command into a list for subprocess
                cmd_parts = command.split()

                result = subprocess.run(
                    cmd_parts, capture_output=True, text=True, timeout=30
                )

                if result.returncode == 0:
                    logger.info(f"✅ Command {i} succeeded: {result.stdout.strip()}")
                    results.append(
                        {
                            "command": command,
                            "success": True,
                            "output": result.stdout.strip(),
                        }
                    )
                else:
                    logger.error(f"❌ Command {i} failed: {result.stderr.strip()}")
                    results.append(
                        {
                            "command": command,
                            "success": False,
                            "error": result.stderr.strip(),
                        }
                    )
                    all_successful = False

            except Exception as e:
                logger.error(f"❌ Exception executing command {i}: {str(e)}")
                results.append({"command": command, "success": False, "error": str(e)})
                all_successful = False

        # Get new config after changes
        new_config = self.get_deployment_config(deployment_name)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "deployment_name": deployment_name,
            "namespace": self.namespace,
            "current_config": current_config,
            "new_config": new_config,
            "commands_executed": results,
            "success": all_successful,
        }

    async def remediate(self, remediation_input: RemediationInput) -> Dict[str, Any]:
        """
        Main skill: Apply remediation based on diagnosis from Agent 1
        """
        logger.info(f"🚀 {self.name} invoked for alert: {remediation_input.alert_name}")
        logger.info(f"📋 Diagnosis received: {remediation_input.diagnosis[:200]}...")

        # Step 1: Analyze diagnosis with LLM to determine which service to remediate
        # Don't rely on alert labels - the alert may come from service A but the fix might be needed in service B
        logger.info("🤖 Analyzing diagnosis to determine remediation target...")

        llm_response = await self.analyze_with_llm(
            remediation_input.diagnosis,
            remediation_input.alert_name,
            remediation_input.alert_labels,
        )

        if not llm_response:
            logger.error("❌ Failed to get remediation commands from LLM")
            return {
                "agent": self.name,
                "alert": remediation_input.alert_name,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "failed",
                "error": "Failed to get remediation commands from LLM",
            }

        # Extract explanation and commands from LLM response
        explanation = llm_response.get("explanation", "No explanation provided")
        commands = llm_response.get("commands", [])

        if not commands:
            logger.error("❌ LLM did not provide any commands")
            return {
                "agent": self.name,
                "alert": remediation_input.alert_name,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "failed",
                "error": "LLM did not provide any commands",
                "llm_explanation": explanation,
            }

        # Extract deployment name from the first command to determine which service is being remediated
        deployment_name = self.microservice_b_deployment  # Default
        if commands:
            # Parse the deployment name from the first command
            import re

            for cmd in commands:
                match = re.search(r"deployment\s+(\S+)", cmd)
                if match:
                    deployment_name = match.group(1)
                    break

        logger.info("=" * 80)
        logger.info("💡 LLM ANALYSIS:")
        logger.info("=" * 80)
        logger.info(f"Target Deployment: {deployment_name}")
        logger.info(explanation)
        logger.info("=" * 80)
        logger.info(f"📋 Commands to execute: {len(commands)}")
        for i, cmd in enumerate(commands, 1):
            logger.info(f"  {i}. {cmd}")
        logger.info("=" * 80)

        # Step 2: Execute the commands from LLM
        remediation_result = self.execute_commands(commands, deployment_name)

        result = {
            "agent": self.name,
            "alert": remediation_input.alert_name,
            "timestamp": remediation_result["timestamp"],
            "deployment": deployment_name,
            "namespace": self.namespace,
            "current_config": remediation_result["current_config"],
            "new_config": remediation_result["new_config"],
            "llm_explanation": explanation,
            "commands": commands,
            "execution_results": remediation_result["commands_executed"],
            "status": "success" if remediation_result["success"] else "failed",
        }

        # Log the result
        if remediation_result["success"]:
            logger.info("=" * 80)
            logger.info("✅ AGENT 2 REMEDIATION COMPLETE!")
            logger.info("=" * 80)
            logger.info(f"Deployment: {deployment_name}")
            logger.info(f"Namespace: {self.namespace}")
            logger.info(
                f"Previous Config: CPU={remediation_result['current_config'].get('cpu_limit')}, Memory={remediation_result['current_config'].get('memory_limit')}"
            )
            logger.info(
                f"New Config: CPU={remediation_result['new_config'].get('cpu_limit')}, Memory={remediation_result['new_config'].get('memory_limit')}"
            )
            logger.info("=" * 80)
        else:
            logger.error("=" * 80)
            logger.error("❌ AGENT 2 REMEDIATION FAILED!")
            logger.error("=" * 80)
            for cmd_result in remediation_result["commands_executed"]:
                if not cmd_result["success"]:
                    logger.error(f"Failed command: {cmd_result['command']}")
                    logger.error(f"Error: {cmd_result.get('error', 'Unknown error')}")
            logger.error("=" * 80)

        return result


class RemediateAgentExecutor(AgentExecutor):
    """Executor for RemediateAgent using A2A framework"""

    def __init__(self):
        """Initialize the executor with the agent"""
        # Get configuration from environment
        llm_endpoint = os.environ.get(
            "LLM_ENDPOINT",
        )
        prometheus_url = os.environ.get(
            "PROMETHEUS_URL", "https://thanos-querier.openshift-monitoring.svc:9091"
        )
        microservice_a_deployment = os.environ.get(
            "MICROSERVICE_A_DEPLOYMENT", "microservice-a"
        )
        microservice_b_deployment = os.environ.get(
            "MICROSERVICE_B_DEPLOYMENT", "microservice-b"
        )
        namespace = os.environ.get("NAMESPACE", "a2a-demo")

        self.agent = RemediateAgent(
            llm_endpoint=llm_endpoint,
            prometheus_url=prometheus_url,
            microservice_a_deployment=microservice_a_deployment,
            microservice_b_deployment=microservice_b_deployment,
            namespace=namespace,
        )
        self._cancelled = False

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> Dict[str, Any]:
        """
        Execute the agent (required by A2A framework)

        Args:
            context: Request context from A2A framework
            event_queue: Event queue for streaming updates

        Returns:
            Remediation result dictionary
        """
        logger.info(f"Executing {self.agent.name} with context: {context}")

        # Extract remediation input from context
        remediation_input = RemediationInput(
            diagnosis=context.get("diagnosis", ""),
            alert_name=context.get("alert_name", "Unknown"),
            alert_labels=context.get("alert_labels", {}),
            diagnostic_data=context.get("diagnostic_data", {}),
        )

        # Execute remediation
        result = await self.agent.remediate(remediation_input)

        # Send events to queue for streaming updates
        if event_queue:
            await event_queue.put({"type": "remediation_complete", "data": result})

        return result

    async def cancel(self):
        """Cancel the agent execution (required by A2A framework)"""
        logger.info(f"Cancelling {self.agent.name}...")
        self._cancelled = True

    async def handle_remediation_request(
        self, remediation_input: RemediationInput
    ) -> Dict[str, Any]:
        """
        Handle incoming remediation request from Agent 1

        Args:
            remediation_input: Remediation input with diagnosis

        Returns:
            Remediation result
        """
        try:
            logger.warning("🚨 REMEDIATION REQUEST RECEIVED from Agent 1")

            # Execute remediation
            result = await self.agent.remediate(remediation_input)

            if result["status"] == "success":
                logger.info("✅ Remediation complete")
            else:
                logger.error("❌ Remediation failed")

            return result
        except Exception as e:
            logger.error(f"Error handling remediation request: {str(e)}")
            return {"status": "error", "message": str(e)}


# Create AgentCard for A2A protocol
def create_agent_card() -> AgentCard:
    """Create A2A AgentCard for RemediateAgent"""
    return AgentCard(
        name="RemediateAgent",
        description="Applies remediation to OpenShift deployments based on diagnosis from DiagnoseAgent. Specializes in patching resource limits and scaling issues.",
        version="1.0.0",
        url=f"http://agent2:{os.environ.get('PORT', '8080')}",
        capabilities=AgentCapabilities(
            streaming=False, statefulness="stateless", tools=[], llmProvider=None
        ),
        skills=[
            AgentSkill(
                id="remediate-deployment",
                name="Remediate Deployment",
                description="Applies remediation to microservice deployments by increasing resource limits based on diagnosis. Uses LLM to determine optimal resource allocation and executes oc commands to patch deployments.",
                inputModes=["application/json"],
                outputModes=["application/json"],
                tags=[
                    "remediation",
                    "kubernetes",
                    "openshift",
                    "deployment",
                    "resource-management",
                ],
                examples=[
                    '{"diagnosis": "Microservice B is CPU-constrained", "alert_name": "HighQueueDepth", "alert_labels": {"service": "microservice-b"}}',
                    '{"diagnosis": "Service experiencing high CPU usage", "alert_name": "MicroserviceBHighCPU", "alert_labels": {"service": "microservice-b"}}',
                ],
            )
        ],
        defaultInputModes=["application/json"],
        defaultOutputModes=["application/json"],
        provider=AgentProvider(
            organization="A2A Demo", url="https://github.com/your-org/a2a-demo"
        ),
        documentationUrl="https://github.com/your-org/a2a-demo/blob/main/README.md",
    )


def main():
    """Main entry point - starts A2A REST FastAPI server with custom webhook"""
    port = int(os.environ.get("PORT", "8080"))

    logger.info("🚀 Starting RemediateAgent A2A Server...")
    logger.info(f"  LLM Endpoint: {os.environ.get('LLM_ENDPOINT', 'default')}")
    logger.info(f"  Prometheus URL: {os.environ.get('PROMETHEUS_URL', 'default')}")
    logger.info(
        f"  Microservice A Deployment: {os.environ.get('MICROSERVICE_A_DEPLOYMENT', 'microservice-a')}"
    )
    logger.info(
        f"  Microservice B Deployment: {os.environ.get('MICROSERVICE_B_DEPLOYMENT', 'microservice-b')}"
    )
    logger.info(f"  Namespace: {os.environ.get('NAMESPACE', 'a2a-demo')}")
    logger.info(f"  Port: {port}")

    # Create executor
    executor = RemediateAgentExecutor()

    # Create agent card
    agent_card = create_agent_card()

    # Create REST handler using DefaultRequestHandler
    from a2a.server.events import InMemoryQueueManager
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.tasks import InMemoryTaskStore

    task_store = InMemoryTaskStore()
    queue_manager = InMemoryQueueManager()
    request_handler = DefaultRequestHandler(
        agent_executor=executor, task_store=task_store, queue_manager=queue_manager
    )

    # Create REST HTTP handler
    rest_handler = RESTHandler(agent_card=agent_card, request_handler=request_handler)

    # Create A2A REST FastAPI application
    a2a_app = A2ARESTFastAPIApplication(
        agent_card=agent_card, http_handler=rest_handler
    )

    # Build the FastAPI app using the proper A2A method
    fastapi_app = a2a_app.build()

    # Add custom webhook endpoint for Agent1
    @fastapi_app.post("/remediate")
    async def remediate_webhook(
        request: RemediationInput, background_tasks: BackgroundTasks
    ):
        """
        Receive remediation request from Agent 1
        This is a custom endpoint outside the A2A protocol for agent-to-agent communication
        """
        logger.info(f"📥 Remediation request received for alert: {request.alert_name}")

        # Handle remediation in background to return response quickly
        background_tasks.add_task(executor.handle_remediation_request, request)

        logger.info("🔔 Queued remediation task for processing")

        return {
            "status": "accepted",
            "message": "Remediation request queued for processing",
            "alert": request.alert_name,
        }

    # Add health endpoint for OpenShift probes
    @fastapi_app.get("/health")
    async def health_check():
        """Health check endpoint for OpenShift liveness/readiness probes"""
        return {"status": "healthy", "agent": "RemediateAgent"}

    logger.info("📡 A2A REST endpoints available:")
    logger.info("  - POST /skills/{skill_id}/invoke - A2A skill invocation")
    logger.info("  - GET /agent-card - A2A agent card")
    logger.info("  - POST /remediate - Agent1 webhook (custom)")
    logger.info("  - GET /health - Health check")

    # Run the server - simple and clean!
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
