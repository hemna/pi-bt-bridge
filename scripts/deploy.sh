#!/bin/bash
# Deploy pi-bt-bridge to Raspberry Pi
#
# This script syncs the project to a Raspberry Pi, sets up a virtual
# environment with system-site-packages (to use system dbus/gi), and
# installs the project in editable mode.
#
# Usage: ./scripts/deploy.sh [user@host]
#        Default: waboring@pi-sugar.hemna.com
#
# Environment variables:
#   PI_HOST - Override default Pi host
#   PI_DIR  - Override project directory (default: ~/pi-bt-bridge)
#
# Examples:
#   ./scripts/deploy.sh
#   ./scripts/deploy.sh pi@raspberrypi.local
#   PI_HOST=pi@mypi.local ./scripts/deploy.sh

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DEFAULT_HOST="waboring@pi-sugar.hemna.com"
PI_HOST="${1:-${PI_HOST:-$DEFAULT_HOST}}"
PI_DIR="${PI_DIR:-~/pi-bt-bridge}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }
echo_step() { echo -e "${CYAN}[STEP]${NC} $1"; }

echo_info "Deploying pi-bt-bridge to $PI_HOST:$PI_DIR"
echo ""

# Step 1: Sync project files
echo_step "1/4 Syncing project files..."

rsync -avz --delete \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    --exclude='.mypy_cache/' \
    --exclude='.ruff_cache/' \
    --exclude='*.egg-info/' \
    --exclude='.opencode/' \
    --exclude='.specify/' \
    "$PROJECT_DIR/" "$PI_HOST:$PI_DIR/"

echo ""

# Step 2: Setup venv and install dependencies
echo_step "2/4 Setting up virtual environment..."

ssh "$PI_HOST" bash << 'REMOTE_SCRIPT'
set -e
cd ~/pi-bt-bridge

# Create venv with system-site-packages if pip is missing
if [ ! -f .venv/bin/pip ]; then
    echo "Creating virtual environment with --system-site-packages..."
    python3 -m venv --system-site-packages .venv
fi

# Upgrade pip
echo "Upgrading pip..."
.venv/bin/python -m pip install --upgrade pip -q

# Install dependencies
echo "Installing dependencies..."
if [ -d "dist/wheels" ] && ls dist/wheels/*.whl 1> /dev/null 2>&1; then
    echo "  Using local wheels from dist/wheels/"
    .venv/bin/pip install --no-index --find-links=dist/wheels/ -r requirements.txt -q
else
    echo "  Using piwheels/PyPI..."
    .venv/bin/pip install -r requirements.txt -q
fi

# Install project in editable mode
echo "Installing project in editable mode..."
.venv/bin/pip install -e . -q

echo "Virtual environment ready!"
REMOTE_SCRIPT

echo ""

# Step 3: Setup config file
echo_step "3/4 Setting up configuration..."

ssh "$PI_HOST" bash << 'REMOTE_SCRIPT'
set -e
cd ~/pi-bt-bridge

# Create config directory and file if missing
if [ ! -f /etc/bt-bridge/config.json ]; then
    echo "Creating /etc/bt-bridge/config.json..."
    sudo mkdir -p /etc/bt-bridge
    sudo cp config.example.json /etc/bt-bridge/config.json
    sudo chmod 644 /etc/bt-bridge/config.json
    echo "  Config created - edit with your TNC's Bluetooth address!"
else
    echo "  Config already exists at /etc/bt-bridge/config.json"
fi
REMOTE_SCRIPT

echo ""

# Step 4: Show status
echo_step "4/4 Verifying installation..."

ssh "$PI_HOST" bash << 'REMOTE_SCRIPT'
set -e
cd ~/pi-bt-bridge

echo "Installed packages:"
.venv/bin/pip list | grep -E '^(bless|dbus-python|PyGObject|pi-bt-bridge)' | sed 's/^/  /'

echo ""
echo "Python version:"
.venv/bin/python --version | sed 's/^/  /'
REMOTE_SCRIPT

echo ""
echo_info "=========================================="
echo_info "Deployment complete!"
echo_info "=========================================="
echo ""
echo "Next steps:"
echo "  1. Edit config with your TNC address:"
echo "     ssh $PI_HOST 'sudo nano /etc/bt-bridge/config.json'"
echo ""
echo "  2. Test the daemon:"
echo "     ssh $PI_HOST 'cd $PI_DIR && .venv/bin/python -m src.main'"
echo ""
echo "  3. Install systemd service (optional):"
echo "     ssh $PI_HOST 'cd $PI_DIR && sudo ./scripts/install.sh'"
echo ""
