# Base Image: Use python 3.11 slim variant to minimize build sizes and optimize cold-start 
# scaling when executing as stateless containers inside Google Cloud Run Jobs.
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python libraries
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy workspace directories: Keep code, target files, and unit test suites isolated 
# inside the container, providing the test runner with a self-contained execution context.
COPY workflows/ ./workflows/
COPY targets/ ./targets/
COPY tests/ ./tests/
COPY run_experiments.py .

# Set default execution command
ENTRYPOINT ["python", "run_experiments.py"]

