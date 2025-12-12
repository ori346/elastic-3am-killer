# Multi-stage build for smaller final image
FROM python:3.11-slim as builder

WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir --user -r requirements.txt


# Final stage
FROM python:3.11-slim

# Create application directory with broad permissions for OpenShift
RUN mkdir -p /app && \
    chmod -R 777 /app

WORKDIR /app

# Copy Python dependencies to a location accessible by any user
COPY --from=builder /root/.local /opt/app-root

# Copy application code
COPY app.py /app/

# Set permissions so any user can read and execute
RUN chmod -R 775 /app && \
    chmod -R 775 /opt/app-root

# Add local bin to PATH for installed packages (OpenShift compatible)
ENV PATH=/opt/app-root/bin:$PATH
ENV PYTHONPATH=/opt/app-root/lib/python3.11/site-packages
ENV HOME=/tmp

# Set Python to run in unbuffered mode (better for logging)
ENV PYTHONUNBUFFERED=1

# Default environment variables
ENV PORT=8080
ENV PROCESSING_DELAY=1.0

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Labels for metadata
LABEL maintainer="demo@example.com"
LABEL description="Processing Service - Microservice B for OpenShift Demo"
LABEL version="1.0.0"

# Run the application
CMD ["python", "-u", "app.py"]
