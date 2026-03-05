#!/bin/bash
# Build Python wheels for Raspberry Pi (armv6l/armv7l) using Docker
#
# This script cross-compiles Python packages for ARM on your Mac using
# Docker with QEMU emulation. The resulting wheels can be transferred
# to a Raspberry Pi for fast installation without compilation.
#
# Usage: ./scripts/build-wheels.sh [requirements-file]
#        Default: requirements.txt
#
# Output: ./dist/wheels/*.whl
#
# Requirements:
#   - Docker Desktop with ARM emulation support
#
# Example:
#   ./scripts/build-wheels.sh
#   ./scripts/build-wheels.sh requirements-dev.txt

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REQUIREMENTS_FILE="${1:-requirements.txt}"
OUTPUT_DIR="$PROJECT_DIR/dist/wheels"
DOCKER_PLATFORM="linux/arm/v7"
DOCKER_IMAGE="python:3.13-slim-bookworm"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check prerequisites
if ! command -v docker &> /dev/null; then
    echo_error "Docker is not installed. Please install Docker Desktop."
    exit 1
fi

if ! docker info &> /dev/null; then
    echo_error "Docker is not running. Please start Docker Desktop."
    exit 1
fi

if [ ! -f "$PROJECT_DIR/$REQUIREMENTS_FILE" ]; then
    echo_error "Requirements file not found: $REQUIREMENTS_FILE"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo_info "Building ARM wheels for Raspberry Pi"
echo_info "  Platform: $DOCKER_PLATFORM"
echo_info "  Image: $DOCKER_IMAGE"
echo_info "  Requirements: $REQUIREMENTS_FILE"
echo_info "  Output: $OUTPUT_DIR/"
echo ""

# Build wheels in Docker
echo_info "Starting Docker build (this may take a few minutes)..."

docker run --rm --platform "$DOCKER_PLATFORM" \
    -v "$OUTPUT_DIR:/wheels" \
    -v "$PROJECT_DIR/$REQUIREMENTS_FILE:/requirements.txt:ro" \
    "$DOCKER_IMAGE" \
    bash -c "
        set -e
        echo '>>> Installing build dependencies...'
        apt-get update -qq
        apt-get install -y -qq \
            gcc \
            pkg-config \
            libdbus-1-dev \
            libgirepository1.0-dev \
            libcairo2-dev \
            > /dev/null
        
        echo '>>> Upgrading pip...'
        pip install --upgrade pip wheel setuptools -q
        
        echo '>>> Building wheels...'
        pip wheel -w /wheels -r /requirements.txt
        
        echo '>>> Done!'
    "

# Fix permissions (Docker creates files as root)
if [ "$(uname)" = "Darwin" ]; then
    # macOS - files should already be owned by user due to Docker Desktop
    :
else
    # Linux - fix ownership
    sudo chown -R "$(id -u):$(id -g)" "$OUTPUT_DIR" 2>/dev/null || true
fi

# List built wheels
echo ""
echo_info "Built wheels:"
echo "----------------------------------------"
ls -lh "$OUTPUT_DIR"/*.whl 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
echo "----------------------------------------"
echo ""
echo_info "Wheels saved to: $OUTPUT_DIR/"
echo_info "To deploy: make deploy (or ./scripts/deploy.sh)"
