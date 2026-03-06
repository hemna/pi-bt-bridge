# Development Guide

This guide covers setting up a development environment and contributing to Pi BT Bridge.

## Development Environment Setup

### Prerequisites

- **Python 3.11+**
- **Git**
- **Make** (optional, but recommended)
- For remote deployment: SSH access to a Raspberry Pi Zero 2 W

### Clone and Install

```bash
# Clone the repository
git clone https://github.com/hemna/pi-bt-bridge.git
cd pi-bt-bridge

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install with development dependencies
pip install -e ".[dev]"
```

### Verify Installation

```bash
# Run tests
pytest

# Run linter
ruff check src/ tests/

# Run type checker
mypy src/
```

## Project Structure

```
pi-bt-bridge/
├── src/
│   ├── main.py                 # Daemon entry point
│   ├── config.py               # Configuration management
│   ├── models/
│   │   ├── state.py            # ConnectionState, BridgeState, ErrorEvent
│   │   ├── kiss.py             # KISS protocol: KISSFrame, KISSParser
│   │   └── connection.py       # BLEConnection, ClassicConnection
│   ├── services/
│   │   ├── ble_service.py      # BLE GATT server (Nordic UART Service)
│   │   ├── classic_service.py  # BT Classic SPP client
│   │   ├── bridge.py           # Bidirectional frame bridging
│   │   ├── pairing_agent.py    # D-Bus Bluetooth pairing agent
│   │   ├── scanner_service.py  # Bluetooth device scanner
│   │   └── web_service.py      # Web interface HTTP server
│   ├── web/
│   │   ├── models.py           # Web interface data models
│   │   ├── templates/          # Jinja2 HTML templates
│   │   │   ├── base.html
│   │   │   ├── status.html
│   │   │   ├── pairing.html
│   │   │   ├── settings.html
│   │   │   └── stats.html
│   │   └── static/
│   │       └── style.css       # Web interface styles
│   └── util/
│       └── logging.py          # Structured logging setup
├── tests/                      # Test suite
├── systemd/                    # Systemd service files
├── scripts/                    # Utility scripts
├── docs/                       # Documentation
├── specs/                      # Feature specifications
├── Makefile                    # Build and deployment targets
├── pyproject.toml              # Project metadata and dependencies
└── config.example.json         # Example configuration
```

## Make Targets

The Makefile provides convenient targets for common development tasks.

### Configuration Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PI_HOST` | `pi@raspberrypi.local` | SSH target for Pi deployment |
| `PI_DIR` | `~/pi-bt-bridge` | Project directory on Pi |

Override on command line: `make deploy PI_HOST=pi@mypi.local`

### All Targets

| Target | Description |
|--------|-------------|
| **help** | Show all available targets with descriptions |
| **deploy** | Deploy project to Pi using rsync and piwheels |
| **deploy-wheels** | Build ARM wheels first, then deploy with local wheels |
| **wheels** | Build ARM wheels in Docker for Raspberry Pi |
| **run-pi** | Run the daemon on Pi in foreground (for testing) |
| **status** | Check daemon status on Pi via systemctl |
| **logs** | Show and follow daemon logs from Pi |
| **test** | Run all tests locally |
| **test-cov** | Run tests with coverage report |
| **lint** | Run ruff linter on src/ and tests/ |
| **lint-fix** | Run ruff linter with auto-fix |
| **typecheck** | Run mypy type checker on src/ |
| **clean** | Remove build artifacts, __pycache__, etc. |
| **clean-wheels** | Remove built wheel files |
| **install-dev** | Install development dependencies locally |
| **pi-shell** | Open interactive SSH shell to Pi |
| **pi-configure** | Run interactive configuration wizard on Pi |
| **pi-config** | Edit config file on Pi with nano |
| **pi-restart** | Restart bt-bridge daemon on Pi |
| **pi-install-service** | Install systemd service on Pi |

### Common Workflows

**Deploy and test changes:**

```bash
# Deploy to Pi
make deploy

# Check logs
make logs

# Or run in foreground for debugging
make run-pi
```

**Run full test suite:**

```bash
make test-cov
```

**Fix linting issues:**

```bash
make lint-fix
```

## Running Tests

### All Tests

```bash
pytest
```

### With Coverage

```bash
pytest --cov=src --cov-report=term-missing
```

