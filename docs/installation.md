# Installation Guide

This guide covers installing Pi BT Bridge on a Raspberry Pi Zero 2 W.

## Prerequisites

### Hardware

- **Raspberry Pi Zero 2 W** (recommended) or any Raspberry Pi with Bluetooth
- MicroSD card (8GB+)
- Power supply
- Your Bluetooth Classic TNC device (e.g., Mobilinkd TNC3/TNC4, Kenwood TH-D74)

### Software

- **Raspberry Pi OS** (Bookworm or later recommended)
- **Python 3.11+**
- **BlueZ 5.x** (included with Raspberry Pi OS)

## Installation Methods

### Method 1: Quick Install (On the Pi)

The simplest method if you're working directly on the Raspberry Pi:

```bash
# Clone the repository
git clone https://github.com/hemna/pi-bt-bridge.git
cd pi-bt-bridge

# Run the install script (requires sudo)
sudo ./scripts/install.sh
```

The install script will:
1. Create `/opt/bt-bridge` directory and copy source files
2. Install Python dependencies
3. Create `/etc/bt-bridge/config.json` from the example config
4. Install the `bluetooth-unblock.service` (fixes RF-kill issues on boot)
5. Install and enable the `bt-bridge.service` systemd unit

### Method 2: Remote Deployment (From Mac/Linux)

Deploy from your development machine to the Pi over SSH:

```bash
# Clone the repository locally
git clone https://github.com/hemna/pi-bt-bridge.git
cd pi-bt-bridge

# Deploy to Pi (default: pi@raspberrypi.local)
make deploy

# Or specify a custom Pi host
make deploy PI_HOST=pi@your-pi-hostname.local
```

This method:
1. Syncs project files to the Pi via `rsync`
2. Creates a virtual environment on the Pi
3. Installs dependencies from piwheels (pre-compiled ARM packages)
4. Sets up the project in development mode

#### Using Pre-built Wheels (Faster)

For faster deployment, especially with slow network or missing piwheels:

```bash
# Build ARM wheels locally using Docker (one-time)
make wheels

# Deploy with local wheels
make deploy-wheels
```

### Method 3: Manual Installation

For more control over the installation process:

```bash
# Install system dependencies
sudo apt update
sudo apt install -y python3-pip python3-dbus python3-gi bluetooth bluez

# Clone and install
git clone https://github.com/hemna/pi-bt-bridge.git
cd pi-bt-bridge
pip3 install -e .

# Create config directory
sudo mkdir -p /etc/bt-bridge
sudo cp config.example.json /etc/bt-bridge/config.json

# Edit configuration
sudo nano /etc/bt-bridge/config.json
```

## Systemd Services

Pi BT Bridge uses two systemd services:

### Main Service: bt-bridge.service

The main daemon that runs the Bluetooth bridge:

```bash
# Enable to start on boot
sudo systemctl enable bt-bridge

# Start the service
sudo systemctl start bt-bridge

# Check status
sudo systemctl status bt-bridge

# View logs
sudo journalctl -u bt-bridge -f
```

### Helper Service: bluetooth-unblock.service

Ensures Bluetooth is unblocked after boot (fixes common RF-kill issues):

```bash
# This is automatically enabled by the install script
sudo systemctl status bluetooth-unblock
```

### Service File Locations

| Service | Location |
|---------|----------|
| `bt-bridge.service` | `/etc/systemd/system/bt-bridge.service` |
| `bluetooth-unblock.service` | `/etc/systemd/system/bluetooth-unblock.service` |

### Service Configuration

The `bt-bridge.service` runs with the following settings:

- **Working Directory**: `/opt/bt-bridge`
- **User**: root (required for Bluetooth access)
- **Restart Policy**: Restart on failure with 5-second delay
- **Security**: Hardened with `ProtectSystem=strict`, `ProtectHome=true`, etc.

## Post-Installation

### 1. Verify Installation

```bash
# Check service status
sudo systemctl status bt-bridge

# Check if web interface is accessible
curl http://localhost:8080/api/status
```

### 2. Access Web Interface

Open a browser and navigate to:

```
http://<pi-ip-address>:8080
```

Or if using mDNS:

```
http://raspberrypi.local:8080
```

### 3. First-Time Configuration

You can configure the bridge either:

1. **Via Web Interface** (recommended): Navigate to the Settings page at `http://<pi-ip>:8080/settings`

2. **Via Configuration File**: Edit `/etc/bt-bridge/config.json`

3. **Via Interactive Wizard**: Run `make pi-configure` from your development machine

See [Configuration Reference](configuration.md) for all available options.

### 4. Pair Your TNC

Use the web interface Pairing page (`http://<pi-ip>:8080/pairing`) to:

1. Scan for Bluetooth devices
2. Select your TNC from the list
3. Complete pairing (enter PIN if required)
4. Set as target device

## Uninstallation

To remove Pi BT Bridge:

```bash
# Stop and disable services
sudo systemctl stop bt-bridge
sudo systemctl disable bt-bridge
sudo systemctl disable bluetooth-unblock

# Remove service files
sudo rm /etc/systemd/system/bt-bridge.service
sudo rm /etc/systemd/system/bluetooth-unblock.service
sudo systemctl daemon-reload

# Remove installation directory
sudo rm -rf /opt/bt-bridge

# Remove configuration (optional - preserves settings)
sudo rm -rf /etc/bt-bridge
```

## Troubleshooting Installation

### Bluetooth adapter not found

```bash
# Check if Bluetooth is blocked
rfkill list bluetooth

# Unblock if needed
sudo rfkill unblock bluetooth

# Verify adapter is present
hciconfig
```

### Service fails to start

```bash
# Check logs for errors
sudo journalctl -u bt-bridge -n 50

# Verify Python version
python3 --version  # Should be 3.11+

# Check if dependencies are installed
python3 -c "import bless; import dbus; import gi"
```

### Permission denied errors

The daemon requires root access for Bluetooth operations. Ensure the service runs as root or the user is in the `bluetooth` group:

```bash
sudo usermod -a -G bluetooth $USER
```

## Next Steps

- [Configuration Reference](configuration.md) - Configure the bridge
- [Web Interface Guide](web-interface.md) - Learn about the web UI
- [Development Guide](development.md) - Set up a development environment
