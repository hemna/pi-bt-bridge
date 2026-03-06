# Contract: Web API Extensions for TCP KISS

**Feature**: 004-tcp-kiss-server  
**Type**: HTTP REST API + SSE

## Modified Endpoints

### GET /api/status (existing, modified response)

**Added fields** in response body:

```json
{
  "ble": { ... },
  "classic": { ... },
  "tcp_kiss": {
    "enabled": true,
    "listening": true,
    "port": 8001,
    "client_count": 2,
    "max_clients": 5,
    "clients": [
      {
        "remote_address": "192.168.1.100:54321",
        "connected_at": "2026-03-06T12:34:56Z",
        "bytes_rx": 1024,
        "bytes_tx": 4096
      },
      {
        "remote_address": "192.168.1.101:12345",
        "connected_at": "2026-03-06T12:35:00Z",
        "bytes_rx": 512,
        "bytes_tx": 2048
      }
    ]
  },
  "uptime_seconds": 3600,
  "started_at": "2026-03-06T11:34:56Z",
  "version": "1.0.0"
}
```

When TCP KISS is disabled:

```json
{
  "tcp_kiss": {
    "enabled": false,
    "listening": false,
    "port": 0,
    "client_count": 0,
    "max_clients": 0,
    "clients": []
  }
}
```

### GET /api/status/stream (SSE, existing, modified events)

The `status` event payload now includes the `tcp_kiss` object as shown above.

### GET /api/stats (existing, modified response)

**Added fields**:

```json
{
  "packets_tx": 100,
  "bytes_tx": 10240,
  "bytes_rx": 51200,
  "errors": 0,
  "tcp_clients_total": 5,
  "tcp_bytes_rx": 2048,
  "tcp_bytes_tx": 8192
}
```

## Contract Tests

### CT-API-001: Status includes TCP KISS
- `GET /api/status` response MUST include `tcp_kiss` object
- `tcp_kiss.enabled` MUST reflect configuration
- `tcp_kiss.client_count` MUST match actual connected clients

### CT-API-002: SSE includes TCP KISS
- SSE `status` events MUST include `tcp_kiss` object
- Client count MUST update within one SSE push cycle (3s) of connect/disconnect
