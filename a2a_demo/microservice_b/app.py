import logging
import os
import time

from flask import Flask, jsonify
from prometheus_client import Counter, Gauge, Histogram, Info, make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
PROCESSING_DELAY = float(os.environ.get("PROCESSING_DELAY", "0.1"))
PORT = int(os.environ.get("PORT", "8080"))

# Define Prometheus metrics
REQUEST_COUNT = Counter(
    "processing_service_requests_total",
    "Total number of requests",
    ["method", "endpoint", "status"],
)

REQUEST_DURATION = Histogram(
    "processing_service_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"],
)

PROCESSING_TIME = Histogram(
    "processing_service_processing_duration_seconds",
    "Time spent in CPU processing",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

CPU_USAGE_APPROXIMATION = Gauge(
    "processing_service_cpu_usage_approximate",
    "Approximate CPU usage based on processing time",
)

ACTIVE_REQUESTS = Gauge(
    "processing_service_active_requests", "Number of currently active requests"
)

SERVICE_INFO = Info("processing_service_info", "Processing service information")

# Set service info
SERVICE_INFO.info({"version": "1.0.0"})


def check_prime(n):
    """Check if a number is prime - CPU intensive for larger numbers"""
    if n < 2:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True


def simulate_cpu_work():
    """
    Simulates CPU-intensive work by counting primes from 3 to 30000.
    This is genuinely CPU-bound work.
    """
    start_time = time.time()
    prime_count = 0

    # Count all prime numbers from 3 to 30000
    for n in range(3, 30001):
        if check_prime(n):
            prime_count += 1

    duration = time.time() - start_time
    return prime_count, duration


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for Kubernetes probes"""
    return (
        jsonify(
            {
                "status": "healthy",
                "service": "processing-service",
                "timestamp": time.time(),
            }
        ),
        200,
    )


@app.route("/process", methods=["POST"])
def process():
    """Main processing endpoint that simulates CPU-intensive work"""
    ACTIVE_REQUESTS.inc()
    start_time = time.time()

    try:
        logger.info("Processing request - counting primes from 3 to 30000")

        # Add configurable delay before CPU work
        if PROCESSING_DELAY > 0:
            time.sleep(PROCESSING_DELAY)

        # Simulate CPU-intensive work by counting primes
        prime_count, cpu_duration = simulate_cpu_work()

        # Update processing metrics
        PROCESSING_TIME.observe(cpu_duration)

        # Calculate approximate CPU usage (processing_time / wall_time * 100)
        cpu_approx = (cpu_duration / (cpu_duration + 0.001)) * 100
        CPU_USAGE_APPROXIMATION.set(cpu_approx)

        # Prepare response
        response = {
            "status": "success",
            "message": "Processing completed",
            "processing_time": cpu_duration,
            "prime_count": prime_count,
            "delay": PROCESSING_DELAY,
        }

        # Record metrics
        REQUEST_COUNT.labels(method="POST", endpoint="/process", status="200").inc()

        duration = time.time() - start_time
        REQUEST_DURATION.labels(method="POST", endpoint="/process").observe(duration)

        logger.info(f"Request completed in {duration:.2f}s")

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")

        REQUEST_COUNT.labels(method="POST", endpoint="/process", status="500").inc()

        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        ACTIVE_REQUESTS.dec()


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
    logger.info(f"Starting Processing Service on port {PORT}")
    logger.info(f"PROCESSING_DELAY: {PROCESSING_DELAY}s")

    # Run Flask app
    # In production, use gunicorn instead
    app.run(host="0.0.0.0", port=PORT, debug=False)
