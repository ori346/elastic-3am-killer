#!/usr/bin/env python3
"""
Common A2A diagnosis sender for sending diagnosis messages to host agent.
"""
import json
import uuid

import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import AgentCard, DataPart, Message, Role, TextPart


class DiagnosisSender:
    """Handles sending diagnosis messages to a host agent via A2A protocol."""

    def __init__(self, host_agent_url: str = "http://localhost:5001"):
        """Initialize the diagnosis sender.

        Args:
            host_agent_url: URL of the host agent (default: http://localhost:5001)
        """
        self.host_agent_url = host_agent_url

    async def send_diagnosis(self, diagnosis_message: str) -> None:
        """Send a diagnosis message to the host agent.

        Args:
            diagnosis_message: The diagnosis text to send to the host agent
        """
        async with httpx.AsyncClient(timeout=600.0) as http_client:
            # Get host agent card
            print("Fetching host agent card...")
            card_response = await http_client.get(
                f"{self.host_agent_url}/.well-known/agent-card.json"
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
                parts=[TextPart(text=diagnosis_message)],
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