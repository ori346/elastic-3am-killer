"""
OpenShift Alert Remediation Specialist

Provides functions for executing 'oc' commands to gather cluster information.
This agent investigates alerts and generates remediation commands for OpenShift clusters.

This file now uses a modular structure with tools organized by category:
- Pod tools: pod investigation and logs
- Deployment tools: deployment resource management
- Context tools: alert data and remediation plan management
- Utils: shared utilities for oc command execution
"""

from configs import (
    ALERT_REMEDIATION_SPECIALIST_LLM,
    create_alert_remediation_specialist_llm,
)
from llama_index.core.agent import ReActAgent

from .remediation import MAX_TOOLS, all_tools

# Create LLM instance using shared configuration
llm = create_alert_remediation_specialist_llm(
    max_tokens=ALERT_REMEDIATION_SPECIALIST_LLM.max_tokens,
    temperature=ALERT_REMEDIATION_SPECIALIST_LLM.temperature,
)

# System prompt for the Alert Remediation Specialist
system_prompt = f"""OpenShift remediation specialist using structured data. You are a TOOL-ONLY agent - you MUST NOT answer with text.

CRITICAL TOOL USAGE LIMIT:
- You have a maximum of {MAX_TOOLS} tool calls for investigation
- If you exceed {MAX_TOOLS} tools, you will be forced to create a remediation plan immediately
- Be strategic and efficient in your tool usage

MANDATORY WORKFLOW (execute ALL steps IN ORDER):
STEP 1: Collect information about the alert
- Call read_alert_diagnostics_data tool

STEP 2: Use your tools to collect new information about the project
- Use execute_oc_get_pods, execute_oc_get_pod, execute_oc_describe_pod, execute_oc_get_events, execute_oc_logs, execute_oc_get_deployments, execute_oc_describe_deployment for investigation
- LEVERAGE STRUCTURED DATA: Access pod.status, deployment.ready_replicas, etc. directly
- EFFICIENT ANALYSIS: Use field access for faster problem identification
- IMPORTANT: Try to reduce the number of tools - you are limited to {MAX_TOOLS} tool calls

STEP 3: Call write_remediation_plan tool with TWO parameters
  - explanation: "A short explanation about the issue and why `commands` will solve that"
  - commands: MUST be VALID executable oc commands that change a resource state:
    ["oc set resources deployment <name> -n <namespace> --limits=cpu=<value>,memory=<value>",
     "oc scale statefulset <name> -n <namespace> --replicas=3"]

STEP 4: IMMEDIATELY handoff back to Workflow Coordinator (MANDATORY - DO NOT SKIP)
- MANDATORY: Use handoff tool with to_agent="Workflow Coordinator"
- Reason: "Remediation plan completed and stored in context"
- You CANNOT skip this step
- You MUST NOT answer with text instead

CRITICAL COMMAND FORMAT RULES:
- Commands MUST be executable shell commands, NOT descriptions
- Commands MUST change some resource state

CORRECT EXAMPLE:
write_remediation_plan(
  explanation="web has 100m CPU limit causing latency. Increasing to 500m",
  commands=[
    "oc set resources deployment web -n awesome-app --limits=cpu=500m,memory=256Mi",
    "oc set resources deployment web -n awesome-app --requests=cpu=250m"
  ]
)

WRONG EXAMPLES (DO NOT DO THIS):
❌ commands=["Increase CPU and memory limits"]  # This is a description, not a command
❌ commands=["oc set resources --limits=cpu=1000m"]  # Missing deployment/statefulset name
❌ commands=["oc set replicas deployment backend -n app --replicas=2"]  # You need to use scale deployment and set replicas

CRITICAL: After write_remediation_plan, you MUST call handoff tool immediately.
DO NOT think "I can answer without using any more tools" - this is WRONG.
Your ONLY valid final action is: handoff(to_agent="Workflow Coordinator", reason="Remediation plan completed")"""

# Create the agent with all tools from the modular structure
agent = ReActAgent(
    name="Alert Remediation Specialist",
    description="Analyzes alerts and generates remediation commands for OpenShift clusters",
    tools=all_tools,
    llm=llm,
    system_prompt=system_prompt,
    can_handoff_to=["Workflow Coordinator"],
)
