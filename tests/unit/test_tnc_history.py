"""Unit tests for TNC device history models."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.models.tnc_history import (
    MAX_FRIENDLY_NAME_LENGTH,
    TNCDevice,
    TNCHistory,
)

# =============================================================================
# TNCDevice Validation Tests (T012)
# =============================================================================


class TestTNCDeviceValidation:
    """Unit tests for TNCDevice field validation."""

    def test_valid_device_creates_successfully(self) -> None:
        """Valid TNCDevice creates without errors."""
        device = TNCDevice(
            address="00:1A:7D:DA:71:13",
            bluetooth_name="TH-D74",
            rfcomm_channel=2,
        )
        assert device.address == "00:1A:7D:DA:71:13"
        assert device.bluetooth_name == "TH-D74"
        assert device.rfcomm_channel == 2
        assert device.friendly_name is None
        assert device.added_at is not None

    def test_mac_address_normalized_to_uppercase(self) -> None:
        """MAC address is normalized to uppercase."""
        device = TNCDevice(
            address="aa:bb:cc:dd:ee:ff",
            bluetooth_name="Test",
        )
        assert device.address == "AA:BB:CC:DD:EE:FF"

    def test_invalid_mac_address_raises(self) -> None:
        """Invalid MAC address raises ValueError."""
        with pytest.raises(ValueError, match="address"):
            TNCDevice(address="invalid", bluetooth_name="Test")

    def test_empty_mac_address_raises(self) -> None:
        """Empty MAC address raises ValueError."""
        with pytest.raises(ValueError, match="address"):
            TNCDevice(address="", bluetooth_name="Test")

    def test_empty_bluetooth_name_raises(self) -> None:
        """Empty bluetooth_name raises ValueError."""
        with pytest.raises(ValueError, match="bluetooth_name"):
            TNCDevice(address="00:11:22:33:44:55", bluetooth_name="")

    def test_rfcomm_channel_too_low_raises(self) -> None:
        """RFCOMM channel below 1 raises ValueError."""
        with pytest.raises(ValueError, match="rfcomm_channel"):
            TNCDevice(
                address="00:11:22:33:44:55",
                bluetooth_name="Test",
                rfcomm_channel=0,
            )

    def test_rfcomm_channel_too_high_raises(self) -> None:
        """RFCOMM channel above 30 raises ValueError."""
        with pytest.raises(ValueError, match="rfcomm_channel"):
            TNCDevice(
                address="00:11:22:33:44:55",
                bluetooth_name="Test",
                rfcomm_channel=31,
            )

    def test_friendly_name_too_long_raises(self) -> None:
        """Friendly name exceeding max length raises ValueError."""
        with pytest.raises(ValueError, match="friendly_name"):
            TNCDevice(
                address="00:11:22:33:44:55",
                bluetooth_name="Test",
                friendly_name="x" * (MAX_FRIENDLY_NAME_LENGTH + 1),
            )

    def test_empty_friendly_name_raises(self) -> None:
        """Empty string friendly_name raises ValueError."""
        with pytest.raises(ValueError, match="friendly_name"):
            TNCDevice(
                address="00:11:22:33:44:55",
                bluetooth_name="Test",
                friendly_name="",
            )

    def test_none_friendly_name_is_valid(self) -> None:
        """None friendly_name is valid (means not set)."""
        device = TNCDevice(
            address="00:11:22:33:44:55",
            bluetooth_name="Test",
            friendly_name=None,
        )
        assert device.friendly_name is None

    def test_display_name_uses_friendly_name(self) -> None:
        """display_name returns friendly_name when set."""
        device = TNCDevice(
            address="00:11:22:33:44:55",
            bluetooth_name="TH-D74",
            friendly_name="Mobile Rig",
        )
        assert device.display_name == "Mobile Rig"

    def test_display_name_falls_back_to_bluetooth_name(self) -> None:
        """display_name returns bluetooth_name when no friendly_name."""
        device = TNCDevice(
            address="00:11:22:33:44:55",
            bluetooth_name="TH-D74",
        )
        assert device.display_name == "TH-D74"


# =============================================================================
# TNCDevice Serialization Tests (T011)
# =============================================================================


class TestTNCDeviceSerialization:
    """Unit tests for TNCDevice to_dict/from_dict."""

    def test_to_dict_all_fields(self) -> None:
        """to_dict includes all fields."""
        now = datetime.now(UTC)
        device = TNCDevice(
            address="00:1A:7D:DA:71:13",
            bluetooth_name="TH-D74",
            friendly_name="Mobile Rig",
            rfcomm_channel=2,
            last_used=now,
            added_at=now,
        )
        data = device.to_dict()

        assert data["address"] == "00:1A:7D:DA:71:13"
        assert data["bluetooth_name"] == "TH-D74"
        assert data["friendly_name"] == "Mobile Rig"
        assert data["rfcomm_channel"] == 2
        assert data["last_used"] == now.isoformat()
        assert data["added_at"] == now.isoformat()

    def test_to_dict_null_optional_fields(self) -> None:
        """to_dict handles None optional fields."""
        device = TNCDevice(
            address="00:11:22:33:44:55",
            bluetooth_name="Test",
        )
        data = device.to_dict()

        assert data["friendly_name"] is None
        assert data["last_used"] is None

    def test_from_dict_creates_device(self) -> None:
        """from_dict creates valid TNCDevice."""
        data = {
            "address": "00:1A:7D:DA:71:13",
            "bluetooth_name": "TH-D74",
            "friendly_name": "Mobile Rig",
            "rfcomm_channel": 2,
            "last_used": "2026-03-06T10:30:00+00:00",
            "added_at": "2026-03-01T14:00:00+00:00",
        }
        device = TNCDevice.from_dict(data)

        assert device.address == "00:1A:7D:DA:71:13"
        assert device.bluetooth_name == "TH-D74"
        assert device.friendly_name == "Mobile Rig"
        assert device.rfcomm_channel == 2
        assert device.last_used is not None

    def test_from_dict_handles_missing_optional_fields(self) -> None:
        """from_dict works with missing optional fields."""
        data = {
            "address": "00:11:22:33:44:55",
            "bluetooth_name": "Test",
        }
        device = TNCDevice.from_dict(data)

        assert device.friendly_name is None
        assert device.last_used is None
        assert device.rfcomm_channel == 2  # default

    def test_round_trip_serialization(self) -> None:
        """TNCDevice survives to_dict/from_dict round trip."""
        now = datetime.now(UTC)
        original = TNCDevice(
            address="AA:BB:CC:DD:EE:FF",
            bluetooth_name="TNC3",
            friendly_name="Base Station",
            rfcomm_channel=1,
            last_used=now,
            added_at=now,
        )

        data = original.to_dict()
        restored = TNCDevice.from_dict(data)

        assert restored.address == original.address
        assert restored.bluetooth_name == original.bluetooth_name
        assert restored.friendly_name == original.friendly_name
        assert restored.rfcomm_channel == original.rfcomm_channel


# =============================================================================
# TNCHistory CRUD Tests (T013)
# =============================================================================


class TestTNCHistoryCRUD:
    """Unit tests for TNCHistory add/get/remove/list operations."""

    @pytest.fixture
    def history(self, tmp_path: Path) -> TNCHistory:
        """Provide a TNCHistory with a temp file."""
        return TNCHistory(path=tmp_path / "tnc-history.json")

    @pytest.fixture
    def sample_device(self) -> TNCDevice:
        """Provide a sample TNCDevice."""
        return TNCDevice(
            address="00:1A:7D:DA:71:13",
            bluetooth_name="TH-D74",
            rfcomm_channel=2,
        )

    def test_add_device(self, history: TNCHistory, sample_device: TNCDevice) -> None:
        """Adding a device stores it in history."""
        history.add(sample_device)
        assert len(history) == 1
        assert "00:1A:7D:DA:71:13" in history

    def test_add_duplicate_updates(self, history: TNCHistory) -> None:
        """Adding device with same address updates the entry."""
        device1 = TNCDevice(
            address="00:11:22:33:44:55",
            bluetooth_name="Original",
            rfcomm_channel=1,
        )
        device2 = TNCDevice(
            address="00:11:22:33:44:55",
            bluetooth_name="Updated",
            rfcomm_channel=2,
        )

        history.add(device1)
        history.add(device2)

        assert len(history) == 1
        stored = history.get("00:11:22:33:44:55")
        assert stored is not None
        assert stored.bluetooth_name == "Updated"
        assert stored.rfcomm_channel == 2

    def test_add_preserves_added_at(self, history: TNCHistory) -> None:
        """Updating a device preserves original added_at timestamp."""
        device1 = TNCDevice(
            address="00:11:22:33:44:55",
            bluetooth_name="Original",
        )
        original_added_at = device1.added_at

        history.add(device1)

        device2 = TNCDevice(
            address="00:11:22:33:44:55",
            bluetooth_name="Updated",
        )
        history.add(device2)

        stored = history.get("00:11:22:33:44:55")
        assert stored is not None
        assert stored.added_at == original_added_at

    def test_get_existing_device(self, history: TNCHistory, sample_device: TNCDevice) -> None:
        """Getting existing device returns it."""
        history.add(sample_device)
        result = history.get("00:1A:7D:DA:71:13")
        assert result is not None
        assert result.bluetooth_name == "TH-D74"

    def test_get_nonexistent_returns_none(self, history: TNCHistory) -> None:
        """Getting nonexistent address returns None."""
        assert history.get("00:11:22:33:44:55") is None

    def test_get_is_case_insensitive(self, history: TNCHistory, sample_device: TNCDevice) -> None:
        """Get works with different MAC address casing."""
        history.add(sample_device)
        result = history.get("00:1a:7d:da:71:13")
        assert result is not None

    def test_remove_device(self, history: TNCHistory, sample_device: TNCDevice) -> None:
        """Removing a device removes it from history."""
        history.add(sample_device)
        result = history.remove("00:1A:7D:DA:71:13")
        assert result is True
        assert len(history) == 0

    def test_remove_nonexistent_returns_false(self, history: TNCHistory) -> None:
        """Removing nonexistent address returns False."""
        result = history.remove("00:11:22:33:44:55")
        assert result is False

    def test_list_all_empty(self, history: TNCHistory) -> None:
        """list_all returns empty list for empty history."""
        assert history.list_all() == []

    def test_list_all_sorted_by_last_used(self, history: TNCHistory) -> None:
        """list_all returns devices sorted by last_used descending."""
        old_device = TNCDevice(
            address="00:11:22:33:44:55",
            bluetooth_name="Old",
            last_used=datetime(2026, 1, 1, tzinfo=UTC),
        )
        new_device = TNCDevice(
            address="AA:BB:CC:DD:EE:FF",
            bluetooth_name="New",
            last_used=datetime(2026, 3, 1, tzinfo=UTC),
        )

        history.add(old_device)
        history.add(new_device)

        result = history.list_all()
        assert len(result) == 2
        assert result[0].bluetooth_name == "New"
        assert result[1].bluetooth_name == "Old"

    def test_list_all_none_last_used_sorts_last(self, history: TNCHistory) -> None:
        """Devices with None last_used sort after used devices."""
        used_device = TNCDevice(
            address="00:11:22:33:44:55",
            bluetooth_name="Used",
            last_used=datetime(2026, 1, 1, tzinfo=UTC),
        )
        unused_device = TNCDevice(
            address="AA:BB:CC:DD:EE:FF",
            bluetooth_name="Unused",
            last_used=None,
        )

        history.add(unused_device)
        history.add(used_device)

        result = history.list_all()
        assert result[0].bluetooth_name == "Used"
        assert result[1].bluetooth_name == "Unused"

    def test_contains_check(self, history: TNCHistory, sample_device: TNCDevice) -> None:
        """'in' operator works for address check."""
        history.add(sample_device)
        assert "00:1A:7D:DA:71:13" in history
        assert "FF:FF:FF:FF:FF:FF" not in history


# =============================================================================
# TNCHistory Persistence Tests (T014)
# =============================================================================


class TestTNCHistoryPersistence:
    """Unit tests for TNCHistory JSON file persistence."""

    def test_save_creates_file(self, tmp_path: Path) -> None:
        """Adding a device creates the history file."""
        history_file = tmp_path / "tnc-history.json"
        history = TNCHistory(path=history_file)

        device = TNCDevice(
            address="00:11:22:33:44:55",
            bluetooth_name="Test",
        )
        history.add(device)

        assert history_file.exists()

    def test_saved_file_is_valid_json(self, tmp_path: Path) -> None:
        """Saved history file contains valid JSON."""
        history_file = tmp_path / "tnc-history.json"
        history = TNCHistory(path=history_file)

        device = TNCDevice(
            address="00:11:22:33:44:55",
            bluetooth_name="Test",
        )
        history.add(device)

        with history_file.open() as f:
            data = json.load(f)

        assert isinstance(data, dict)
        assert data["version"] == 1
        assert isinstance(data["devices"], list)
        assert len(data["devices"]) == 1

    def test_reload_preserves_data(self, tmp_path: Path) -> None:
        """History data survives save and reload (simulated restart)."""
        history_file = tmp_path / "tnc-history.json"

        # Create and save
        history1 = TNCHistory(path=history_file)
        history1.add(
            TNCDevice(
                address="00:11:22:33:44:55",
                bluetooth_name="Device1",
                rfcomm_channel=1,
            )
        )
        history1.add(
            TNCDevice(
                address="AA:BB:CC:DD:EE:FF",
                bluetooth_name="Device2",
                friendly_name="My TNC",
                rfcomm_channel=2,
            )
        )

        # Reload (simulate restart)
        history2 = TNCHistory(path=history_file)

        assert len(history2) == 2
        device1 = history2.get("00:11:22:33:44:55")
        assert device1 is not None
        assert device1.bluetooth_name == "Device1"

        device2 = history2.get("AA:BB:CC:DD:EE:FF")
        assert device2 is not None
        assert device2.friendly_name == "My TNC"

    def test_missing_file_starts_empty(self, tmp_path: Path) -> None:
        """Missing history file results in empty history."""
        history = TNCHistory(path=tmp_path / "nonexistent.json")
        assert len(history) == 0

    def test_corrupted_file_starts_empty(self, tmp_path: Path) -> None:
        """Corrupted history file results in empty history."""
        history_file = tmp_path / "corrupted.json"
        history_file.write_text("{ invalid json !!!")

        history = TNCHistory(path=history_file)
        assert len(history) == 0

    def test_invalid_format_starts_empty(self, tmp_path: Path) -> None:
        """History file with wrong format results in empty history."""
        history_file = tmp_path / "invalid.json"
        history_file.write_text('"just a string"')

        history = TNCHistory(path=history_file)
        assert len(history) == 0

    def test_remove_saves_to_file(self, tmp_path: Path) -> None:
        """Removing a device updates the file."""
        history_file = tmp_path / "tnc-history.json"
        history = TNCHistory(path=history_file)

        history.add(
            TNCDevice(
                address="00:11:22:33:44:55",
                bluetooth_name="Test",
            )
        )
        history.remove("00:11:22:33:44:55")

        # Reload and verify
        history2 = TNCHistory(path=history_file)
        assert len(history2) == 0

    def test_version_field_in_file(self, tmp_path: Path) -> None:
        """History file includes version field."""
        history_file = tmp_path / "tnc-history.json"
        history = TNCHistory(path=history_file)
        history.add(
            TNCDevice(
                address="00:11:22:33:44:55",
                bluetooth_name="Test",
            )
        )

        with history_file.open() as f:
            data = json.load(f)

        assert data["version"] == 1


# =============================================================================
# TNCHistory Persistence - US2 Tests (T028, T029)
# =============================================================================


class TestTNCHistoryRestart:
    """Unit tests for history persistence across restarts."""

    def test_file_created_on_first_write(self, tmp_path: Path) -> None:
        """History file is created on first device add."""
        history_file = tmp_path / "subdir" / "tnc-history.json"
        assert not history_file.exists()

        history = TNCHistory(path=history_file)
        history.add(
            TNCDevice(
                address="00:11:22:33:44:55",
                bluetooth_name="Test",
            )
        )

        assert history_file.exists()

    def test_reload_after_restart(self, tmp_path: Path) -> None:
        """Full restart simulation: create, save, destroy, reload."""
        history_file = tmp_path / "tnc-history.json"

        # Session 1
        h1 = TNCHistory(path=history_file)
        h1.add(
            TNCDevice(
                address="00:11:22:33:44:55",
                bluetooth_name="TNC-A",
                friendly_name="Alpha",
                rfcomm_channel=1,
            )
        )
        h1.add(
            TNCDevice(
                address="AA:BB:CC:DD:EE:FF",
                bluetooth_name="TNC-B",
                rfcomm_channel=2,
            )
        )
        h1.add(
            TNCDevice(
                address="11:22:33:44:55:66",
                bluetooth_name="TNC-C",
                friendly_name="Charlie",
                rfcomm_channel=3,
            )
        )

        # Session 2 (restart)
        h2 = TNCHistory(path=history_file)
        assert len(h2) == 3

        a = h2.get("00:11:22:33:44:55")
        assert a is not None
        assert a.bluetooth_name == "TNC-A"
        assert a.friendly_name == "Alpha"
        assert a.rfcomm_channel == 1

        b = h2.get("AA:BB:CC:DD:EE:FF")
        assert b is not None
        assert b.bluetooth_name == "TNC-B"
        assert b.friendly_name is None
        assert b.rfcomm_channel == 2


# =============================================================================
# TNCDevice last_used Tests (T048)
# =============================================================================


class TestTNCDeviceLastUsed:
    """Unit tests for last_used timestamp behavior."""

    def test_last_used_updates_on_set(self, tmp_path: Path) -> None:
        """last_used can be updated after creation."""
        device = TNCDevice(
            address="00:11:22:33:44:55",
            bluetooth_name="Test",
        )
        assert device.last_used is None

        now = datetime.now(UTC)
        device.last_used = now
        assert device.last_used == now

    def test_last_used_persists_through_save(self, tmp_path: Path) -> None:
        """last_used timestamp survives save and reload."""
        history_file = tmp_path / "tnc-history.json"
        now = datetime.now(UTC)

        h1 = TNCHistory(path=history_file)
        device = TNCDevice(
            address="00:11:22:33:44:55",
            bluetooth_name="Test",
            last_used=now,
        )
        h1.add(device)

        h2 = TNCHistory(path=history_file)
        loaded = h2.get("00:11:22:33:44:55")
        assert loaded is not None
        assert loaded.last_used is not None
