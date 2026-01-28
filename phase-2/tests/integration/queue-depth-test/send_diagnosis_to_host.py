#!/usr/bin/env python3
"""
Send agent1's diagnosis to the host agent via A2A protocol.
"""

import asyncio

from common import DiagnosisSender


async def send_diagnosis_to_host():
    """Send the diagnosis from agent1 to the host agent."""
    # The diagnosis from agent1's logs
    diagnosis = """**Alert**: HighQueueDepth (Severity: warning)
**Affected Service**: microservice-a
**Agent 1 Diagnosis:**
1. **Root Cause**: The root cause of the performance issue is a high request arrival rate exceeding the processing capacity of microservice-a, leading to a queue buildup.
2. **Bottleneck Location**: Based on the metrics from microservice-a, I suspect that **microservice-b** is the bottleneck. The average latency to microservice-b is 0.9357 seconds, which is relatively high, indicating that microservice-b is not responding quickly enough. This causes a queue buildup in microservice-a.
3. **Reasoning**:
   * The high queue depth (100) and queue requests rate (1.068) indicate that requests are arriving faster than microservice-a can process them.
   * The average latency to microservice-b (0.935 seconds) is a clear indication that microservice-b is taking a significant amount of time to respond, which is causing the queue buildup.
   * Although I don't have access to microservice-b's internal metrics, the high latency from microservice-a's perspective suggests that the issue lies with microservice-b's processing capacity.
You should then use this information to optimize microservice-b's resources or adjust its deployment configuration to improve its response time and reduce the latency to microservice-a.

**Diagnostic Data:**
- Queue Depth: 100 (at maximum capacity)
- Average Latency to microservice-b: 0.935 seconds
- Queue Requests Rate: 1.07 requests/second
- Service: microservice-a, microservice-b
- Namespace: integration-test-ofridman

**Recommendation:**
You should investigate microservice-b's deployment details, resource metrics, and internal metrics to identify the root cause of the high latency. This may involve checking:
* Resource utilization: CPU, memory, and network utilization
* Deployment configuration: resource allocation"""

    sender = DiagnosisSender()
    await sender.send_diagnosis(diagnosis)


if __name__ == "__main__":
    asyncio.run(send_diagnosis_to_host())
