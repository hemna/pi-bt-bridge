#!/bin/bash
# Interactive configuration script for pi-bt-bridge
#
# This script helps users set up /etc/bt-bridge/config.json by:
# 1. Scanning for nearby Bluetooth devices
# 2. Letting the user select their TNC device
# 3. Configuring other options interactively
#
# Usage: sudo ./scripts/configure.sh
#
# Must be run on the Raspberry Pi with Bluetooth enabled.

set -e

# Configuration
CONFIG_DIR="/etc/bt-bridge"
CONFIG_FILE="$CONFIG_DIR/config.json"
EXAMPLE_CONFIG="config.example.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }
echo_step() { echo -e "${CYAN}[STEP]${NC} $1"; }
echo_bold() { echo -e "${BOLD}$1${NC}"; }

# Check if running as root (needed for /etc/bt-bridge)
check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo_error "This script must be run as root (sudo)"
        echo "  Usage: sudo $0"
        exit 1
    fi
}

# Check if Bluetooth is available
check_bluetooth() {
    if ! command -v bluetoothctl &> /dev/null; then
        echo_error "bluetoothctl not found. Please install bluez:"
        echo "  sudo apt install bluez"
        exit 1
    fi

    if ! systemctl is-active --quiet bluetooth; then
        echo_warn "Bluetooth service is not running. Starting it..."
        systemctl start bluetooth
        sleep 2
    fi

    # Check if adapter exists
    if ! hciconfig hci0 &> /dev/null; then
        echo_error "No Bluetooth adapter found (hci0)"
        exit 1
    fi
}

# Scan for Bluetooth devices
scan_devices() {
    echo_step "Scanning for Bluetooth devices..."
    echo "  Please make sure your TNC is powered on and in pairing mode."
    echo "  Scanning for 10 seconds..."
    echo ""

    # Start scan and capture devices
    local devices_file=$(mktemp)
    
    # Use timeout to limit scan duration
    timeout 10s bluetoothctl --timeout 10 scan on &> /dev/null &
    local scan_pid=$!
    
    # Show countdown
    for i in {10..1}; do
        echo -ne "\r  Scanning... $i seconds remaining "
        sleep 1
    done
    echo -e "\r  Scanning complete!              "
    
    # Wait for scan to finish
    wait $scan_pid 2>/dev/null || true
    
    # Get list of devices
    bluetoothctl devices > "$devices_file"
    
    echo "$devices_file"
}

