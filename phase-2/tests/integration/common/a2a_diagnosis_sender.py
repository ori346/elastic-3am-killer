#!/usr/bin/env python3
"""
Common A2A diagnosis sender for sending diagnosis messages to workflow coordinator.
"""
import json
import uuid

import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import AgentCard, DataPart, Message, Role, TextPart


class DiagnosisSender:
    """Handles sending diagnosis messages to a workflow coordinator via A2A protocol."""

    def __init__(self, workflow_coordinator_url: str = "http://localhost:5001"):
        """Initialize the diagnosis sender.

        Args:
            workflow_coordinator_url: URL of the workflow coordinator (default: http://localhost:5001)
        """
        self.workflow_coordinator_url = workflow_coordinator_url

    async def send_diagnosis_json(self, diagnosis_data: dict) -> None:
        """Send a JSON diagnosis request to the workflow coordinator.

        Args:
            diagnosis_data: The diagnosis JSON data to send to the workflow coordinator
        """
        async with httpx.AsyncClient(timeout=600.0) as http_client:
            # Get workflow coordinator card
            print("Fetching workflow coordinator card...")
            card_response = await http_client.get(
                f"{self.workflow_coordinator_url}/.well-known/agent-card.json"
            )
            agent_card_data = card_response.json()

            # Replace service URL when running on OpenShift
            # if "url" in agent_card_data:
            #     agent_card_data["url"] = https://elastic-3am-killer-integration-test-ofridman.apps.ai-dev02.kni.syseng.devcluster.openshift.com
            #
            #     print(f"Adjusted agent URL to: {agent_card_data['url']}")

            # Recreate agent card with modified URL
            agent_card = AgentCard.model_validate(agent_card_data)
            print(f"Workflow coordinator: {agent_card.name}")
            print(f"Skills: {[skill.name for skill in agent_card.skills]}")

            # Create client
            config = ClientConfig(httpx_client=http_client)
            factory = ClientFactory(config=config)
            client = factory.create(card=agent_card)

            # Send message with JSON diagnosis
            print(
                f"\nSending diagnosis for incident {diagnosis_data.get('incident_id', 'unknown')} to workflow coordinator..."
            )
            message = Message(
                message_id=str(uuid.uuid4()),
                role=Role.user,
                parts=[DataPart(data=diagnosis_data)],
            )

            # Process response
            print("Waiting for response...\n")
            result_text = ""
            async for event in client.send_message(message):
                if isinstance(event, Message):
                    for part in event.parts:
                        if isinstance(part.root, DataPart):
                            result_text += json.dumps(part.root.data, indent=2)
                        elif isinstance(part.root, TextPart):
                            result_text += part.root.text

            print("=" * 80)
            print("HOST AGENT RESPONSE:")
            print("=" * 80)
            print(result_text)
            print("=" * 80)
