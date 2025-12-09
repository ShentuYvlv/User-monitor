#!/bin/bash

# Build the docker image
echo "Building Docker image..."
docker build -t brand-monitor .

# Run the container
echo "Running Docker container..."
# -d: Detached mode
# -p: Map port 8000 to 8000
# -v: Mount static volume so images persist outside container
# --env-file: Load .env variables
docker run -d \
    --name brand-monitor-container \
    -p 8000:8000 \
    -v $(pwd)/static:/app/static \
    --env-file .env \
    --restart always \
    brand-monitor

echo "Deployment complete. API accessible at http://localhost:8000"
