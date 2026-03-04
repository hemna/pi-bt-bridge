# Pi BT Bridge

A Bluetooth LE to Bluetooth Classic bridge daemon for Raspberry Pi, designed to connect iOS ham radio apps to Bluetooth Classic TNC devices.

## Overview

Many ham radio TNC (Terminal Node Controller) devices use Bluetooth Classic Serial Port Profile (SPP) for connectivity. However, iOS devices only support Bluetooth Low Energy (BLE), not Bluetooth Classic. This daemon bridges the gap by:

1. Advertising a BLE GATT service (Nordic UART Service) that iOS apps can connect to
2. Connecting to your TNC device over Bluetooth Classic SPP
3. Transparently forwarding KISS protocol frames bidirectionally

```
┌─────────┐      BLE/NUS      ┌──────────────┐    BT Classic/SPP    ┌─────────┐
│  iPhone │ ◄───────────────► │  Pi BT Bridge │ ◄─────────────────► │   TNC   │
│   App   │                   │    Daemon     │                      │ Device  │
└─────────┘                   └──────────────┘                      └─────────┘
```

## Hardware Requirements

- **Raspberry Pi Zero 2 W** (recommended) or any Pi with Bluetooth
- Your Bluetooth Classic TNC device (e.g., Mobilinkd TNC3, TNC4)

## Software Requirements

- Raspberry Pi OS (Bookworm or later recommended)
- Python 3.11+
- BlueZ 5.x (included with Raspberry Pi OS)

## Installation

### Quick Install (Recommended)

```bash
# Clone the repository
git clone https://github.com/youruser/pi-bt-bridge.git
cd pi-bt-bridge

# Run the install script (requires sudo)
sudo ./scripts/install.sh
```

### Manual Installation

```bash
# Install system dependencies
sudo apt update
sudo apt install -y python3-pip python3-dbus python3-gi bluetooth bluez

# Clone and install
git clone https://github.com/youruser/pi-bt-bridge.git
cd pi-bt-bridge
pip3 install -e .

# Create config directory
sudo mkdir -p /etc/bt-bridge
sudo cp config.example.json /etc/bt-bridge/config.json
```

## Configuration

Edit the configuration file at `/etc/bt-bridge/config.json`:

```json
{
  "target_address": "00:11:22:33:44:55",
  "target_pin": "0000",
  "device_name": "PiBTBridge",
  "log_level": "INFO",
  "log_file": "/var/log/bt-bridge.log",
  "buffer_size": 4096,
  "reconnect_max_delay": 30,
  "status_socket": "/var/run/bt-bridge.sock"
}
```

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `target_address` | MAC address of your TNC device (required) | - |
| `target_pin` | Bluetooth pairing PIN | `"0000"` |
| `device_name` | BLE advertised name (shown on iPhone) | `"PiBTBridge"` |
| `log_level` | Logging verbosity: DEBUG, INFO, WARNING, ERROR | `"INFO"` |
| `log_file` | Log file path, or `null` for stdout | `null` |
| `buffer_size` | Internal buffer size in bytes | `4096` |
| `reconnect_max_delay` | Max seconds between reconnection attempts | `30` |
| `status_socket` | Unix socket path for status queries | `/var/run/bt-bridge.sock` |

### Finding Your TNC's Bluetooth Address

```bash
# Make sure your TNC is in pairing mode, then scan:
bluetoothctl scan on

# Look for your device in the output, e.g.:
# [NEW] Device 00:11:22:33:44:55 Mobilinkd TNC3
```

## Usage

### Running as a Systemd Service (Recommended)

```bash
# Enable service to start on boot
sudo systemctl enable bt-bridge

# Start the service
sudo systemctl start bt-bridge

# Check status
sudo systemctl status bt-bridge

# View logs
sudo journalctl -u bt-bridge -f
```

### Running Manually

```bash
# With default config location
sudo python3 -m src.main

# With custom config file
BT_BRIDGE_CONFIG=/path/to/config.json sudo python3 -m src.main
```

### Connecting from iOS

1. Ensure the bridge daemon is running
2. On your iPhone, open your ham radio app (e.g., APRS.fi, APRSDroid via Catalyst)
3. Go to the app's Bluetooth settings
4. Look for "PiBTBridge" (or your configured `device_name`)
5. Connect - the bridge will automatically forward data to/from your TNC

## Pairing Your TNC

Before the bridge can connect to your TNC, you need to pair them:

```bash
# Start bluetoothctl
bluetoothctl

# Enable the agent
agent on
default-agent

# Scan for devices
scan on

# When you see your TNC, pair with it
pair 00:11:22:33:44:55

# Trust the device for auto-reconnect
trust 00:11:22:33:44:55

# Exit
exit
```

## Troubleshooting

### Bridge won't start

```bash
# Check if Bluetooth is enabled
sudo systemctl status bluetooth

# Ensure adapter is up
sudo hciconfig hci0 up

# Check for errors
sudo journalctl -u bt-bridge -n 50
```

### Can't connect to TNC

```bash
# Verify TNC is paired
bluetoothctl info 00:11:22:33:44:55

# Check if TNC is in range and powered on
bluetoothctl connect 00:11:22:33:44:55
```

### iPhone can't see the bridge

```bash
# Verify BLE advertising is working
sudo btmgmt info

# Check daemon logs for BLE errors
sudo journalctl -u bt-bridge | grep -i ble
```

### Connection drops frequently

- Move the Pi closer to both the iPhone and TNC
- Check for WiFi interference (2.4GHz)
- Increase `reconnect_max_delay` in config if reconnection is too aggressive

## Development

### Setting Up Development Environment

```bash
# Clone the repo
git clone https://github.com/youruser/pi-bt-bridge.git
cd pi-bt-bridge

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Run specific test categories
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m contract      # Contract tests only
```

### Code Quality

```bash
# Linting
ruff check src/ tests/

# Type checking
mypy src/

# Auto-fix lint issues
ruff check --fix src/ tests/
```

## Architecture

```
src/
├── main.py              # Daemon entry point
├── config.py            # Configuration management
├── models/
│   ├── state.py         # ConnectionState, BridgeState, ErrorEvent
│   ├── kiss.py          # KISS protocol: KISSFrame, KISSParser
│   └── connection.py    # BLEConnection, ClassicConnection
├── services/
│   ├── ble_service.py   # BLE GATT server (Nordic UART Service)
│   ├── classic_service.py  # BT Classic SPP client
│   └── bridge.py        # Bidirectional frame bridging
└── util/
    └── logging.py       # Structured logging setup
```

## Protocol Details

### BLE Service (Nordic UART Service)

- **Service UUID**: `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`
- **TX Characteristic** (write): `6E400002-B5A3-F393-E0A9-E50E24DCCA9E`
- **RX Characteristic** (notify): `6E400003-B5A3-F393-E0A9-E50E24DCCA9E`

### KISS Protocol

The bridge transparently forwards KISS frames without modification:
- Frame delimiter: `0xC0` (FEND)
- Escape character: `0xDB` (FESC)
- Escaped FEND: `0xDB 0xDC`
- Escaped FESC: `0xDB 0xDD`

## License

MIT License - See LICENSE file for details.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Ensure all tests pass and linting is clean
5. Submit a pull request

## Acknowledgments

- [bless](https://github.com/kevincar/bless) - BLE GATT server library
- [BlueZ](http://www.bluez.org/) - Linux Bluetooth stack
- Nordic Semiconductor for the UART Service specification
