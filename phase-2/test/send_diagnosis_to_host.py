#!/usr/bin/env python3
"""
Send agent1's diagnosis to the host agent via A2A protocol.
"""
import asyncio
import uuid

import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import AgentCard, Message, Role, TextPart


async def send_diagnosis_to_host():
    """Send the diagnosis from agent1 to the host agent."""

    # The diagnosis from agent1's logs
    diagnosis = """
**Alert**: HighQueueDepth (Severity: warning)
**Affected Service**: microservice-a
**Agent 1 Diagnosis:**
1. **Root Cause**: The root cause of the performance issue is a high request arrival rate exceeding the processing capacity of Microservice A, leading to a queue buildup.
2. **Bottleneck Location**: Based on the metrics from Microservice A, I suspect that **Microservice B** is the bottleneck. The average latency to Microservice B is 0.9357 seconds, which is relatively high, indicating that Microservice B is not responding quickly enough. This causes a queue buildup in Microservice A.
3. **Reasoning**:
   * The high queue depth (100) and queue requests rate (1.068) indicate that requests are arriving faster than Microservice A can process them.
   * The average latency to Microservice B (0.935 seconds) is a clear indication that Microservice B is taking a significant amount of time to respond, which is causing the queue buildup.
   * Although I don't have access to Microservice B's internal metrics, the high latency from Microservice A's perspective suggests that the issue lies with Microservice B's processing capacity.
**Recommendation:**
You should investigate Microservice B's deployment details, resource metrics, and internal metrics to identify the root cause of the high latency. This may involve checking:

* Resource utilization: CPU, memory, and network utilization
* Deployment configuration: resource allocation

You should then use this information to optimize Microservice B's resources or adjust its deployment configuration to improve its response time and reduce the latency to Microservice A.

**Diagnostic Data:**
- Queue Depth: 100 (at maximum capacity)
- Average Latency to Microservice B: 0.935 seconds
- Queue Requests Rate: 1.07 requests/second
- Service: microservice-a, microservice-b
- Namespace: integration-test
"""

    host_agent_url = "http://localhost:5001"

    async with httpx.AsyncClient(timeout=600.0) as http_client:
        # Get host agent card
        print("Fetching host agent card...")
        card_response = await http_client.get(
            f"{host_agent_url}/.well-known/agent-card.json"
        )
        agent_card_data = card_response.json()

        # Replace service URL with localhost
        if "url" in agent_card_data:
            agent_card_data["url"] = agent_card_data["url"].replace(
                "http://host-agent:", "http://localhost:"
            )
            print(f"Adjusted agent URL to: {agent_card_data['url']}")

        agent_card = AgentCard.model_validate(agent_card_data)
        print(f"Host agent: {agent_card.name}")
        print(f"Skills: {[skill.name for skill in agent_card.skills]}")

        # Create client
        config = ClientConfig(httpx_client=http_client)
        factory = ClientFactory(config=config)
        client = factory.create(card=agent_card)

        # Send message with diagnosis
        print("\nSending diagnosis to host agent...")
        message = Message(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[TextPart(text=diagnosis)],
        )

        # Process response
        print("Waiting for response...\n")
        result_text = ""
        async for event in client.send_message(message):
            if isinstance(event, Message):
                for part in event.parts:
                    if isinstance(part, TextPart):
                        result_text += part.text
                    elif hasattr(part, "root") and hasattr(part.root, "text"):
                        result_text += part.root.text
                    elif hasattr(part, "text"):
                        result_text += part.text
            elif isinstance(event, tuple):
                task, _ = event
                # Get agent messages from task history
                for msg in task.history:
                    if msg.role == Role.agent:
                        for part in msg.parts:
                            if isinstance(part, TextPart):
                                result_text += part.text
                            elif hasattr(part, "root") and hasattr(part.root, "text"):
                                result_text += part.root.text
                            elif hasattr(part, "text"):
                                result_text += part.text

        print("=" * 80)
        print("HOST AGENT RESPONSE:")
        print("=" * 80)
        print(result_text)
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(send_diagnosis_to_host())
