import asyncio
import logging
import os
import ssl
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

LLM_ENDPOINT = os.environ.get(
    "LLM_ENDPOINT",
    "https://redhataillama-31-8b-instruct-quickstart-llms.apps.ai-dev02.kni.syseng.devcluster.openshift.com",
)
PROMETHEUS_URL = os.environ.get(
    "PROMETHEUS_URL", "https://thanos-querier.openshift-monitoring.svc:9091"
)
MICROSERVICE_A_URL = os.environ.get("MICROSERVICE_A_URL", "http://microservice-a:8080")
AGENT2_URL = os.environ.get("AGENT2_URL", "http://agent2:8080")


class DiagnosticData(BaseModel):
    """Data collected for diagnosis"""

    timestamp: str
    alert_name: str
    queue_depth: Optional[float] = None
    queue_status: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    prometheus_queries: Dict[str, Any] = Field(default_factory=dict)


class AlertInput(BaseModel):
    """Input model for alert diagnosis skill"""

    alert_name: str
    alert_labels: Dict[str, str] = Field(default_factory=dict)
    alert_annotations: Dict[str, str] = Field(default_factory=dict)


class DiagnoseAgent(BaseModel):
    """Agent 1: Diagnoses microservice performance issues by analyzing Prometheus metrics and system health"""

    name: str = "DiagnoseAgent"
    llm_endpoint: str = Field(default=LLM_ENDPOINT)
    prometheus_url: str = Field(default=PROMETHEUS_URL)
    microservice_a_url: str = Field(default=MICROSERVICE_A_URL)
    agent2_url: str = Field(default=AGENT2_URL)

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

    async def get_microservice_a_status(self) -> Dict[str, Any]:
        """Get queue status from Microservice A"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.microservice_a_url}/queue/status",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status == 200:
                        return await response.json()
            return {}
        except Exception as e:
            logger.error(f"Error getting Microservice A status: {str(e)}")
            return {}

    async def get_microservice_a_metrics(self) -> Dict[str, Any]:
        """Get Prometheus metrics from Microservice A"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.microservice_a_url}/metrics",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status == 200:
                        metrics_text = await response.text()

                        # Parse relevant metrics
                        metrics = {}
                        for line in metrics_text.split("\n"):
                            if (
                                "queue_service_queue_depth" in line
                                and not line.startswith("#")
                            ):
                                metrics["queue_depth"] = float(line.split()[-1])
                            elif (
                                "queue_service_microservice_b_latency_seconds_sum"
                                in line
                            ):
                                metrics["b_latency_sum"] = float(line.split()[-1])
                            elif (
                                "queue_service_microservice_b_latency_seconds_count"
                                in line
                            ):
                                metrics["b_latency_count"] = float(line.split()[-1])

                        # Calculate average latency to Microservice B
                        if (
                            "b_latency_sum" in metrics
                            and "b_latency_count" in metrics
                            and metrics["b_latency_count"] > 0
                        ):
                            metrics["b_avg_latency"] = (
                                metrics["b_latency_sum"] / metrics["b_latency_count"]
                            )

                        return metrics
        except Exception as e:
            logger.error(f"Error getting Microservice A metrics: {str(e)}")
            return {}

    async def collect_diagnostic_data(
        self, alert_name: str, alert_labels: Dict[str, str] = None
    ) -> DiagnosticData:
        """Collect all relevant diagnostic data based on the alert"""
        logger.info(f"📊 Collecting diagnostic data for alert: {alert_name}...")

        if alert_labels is None:
            alert_labels = {}

        # Collect data in parallel
        queue_status, metrics, queue_depth_results = await asyncio.gather(
            self.get_microservice_a_status(),
            self.get_microservice_a_metrics(),
            self.query_prometheus("queue_service_queue_depth"),
            return_exceptions=True,
        )

        # Handle exceptions
        if isinstance(queue_status, Exception):
            logger.error(f"Error collecting queue status: {queue_status}")
            queue_status = {}
        if isinstance(metrics, Exception):
            logger.error(f"Error collecting metrics: {metrics}")
            metrics = {}
        if isinstance(queue_depth_results, Exception):
            logger.error(f"Error querying queue depth: {queue_depth_results}")
            queue_depth_results = []

        queue_depth = None
        if queue_depth_results and len(queue_depth_results) > 0:
            queue_depth = float(queue_depth_results[0]["value"][1])

        # Collect Prometheus queries - different based on alert type
        prometheus_queries = {}

        # Common queries for all alerts
        common_queries = {
            "queue_depth": "queue_service_queue_depth",
            "queue_requests_rate": "rate(queue_service_requests_total[5m])",
            "processing_errors_rate": "rate(queue_service_processing_errors_total[5m])",
        }

        # Agent1 can ONLY query metrics from Microservice A
        # It cannot access Microservice B metrics or deployment details
        for name, query in common_queries.items():
            results = await self.query_prometheus(query)
            if results:
                prometheus_queries[name] = results

        return DiagnosticData(
            timestamp=datetime.utcnow().isoformat(),
            alert_name=alert_name,
            queue_depth=queue_depth,
            queue_status=queue_status,
            metrics=metrics,
            prometheus_queries=prometheus_queries,
        )

    async def analyze_with_llm(
        self,
        diagnostic_data: DiagnosticData,
        alert_labels: Dict[str, str] = None,
        alert_annotations: Dict[str, str] = None,
    ) -> Optional[str]:
        """Send diagnostic data to LLM for analysis"""
        logger.info("🤖 Analyzing with LLM...")

        if alert_labels is None:
            alert_labels = {}
        if alert_annotations is None:
            alert_annotations = {}

        # Prepare the context for the LLM - make it generic based on alert data
        avg_latency = diagnostic_data.metrics.get("b_avg_latency", "unknown")

        # Build metrics summary dynamically
        metrics_summary = []
        if diagnostic_data.queue_status:
            metrics_summary.append("**Current Queue Status**:")
            metrics_summary.append(
                f"- Queue Depth: {diagnostic_data.queue_status.get('queue_depth', 'unknown')}"
            )
            metrics_summary.append(
                f"- Max Queue Size: {diagnostic_data.queue_status.get('max_queue_size', 'unknown')}"
            )

        if diagnostic_data.metrics:
            metrics_summary.append("\n**Service Metrics**:")
            metrics_summary.append(
                f"- Queue Depth: {diagnostic_data.metrics.get('queue_depth', 'unknown')}"
            )
            if avg_latency != "unknown":
                metrics_summary.append(
                    f"- Average Latency to Microservice B: {avg_latency} seconds"
                )
            metrics_summary.append(
                f"- Total calls to Microservice B: {diagnostic_data.metrics.get('b_latency_count', 'unknown')}"
            )

        if diagnostic_data.prometheus_queries:
            metrics_summary.append("\n**Prometheus Metrics**:")
            for metric_name, metric_data in diagnostic_data.prometheus_queries.items():
                if metric_data:
                    value = (
                        metric_data[0].get("value", ["", "unknown"])[1]
                        if metric_data
                        else "unknown"
                    )
                    metrics_summary.append(f"- {metric_name}: {value}")

        alert_description = alert_annotations.get(
            "description",
            alert_annotations.get(
                "summary", f"{diagnostic_data.alert_name} alert is firing"
            ),
        )
        affected_service = alert_labels.get("service", "unknown")
        severity = alert_labels.get("severity", "unknown")

        context = f"""
I am Agent 1, analyzing a microservice performance issue in an OpenShift cluster.

**Alert**: {diagnostic_data.alert_name} (Severity: {severity})
**Description**: {alert_description}
**Affected Service**: {affected_service}

{chr(10).join(metrics_summary)}

**System Architecture & Data Flow**:
This is a distributed system with the following components:

1. **Client Simulator**:
   - Sends HTTP requests to Microservice A at a continuous rate

2. **Microservice A (Queue Service)**:
   - Receives incoming requests from clients
   - Maintains an internal message queue (max size: 100)
   - Processes queued items by calling Microservice B
   - Exposes metrics: queue_depth, request rates, latency to Microservice B

3. **Microservice B (Processing Service)**:
   - Receives requests from Microservice A
   - Performs computational work
   - Runs in Kubernetes with configured resource limits (CPU/Memory)
   - I CANNOT access Microservice B's metrics or deployment details

**My Access Limitations (Agent 1)**:
- ✅ I CAN access: Microservice A metrics, queue status, and latency to Microservice B
- ❌ I CANNOT access: Microservice B internal metrics, CPU/memory usage, or deployment configuration
- ❌ I CANNOT access: OpenShift deployment details or resource specifications

**Key Relationships**:
- Queue depth in Microservice A reflects the balance between incoming request rate and processing throughput
- Microservice A's ability to process requests depends on Microservice B's response time
- High latency to Microservice B causes queue buildup in Microservice A
- High queue depth indicates requests are arriving faster than they can be processed

**Your Task**:
Based on the metrics I collected from Microservice A, determine:
1. What is the root cause of this performance issue?
2. Is the problem in Microservice A or Microservice B?
3. If you suspect that one of the Microservices is the bottleneck, clearly state that in which Microsevice do you suspect that is the probelm Agent 2 needs to investigate Microservices resources.

Provide a clear diagnosis that Agent 2 can use to remediate the issue. Agent 2 has access to both microservices' deployment details and resource metrics.
"""

        try:
            payload = {
                "model": "redhataillama-31-8b-instruct",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are Agent 1, an expert microservices troubleshooting assistant. You can only access Microservice A's metrics. Analyze the data and identify if the problem is in Microservice A or B based on queue depth and latency metrics. Provide a clear diagnosis for Agent 2 to act upon.",
                    },
                    {"role": "user", "content": context},
                ],
                "stream": False,
                "temperature": 0.7,
                "max_tokens": 400,
            }

            logger.info(f"Sending request to LLM at {self.llm_endpoint}")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.llm_endpoint}/v1/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    response.raise_for_status()
                    result = await response.json()

                    if "choices" in result and len(result["choices"]) > 0:
                        diagnosis = result["choices"][0]["message"]["content"]
                        return diagnosis
                    else:
                        logger.error(f"Unexpected LLM response format: {result}")
                        return None

        except Exception as e:
            logger.error(f"Error analyzing with LLM: {str(e)}")
            return None

    async def call_agent2(
        self, diagnosis: str, alert_name: str, alert_labels: Dict[str, str] = None
    ) -> Optional[Dict[str, Any]]:
        """Trigger Agent 2 for remediation via webhook"""
        logger.info("📤 Calling Agent 2 webhook for remediation...")
        logger.info("💡 Agent 2 will determine and apply appropriate remediation")

        if alert_labels is None:
            alert_labels = {}

        try:
            # Prepare payload for Agent 2
            payload = {
                "diagnosis": diagnosis,
                "alert_name": alert_name,
                "alert_labels": alert_labels,
                "diagnostic_data": {},
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.agent2_url}/remediate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(
                            f"✅ Agent 2 acknowledged remediation request: {result.get('message')}"
                        )
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"❌ Agent 2 returned error {response.status}: {error_text}"
                        )
                        return {
                            "triggered": False,
                            "error": f"HTTP {response.status}: {error_text}",
                        }
        except Exception as e:
            logger.error(f"❌ Error calling Agent 2: {str(e)}")
            return {"triggered": False, "error": str(e)}

    async def diagnose_alert(self, alert_input: AlertInput) -> Dict[str, Any]:
        """
        Main skill: Diagnose microservice performance alerts
        """
        logger.info(f"🚀 DiagnoseAgent invoked for alert: {alert_input.alert_name}")

        # Step 1: Collect diagnostic data
        diagnostic_data = await self.collect_diagnostic_data(
            alert_input.alert_name, alert_input.alert_labels
        )

        # Step 2: Analyze with LLM
        diagnosis = await self.analyze_with_llm(
            diagnostic_data, alert_input.alert_labels, alert_input.alert_annotations
        )

        # Log the diagnosis
        if diagnosis:
            logger.info("=" * 80)
            logger.info("🔍 AGENT 1 DIAGNOSIS:")
            logger.info("=" * 80)
            logger.info(diagnosis)
            logger.info("=" * 80)
        else:
            logger.error("❌ Failed to get diagnosis from LLM")

        # Step 3: Call Agent 2 for remediation
        agent2_result = None
        if diagnosis:
            agent2_result = await self.call_agent2(
                diagnosis, alert_input.alert_name, alert_input.alert_labels
            )

        result = {
            "agent": self.name,
            "alert": alert_input.alert_name,
            "timestamp": diagnostic_data.timestamp,
            "diagnostic_data": diagnostic_data.model_dump(),
            "diagnosis": diagnosis,
            "status": "success" if diagnosis else "failed",
            "next_step": "Agent 2 will apply appropriate remediation based on the diagnosis",
            "agent2_response": agent2_result,
        }

        if agent2_result:
            logger.info("=" * 80)
            logger.info("🔧 AGENT 2 REMEDIATION TRIGGERED")
            logger.info("=" * 80)

        return result


