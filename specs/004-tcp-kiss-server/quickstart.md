# Quickstart: TCP KISS Server

**Feature**: 004-tcp-kiss-server

## Configuration

Add TCP KISS settings to `/etc/bt-bridge/config.json`:

```json
{
  "target_address": "24:71:89:8D:26:EF",
  "rfcomm_channel": 2,
  "tcp_kiss_enabled": true,
  "tcp_kiss_port": 8001,
  "tcp_kiss_max_clients": 5
}
```

All TCP settings are optional. Defaults: enabled on port 8001, max 5 clients.

To disable: set `"tcp_kiss_enabled": false`.

## Testing with netcat

Quick test to verify the TCP KISS server is running:

```bash
# Connect to the TCP KISS server
nc pi-sugar.hemna.com 8001

# Send a KISS data frame (hex: FEND, cmd=0x00, data "test", FEND)
printf '\xc0\x00test\xc0' | nc pi-sugar.hemna.com 8001
```

## Testing with Direwolf

In `direwolf.conf`, configure a KISS TCP connection:

```
KISSPORT 8001
```

Or connect Direwolf as a KISS client:

```bash
kissutil -h pi-sugar.hemna.com:8001
```

## Testing with APRSIS32

1. Open APRSIS32
2. Configure → Ports → New Port
3. Select "KISS TCP/IP"
4. Host: `pi-sugar.hemna.com`
5. Port: `8001`
6. Click Connect

## Verifying Multi-Client

1. Connect via BLE (iOS APRS Chat app)
2. Connect via TCP (any KISS client)
3. Have another radio transmit a packet
4. Both clients should display the received packet

## Web Status

View connected TCP clients at: `http://pi-sugar.hemna.com:8080/`

The status page shows:
- TCP KISS server status (listening/disabled)
- Number of connected clients
- Per-client IP address and connection time

## Development Testing

```bash
# Run unit tests
.venv/bin/python -m pytest tests/unit/test_tcp_kiss_service.py -v

# Run contract tests
.venv/bin/python -m pytest tests/contract/test_tcp_kiss_framing.py -v

# Run integration tests
.venv/bin/python -m pytest tests/integration/test_tcp_bridge.py -v

# Run all tests
.venv/bin/python -m pytest tests/ --ignore=tests/integration/test_bridge_flow.py -v
```

## Deploy to Pi

```bash
rsync -avz --exclude='.venv' --exclude='__pycache__' --exclude='.git' --exclude='*.pyc' \
  src/ waboring@pi-sugar.hemna.com:~/pi-bt-bridge/src/

# Restart the service
ssh waboring@pi-sugar.hemna.com "sudo kill -9 \$(pgrep -f 'src.main') 2>/dev/null; \
  sudo kill -9 \$(pgrep btmgmt) 2>/dev/null; sleep 2; sudo systemctl start bt-bridge"
```
