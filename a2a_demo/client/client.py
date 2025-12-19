import logging
import os
import signal
import time

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
MICROSERVICE_A_URL = os.environ.get("MICROSERVICE_A_URL", "http://microservice-a:8080")
REQUEST_RATE = float(os.environ.get("REQUEST_RATE", "2.0"))  # requests per second

# Global flag for graceful shutdown
running = True


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully"""
    global running
    logger.info("Shutdown signal received, stopping client...")
    running = False


def send_request(message_id):
    """Send a single request to Microservice A"""
    try:
        start_time = time.time()
        response = requests.post(
            f"{MICROSERVICE_A_URL}/enqueue",
            json={"message": f"message_{message_id}"},
            timeout=10,
        )
        duration = time.time() - start_time

        if response.status_code == 200:
            data = response.json()
            logger.info(
                f"Request #{message_id} successful (queue_depth: {data.get('queue_depth')}, {duration:.2f}s)"
            )
        elif response.status_code == 503:
            logger.warning(
                f"Request #{message_id} failed: Queue is full ({duration:.2f}s)"
            )
        else:
            logger.error(
                f"Request #{message_id} failed with status {response.status_code} ({duration:.2f}s)"
            )

    except requests.exceptions.Timeout:
        logger.error(f"Request #{message_id} timed out")
    except requests.exceptions.ConnectionError:
        logger.error(
            f"Request #{message_id} failed: Could not connect to {MICROSERVICE_A_URL}"
        )
    except Exception as e:
        logger.error(f"Request #{message_id} failed with error: {str(e)}")


def main():
    """Main client loop"""
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Starting client simulator")
    logger.info(f"Target: {MICROSERVICE_A_URL}")
    logger.info(f"Request rate: {REQUEST_RATE} requests/second")

    # Calculate sleep time between requests
    sleep_time = 1.0 / REQUEST_RATE if REQUEST_RATE > 0 else 1.0

    message_id = 0

    while running:
        message_id += 1
        send_request(message_id)

        # Sleep to maintain the desired request rate
        time.sleep(sleep_time)

    logger.info("Client simulator stopped")


if __name__ == "__main__":
    main()
