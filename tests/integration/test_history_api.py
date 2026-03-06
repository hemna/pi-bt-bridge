"""Integration tests for TNC history API endpoints.

Tests the WebService TNC history handler methods using mocked aiohttp
request/response objects. Validates the full flow from HTTP request
through to TNCHistory persistence and back.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Configuration
from src.models.tnc_history import TNCDevice, TNCHistory

# =============================================================================
# Module-level aiohttp mock setup
# =============================================================================

# We need to mock aiohttp before importing web_service.
# Store original module refs so we can restore them.
_orig_modules: dict[str, object] = {}


def _json_response(data, **kwargs):
    """Fake web.json_response that returns a plain dict."""
    return {"body": data, "status": kwargs.get("status", 200)}


# Create mock web module with a real side_effect on json_response
_mock_web = MagicMock()
_mock_web.json_response = MagicMock(side_effect=_json_response)
_mock_web.Request = MagicMock
_mock_web.Response = MagicMock
_mock_web.StreamResponse = MagicMock

# Install mocks before importing web_service
for mod_name in ("aiohttp", "aiohttp.web", "jinja2", "aiohttp_jinja2"):
    _orig_modules[mod_name] = sys.modules.get(mod_name)

sys.modules["aiohttp"] = MagicMock()
sys.modules["aiohttp.web"] = _mock_web
sys.modules["jinja2"] = MagicMock()
sys.modules["aiohttp_jinja2"] = MagicMock()

# Now import web_service - it will pick up our mocked aiohttp
import src.services.web_service as _ws_mod  # noqa: E402
from src.services.web_service import WebService  # noqa: E402

_ws_mod.web = _mock_web


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _reset_json_response_mock():
    """Reset the json_response mock call history before each test."""
    _mock_web.json_response.reset_mock()
    _mock_web.json_response.side_effect = _json_response
    yield


@pytest.fixture
def tmp_history_file(tmp_path):
    """Provide a temporary history file path."""
    return str(tmp_path / "test-history.json")


@pytest.fixture
def config(tmp_path, tmp_history_file):
    """Provide a test configuration."""
    return Configuration(
        target_address="00:11:22:33:44:55",
        target_pin="1234",
        device_name="TestBridge",
        history_file=tmp_history_file,
    )


@pytest.fixture
def tnc_history(tmp_history_file):
    """Provide a fresh TNCHistory instance."""
    return TNCHistory(path=tmp_history_file)


@pytest.fixture
def sample_device():
    """Provide a sample TNCDevice."""
    return TNCDevice(
        address="AA:BB:CC:DD:EE:FF",
        bluetooth_name="Mobilinkd TNC3",
        friendly_name="Base Station",
        rfcomm_channel=1,
    )


@pytest.fixture
def sample_device_2():
    """Provide a second sample TNCDevice."""
    return TNCDevice(
        address="11:22:33:44:55:66",
        bluetooth_name="TH-D74",
        friendly_name=None,
        rfcomm_channel=2,
    )


@pytest.fixture
def web_service(config):
    """Provide a WebService instance with mocked dependencies."""
    ws = WebService(
        host="127.0.0.1",
        port=8080,
        config=config,
        bridge_state=None,
    )
    return ws


def _make_mock_request(
    match_info: dict | None = None,
    json_data: dict | None = None,
    json_error: bool = False,
) -> MagicMock:
    """Create a mock aiohttp request.

    Args:
        match_info: URL path parameters.
        json_data: JSON body data.
        json_error: If True, request.json() raises JSONDecodeError.

    Returns:
        Mock request object.
    """
    request = MagicMock()
    request.match_info = match_info or {}

    if json_error:
        request.json = AsyncMock(side_effect=json.JSONDecodeError("test", "", 0))
    elif json_data is not None:
        request.json = AsyncMock(return_value=json_data)
    else:
        request.json = AsyncMock(return_value={})

    return request


# =============================================================================
# Tests: Model-level integration (TNCHistory + TNCDevice persistence)
# =============================================================================


class TestTNCHistoryIntegration:
    """Integration tests for TNCHistory persistence across operations."""

    def test_add_then_list_returns_device(
        self, tnc_history: TNCHistory, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Empty history
        WHEN: A device is added
        THEN: It appears in list_all
        """
        tnc_history.add(sample_device)
        devices = tnc_history.list_all()
        assert len(devices) == 1
        assert devices[0].address == sample_device.address

    def test_add_update_preserves_added_at(
        self, tnc_history: TNCHistory, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device in history
        WHEN: Same device is added again with updated name
        THEN: added_at is preserved, other fields updated
        """
        tnc_history.add(sample_device)
        original_added_at = tnc_history.get(sample_device.address).added_at

        updated = TNCDevice(
            address=sample_device.address,
            bluetooth_name="Updated Name",
            rfcomm_channel=3,
        )
        tnc_history.add(updated)

        result = tnc_history.get(sample_device.address)
        assert result.added_at == original_added_at
        assert result.bluetooth_name == "Updated Name"
        assert result.rfcomm_channel == 3

    def test_multiple_devices_sorted_by_last_used(
        self,
        tnc_history: TNCHistory,
        sample_device: TNCDevice,
        sample_device_2: TNCDevice,
    ) -> None:
        """
        GIVEN: Two devices in history
        WHEN: One has more recent last_used
        THEN: list_all returns most recently used first
        """
        sample_device.last_used = datetime(2026, 1, 1, tzinfo=UTC)
        sample_device_2.last_used = datetime(2026, 3, 1, tzinfo=UTC)

        tnc_history.add(sample_device)
        tnc_history.add(sample_device_2)

        devices = tnc_history.list_all()
        assert len(devices) == 2
        assert devices[0].address == sample_device_2.address
        assert devices[1].address == sample_device.address

    def test_remove_then_get_returns_none(
        self, tnc_history: TNCHistory, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device in history
        WHEN: Device is removed
        THEN: get() returns None
        """
        tnc_history.add(sample_device)
        tnc_history.remove(sample_device.address)
        assert tnc_history.get(sample_device.address) is None

    def test_persistence_survives_reload(
        self,
        tmp_history_file: str,
        sample_device: TNCDevice,
        sample_device_2: TNCDevice,
    ) -> None:
        """
        GIVEN: History with multiple devices saved to disk
        WHEN: A new TNCHistory is created from same file
        THEN: All devices are restored correctly
        """
        history1 = TNCHistory(path=tmp_history_file)
        history1.add(sample_device)
        history1.add(sample_device_2)

        # Simulate daemon restart
        history2 = TNCHistory(path=tmp_history_file)
        assert len(history2) == 2

        restored = history2.get(sample_device.address)
        assert restored is not None
        assert restored.bluetooth_name == sample_device.bluetooth_name
        assert restored.friendly_name == sample_device.friendly_name

    def test_add_remove_add_cycle(self, tnc_history: TNCHistory, sample_device: TNCDevice) -> None:
        """
        GIVEN: Empty history
        WHEN: Device is added, removed, then added again
        THEN: Device exists with fresh added_at
        """
        tnc_history.add(sample_device)
        original_added_at = tnc_history.get(sample_device.address).added_at

        tnc_history.remove(sample_device.address)
        assert len(tnc_history) == 0

        # Re-add with new timestamp
        new_device = TNCDevice(
            address=sample_device.address,
            bluetooth_name=sample_device.bluetooth_name,
            rfcomm_channel=sample_device.rfcomm_channel,
        )
        tnc_history.add(new_device)
        restored = tnc_history.get(sample_device.address)
        assert restored is not None
        # added_at should be fresh (not the original)
        assert restored.added_at >= original_added_at


# =============================================================================
# Tests: API handler integration
# =============================================================================


class TestTNCHistoryAPIList:
    """Tests for GET /api/tnc-history."""

    @pytest.mark.asyncio
    async def test_list_empty_history(self, web_service: WebService) -> None:
        """
        GIVEN: Empty TNC history
        WHEN: GET /api/tnc-history
        THEN: Returns empty device list with count 0
        """
        request = _make_mock_request()
        result = await web_service._handle_api_tnc_history_list(request)

        assert result["body"]["count"] == 0
        assert result["body"]["devices"] == []
        assert result["body"]["current_address"] == web_service.config.target_address

    @pytest.mark.asyncio
    async def test_list_with_devices(
        self, web_service: WebService, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: History with one device
        WHEN: GET /api/tnc-history
        THEN: Returns device list with count 1
        """
        web_service._tnc_history.add(sample_device)

        request = _make_mock_request()
        result = await web_service._handle_api_tnc_history_list(request)

        assert result["body"]["count"] == 1
        assert len(result["body"]["devices"]) == 1
        assert result["body"]["devices"][0]["address"] == sample_device.address

    @pytest.mark.asyncio
    async def test_list_includes_is_current_flag(self, web_service: WebService) -> None:
        """
        GIVEN: Device matching current target_address
        WHEN: GET /api/tnc-history
        THEN: Device has is_current=True
        """
        device = TNCDevice(
            address=web_service.config.target_address,
            bluetooth_name="Current TNC",
            rfcomm_channel=2,
        )
        web_service._tnc_history.add(device)

        request = _make_mock_request()
        result = await web_service._handle_api_tnc_history_list(request)

        assert result["body"]["devices"][0]["is_current"] is True


class TestTNCHistoryAPIGet:
    """Tests for GET /api/tnc-history/{address}."""

    @pytest.mark.asyncio
    async def test_get_existing_device(
        self, web_service: WebService, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device in history
        WHEN: GET /api/tnc-history/{address}
        THEN: Returns device details with 200
        """
        web_service._tnc_history.add(sample_device)

        request = _make_mock_request(match_info={"address": sample_device.address})
        result = await web_service._handle_api_tnc_history_get(request)

        assert result["status"] == 200
        assert result["body"]["address"] == sample_device.address
        assert result["body"]["bluetooth_name"] == sample_device.bluetooth_name

    @pytest.mark.asyncio
    async def test_get_nonexistent_device(self, web_service: WebService) -> None:
        """
        GIVEN: Empty history
        WHEN: GET /api/tnc-history/{address} with unknown address
        THEN: Returns 404 with error message
        """
        request = _make_mock_request(match_info={"address": "FF:FF:FF:FF:FF:FF"})
        result = await web_service._handle_api_tnc_history_get(request)

        assert result["status"] == 404
        assert result["body"]["success"] is False
        assert "not found" in result["body"]["message"]


class TestTNCHistoryAPIAdd:
    """Tests for POST /api/tnc-history."""

    @pytest.mark.asyncio
    async def test_add_new_device(self, web_service: WebService) -> None:
        """
        GIVEN: Empty history
        WHEN: POST /api/tnc-history with valid device data
        THEN: Returns 201 and device is persisted
        """
        request = _make_mock_request(
            json_data={
                "address": "AA:BB:CC:DD:EE:FF",
                "bluetooth_name": "Mobilinkd TNC3",
                "rfcomm_channel": 1,
            }
        )

        result = await web_service._handle_api_tnc_history_add(request)

        assert result["status"] == 201
        assert result["body"]["success"] is True
        assert "added" in result["body"]["message"]

        # Verify persistence
        device = web_service._tnc_history.get("AA:BB:CC:DD:EE:FF")
        assert device is not None
        assert device.bluetooth_name == "Mobilinkd TNC3"

    @pytest.mark.asyncio
    async def test_add_existing_device_returns_200(
        self, web_service: WebService, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device already in history
        WHEN: POST /api/tnc-history with same address
        THEN: Returns 200 (update) not 201 (create)
        """
        web_service._tnc_history.add(sample_device)

        request = _make_mock_request(
            json_data={
                "address": sample_device.address,
                "bluetooth_name": "Updated Name",
                "rfcomm_channel": 3,
            }
        )

        result = await web_service._handle_api_tnc_history_add(request)

        assert result["status"] == 200
        assert "updated" in result["body"]["message"]

    @pytest.mark.asyncio
    async def test_add_invalid_mac_returns_400(self, web_service: WebService) -> None:
        """
        GIVEN: POST with invalid MAC address
        WHEN: Validation runs
        THEN: Returns 400 with error details
        """
        request = _make_mock_request(
            json_data={
                "address": "invalid-mac",
                "bluetooth_name": "Test",
                "rfcomm_channel": 1,
            }
        )

        result = await web_service._handle_api_tnc_history_add(request)

        assert result["status"] == 400
        assert result["body"]["success"] is False
        assert "address" in result["body"]["errors"]

    @pytest.mark.asyncio
    async def test_add_missing_bluetooth_name_returns_400(self, web_service: WebService) -> None:
        """
        GIVEN: POST without bluetooth_name
        WHEN: Validation runs
        THEN: Returns 400 with error
        """
        request = _make_mock_request(
            json_data={
                "address": "AA:BB:CC:DD:EE:FF",
                "rfcomm_channel": 1,
            }
        )

        result = await web_service._handle_api_tnc_history_add(request)

        assert result["status"] == 400
        assert "bluetooth_name" in result["body"]["errors"]

    @pytest.mark.asyncio
    async def test_add_invalid_rfcomm_channel_returns_400(self, web_service: WebService) -> None:
        """
        GIVEN: POST with rfcomm_channel out of range
        WHEN: Validation runs
        THEN: Returns 400 with error
        """
        request = _make_mock_request(
            json_data={
                "address": "AA:BB:CC:DD:EE:FF",
                "bluetooth_name": "Test",
                "rfcomm_channel": 99,
            }
        )

        result = await web_service._handle_api_tnc_history_add(request)

        assert result["status"] == 400
        assert "rfcomm_channel" in result["body"]["errors"]

    @pytest.mark.asyncio
    async def test_add_invalid_json_returns_400(self, web_service: WebService) -> None:
        """
        GIVEN: POST with malformed JSON body
        WHEN: Parsing fails
        THEN: Returns 400
        """
        request = _make_mock_request(json_error=True)

        result = await web_service._handle_api_tnc_history_add(request)

        assert result["status"] == 400
        assert "Invalid JSON" in result["body"]["message"]

    @pytest.mark.asyncio
    async def test_add_with_friendly_name(self, web_service: WebService) -> None:
        """
        GIVEN: POST with optional friendly_name
        WHEN: Device is added
        THEN: friendly_name is persisted
        """
        request = _make_mock_request(
            json_data={
                "address": "AA:BB:CC:DD:EE:FF",
                "bluetooth_name": "Mobilinkd TNC3",
                "friendly_name": "My TNC",
                "rfcomm_channel": 1,
            }
        )

        result = await web_service._handle_api_tnc_history_add(request)

        assert result["status"] == 201
        device = web_service._tnc_history.get("AA:BB:CC:DD:EE:FF")
        assert device.friendly_name == "My TNC"


class TestTNCHistoryAPIUpdate:
    """Tests for PUT /api/tnc-history/{address}."""

    @pytest.mark.asyncio
    async def test_update_friendly_name(
        self, web_service: WebService, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device in history
        WHEN: PUT with new friendly_name
        THEN: Name is updated, other fields preserved
        """
        web_service._tnc_history.add(sample_device)

        request = _make_mock_request(
            match_info={"address": sample_device.address},
            json_data={"friendly_name": "New Name"},
        )

        result = await web_service._handle_api_tnc_history_update(request)

        assert result["status"] == 200
        assert result["body"]["success"] is True

        updated = web_service._tnc_history.get(sample_device.address)
        assert updated.friendly_name == "New Name"
        assert updated.bluetooth_name == sample_device.bluetooth_name

    @pytest.mark.asyncio
    async def test_update_rfcomm_channel(
        self, web_service: WebService, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device in history
        WHEN: PUT with new rfcomm_channel
        THEN: Channel is updated
        """
        web_service._tnc_history.add(sample_device)

        request = _make_mock_request(
            match_info={"address": sample_device.address},
            json_data={"rfcomm_channel": 5},
        )

        result = await web_service._handle_api_tnc_history_update(request)

        assert result["status"] == 200
        updated = web_service._tnc_history.get(sample_device.address)
        assert updated.rfcomm_channel == 5

    @pytest.mark.asyncio
    async def test_update_clear_friendly_name(
        self, web_service: WebService, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device with friendly_name
        WHEN: PUT with friendly_name=null
        THEN: friendly_name is cleared
        """
        web_service._tnc_history.add(sample_device)
        assert sample_device.friendly_name is not None

        request = _make_mock_request(
            match_info={"address": sample_device.address},
            json_data={"friendly_name": None},
        )

        result = await web_service._handle_api_tnc_history_update(request)

        assert result["status"] == 200
        updated = web_service._tnc_history.get(sample_device.address)
        assert updated.friendly_name is None

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_404(self, web_service: WebService) -> None:
        """
        GIVEN: Empty history
        WHEN: PUT /api/tnc-history/{address}
        THEN: Returns 404
        """
        request = _make_mock_request(
            match_info={"address": "FF:FF:FF:FF:FF:FF"},
            json_data={"friendly_name": "Test"},
        )

        result = await web_service._handle_api_tnc_history_update(request)

        assert result["status"] == 404
        assert result["body"]["success"] is False

    @pytest.mark.asyncio
    async def test_update_invalid_rfcomm_returns_400(
        self, web_service: WebService, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device in history
        WHEN: PUT with invalid rfcomm_channel
        THEN: Returns 400
        """
        web_service._tnc_history.add(sample_device)

        request = _make_mock_request(
            match_info={"address": sample_device.address},
            json_data={"rfcomm_channel": 99},
        )

        result = await web_service._handle_api_tnc_history_update(request)

        assert result["status"] == 400

    @pytest.mark.asyncio
    async def test_update_empty_friendly_name_returns_400(
        self, web_service: WebService, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device in history
        WHEN: PUT with empty string friendly_name
        THEN: Returns 400 (empty not allowed, use null to clear)
        """
        web_service._tnc_history.add(sample_device)

        request = _make_mock_request(
            match_info={"address": sample_device.address},
            json_data={"friendly_name": ""},
        )

        result = await web_service._handle_api_tnc_history_update(request)

        assert result["status"] == 400

    @pytest.mark.asyncio
    async def test_update_too_long_friendly_name_returns_400(
        self, web_service: WebService, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device in history
        WHEN: PUT with friendly_name > 50 chars
        THEN: Returns 400
        """
        web_service._tnc_history.add(sample_device)

        request = _make_mock_request(
            match_info={"address": sample_device.address},
            json_data={"friendly_name": "A" * 51},
        )

        result = await web_service._handle_api_tnc_history_update(request)

        assert result["status"] == 400


class TestTNCHistoryAPIDelete:
    """Tests for DELETE /api/tnc-history/{address}."""

    @pytest.mark.asyncio
    async def test_delete_existing_device(
        self, web_service: WebService, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device in history (not the current target)
        WHEN: DELETE /api/tnc-history/{address}
        THEN: Device is removed, returns 200
        """
        web_service._tnc_history.add(sample_device)

        request = _make_mock_request(match_info={"address": sample_device.address})

        result = await web_service._handle_api_tnc_history_delete(request)

        assert result["status"] == 200
        assert result["body"]["success"] is True
        assert web_service._tnc_history.get(sample_device.address) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, web_service: WebService) -> None:
        """
        GIVEN: Empty history
        WHEN: DELETE /api/tnc-history/{address}
        THEN: Returns 404
        """
        request = _make_mock_request(match_info={"address": "FF:FF:FF:FF:FF:FF"})

        result = await web_service._handle_api_tnc_history_delete(request)

        assert result["status"] == 404
        assert result["body"]["success"] is False

    @pytest.mark.asyncio
    async def test_delete_current_target_returns_409(self, web_service: WebService) -> None:
        """
        GIVEN: Device that is the current target_address
        WHEN: DELETE /api/tnc-history/{address}
        THEN: Returns 409 Conflict
        """
        current_device = TNCDevice(
            address=web_service.config.target_address,
            bluetooth_name="Current TNC",
            rfcomm_channel=2,
        )
        web_service._tnc_history.add(current_device)

        request = _make_mock_request(match_info={"address": web_service.config.target_address})

        result = await web_service._handle_api_tnc_history_delete(request)

        assert result["status"] == 409
        assert result["body"]["success"] is False
        assert "Cannot remove" in result["body"]["message"]

        # Device should still exist
        assert web_service._tnc_history.get(web_service.config.target_address) is not None


class TestTNCHistoryAPISelect:
    """Tests for POST /api/tnc-history/{address}/select."""

    @pytest.mark.asyncio
    async def test_select_paired_device(
        self, web_service: WebService, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device in history that is paired
        WHEN: POST /api/tnc-history/{address}/select
        THEN: Config is updated, returns 200 with connecting=True
        """
        web_service._tnc_history.add(sample_device)
        web_service._check_device_paired = MagicMock(return_value=True)

        with patch.object(_ws_mod, "save_config"):
            request = _make_mock_request(match_info={"address": sample_device.address})
            result = await web_service._handle_api_tnc_history_select(request)

        assert result["status"] == 200
        assert result["body"]["success"] is True
        assert result["body"]["connecting"] is True
        assert web_service.config.target_address == sample_device.address

    @pytest.mark.asyncio
    async def test_select_updates_last_used(
        self, web_service: WebService, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device in history
        WHEN: Device is selected
        THEN: last_used timestamp is updated
        """
        web_service._tnc_history.add(sample_device)
        web_service._check_device_paired = MagicMock(return_value=True)

        before = datetime.now(UTC)
        with patch.object(_ws_mod, "save_config"):
            request = _make_mock_request(match_info={"address": sample_device.address})
            await web_service._handle_api_tnc_history_select(request)

        device = web_service._tnc_history.get(sample_device.address)
        assert device.last_used is not None
        assert device.last_used >= before

    @pytest.mark.asyncio
    async def test_select_nonexistent_returns_404(self, web_service: WebService) -> None:
        """
        GIVEN: Empty history
        WHEN: POST /api/tnc-history/{address}/select
        THEN: Returns 404
        """
        request = _make_mock_request(match_info={"address": "FF:FF:FF:FF:FF:FF"})

        result = await web_service._handle_api_tnc_history_select(request)

        assert result["status"] == 404

    @pytest.mark.asyncio
    async def test_select_unpaired_returns_400(
        self, web_service: WebService, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device in history but NOT paired
        WHEN: POST /api/tnc-history/{address}/select
        THEN: Returns 400 with is_paired=False
        """
        web_service._tnc_history.add(sample_device)
        web_service._check_device_paired = MagicMock(return_value=False)

        request = _make_mock_request(match_info={"address": sample_device.address})

        result = await web_service._handle_api_tnc_history_select(request)

        assert result["status"] == 400
        assert result["body"]["is_paired"] is False

    @pytest.mark.asyncio
    async def test_select_updates_rfcomm_in_config(
        self, web_service: WebService, sample_device: TNCDevice
    ) -> None:
        """
        GIVEN: Device with rfcomm_channel=1
        WHEN: Device is selected
        THEN: Config rfcomm_channel is updated to match
        """
        assert sample_device.rfcomm_channel == 1
        web_service._tnc_history.add(sample_device)
        web_service._check_device_paired = MagicMock(return_value=True)

        with patch.object(_ws_mod, "save_config"):
            request = _make_mock_request(match_info={"address": sample_device.address})
            await web_service._handle_api_tnc_history_select(request)

        assert web_service.config.rfcomm_channel == 1


class TestTNCHistoryAutoAdd:
    """Tests for auto-add to history from /api/pairing/use."""

    @pytest.mark.asyncio
    async def test_pairing_use_adds_to_history(self, web_service: WebService) -> None:
        """
        GIVEN: A device is selected via /api/pairing/use
        WHEN: The endpoint completes successfully
        THEN: Device is auto-added to TNC history
        """
        # Mock pairing manager with discovered device
        mock_pm = MagicMock()
        mock_device = MagicMock()
        mock_device.address = "AA:BB:CC:DD:EE:FF"
        mock_device.name = "Mobilinkd TNC3"
        mock_pm.session.discovered_devices = [mock_device]
        web_service._get_pairing_manager = MagicMock(return_value=mock_pm)

        request = _make_mock_request(
            json_data={
                "address": "AA:BB:CC:DD:EE:FF",
            }
        )

        with patch.object(_ws_mod, "save_config"):
            await web_service._handle_api_pairing_use(request)

        # Verify device was added to history
        device = web_service._tnc_history.get("AA:BB:CC:DD:EE:FF")
        assert device is not None
        assert device.bluetooth_name == "Mobilinkd TNC3"

    @pytest.mark.asyncio
    async def test_pairing_use_unknown_name_defaults(self, web_service: WebService) -> None:
        """
        GIVEN: Device not found in discovered devices
        WHEN: /api/pairing/use is called
        THEN: Device is added with bluetooth_name="Unknown"
        """
        mock_pm = MagicMock()
        mock_pm.session.discovered_devices = []  # No discovered devices
        web_service._get_pairing_manager = MagicMock(return_value=mock_pm)

        request = _make_mock_request(
            json_data={
                "address": "AA:BB:CC:DD:EE:FF",
            }
        )

        with patch.object(_ws_mod, "save_config"):
            await web_service._handle_api_pairing_use(request)

        device = web_service._tnc_history.get("AA:BB:CC:DD:EE:FF")
        assert device is not None
        assert device.bluetooth_name == "Unknown"


# =============================================================================
# End-to-end flow tests
# =============================================================================


class TestTNCHistoryE2EFlow:
    """End-to-end tests simulating complete user workflows."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_add_update_select_delete(self, web_service: WebService) -> None:
        """
        GIVEN: Empty history
        WHEN: User adds, updates, selects, and removes a device
        THEN: Each operation succeeds and state is consistent
        """
        web_service._check_device_paired = MagicMock(return_value=True)

        # 1. Add device
        request = _make_mock_request(
            json_data={
                "address": "AA:BB:CC:DD:EE:FF",
                "bluetooth_name": "Mobilinkd TNC3",
                "rfcomm_channel": 1,
            }
        )
        result = await web_service._handle_api_tnc_history_add(request)
        assert result["status"] == 201

        # 2. Update friendly name
        request = _make_mock_request(
            match_info={"address": "AA:BB:CC:DD:EE:FF"},
            json_data={"friendly_name": "My TNC"},
        )
        result = await web_service._handle_api_tnc_history_update(request)
        assert result["status"] == 200
        assert result["body"]["device"]["display_name"] == "My TNC"

        # 3. Select as active
        with patch.object(_ws_mod, "save_config"):
            request = _make_mock_request(match_info={"address": "AA:BB:CC:DD:EE:FF"})
            result = await web_service._handle_api_tnc_history_select(request)
        assert result["status"] == 200
        assert web_service.config.target_address == "AA:BB:CC:DD:EE:FF"

        # 4. Add second device
        request = _make_mock_request(
            json_data={
                "address": "11:22:33:44:55:66",
                "bluetooth_name": "TH-D74",
                "rfcomm_channel": 2,
            }
        )
        result = await web_service._handle_api_tnc_history_add(request)
        assert result["status"] == 201

        # 5. Switch to second device
        with patch.object(_ws_mod, "save_config"):
            request = _make_mock_request(match_info={"address": "11:22:33:44:55:66"})
            result = await web_service._handle_api_tnc_history_select(request)
        assert result["status"] == 200
        assert web_service.config.target_address == "11:22:33:44:55:66"

        # 6. Delete first device (no longer active)
        request = _make_mock_request(match_info={"address": "AA:BB:CC:DD:EE:FF"})
        result = await web_service._handle_api_tnc_history_delete(request)
        assert result["status"] == 200

        # 7. Verify final state
        request = _make_mock_request()
        result = await web_service._handle_api_tnc_history_list(request)
        assert result["body"]["count"] == 1
        assert result["body"]["devices"][0]["address"] == "11:22:33:44:55:66"

    @pytest.mark.asyncio
    async def test_pair_then_quick_switch(self, web_service: WebService) -> None:
        """
        GIVEN: User pairs two TNCs via pairing flow
        WHEN: User switches between them via history
        THEN: Quick switch works and history is maintained
        """
        web_service._check_device_paired = MagicMock(return_value=True)

        # Simulate two devices paired via /api/pairing/use
        for addr, name in [
            ("AA:BB:CC:DD:EE:FF", "Mobilinkd TNC3"),
            ("11:22:33:44:55:66", "TH-D74"),
        ]:
            mock_pm = MagicMock()
            mock_device = MagicMock()
            mock_device.address = addr
            mock_device.name = name
            mock_pm.session.discovered_devices = [mock_device]
            web_service._get_pairing_manager = MagicMock(return_value=mock_pm)

            with patch.object(_ws_mod, "save_config"):
                request = _make_mock_request(json_data={"address": addr})
                await web_service._handle_api_pairing_use(request)

        # Both should be in history
        request = _make_mock_request()
        result = await web_service._handle_api_tnc_history_list(request)
        assert result["body"]["count"] == 2

        # Quick switch to first
        with patch.object(_ws_mod, "save_config"):
            request = _make_mock_request(match_info={"address": "AA:BB:CC:DD:EE:FF"})
            result = await web_service._handle_api_tnc_history_select(request)
        assert result["status"] == 200
        assert web_service.config.target_address == "AA:BB:CC:DD:EE:FF"

        # Quick switch to second
        with patch.object(_ws_mod, "save_config"):
            request = _make_mock_request(match_info={"address": "11:22:33:44:55:66"})
            result = await web_service._handle_api_tnc_history_select(request)
        assert result["status"] == 200
        assert web_service.config.target_address == "11:22:33:44:55:66"