class DiagnoseAgentExecutor(AgentExecutor):
    """Executor for DiagnoseAgent using A2A framework"""

    def __init__(self):
        """Initialize the executor with the agent"""
        self.agent = DiagnoseAgent(
            llm_endpoint=LLM_ENDPOINT,
            prometheus_url=PROMETHEUS_URL,
            microservice_a_url=MICROSERVICE_A_URL,
            agent2_url=AGENT2_URL,
        )
        self._cancelled = False

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> Dict[str, Any]:
        """
        Execute the agent (required by A2A framework)
        """
        logger.info(f"Executing {self.agent.name} with context: {context}")

        # Extract alert info from context
        alert_input = AlertInput(
            alert_name=context.get("alert_name", "Unknown"),
            alert_labels=context.get("alert_labels", {}),
            alert_annotations=context.get("alert_annotations", {}),
        )

        # Execute diagnosis
        result = await self.agent.diagnose_alert(alert_input)

        # Send events to queue for streaming updates
        if event_queue:
            await event_queue.put({"type": "diagnosis_complete", "data": result})

        return result

    async def cancel(self):
        """Cancel the agent execution (required by A2A framework)"""
        logger.info(f"Cancelling {self.agent.name}...")
        self._cancelled = True


# Create AgentCard for A2A protocol
def create_agent_card() -> AgentCard:
    """Create A2A AgentCard for DiagnoseAgent"""
    return AgentCard(
        name="DiagnoseAgent",
        description="Diagnoses microservice performance issues by analyzing Prometheus metrics and queue depths. Specializes in identifying bottlenecks in distributed systems.",
        version="1.0.0",
        url=f"http://agent1:{os.environ.get('PORT', '8080')}",
        capabilities=AgentCapabilities(
            streaming=False, statefulness="stateless", tools=[], llmProvider=None
        ),
        skills=[
            AgentSkill(
                id="diagnose-alert",
                name="Diagnose Microservice Alert",
                description="Analyzes microservice performance alerts by collecting metrics from Prometheus and services, uses LLM to diagnose root cause, and triggers remediation agent",
                inputModes=["application/json"],
                outputModes=["application/json"],
                tags=["observability", "diagnosis", "prometheus", "troubleshooting"],
                examples=[
                    '{"alert_name": "HighQueueDepth", "alert_labels": {"severity": "warning", "service": "microservice-a"}}',
                    '{"alert_name": "MicroserviceBHighCPU", "alert_labels": {"severity": "warning", "service": "microservice-b"}}',
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


# Alertmanager webhook models
class AlertmanagerWebhook(BaseModel):
    """Alertmanager webhook payload model"""

    version: str = "4"
    groupKey: str = ""
    truncatedAlerts: int = 0
    status: str
    receiver: str = ""
    groupLabels: Dict[str, Any] = Field(default_factory=dict)
    commonLabels: Dict[str, Any] = Field(default_factory=dict)
    commonAnnotations: Dict[str, Any] = Field(default_factory=dict)
    externalURL: str = ""
    alerts: list[Dict[str, Any]] = Field(default_factory=list)


def main():
    """Main entry point - starts A2A REST FastAPI server with custom webhook"""
    port = int(os.environ.get("PORT", "8080"))

    logger.info("🚀 Starting DiagnoseAgent A2A Server...")
    logger.info(f"  LLM Endpoint: {LLM_ENDPOINT}")
    logger.info(f"  Prometheus URL: {PROMETHEUS_URL}")
    logger.info(f"  Microservice A URL: {MICROSERVICE_A_URL}")
    logger.info(f"  Agent2 URL: {AGENT2_URL}")
    logger.info(f"  Port: {port}")

    # Create executor
    executor = DiagnoseAgentExecutor()

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

    # Add custom webhook endpoint for Alertmanager
    @fastapi_app.post("/webhook")
    async def alertmanager_webhook(
        webhook_data: AlertmanagerWebhook, background_tasks: BackgroundTasks
    ):
        """
        Receive alerts from Alertmanager webhook
        This is a custom endpoint outside the A2A protocol for receiving Prometheus alerts
        """
        logger.info(
            f"📥 Webhook received: status={webhook_data.status}, alerts={len(webhook_data.alerts)}"
        )

        # Process firing alerts only, ignore resolved alerts
        if webhook_data.status == "firing" and webhook_data.alerts:
            for alert in webhook_data.alerts:
                if alert.get("status") == "firing":
                    alert_name = alert.get("labels", {}).get("alertname", "Unknown")
                    alert_labels = alert.get("labels", {})
                    alert_annotations = alert.get("annotations", {})

                    # Create alert input
                    alert_input = AlertInput(
                        alert_name=alert_name,
                        alert_labels=alert_labels,
                        alert_annotations=alert_annotations,
                    )

                    # Handle alert in background
                    async def process_alert():
                        try:
                            logger.warning(f"🚨 Processing alert: {alert_name}")
                            result = await executor.agent.diagnose_alert(alert_input)
                            if result["status"] == "success":
                                logger.info("✅ Diagnosis complete")
                            else:
                                logger.error("❌ Diagnosis failed")
                        except Exception as e:
                            logger.error(f"Error processing alert: {str(e)}")

                    background_tasks.add_task(process_alert)
                    logger.info(f"🔔 Queued alert '{alert_name}' for processing")
        elif webhook_data.status == "resolved":
            # Log resolved alerts but verify the metrics actually show resolution
            async def verify_resolution():
                for alert in webhook_data.alerts:
                    alert_name = alert.get("labels", {}).get("alertname", "Unknown")

                    # Check current queue depth to verify resolution
                    queue_depth_results = await executor.agent.query_prometheus(
                        "queue_service_queue_depth"
                    )
                    current_queue_depth = None
                    if queue_depth_results and len(queue_depth_results) > 0:
                        current_queue_depth = float(queue_depth_results[0]["value"][1])

                    # Get queue status from Microservice A
                    queue_status = await executor.agent.get_microservice_a_status()

                    if current_queue_depth is not None and current_queue_depth > 10:
                        logger.warning(
                            f"⚠️  Alert marked as resolved but queue depth still high: {current_queue_depth}"
                        )
                        logger.warning(
                            "⚠️  This may be a false resolution - alert might re-fire soon"
                        )
                        logger.info(f"Current queue status: {queue_status}")
                    else:
                        logger.info(
                            f"✅ Alert resolved: {alert_name} - queue depth: {current_queue_depth}"
                        )

            background_tasks.add_task(verify_resolution)

        return {
            "status": "accepted",
            "message": f"Received {len(webhook_data.alerts)} alert(s)",
        }

    # Add health endpoint for Kubernetes probes
    @fastapi_app.get("/health")
    async def health_check():
        """Health check endpoint for Kubernetes liveness/readiness probes"""
        return {"status": "healthy", "agent": "DiagnoseAgent"}

    logger.info("📡 A2A REST endpoints available:")
    logger.info("  - POST /skills/{skill_id}/invoke - A2A skill invocation")
    logger.info("  - GET /agent-card - A2A agent card")
    logger.info("  - POST /webhook - Alertmanager webhook (custom)")
    logger.info("  - GET /health - Health check")

    # Run the server - simple and clean!
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