### By Category

```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# Contract tests only
pytest -m contract
```

### Specific File or Test

```bash
# Run tests in a file
pytest tests/test_config.py

# Run a specific test
pytest tests/test_config.py::test_load_config_valid
```

### Verbose Output

```bash
pytest -v
```

## Code Quality

### Linting with Ruff

```bash
# Check for issues
ruff check src/ tests/

# Auto-fix issues
ruff check --fix src/ tests/
```

### Type Checking with mypy

```bash
mypy src/
```

### Pre-commit (Optional)

Install pre-commit hooks to run checks automatically:

```bash
pip install pre-commit
pre-commit install
```

## Remote Development Workflow

### Initial Setup

1. Ensure SSH access to your Pi:
   ```bash
   ssh pi@raspberrypi.local
   ```

2. Deploy the project:
   ```bash
   make deploy
   ```

3. Install systemd service:
   ```bash
   make pi-install-service
   ```

### Development Cycle

1. Make changes locally
2. Deploy to Pi:
   ```bash
   make deploy
   ```
3. Restart and test:
   ```bash
   make pi-restart
   make logs
   ```

### Debugging on Pi

```bash
# Run in foreground with debug logging
make run-pi

# Or SSH in and run manually
make pi-shell
cd ~/pi-bt-bridge
source .venv/bin/activate
python -m src.main
```

## Building ARM Wheels

For faster deployment, pre-build ARM wheels using Docker:

### Prerequisites

- Docker installed
- QEMU for ARM emulation (Docker Desktop handles this automatically)

### Build Wheels

```bash
# Build all wheels
make wheels

# Or run script directly
./scripts/build-wheels.sh
```

This creates ARM-compatible wheels in the `wheels/` directory.

### Deploy with Local Wheels

```bash
make deploy-wheels
```

## Debugging

### BLE Advertising Issues

```bash
# Run the BLE debug script
./scripts/debug-ble.sh

# Or test advertising standalone
python scripts/test-ble-advert.py
```

### Check Bluetooth State

```bash
# On the Pi
bluetoothctl show

# Check if adapter is up
hciconfig

# Unblock if needed
sudo rfkill unblock bluetooth
```

### View Detailed Logs

```bash
# Full logs with debug level
sudo journalctl -u bt-bridge -f

# Or configure debug logging
# Edit /etc/bt-bridge/config.json: "log_level": "DEBUG"
sudo systemctl restart bt-bridge
```

### Bluetooth Pairing Issues

```bash
# Run interactive pairing helper
./scripts/bt-pair.sh

# Or use bluetoothctl manually
bluetoothctl
> scan on
> pair 00:1A:7D:DA:71:13
> trust 00:1A:7D:DA:71:13
> exit
```

### Check RFCOMM Channel

```bash
# Find SPP channel for a device
sdptool browse 00:1A:7D:DA:71:13
```

## Adding New Features

### Feature Branch Workflow

1. Create a feature branch:
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. Write a spec in `specs/XXX-feature-name/`:
   - `spec.md` - Requirements and user stories
   - `plan.md` - Implementation plan
   - `tasks.md` - Task breakdown

3. Implement the feature with tests

4. Update documentation in `docs/`

5. Submit a pull request

### Code Style Guidelines

- Follow PEP 8 and existing code patterns
- Use type hints for all function signatures
- Write docstrings for public functions and classes
- Keep functions focused and small
- Add tests for new functionality

## Useful Scripts

| Script | Purpose |
|--------|---------|
| `scripts/install.sh` | Full installation on Pi |
| `scripts/deploy.sh` | Remote deployment from Mac/Linux |
| `scripts/configure.sh` | Interactive configuration wizard |
| `scripts/bt-pair.sh` | Interactive Bluetooth pairing |
| `scripts/build-wheels.sh` | Cross-compile ARM wheels |
| `scripts/debug-ble.sh` | Debug BLE advertising |
| `scripts/test-ble-advert.py` | Standalone BLE advertising test |
| `scripts/bridge_log.py` | Debug version with packet logging |

## See Also

- [Installation Guide](installation.md) - Production installation
- [Configuration Reference](configuration.md) - All configuration options
- [API Reference](api.md) - REST API documentation
- [Web Interface Guide](web-interface.md) - Web UI documentation
