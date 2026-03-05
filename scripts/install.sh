#!/bin/bash
# Installation script for BT Bridge daemon
set -e

INSTALL_DIR="/opt/bt-bridge"
CONFIG_DIR="/etc/bt-bridge"
SERVICE_FILE="/etc/systemd/system/bt-bridge.service"
BT_UNBLOCK_SERVICE="/etc/systemd/system/bluetooth-unblock.service"

echo "Installing BT Bridge daemon..."

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"

# Copy source files
cp -r src "$INSTALL_DIR/"
cp pyproject.toml "$INSTALL_DIR/"

# Install Python dependencies
cd "$INSTALL_DIR"
python3 -m pip install -e .

# Copy example config if no config exists
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    if [ -f config.example.json ]; then
        cp config.example.json "$CONFIG_DIR/config.json"
        echo "Created default config at $CONFIG_DIR/config.json"
        echo "Please edit this file with your TNC's Bluetooth address!"
    fi
fi

# Install Bluetooth unblock service (fixes RF-kill on boot)
if [ -f systemd/bluetooth-unblock.service ]; then
    cp systemd/bluetooth-unblock.service "$BT_UNBLOCK_SERVICE"
    systemctl enable bluetooth-unblock.service
    echo "Installed bluetooth-unblock service"
fi

# Install main systemd service
cp systemd/bt-bridge.service "$SERVICE_FILE"
systemctl daemon-reload

echo ""
echo "Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Edit $CONFIG_DIR/config.json with your TNC's Bluetooth address"
echo "  2. Enable the service: sudo systemctl enable bt-bridge"
echo "  3. Start the service: sudo systemctl start bt-bridge"
echo "  4. Check status: sudo systemctl status bt-bridge"
