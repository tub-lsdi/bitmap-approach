#!/bin/bash

CONTAINER_NAME="cs-jp-lp-benchmark"
LOCAL_RESULTS_DIR="./data/bench_results"

echo "Copying benchmark results from Docker container..."
echo "Container: $CONTAINER_NAME"
echo "Destination: $LOCAL_RESULTS_DIR"
echo ""

# Check if container exists
if ! docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Error: Container '$CONTAINER_NAME' not found."
    echo "Make sure you've run 'docker-compose up' first."
    exit 1
fi

# Create local results directory if it doesn't exist
mkdir -p "$LOCAL_RESULTS_DIR"

# Copy results from container
echo "Copying files..."
docker cp "${CONTAINER_NAME}:/app/data/bench_results/." "$LOCAL_RESULTS_DIR/"

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Successfully copied results to $LOCAL_RESULTS_DIR"
    echo ""
    echo "Files copied:"
    ls -lh "$LOCAL_RESULTS_DIR"
else
    echo ""
    echo "✗ Error copying files from container"
    exit 1
