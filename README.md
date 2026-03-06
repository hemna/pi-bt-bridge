# Pi BT Bridge

A Bluetooth LE to Bluetooth Classic bridge daemon for Raspberry Pi Zero 2 W, designed to connect iOS ham radio apps to Bluetooth Classic TNC devices.

## Overview

Many ham radio TNC (Terminal Node Controller) devices use Bluetooth Classic Serial Port Profile (SPP) for connectivity. However, iOS devices only support Bluetooth Low Energy (BLE), not Bluetooth Classic. This daemon bridges the gap by:

1. Advertising a BLE GATT service (Nordic UART Service) that iOS apps can connect to
2. Connecting to your TNC device over Bluetooth Classic SPP
3. Transparently forwarding KISS protocol frames bidirectionally

```
┌─────────┐      BLE/NUS      ┌──────────────┐    BT Classic/SPP    ┌─────────┐
│  iPhone │ ◄───────────────► │  Raspberry   │ ◄─────────────────► │   TNC   │
│   App   │                   │   Pi Zero    │                      │ Device  │
└─────────┘                   └──────────────┘                      └─────────┘
```

**Features:**

- Web interface for configuration, pairing, and monitoring
- Auto-reconnection with exponential backoff
- Real-time status via Server-Sent Events (SSE)
- Systemd service for automatic startup

## Hardware Requirements

- **Raspberry Pi Zero 2 W** (recommended) or any Pi with Bluetooth
- Your Bluetooth Classic TNC device (e.g., Mobilinkd TNC3/TNC4, Kenwood TH-D74)

## Software Requirements

- Raspberry Pi OS (Bookworm or later recommended)
- Python 3.11+
- BlueZ 5.x (included with Raspberry Pi OS)

## Quick Start

### 1. Install

```bash
git clone https://github.com/hemna/pi-bt-bridge.git
cd pi-bt-bridge
sudo ./scripts/install.sh
```

### 2. Access Web Interface

Open a browser and navigate to:

```
http://<pi-ip-address>:8080
```

### 3. Pair Your TNC

1. Go to the **Pairing** page
2. Click "Scan for Devices"
3. Select your TNC and click "Pair"
4. Enter PIN if prompted (usually `0000`)
5. Click "Use as TNC" to set as target

### 4. Connect from iOS

1. Open your ham radio app (e.g., APRS.fi)
2. Go to Bluetooth settings
3. Connect to "PiBTBridge"

See [Installation Guide](docs/installation.md) for detailed instructions.

## Web Interface

Pi BT Bridge includes a built-in web interface for easy management.

![Status Page](docs/screenshots/status.png)

| Page | Description |
|------|-------------|
| **Status** | Real-time connection status and bridge info |
| **Pairing** | Scan for and pair with Bluetooth devices |
| **Settings** | Configure device name, target TNC, logging |
| **Statistics** | View packet counts and throughput |

See [Web Interface Guide](docs/web-interface.md) for details.

## Configuration

Edit `/etc/bt-bridge/config.json` or use the web interface Settings page.

| Option | Default | Description |
|--------|---------|-------------|
| `target_address` | (required) | TNC Bluetooth MAC address |
| `device_name` | `"PiBTBridge"` | BLE name shown on iPhone |
| `rfcomm_channel` | `2` | RFCOMM channel (1-30) |
| `web_port` | `8080` | Web interface port |
| `log_level` | `"INFO"` | DEBUG, INFO, WARNING, ERROR |

See [Configuration Reference](docs/configuration.md) for all options.

## Usage

### Systemd Service

```bash
# Start/stop/restart
sudo systemctl start bt-bridge
sudo systemctl stop bt-bridge
sudo systemctl restart bt-bridge

# View logs
sudo journalctl -u bt-bridge -f

# Enable on boot
sudo systemctl enable bt-bridge
```

### Running Manually

```bash
sudo python3 -m src.main

# With custom config
BT_BRIDGE_CONFIG=/path/to/config.json sudo python3 -m src.main
```

## Troubleshooting

### Bridge won't start

```bash
# Check Bluetooth adapter
sudo hciconfig hci0 up
sudo rfkill unblock bluetooth

# Check logs
sudo journalctl -u bt-bridge -n 50
```

### Can't connect to TNC

```bash
# Verify TNC is paired
bluetoothctl info 00:11:22:33:44:55

# Check RFCOMM channel
sdptool browse 00:11:22:33:44:55
```

### iPhone can't see the bridge

```bash
# Check BLE advertising
sudo btmgmt info

# Check logs for BLE errors
sudo journalctl -u bt-bridge | grep -i ble
```

## Development

```bash
# Clone and setup
git clone https://github.com/hemna/pi-bt-bridge.git
cd pi-bt-bridge
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Deploy to Pi
make deploy PI_HOST=pi@raspberrypi.local
```

See [Development Guide](docs/development.md) for make targets and workflows.

## Architecture

```
src/
├── main.py                 # Daemon entry point
├── config.py               # Configuration management
├── models/
│   ├── state.py            # ConnectionState, BridgeState
│   ├── kiss.py             # KISS protocol parser
│   └── connection.py       # Connection tracking
├── services/
│   ├── ble_service.py      # BLE GATT server (Nordic UART)
│   ├── classic_service.py  # BT Classic SPP client
│   ├── bridge.py           # Bidirectional forwarding
│   ├── pairing_agent.py    # D-Bus pairing agent
│   ├── scanner_service.py  # Bluetooth device scanner
│   └── web_service.py      # Web interface (aiohttp)
└── web/
    ├── models.py           # Web data models
    ├── templates/          # Jinja2 HTML templates
    └── static/             # CSS styles
```

## Protocol Details

### BLE Service (Nordic UART Service)

| UUID | Description |
|------|-------------|
| `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` | Service UUID |
| `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` | TX Characteristic (write) |
| `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` | RX Characteristic (notify) |

### KISS Protocol

The bridge transparently forwards KISS frames:

- Frame delimiter: `0xC0` (FEND)
- Escape character: `0xDB` (FESC)
- Escaped FEND: `0xDB 0xDC`
- Escaped FESC: `0xDB 0xDD`

## Documentation

| Document | Description |
|----------|-------------|
| [Installation Guide](docs/installation.md) | Detailed installation instructions |
| [Configuration Reference](docs/configuration.md) | All configuration options |
| [Web Interface Guide](docs/web-interface.md) | Using the web UI |
| [API Reference](docs/api.md) | REST API documentation |
| [Development Guide](docs/development.md) | Development workflow |

## License

MIT License - See LICENSE file for details.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Ensure tests pass and linting is clean
5. Submit a pull request

## Acknowledgments

- [bless](https://github.com/kevincar/bless) - BLE GATT server library
- [BlueZ](http://www.bluez.org/) - Linux Bluetooth stack
- Nordic Semiconductor for the UART Service specification
