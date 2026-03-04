# Quickstart: Bluetooth LE to Classic Bridge

**Feature**: 001-bt-bridge-daemon  
**Target**: Raspberry Pi Zero 2 W with Raspberry Pi OS (Bookworm)

## Prerequisites

### Hardware

- Raspberry Pi Zero 2 W (with built-in Bluetooth)
- Power supply (5V 2.5A recommended)
- SD card with Raspberry Pi OS Lite (Bookworm)

### Software

- Python 3.11+
- BlueZ 5.55+
- Bluetooth-enabled TNC (e.g., Mobilinkd TNC3, Kenwood TH-D74)
- iPhone with BLE-capable packet radio app

## Installation

### 1. System Dependencies

```bash
sudo apt update
sudo apt install -y \
    python3-pip \
    python3-venv \
    python3-dbus \
    python3-gi \
    bluez \
    bluez-tools
```

### 2. Verify Bluetooth

```bash
# Check BlueZ version (need 5.55+)
bluetoothctl --version

# Verify adapter is present
hciconfig hci0

# Should show: UP RUNNING PSCAN
```

### 3. Clone and Setup

```bash
# Clone repository
git clone https://github.com/youruser/pi-bt-bridge.git
cd pi-bt-bridge

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 4. Configure

```bash
# Create config directory
sudo mkdir -p /etc/bt-bridge

# Copy example config
sudo cp config.example.json /etc/bt-bridge/config.json

# Edit configuration
sudo nano /etc/bt-bridge/config.json
```

**Minimum configuration**:

```json
{
    "target_address": "00:11:22:33:44:55",
    "device_name": "PiBTBridge"
}
```

Replace `00:11:22:33:44:55` with your TNC's Bluetooth address.

### 5. Find TNC Address

```bash
# Make TNC discoverable, then scan
bluetoothctl scan on

# Look for your TNC name, note the address
# Example: [NEW] Device 00:11:22:33:44:55 Mobilinkd TNC3

# Stop scanning
bluetoothctl scan off
```

## Running the Bridge

### Manual Start (Development)

```bash
cd pi-bt-bridge
source venv/bin/activate
python -m src.main
```

Expected output:

```
2026-03-04 12:00:00 INFO Starting BT Bridge daemon...
2026-03-04 12:00:00 INFO BLE: Advertising as 'PiBTBridge'
2026-03-04 12:00:01 INFO Classic: Connecting to 00:11:22:33:44:55...
2026-03-04 12:00:03 INFO Classic: Connected to Mobilinkd TNC3
2026-03-04 12:00:03 INFO Bridge ready. Waiting for BLE connection...
```

### Systemd Service (Production)

```bash
# Install service
sudo cp systemd/bt-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable auto-start
sudo systemctl enable bt-bridge

# Start now
sudo systemctl start bt-bridge

# Check status
sudo systemctl status bt-bridge
```

## Connecting

### From iPhone

1. Open your BLE-compatible packet radio app
2. Scan for Bluetooth devices
3. Select "PiBTBridge" (or your configured name)
4. Wait for connection (LED/status indicator)
5. App should show connected state

### Verify Bridge

```bash
# Check status via socket
echo '{"cmd":"status"}' | nc -U /var/run/bt-bridge.sock

# Expected response:
# {"ble_state":"connected","classic_state":"connected","frames_bridged":0}
```

## Testing the Bridge

### Send Test Frame

From your iPhone app, send a beacon or test packet. You should see:

```
2026-03-04 12:05:00 INFO Frame bridged: BLE→Classic, 45 bytes
```

### Monitor Logs

```bash
# Follow daemon logs
sudo journalctl -u bt-bridge -f
```

## Troubleshooting

### BLE Not Advertising

```bash
# Check Bluetooth status
sudo systemctl status bluetooth

# Restart Bluetooth
sudo systemctl restart bluetooth

# Verify adapter mode
sudo hciconfig hci0 piscan  # Make discoverable
```

### Classic Connection Fails

```bash
# Verify TNC is powered and discoverable
bluetoothctl
> scan on
# Wait for TNC to appear
> scan off

# Try manual pair
> pair 00:11:22:33:44:55
> trust 00:11:22:33:44:55
```

### Permission Denied

```bash
# Add user to bluetooth group
sudo usermod -aG bluetooth $USER

# Or run as root (for systemd)
sudo systemctl restart bt-bridge
```

### Check Logs for Errors

```bash
# View recent logs
sudo journalctl -u bt-bridge --since "5 minutes ago"

# Check for BlueZ errors
sudo journalctl -u bluetooth --since "5 minutes ago"
```

## Configuration Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `target_address` | string | **required** | TNC Bluetooth MAC address |
| `target_pin` | string | "0000" | Pairing PIN |
| `device_name` | string | "PiBTBridge" | Advertised BLE name |
| `log_level` | string | "INFO" | DEBUG, INFO, WARNING, ERROR |
| `log_file` | string | null | Log file path (null=stdout) |
| `buffer_size` | int | 4096 | Queue buffer size (bytes) |
| `reconnect_max_delay` | int | 30 | Max reconnect wait (seconds) |
| `status_socket` | string | "/var/run/bt-bridge.sock" | Unix socket for status |

## Verification Checklist

- [ ] `bluetoothctl --version` shows 5.55+
- [ ] `hciconfig hci0` shows UP RUNNING
- [ ] TNC appears in `bluetoothctl scan`
- [ ] Config file has correct `target_address`
- [ ] `systemctl status bt-bridge` shows active
- [ ] iPhone can discover "PiBTBridge"
- [ ] iPhone can connect to bridge
- [ ] Test packet flows through bridge

## Next Steps

1. Configure your packet radio app for the bridge connection
2. Set up auto-reconnect in your app preferences
3. Consider adding monitoring/alerting for the daemon
4. Review logs periodically for connection issues
