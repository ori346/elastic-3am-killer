#!/usr/bin/env python3
"""
Send agent1's diagnosis to the host agent via A2A protocol.
"""

import asyncio

from common import DiagnosisSender


async def send_diagnosis_to_host():
    """Send the diagnosis from agent1 to the host agent."""
    # Create JSON diagnosis data
    diagnosis = {
        "incident_id": "cXVldWUtZGVwdGgtdGVzdC0wMDE=",  # base64 encoded: queue-depth-test-001
        "namespace": "integration-test-ofridman",
        "alert": {
            "name": "HighQueueDepth",
            "severity": "warning",
            "service": "microservice-a",
            "description": "microservice-a's queue depth has exceeded maximum capacity",
        },
        "diagnostics_suggestions": """Root Cause: The root cause of the performance issue is a high request arrival rate exceeding the processing capacity of microservice-a, leading to a queue buildup.

Bottleneck Location: Based on the metrics from microservice-a, microservice-b appears to be the bottleneck. The average latency to microservice-b is 0.9357 seconds, which is relatively high, indicating that microservice-b is not responding quickly enough.

Reasoning:
* The high queue depth (100) and queue requests rate (1.068) indicate that requests are arriving faster than microservice-a can process them.
* The average latency to microservice-b (0.935 seconds) is a clear indication that microservice-b is taking a significant amount of time to respond.

Recommendation: Investigate microservice-b's deployment details, resource metrics, and internal metrics to identify the root cause of the high latency. This may involve checking resource utilization (CPU, memory, network) and deployment configuration.""",
        "message_type": "remediation_request",
        "logs": [
            "2026-02-09 10:33:47,983 - __main__ - INFO - Microservice B responded successfully in 0.90s",
            "2026-02-09 10:33:47,983 - __main__ - INFO - Processing message from queue. Queue depth: 99",
            "2026-02-09 10:33:48,176 - __main__ - INFO - Message enqueued. Queue depth: 100",
            '2026-02-09 10:33:48,177 - werkzeug - INFO - 10.129.4.186 - - [09/Feb/2026 10:33:48] "POST /enqueue HTTP/1.1" 200 -',
            "2026-02-09 10:33:48,679 - __main__ - WARNING - Queue is full (100/100)",
            '2026-02-09 10:33:48,680 - werkzeug - INFO - 10.129.4.186 - - [09/Feb/2026 10:33:48] "POST /enqueue HTTP/1.1" 503 -',
            "2026-02-09 10:33:48,882 - __main__ - INFO - Microservice B responded successfully in 0.90s",
            "2026-02-09 10:33:48,883 - __main__ - INFO - Processing message from queue. Queue depth: 99",
            "2026-02-09 10:33:49,182 - __main__ - INFO - Message enqueued. Queue depth: 100",
            '2026-02-09 10:33:49,183 - werkzeug - INFO - 10.129.4.186 - - [09/Feb/2026 10:33:49] "POST /enqueue HTTP/1.1" 200 -',
            "2026-02-09 10:33:49,685 - __main__ - WARNING - Queue is full (100/100)",
            '2026-02-09 10:33:49,686 - werkzeug - INFO - 10.129.4.186 - - [09/Feb/2026 10:33:49] "POST /enqueue HTTP/1.1" 503 -',
        ],
    }

    sender = DiagnosisSender()
    await sender.send_diagnosis_json(diagnosis)


if __name__ == "__main__":
    asyncio.run(send_diagnosis_to_host())
