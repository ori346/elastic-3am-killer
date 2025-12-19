import logging
import os
import threading
import time
from collections import deque

import requests
from flask import Flask, jsonify, request
from prometheus_client import Counter, Gauge, Histogram, make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
MICROSERVICE_B_URL = os.environ.get("MICROSERVICE_B_URL", "http://microservice-b:8080")
PORT = int(os.environ.get("PORT", "8080"))
MAX_QUEUE_SIZE = int(os.environ.get("MAX_QUEUE_SIZE", "100"))

# Queue for messages
message_queue = deque()
queue_lock = threading.Lock()

# Define Prometheus metrics
REQUEST_COUNT = Counter(
    "queue_service_requests_total",
    "Total number of requests",
    ["method", "endpoint", "status"],
)

REQUEST_DURATION = Histogram(
    "queue_service_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"],
)

QUEUE_DEPTH = Gauge("queue_service_queue_depth", "Current depth of the message queue")

MICROSERVICE_B_LATENCY = Histogram(
    "queue_service_microservice_b_latency_seconds",
    "Latency when calling Microservice B",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

PROCESSING_ERRORS = Counter(
    "queue_service_processing_errors_total",
    "Total number of processing errors",
    ["error_type"],
)


def process_queue_worker():
    """Background worker thread that processes the queue"""
    logger.info("Queue worker thread started")

    while True:
        message = None

        with queue_lock:
            if len(message_queue) > 0:
                message = message_queue.popleft()
                QUEUE_DEPTH.set(len(message_queue))

        if message:
            try:
                logger.info(
                    f"Processing message from queue. Queue depth: {len(message_queue)}"
                )

                # Call Microservice B
                start_time = time.time()
                response = requests.post(
                    f"{MICROSERVICE_B_URL}/process", json={"data": message}, timeout=120
                )
                latency = time.time() - start_time

                MICROSERVICE_B_LATENCY.observe(latency)

                if response.status_code == 200:
                    logger.info(
                        f"Microservice B responded successfully in {latency:.2f}s"
                    )
                else:
                    logger.warning(
                        f"Microservice B returned status {response.status_code}"
                    )
                    PROCESSING_ERRORS.labels(error_type="microservice_b_error").inc()

            except requests.exceptions.Timeout:
                logger.error("Timeout calling Microservice B (exceeded 120s)")
                PROCESSING_ERRORS.labels(error_type="timeout").inc()
            except requests.exceptions.ConnectionError:
                logger.error(
                    f"Connection error calling Microservice B at {MICROSERVICE_B_URL}"
                )
                PROCESSING_ERRORS.labels(error_type="connection_error").inc()
                # Sleep a bit to avoid hammering a dead service
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                PROCESSING_ERRORS.labels(error_type="unknown").inc()
        else:
            # No messages in queue, sleep briefly
            time.sleep(0.1)


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for Kubernetes probes"""
    with queue_lock:
        queue_size = len(message_queue)

    return (
        jsonify(
            {
                "status": "healthy",
                "service": "queue-service",
                "queue_depth": queue_size,
                "timestamp": time.time(),
            }
        ),
        200,
    )


@app.route("/enqueue", methods=["POST"])
def enqueue():
    """Endpoint to enqueue a new message for processing"""
    start_time = time.time()

    try:
        # Parse request data
        data = request.get_json() or {}
        message = data.get("message", f"message_{int(time.time())}")

        with queue_lock:
            current_queue_size = len(message_queue)

            if current_queue_size >= MAX_QUEUE_SIZE:
                logger.warning(f"Queue is full ({current_queue_size}/{MAX_QUEUE_SIZE})")

                REQUEST_COUNT.labels(
                    method="POST", endpoint="/enqueue", status="503"
                ).inc()

                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Queue is full",
                            "queue_depth": current_queue_size,
                            "max_queue_size": MAX_QUEUE_SIZE,
                        }
                    ),
                    503,
                )

            # Add to queue
            message_queue.append(message)
            new_queue_size = len(message_queue)
            QUEUE_DEPTH.set(new_queue_size)

        logger.info(f"Message enqueued. Queue depth: {new_queue_size}")

        # Record metrics
        REQUEST_COUNT.labels(method="POST", endpoint="/enqueue", status="200").inc()

        duration = time.time() - start_time
        REQUEST_DURATION.labels(method="POST", endpoint="/enqueue").observe(duration)

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Message enqueued",
                    "queue_depth": new_queue_size,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Error enqueueing message: {str(e)}")

        REQUEST_COUNT.labels(method="POST", endpoint="/enqueue", status="500").inc()

        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/queue/status", methods=["GET"])
def queue_status():
    """Get current queue status"""
    with queue_lock:
        queue_size = len(message_queue)

    return (
        jsonify(
            {
                "queue_depth": queue_size,
                "max_queue_size": MAX_QUEUE_SIZE,
                "microservice_b_url": MICROSERVICE_B_URL,
            }
        ),
        200,
    )


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({"status": "error", "message": "Endpoint not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal error: {str(error)}")
    return jsonify({"status": "error", "message": "Internal server error"}), 500


# Add prometheus wsgi middleware for /metrics endpoint
app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/metrics": make_wsgi_app()})


if __name__ == "__main__":
    logger.info(f"Starting Queue Service on port {PORT}")
    logger.info(f"MICROSERVICE_B_URL: {MICROSERVICE_B_URL}")
    logger.info(f"MAX_QUEUE_SIZE: {MAX_QUEUE_SIZE}")

    # Start background queue worker thread
    worker_thread = threading.Thread(target=process_queue_worker, daemon=True)
    worker_thread.start()
    logger.info("Background queue worker started")

    # Run Flask app
    app.run(host="0.0.0.0", port=PORT, debug=False)
