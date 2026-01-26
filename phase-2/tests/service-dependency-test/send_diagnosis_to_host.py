#!/usr/bin/env python3
"""
Send agent1's diagnosis to the host agent via A2A protocol for service dependency failure test.
"""
import asyncio
import json
import uuid

import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import AgentCard, DataPart, Message, Role, TextPart


async def send_diagnosis_to_host():
    """Send the diagnosis from agent1 to the host agent."""

    # The diagnosis from agent1's logs for frontend high error rate scenario
    diagnosis = """**Alert**: FrontendHighErrorRate (Severity: warning)
**Affected Service**: frontend-web
**Namespace**: integration-test-ofridman

**Diagnosis Summary:**
Frontend service is healthy but experiencing 95% HTTP 500 error rate due to failed dependency connection.

**Frontend Service Status** (HEALTHY):
- Pods: 2/2 READY and RUNNING
- CPU: 15%, Memory: 25% (normal levels)
- Health checks: PASSING

**Root Cause Identified:**
Connection refused to backend-api:8080 - "Failed to connect to backend-api:8080 - Connection refused"

**Dependency Chain:**
frontend-web (HEALTHY) → backend-api:8080 (CONNECTION REFUSED)

**Impact:**
- Error Rate: 95% (HTTP 500)
- Failed Requests: 190/min

**Recommendation:**
The problem is NOT in frontend-web. Investigate backend-api service:
1. Check if backend-api pods are running and ready
2. Verify backend-api service exists and has valid endpoints
3. Check backend-api logs for crashes or startup failures
4. Confirm backend-api is listening on port 8080"""

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
                    if isinstance(part.root, DataPart):
                        result_text += json.dumps(part.root.data, indent=2)

        print("=" * 80)
        print("HOST AGENT RESPONSE:")
        print("=" * 80)
        print(result_text)
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(send_diagnosis_to_host())
