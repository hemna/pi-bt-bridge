# Research: TNC Radio History

**Feature**: 003-tnc-radio-history  
**Date**: 2026-03-06

## Research Tasks

### 1. Storage Format and Location

**Question**: How should TNC history be persisted?

**Decision**: Use a separate JSON file (`/etc/bt-bridge/tnc-history.json`)

**Rationale**:
- Separates history data from main configuration (config.json)
- History can be backed up/restored independently
- JSON is human-readable and matches existing config pattern
- File-based storage fits the single-file daemon model (no database needed)
- Location in `/etc/bt-bridge/` keeps all persistent data in one place

**Alternatives Considered**:
1. **Embedded in config.json**: Rejected - pollutes config with dynamic data that changes frequently
2. **SQLite database**: Rejected - overkill for <20 records, adds dependency
3. **In-memory only**: Rejected - doesn't persist across restarts

### 2. History Entry Data Model

**Question**: What fields should be stored for each TNC?

**Decision**: Store minimal identifying and operational data:
```python
@dataclass
class TNCDevice:
    address: str           # MAC address (primary key)
    bluetooth_name: str    # Name from Bluetooth discovery
    friendly_name: str     # User-assigned name (optional)
    rfcomm_channel: int    # RFCOMM channel for SPP
    last_used: datetime    # Last successful connection
    added_at: datetime     # When first added to history
```

**Rationale**:
- `address` is the unique identifier (MAC addresses are globally unique)
- `bluetooth_name` provides fallback display when no friendly name set
- `friendly_name` allows user customization for multiple similar radios
- `rfcomm_channel` is required for SPP connection
- `last_used` enables sorting by recency and status display
- `added_at` useful for debugging/history tracking

**Alternatives Considered**:
1. **Store PIN codes**: Rejected - security concern, PIN handling is separate from history
2. **Store connection statistics**: Rejected - scope creep, can add later if needed

### 3. Maximum History Size

**Question**: Should history size be limited?

**Decision**: Soft limit of 20 entries, no hard enforcement

**Rationale**:
- Typical ham operator has 1-5 TNC radios
- 20 entries covers extreme cases (club stations, testing scenarios)
- JSON file stays small (<10KB even with 20 entries)
- UI remains usable with 20 items
- No need for complex LRU eviction

**Alternatives Considered**:
1. **Hard limit with auto-eviction**: Rejected - complicates implementation, unlikely to be needed
2. **Unlimited**: Acceptable but 20 is reasonable documentation of expected scale

### 4. API Design Pattern

**Question**: How should history be exposed via API?

**Decision**: RESTful CRUD endpoints under `/api/tnc-history/`:
- `GET /api/tnc-history` - List all TNCs in history
- `POST /api/tnc-history` - Add TNC to history (or update if exists)
- `GET /api/tnc-history/{address}` - Get single TNC details
- `PUT /api/tnc-history/{address}` - Update TNC (friendly name)
- `DELETE /api/tnc-history/{address}` - Remove TNC from history
- `POST /api/tnc-history/{address}/select` - Select TNC as active target

**Rationale**:
- Follows REST conventions established by existing API
- MAC address in URL uniquely identifies resource
- Separate `/select` action for state change vs data update
- Matches existing `/api/pairing/` and `/api/settings` patterns

**Alternatives Considered**:
1. **Single endpoint with action param**: Rejected - less RESTful, harder to document
2. **GraphQL**: Rejected - overkill, not used elsewhere in project

### 5. Integration with Existing TNC Selection

**Question**: How does history integrate with current pairing/scanning flow?

**Decision**: History complements (not replaces) scanning:
1. Web UI shows history list in TNC Selection section
2. "Scan for Devices" still available for new devices
3. Newly paired/used devices auto-added to history
4. Selecting from history sets `target_address` in config
5. History and scan results can coexist in UI

**Rationale**:
- Users still need to discover new TNCs via scanning
- History provides quick access to known TNCs
- Auto-add ensures history stays current without user action
- Single `target_address` in config keeps connection logic unchanged

**Alternatives Considered**:
1. **Replace scanning entirely**: Rejected - still need way to add new TNCs
2. **Separate page for history**: Rejected - increases navigation, better integrated

### 6. Handling Unpaired Devices in History

**Question**: What if a TNC in history is no longer paired at Bluetooth level?

**Decision**: Show warning indicator, allow re-pairing from history view

**Rationale**:
- Devices can become unpaired (system reset, adapter change)
- History entry still valid - user might want to re-pair
- Warning helps user understand why connection might fail
- Offering re-pair action keeps workflow smooth

**Implementation**:
- Check paired status when listing history
- Add `paired` boolean to API response
- UI shows warning badge for unpaired devices
- "Pair" button available for unpaired entries

### 7. File Locking and Concurrency

**Question**: How to handle concurrent access to history file?

**Decision**: Simple read-modify-write with in-memory cache

**Rationale**:
- Single daemon process (no multi-process concerns)
- Web requests are async but serialized through aiohttp
- History operations are infrequent (user-initiated)
- In-memory cache reduces file I/O
- Write-through on modifications ensures persistence

**Implementation**:
```python
class TNCHistory:
    def __init__(self, path: Path):
        self._path = path
        self._devices: dict[str, TNCDevice] = {}
        self._load()
    
    def _load(self) -> None: ...
    def _save(self) -> None: ...
    def add(self, device: TNCDevice) -> None: ...
    def remove(self, address: str) -> None: ...
    def get(self, address: str) -> TNCDevice | None: ...
    def list_all(self) -> list[TNCDevice]: ...
```

## Summary of Decisions

| Topic | Decision |
|-------|----------|
| Storage | JSON file at `/etc/bt-bridge/tnc-history.json` |
| Data Model | TNCDevice with address, names, channel, timestamps |
| Size Limit | Soft limit of 20 entries |
| API Pattern | RESTful CRUD under `/api/tnc-history/` |
| UI Integration | Integrated into existing TNC Selection section |
| Unpaired Handling | Show warning, allow re-pair from history |
| Concurrency | In-memory cache with write-through persistence |
