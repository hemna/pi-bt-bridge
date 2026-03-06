# Quickstart: TNC Radio History

**Feature**: 003-tnc-radio-history  
**Date**: 2026-03-06

## Overview

This feature adds persistent TNC radio history to Pi BT Bridge, allowing quick switching between previously paired TNC devices.

## Key Files

| File | Purpose |
|------|---------|
| `src/models/tnc_history.py` | TNCDevice and TNCHistory data models |
| `src/services/web_service.py` | API endpoints (modified) |
| `src/web/templates/status.html` | UI for TNC selection (modified) |
| `/etc/bt-bridge/tnc-history.json` | Persistent history storage |

## Data Model

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class TNCDevice:
    address: str           # MAC address (unique key)
    bluetooth_name: str    # Name from Bluetooth
    friendly_name: str | None = None
    rfcomm_channel: int = 2
    last_used: datetime | None = None
    added_at: datetime = field(default_factory=datetime.now)
    
    @property
    def display_name(self) -> str:
        return self.friendly_name or self.bluetooth_name
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tnc-history` | List all TNCs in history |
| POST | `/api/tnc-history` | Add TNC to history |
| GET | `/api/tnc-history/{addr}` | Get single TNC |
| PUT | `/api/tnc-history/{addr}` | Update TNC (friendly name) |
| DELETE | `/api/tnc-history/{addr}` | Remove from history |
| POST | `/api/tnc-history/{addr}/select` | Select as active TNC |

## Usage Flow

1. **First Time**: User scans and pairs TNC via existing pairing flow
2. **Auto-Add**: When TNC is used, it's automatically added to history
3. **Quick Switch**: User selects TNC from history list in web UI
4. **Customize**: User can set friendly names for easy identification

## Testing

```bash
# Run unit tests
pytest tests/unit/test_tnc_history.py -v

# Run integration tests
pytest tests/integration/test_history_api.py -v

# Manual API test
curl http://localhost:8080/api/tnc-history
```

## Configuration

New config option in `/etc/bt-bridge/config.json`:

```json
{
  "history_file": "/etc/bt-bridge/tnc-history.json"
}
```

Default: `/etc/bt-bridge/tnc-history.json`

## Dependencies

No new dependencies required. Uses existing:
- `dataclasses` (stdlib)
- `json` (stdlib)
- `aiohttp` (existing)
