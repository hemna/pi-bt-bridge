#!/bin/bash
# Pair with a Bluetooth device interactively
#
# Usage: sudo ./scripts/bt-pair.sh <MAC_ADDRESS> [PIN]
#        Default PIN: 0000
#
# This script guides you through Bluetooth pairing step by step.

set -e

MAC="${1:-}"
PIN="${2:-0000}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }
echo_step() { echo -e "${CYAN}[STEP]${NC} $1"; }

if [ -z "$MAC" ]; then
    echo "Usage: $0 <MAC_ADDRESS> [PIN]"
    echo "Example: $0 24:71:89:8D:26:EF 0000"
    echo ""
    echo "To find your device's MAC address, run:"
    echo "  bluetoothctl scan on"
    exit 1
fi

if [ "$EUID" -ne 0 ]; then
    echo_error "Please run as root: sudo $0 $MAC $PIN"
    exit 1
fi

echo ""
echo_step "Bluetooth Pairing Helper"
echo "  Device: $MAC"
echo "  PIN: $PIN"
echo ""

# Check if device exists
if ! bluetoothctl devices | grep -q "$MAC"; then
    echo_warn "Device $MAC not found in known devices."
    echo ""
    echo "Scanning for device (make sure it's in pairing mode)..."
    
    # Scan for 15 seconds
    timeout 15s bluetoothctl scan on &>/dev/null &
    SCAN_PID=$!
    
    for i in {15..1}; do
        echo -ne "\r  Scanning... $i seconds remaining "
        sleep 1
        if bluetoothctl devices | grep -q "$MAC"; then
            echo -e "\r  Device found!                    "
            break
        fi
    done
    
    kill $SCAN_PID 2>/dev/null || true
    wait $SCAN_PID 2>/dev/null || true
    
    if ! bluetoothctl devices | grep -q "$MAC"; then
        echo ""
        echo_error "Device not found. Make sure:"
        echo "  1. Device is powered on"
        echo "  2. Device is in pairing/discovery mode"
        echo "  3. Device is within range"
        exit 1
    fi
fi

# Get device name
DEVICE_NAME=$(bluetoothctl devices | grep "$MAC" | sed "s/Device $MAC //")
echo_info "Found device: $DEVICE_NAME ($MAC)"
echo ""

# Check if already paired
if bluetoothctl info "$MAC" 2>/dev/null | grep -q "Paired: yes"; then
    echo_info "Device is already paired!"
    bluetoothctl trust "$MAC" &>/dev/null
    exit 0
fi

# Make Pi discoverable (so device can initiate pairing too)
echo_step "Making Pi discoverable..."
bluetoothctl discoverable on &>/dev/null
bluetoothctl pairable on &>/dev/null

echo ""
echo_bold "=============================================="
echo_bold "  PAIRING INSTRUCTIONS"
echo_bold "=============================================="
echo ""
echo "You need to pair using the interactive bluetoothctl."
echo ""
echo "Run these commands:"
echo ""
echo "  ${CYAN}sudo bluetoothctl${NC}"
echo ""
echo "Then inside bluetoothctl:"
echo ""
echo "  ${CYAN}agent on${NC}"
echo "  ${CYAN}default-agent${NC}"
echo "  ${CYAN}pair $MAC${NC}"
echo ""
echo "When prompted for PIN, enter: ${BOLD}$PIN${NC}"
echo ""
echo "After pairing succeeds:"
echo ""
echo "  ${CYAN}trust $MAC${NC}"
echo "  ${CYAN}quit${NC}"
echo ""
echo_bold "=============================================="
echo ""
echo_warn "If pairing fails from Pi, try from your device:"
echo "  1. On your TNC/radio, go to Bluetooth settings"
echo "  2. Search for devices"
echo "  3. Select '$(hostname)' and pair"
echo "  4. Enter PIN $PIN if prompted"
echo ""

read -p "Press Enter when ready to start bluetoothctl..." _

# Start interactive bluetoothctl
exec bluetoothctl
