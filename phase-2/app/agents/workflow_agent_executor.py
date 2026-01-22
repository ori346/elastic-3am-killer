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
from a2a.types import DataPart, Message, TextPart
from configs import WORKFLOW
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
    """A dummy agent that starts the ReAct agents."""

    def __init__(self):
        self.agent = self._create_workflow_agent()

    def _create_workflow_agent(self) -> AgentWorkflow:
        return AgentWorkflow(
            agents=[host_agent, remediate_agent, report_generator_agent],
            root_agent=host_agent.name,
            initial_state={
            "alert_name": "",
            "namespace": "",
            "alert_diagnostics": "",
            "commands_execution_results": [],
            "alert_status": "",
            "report": {},
            "remediation_plan": {},
            }
        )

    def _extract_text_from_message(self, message: Message) -> str:
        if not message or not message.parts:
            return "No diagnostics provided"

        text_parts = []
        for part in message.parts:
            if isinstance(part.root, TextPart):
                text_parts.append(part.root.text)
            elif isinstance(part.root, DataPart):
                text_parts.append(json.dumps(part.root.data, indent=2))

        return "\n".join(text_parts) if text_parts else "No diagnostics provided"

    async def _generate_execution_prompt(
        self, context: RequestContext, retry_count: int
    ) -> str:
        """Generate appropriate prompt based on whether this is a retry or initial execution."""
        if retry_count > 0:
            return "You failed to generate a report. Please continue from where you stopped and complete the report generation."
        else:
            alert_diagnostics = self._extract_text_from_message(context.message)
            return f"""You received this alert information:
{alert_diagnostics}
Write all relevant information to the context and don't omit any important detail."""

    async def _execute_workflow_with_streaming(self, prompt: str) -> dict:
        """Execute a single workflow attempt with event streaming and return final state.
        This method does not handle retries - it performs one execution attempt only."""
        logger.info("Running ReActAgent autonomous workflow...")

        ctx = Context(workflow=self.agent)
        handler = self.agent.run(prompt, ctx=ctx)

        current_agent = None
        async for event in handler.stream_events():
            current_agent = await self._process_workflow_event(event, current_agent)

        logger.info("Agent workflow completed autonomously")

        state = await ctx.store.get("state")
        return state

    async def _process_workflow_event(self, event, current_agent: str) -> str:
        """Process individual workflow events and log appropriately."""
        if (
            hasattr(event, "current_agent_name")
            and event.current_agent_name != current_agent
        ):
            current_agent = event.current_agent_name
            logger.info(f"\n{'=' * 50}\n🤖 Agent: {current_agent}\n{'=' * 50}")

        elif isinstance(event, AgentOutput):
            if event.response.content:
                logger.info(f"📤 Output: {event.response.content}")
            # if event.tool_calls:
            #     logger.info(f"🛠️  Planning to use tools: {[call.tool_name for call in event.tool_calls]}")

        elif isinstance(event, ToolCallResult):
            logger.info(f"🔧 Tool Result ({event.tool_name}):")
            logger.info(f"  Arguments: {event.tool_kwargs}")
            logger.info(f"  Output: {event.tool_output}")

        elif isinstance(event, ToolCall):
            logger.info(f"🔨 Calling Tool: {event.tool_name}")
            # logger.info(f"  With arguments: {event.tool_kwargs}")

        return current_agent

    async def _handle_execution_success(
        self, report: dict, event_queue: EventQueue, updater: TaskUpdater
    ) -> None:
        """Handle successful workflow completion by sending report and marking task complete."""
        response_message = updater.new_agent_message(parts=[DataPart(data=report)])
        await event_queue.enqueue_event(response_message)
        await updater.complete()
        logger.info("Task execution completed successfully")

    async def _handle_retry_exhaustion(
        self, retry_count: int, event_queue: EventQueue, updater: TaskUpdater
    ) -> None:
        """Handle failure after exhausting all retry attempts."""
        logger.error(
            f"Report generation failed after {retry_count + 1} attempts, exceeding max_retries ({WORKFLOW.max_retries})"
        )

        error_message = updater.new_agent_message(
            parts=[
                TextPart(
                    text="# Remediation process failed\n The workflow was unable to complete the report generation. Please continue from where you stop and finsish the remediation process."
                )
            ]
        )
        await event_queue.enqueue_event(error_message)
        await updater.failed()

    async def _handle_execution_exception(
        self, exception: Exception, event_queue: EventQueue, updater: TaskUpdater
    ) -> None:
        """Handle unexpected exceptions during orchestration."""
        logger.error(f"Error during orchestration: {str(exception)}", exc_info=True)

        error_message = updater.new_agent_message(
            parts=[TextPart(text=f"# Orchestration Error\n\n{str(exception)}")]
        )
        await event_queue.enqueue_event(error_message)
        await updater.failed()
        logger.info("Task marked as failed")

    async def _execute_with_retry_tracking(
        self, context: RequestContext, event_queue: EventQueue, updater: TaskUpdater
    ) -> None:
        """Execute workflow with iterative retry tracking."""
        current_retry = 0

        while current_retry <= WORKFLOW.max_retries:
            if current_retry > 0:
                logger.info(
                    f"Retrying workflow execution (attempt {current_retry + 1}/{WORKFLOW.max_retries + 1})"
                )

            prompt = await self._generate_execution_prompt(context, current_retry)
            state = await self._execute_workflow_with_streaming(prompt)
            report = state["report"]

            if report:
                await self._handle_execution_success(report, event_queue, updater)
                return

            current_retry += 1

        await self._handle_retry_exhaustion(current_retry - 1, event_queue, updater)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute the orchestration workflow."""
        # Create TaskUpdater for proper A2A protocol lifecycle management
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        try:
            logger.info("Host agent received alert diagnostics")

            # Submit task if this is a new task (not a continuation)
            if not context.current_task:
                await updater.submit()

            # Mark task as started
            await updater.start_work()

            # Execute the workflow with retry tracking
            await self._execute_with_retry_tracking(context, event_queue, updater)

        except Exception as e:
            await self._handle_execution_exception(e, event_queue, updater)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Handle task cancellation."""
        logger.info("Received cancellation request")

        # Create TaskUpdater for proper cancellation
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()

        logger.info("Task cancelled")