# Display devices and let user select
select_device() {
    local devices_file="$1"
    
    echo ""
    echo_bold "Found Bluetooth devices:"
    echo "----------------------------------------"
    
    # Parse and display devices with numbers
    local i=1
    declare -a addresses
    declare -a names
    
    while IFS= read -r line; do
        if [[ "$line" =~ ^Device\ ([0-9A-Fa-f:]+)\ (.*)$ ]]; then
            local addr="${BASH_REMATCH[1]}"
            local name="${BASH_REMATCH[2]}"
            printf "  %2d) %s  %s\n" "$i" "$addr" "$name"
            addresses+=("$addr")
            names+=("$name")
            ((i++))
        fi
    done < "$devices_file"
    
    echo "----------------------------------------"
    
    if [ ${#addresses[@]} -eq 0 ]; then
        echo_warn "No devices found. Make sure your TNC is:"
        echo "  1. Powered on"
        echo "  2. In pairing/discovery mode"
        echo "  3. Within range"
        echo ""
        echo "You can enter the MAC address manually."
        echo ""
        read -p "Enter TNC MAC address (XX:XX:XX:XX:XX:XX): " TARGET_ADDRESS
        TARGET_NAME="Unknown"
        return
    fi
    
    echo ""
    echo "  0) Enter address manually"
    echo ""
    
    while true; do
        read -p "Select your TNC device [1-${#addresses[@]}]: " selection
        
        if [ "$selection" = "0" ]; then
            read -p "Enter TNC MAC address (XX:XX:XX:XX:XX:XX): " TARGET_ADDRESS
            TARGET_NAME="Unknown"
            break
        elif [[ "$selection" =~ ^[0-9]+$ ]] && [ "$selection" -ge 1 ] && [ "$selection" -le ${#addresses[@]} ]; then
            TARGET_ADDRESS="${addresses[$((selection-1))]}"
            TARGET_NAME="${names[$((selection-1))]}"
            break
        else
            echo_error "Invalid selection. Please try again."
        fi
    done
    
    # Clean up
    rm -f "$devices_file"
}

# Validate MAC address format
validate_mac() {
    local mac="$1"
    if [[ "$mac" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]]; then
        return 0
    else
        return 1
    fi
}

# Configure additional options
configure_options() {
    echo ""
    echo_bold "Additional Configuration"
    echo "----------------------------------------"
    
    # Device name
    read -p "BLE device name (shown on iPhone) [PiBTBridge]: " DEVICE_NAME
    DEVICE_NAME="${DEVICE_NAME:-PiBTBridge}"
    
    # PIN
    read -p "Bluetooth pairing PIN [0000]: " TARGET_PIN
    TARGET_PIN="${TARGET_PIN:-0000}"
    
    # Log level
    echo ""
    echo "Log levels: DEBUG, INFO, WARNING, ERROR"
    read -p "Log level [INFO]: " LOG_LEVEL
    LOG_LEVEL="${LOG_LEVEL:-INFO}"
    LOG_LEVEL="${LOG_LEVEL^^}"  # Convert to uppercase
    
    # Log file
    read -p "Log file path [/var/log/bt-bridge.log]: " LOG_FILE
    LOG_FILE="${LOG_FILE:-/var/log/bt-bridge.log}"
    
    echo "----------------------------------------"
}

# Pair with device if needed
pair_device() {
    echo ""
    echo_step "Checking pairing status..."
    
    local paired=$(bluetoothctl info "$TARGET_ADDRESS" 2>/dev/null | grep "Paired: yes" || true)
    
    if [ -n "$paired" ]; then
        echo_info "Device is already paired."
    else
        echo_warn "Device is not paired."
        read -p "Would you like to pair now? [Y/n]: " do_pair
        do_pair="${do_pair:-Y}"
        
        if [[ "$do_pair" =~ ^[Yy] ]]; then
            echo "Pairing with $TARGET_ADDRESS..."
            echo "  If prompted, confirm the PIN on your TNC."
            echo ""
            
            # Trust and pair
            bluetoothctl << EOF
agent on
default-agent
pair $TARGET_ADDRESS
trust $TARGET_ADDRESS
EOF
            
            # Verify pairing
            sleep 2
            paired=$(bluetoothctl info "$TARGET_ADDRESS" 2>/dev/null | grep "Paired: yes" || true)
            if [ -n "$paired" ]; then
                echo_info "Pairing successful!"
            else
                echo_warn "Pairing may have failed. You can retry manually with:"
                echo "  bluetoothctl pair $TARGET_ADDRESS"
            fi
        fi
    fi
}

# Generate and save config
save_config() {
    echo ""
    echo_step "Saving configuration..."
    
    # Create config directory
    mkdir -p "$CONFIG_DIR"
    
    # Generate config JSON
    cat > "$CONFIG_FILE" << EOF
{
  "target_address": "$TARGET_ADDRESS",
  "target_pin": "$TARGET_PIN",
  "device_name": "$DEVICE_NAME",
  "log_level": "$LOG_LEVEL",
  "log_file": "$LOG_FILE",
  "buffer_size": 4096,
  "reconnect_max_delay": 30,
  "status_socket": "/var/run/bt-bridge.sock"
}
EOF
    
    chmod 644 "$CONFIG_FILE"
    
    echo_info "Configuration saved to $CONFIG_FILE"
}

# Display summary
show_summary() {
    echo ""
    echo_bold "=========================================="
    echo_bold "Configuration Summary"
    echo_bold "=========================================="
    echo ""
    echo "  Target TNC:    $TARGET_ADDRESS ($TARGET_NAME)"
    echo "  Pairing PIN:   $TARGET_PIN"
    echo "  BLE Name:      $DEVICE_NAME"
    echo "  Log Level:     $LOG_LEVEL"
    echo "  Log File:      $LOG_FILE"
    echo ""
    echo "  Config File:   $CONFIG_FILE"
    echo ""
    echo_bold "=========================================="
    echo ""
    echo "Next steps:"
    echo "  1. Test the daemon:"
    echo "     cd ~/pi-bt-bridge && .venv/bin/python -m src.main"
    echo ""
    echo "  2. Install as system service:"
    echo "     sudo systemctl enable bt-bridge"
    echo "     sudo systemctl start bt-bridge"
    echo ""
    echo "  3. Connect from your iPhone to '$DEVICE_NAME'"
    echo ""
}

# Main flow
main() {
    echo ""
    echo_bold "=========================================="
    echo_bold "  Pi BT Bridge Configuration Wizard"
    echo_bold "=========================================="
    echo ""
    
    check_root
    check_bluetooth
    
    # Check for existing config
    if [ -f "$CONFIG_FILE" ]; then
        echo_warn "Existing configuration found at $CONFIG_FILE"
        read -p "Overwrite? [y/N]: " overwrite
        if [[ ! "$overwrite" =~ ^[Yy] ]]; then
            echo "Keeping existing configuration."
            exit 0
        fi
    fi
    
    # Scan and select device
    devices_file=$(scan_devices)
    select_device "$devices_file"
    
    # Validate MAC address
    if ! validate_mac "$TARGET_ADDRESS"; then
        echo_error "Invalid MAC address format: $TARGET_ADDRESS"
        echo "  Expected format: XX:XX:XX:XX:XX:XX"
        exit 1
    fi
    
    echo ""
    echo_info "Selected: $TARGET_ADDRESS ($TARGET_NAME)"
    
    # Configure options
    configure_options
    
    # Pair if needed
    pair_device
    
    # Save config
    save_config
    
    # Show summary
    show_summary
}

# Run main
main "$@"
