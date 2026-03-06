# Configuration Reference

This document describes all configuration options for Pi BT Bridge.

## Configuration File

### Location

The default configuration file location is:

```
/etc/bt-bridge/config.json
```

### Environment Variable Override

You can specify an alternative configuration file using the `BT_BRIDGE_CONFIG` environment variable:

```bash
# Using a custom config file
BT_BRIDGE_CONFIG=/home/pi/my-config.json sudo python3 -m src.main
```

## Configuration Options

| Option | Type | Default | Valid Range | Description |
|--------|------|---------|-------------|-------------|
| `target_address` | string | **required** | Valid MAC address | Bluetooth Classic MAC address of your TNC device |
| `target_pin` | string | `"0000"` | Any string | Pairing PIN for the TNC (if required) |
| `rfcomm_channel` | int | `2` | 1-30 | RFCOMM channel for SPP connection |
| `device_name` | string | `"PiBTBridge"` | Any string | BLE advertised name (shown on iPhone) |
| `log_level` | string | `"INFO"` | DEBUG, INFO, WARNING, ERROR | Logging verbosity |
| `log_file` | string | `null` | Valid path or null | Log file path (null for stdout/journal) |
| `buffer_size` | int | `4096` | 1024-65536 | Internal buffer size in bytes |
| `reconnect_max_delay` | int | `30` | 5-300 | Maximum seconds between reconnect attempts |
| `status_socket` | string | `"/var/run/bt-bridge.sock"` | Valid path | Unix socket path for status queries |
| `web_enabled` | bool | `true` | true/false | Enable the web interface |
| `web_port` | int | `8080` | 1024-65535 | HTTP port for web interface |
| `web_host` | string | `"0.0.0.0"` | IP address or hostname | Host to bind web interface to |
| `history_file` | string | `"/etc/bt-bridge/tnc-history.json"` | Valid file path | Path to TNC history JSON file |

## Option Details

### target_address (required)

The Bluetooth MAC address of your TNC device. This is the only required configuration option.

Format: `XX:XX:XX:XX:XX:XX` (colon-separated hexadecimal)

**Finding your TNC's address:**

```bash
# Put your TNC in pairing mode, then scan:
bluetoothctl scan on

# Example output:
# [NEW] Device 00:1A:7D:DA:71:13 TH-D74
```

### target_pin

The PIN code used for Bluetooth pairing. Most TNCs use `"0000"` or `"1234"`.

### rfcomm_channel

The RFCOMM channel number for the Serial Port Profile (SPP) connection. Common values:

| Device | Channel |
|--------|---------|
| Kenwood TH-D74 | 2 |
| Mobilinkd TNC3/TNC4 | 1 |

You can discover the correct channel using `sdptool`:

```bash
sdptool browse 00:1A:7D:DA:71:13
```

### device_name

The name advertised over BLE that will appear on your iPhone when scanning for Bluetooth devices.

### log_level

Controls the verbosity of log output:

| Level | Description |
|-------|-------------|
| `DEBUG` | Detailed debugging information, including packet contents |
| `INFO` | General operational information |
| `WARNING` | Warning messages for potential issues |
| `ERROR` | Error messages only |

### log_file

Path to write log output. Set to `null` to log to stdout (captured by systemd journal).

```json
{
  "log_file": "/var/log/bt-bridge.log"
}
```

### buffer_size

Internal queue buffer size in bytes. Increase if you experience data loss with high-throughput applications.

### reconnect_max_delay

Maximum delay (in seconds) between reconnection attempts when the Classic Bluetooth connection is lost. The daemon uses exponential backoff starting from 1 second up to this maximum.

### status_socket

Unix socket path for external status queries. Used by monitoring tools.

### web_enabled

Enable or disable the web interface. Set to `false` if you only need the bridge functionality without the web UI.

### web_port

HTTP port for the web interface. Default is `8080`. Change this if you have a conflict with another service.

**Note:** Changing the port requires a daemon restart.

### web_host

IP address or hostname to bind the web interface to:

| Value | Description |
|-------|-------------|
| `"0.0.0.0"` | Listen on all interfaces (default) |
| `"127.0.0.1"` | Listen only on localhost |
| `"192.168.1.100"` | Listen on specific interface |

### history_file

Path to the JSON file where TNC device history is stored. This file is created automatically when the first TNC is added to history (either through the pairing flow or the TNC history API).

The file persists across daemon restarts, allowing users to quickly switch between previously paired TNC devices without re-scanning.

```json
{
  "history_file": "/etc/bt-bridge/tnc-history.json"
}
```

## Complete Example

```json
{
  "target_address": "00:1A:7D:DA:71:13",
  "target_pin": "0000",
  "rfcomm_channel": 2,
  "device_name": "PiBTBridge",
  "log_level": "INFO",
  "log_file": null,
  "buffer_size": 4096,
  "reconnect_max_delay": 30,
  "status_socket": "/var/run/bt-bridge.sock",
  "web_enabled": true,
  "web_port": 8080,
  "web_host": "0.0.0.0",
  "history_file": "/etc/bt-bridge/tnc-history.json"
}
```

## Validation Rules

The configuration is validated on load. Invalid configurations will prevent the daemon from starting.

| Option | Validation |
|--------|------------|
| `target_address` | Must be valid MAC format (`XX:XX:XX:XX:XX:XX`) |
| `log_level` | Must be one of: DEBUG, INFO, WARNING, ERROR |
| `buffer_size` | Must be between 1024 and 65536 |
| `reconnect_max_delay` | Must be between 5 and 300 |
| `rfcomm_channel` | Must be between 1 and 30 |
| `web_port` | Must be between 1024 and 65535 |

## Changing Configuration

### Via Configuration File

1. Edit the configuration file:
   ```bash
   sudo nano /etc/bt-bridge/config.json
   ```

2. Restart the daemon:
   ```bash
   sudo systemctl restart bt-bridge
   ```

### Via Web Interface

1. Navigate to the Settings page: `http://<pi-ip>:8080/settings`
2. Modify the desired settings
3. Click "Save Settings"
4. Click "Restart Bridge" if prompted (required for some changes)

### Via Make Target

From your development machine:

```bash
# Interactive configuration wizard
make pi-configure

# Or edit manually
make pi-config
```

## See Also

- [Installation Guide](installation.md) - How to install Pi BT Bridge
- [Web Interface Guide](web-interface.md) - Using the web interface
- [API Reference](api.md) - REST API for programmatic configuration
