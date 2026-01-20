"""
Workflow Agent Executor

Orchestrates remediate_agent and report_maker_agent to handle alert diagnosis,
command execution decisions, and report generation.
"""

import json
import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import DataPart, Message, MessageSendParams, TextPart
from llama_index.core.agent.workflow import (
    AgentOutput,
    AgentWorkflow,
    ToolCall,
    ToolCallResult,
)
from llama_index.core.workflow import Context

from .host_agent import agent as host_agent
from .remediate_agent import agent as remediate_agent
from .report_maker_agent import agent as report_generator_agent

logger = logging.getLogger(__name__)


class WorkflowAgentExecutor(AgentExecutor):
    """Orchestrator agent that coordinates remediation and reporting."""

    def __init__(
        self,
    ):
        # Create the orchestrator agent once during initialization
        self.agent = self._create_workflow_agent()

    def _create_workflow_agent(self) -> AgentWorkflow:
        """Create the main workflow agent."""

        initial_state = {
            "alert_name": "",
            "namespace": "",
            "alert_diagnostics": "",
            "commands_execution_results": [],
            "alert_status": "Firing",
            "report": {},
            "remediation_plan": {},
        }

        return AgentWorkflow(
            agents=[host_agent, remediate_agent, report_generator_agent],
            root_agent=host_agent.name,
            initial_state=initial_state,
        )

    def _extract_text_from_message(self, message: Message) -> str:
        """Extract text content from A2A message parts."""
        if not message or not message.parts:
            return "No diagnostics provided"

        text_parts = []
        for part in message.parts:
            if isinstance(part.root, TextPart):
                text_parts.append(part.root.text)
            elif isinstance(part, DataPart):
                text_parts.append(json.dumps(part.root.data, indent=2))

        return "\n".join(text_parts) if text_parts else "No diagnostics provided"

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute the orchestration workflow."""
        # Create TaskUpdater for proper A2A protocol lifecycle management
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        try:
            message = context.message
            logger.info("Host agent received alert diagnostics")

            # Submit task if this is a new task (not a continuation)
            if not context.current_task:
                await updater.submit()

            # Mark task as started
            await updater.start_work()

            alert_diagnostics = self._extract_text_from_message(message)

            # Create a directive prompt
            orchestration_prompt = f"""You received this alert information:
{alert_diagnostics}
Write all relevant information to the context and don't omit any important detail."""

            logger.info("Running ReActAgent autonomous workflow...")

            ctx = Context(workflow=self.agent)
            handler = self.agent.run(orchestration_prompt, ctx=ctx)

            current_agent = None
            async for event in handler.stream_events():
                if (
                    hasattr(event, "current_agent_name")
                    and event.current_agent_name != current_agent
                ):
                    current_agent = event.current_agent_name
                    logger.info(f"\n{'=' * 50}\n🤖 Agent: {current_agent}\n{'=' * 50}")
                elif isinstance(event, AgentOutput):
                    if event.response.content:
                        logger.info(f"📤 Output: {event.response.content}")
                    if event.tool_calls:
                        logger.info(
                            f"🛠️  Planning to use tools: {[call.tool_name for call in event.tool_calls]}"
                        )
                elif isinstance(event, ToolCallResult):
                    logger.info(f"🔧 Tool Result ({event.tool_name}):")
                    logger.info(f"  Arguments: {event.tool_kwargs}")
                    logger.info(f"  Output: {event.tool_output}")
                elif isinstance(event, ToolCall):
                    logger.info(f"🔨 Calling Tool: {event.tool_name}")
                    logger.info(f"  With arguments: {event.tool_kwargs}")

            logger.info("Agent workflow completed autonomously")

            state = await ctx.store.get("state")
            report = state["report"]

            if not report:
                logger.warning("Report not generated, retrying execution")
                # Create a new context with a message to continue from where it stopped
                retry_message = Message(
                    message_id=f"{context.message.message_id}_retry",
                    role=context.message.role,
                    task_id=context.task_id,
                    context_id=context.context_id,
                    parts=[
                        TextPart(
                            text="You failed to generate a report. Please continue from where you stopped and complete the report generation."
                        )
                    ],
                )
                retry_request = MessageSendParams(message=retry_message)
                retry_context = RequestContext(
                    request=retry_request,
                    task_id=context.task_id,
                    context_id=context.context_id,
                    task=context.current_task,
                )
                await self.execute(retry_context, event_queue)
                return
            # Create and send response message using TaskUpdater helper
            response_message = updater.new_agent_message(parts=[DataPart(data=report)])
            await event_queue.enqueue_event(response_message)

            # Mark task as completed
            await updater.complete()
            logger.info("Task execution completed successfully")

        except Exception as e:
            logger.error(f"Error during orchestration: {str(e)}", exc_info=True)

            # Create and send error message using TaskUpdater helper
            error_message = updater.new_agent_message(
                parts=[TextPart(text=f"# Orchestration Error\n\n{str(e)}")]
            )
            await event_queue.enqueue_event(error_message)

            # Mark task as failed
            await updater.failed()
            logger.info("Task marked as failed")

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Handle task cancellation."""
        logger.info("Received cancellation request")

        # Create TaskUpdater for proper cancellation
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()

        logger.info("Task cancelled")
