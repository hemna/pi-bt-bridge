# pi-bt-bridge Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-04

## Active Technologies
- Python 3.11+ + aiohttp (web), dataclasses (models), JSON (persistence) (003-tnc-radio-history)
- JSON file (`/etc/bt-bridge/tnc-history.json`) (003-tnc-radio-history)

- Python 3.11+ + bless (BLE GATT), dbus-python (SPP), PyGObject (GLib loop) (001-bt-bridge-daemon)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.11+: Follow standard conventions

## Recent Changes
- 003-tnc-radio-history: Added Python 3.11+ + aiohttp (web), dataclasses (models), JSON (persistence)

- 001-bt-bridge-daemon: Added Python 3.11+ + bless (BLE GATT), dbus-python (SPP), PyGObject (GLib loop)

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
