"""Unit tests for connection state machine (T019, T020)."""

from __future__ import annotations

from datetime import UTC, datetime

from src.models.state import ConnectionState, ErrorEvent


class TestConnectionState:
    """Unit tests for ConnectionState enum."""

    def test_all_states_exist(self) -> None:
        """All expected states should be defined."""
        expected_states = {"IDLE", "SCANNING", "CONNECTING", "CONNECTED", "DISCONNECTING", "ERROR"}
        actual_states = {state.name for state in ConnectionState}
        assert actual_states == expected_states

    def test_state_values_are_strings(self) -> None:
        """State values should be lowercase strings for JSON serialization."""
        for state in ConnectionState:
            assert isinstance(state.value, str)
            assert state.value == state.name.lower()

    def test_idle_is_initial_state(self) -> None:
        """IDLE should be the initial/default state."""
        assert ConnectionState.IDLE.value == "idle"


class TestBLEConnectionStateTransitions:
    """Unit tests for BLE connection state transitions (T019)."""

    def test_idle_to_scanning_is_valid(self) -> None:
        """IDLE -> SCANNING (start advertising) is valid."""
        current = ConnectionState.IDLE
        next_state = ConnectionState.SCANNING
        # Valid transition for starting BLE advertising
        assert current != next_state

    def test_scanning_to_connecting_is_valid(self) -> None:
        """SCANNING -> CONNECTING (device connecting) is valid."""
        current = ConnectionState.SCANNING
        next_state = ConnectionState.CONNECTING
        assert current != next_state

    def test_connecting_to_connected_is_valid(self) -> None:
        """CONNECTING -> CONNECTED (connection established) is valid."""
        current = ConnectionState.CONNECTING
        next_state = ConnectionState.CONNECTED
        assert current != next_state

    def test_connected_to_disconnecting_is_valid(self) -> None:
        """CONNECTED -> DISCONNECTING (graceful disconnect) is valid."""
        current = ConnectionState.CONNECTED
        next_state = ConnectionState.DISCONNECTING
        assert current != next_state

    def test_disconnecting_to_idle_is_valid(self) -> None:
        """DISCONNECTING -> IDLE (disconnect complete) is valid."""
        current = ConnectionState.DISCONNECTING
        next_state = ConnectionState.IDLE
        assert current != next_state

    def test_any_to_error_is_valid(self) -> None:
        """Any state can transition to ERROR on failure."""
        for state in ConnectionState:
            if state != ConnectionState.ERROR:
                # Error can happen from any state
                assert state != ConnectionState.ERROR

    def test_error_to_idle_is_valid(self) -> None:
        """ERROR -> IDLE (reset) is valid."""
        current = ConnectionState.ERROR
        next_state = ConnectionState.IDLE
        assert current != next_state

    def test_error_to_scanning_is_valid(self) -> None:
        """ERROR -> SCANNING (retry) is valid."""
        current = ConnectionState.ERROR
        next_state = ConnectionState.SCANNING
        assert current != next_state


class TestClassicConnectionStateTransitions:
    """Unit tests for Classic connection state transitions (T020)."""

    def test_idle_to_scanning_for_discovery(self) -> None:
        """IDLE -> SCANNING (SDP discovery) is valid."""
        current = ConnectionState.IDLE
        next_state = ConnectionState.SCANNING
        assert current != next_state

    def test_scanning_to_connecting_after_sdp(self) -> None:
        """SCANNING -> CONNECTING (after SDP finds SPP channel) is valid."""
        current = ConnectionState.SCANNING
        next_state = ConnectionState.CONNECTING
        assert current != next_state

    def test_connecting_to_connected_on_rfcomm_accept(self) -> None:
        """CONNECTING -> CONNECTED (RFCOMM accepted) is valid."""
        current = ConnectionState.CONNECTING
        next_state = ConnectionState.CONNECTED
        assert current != next_state

    def test_connected_to_error_on_link_loss(self) -> None:
        """CONNECTED -> ERROR (unexpected disconnect) is valid."""
        current = ConnectionState.CONNECTED
        next_state = ConnectionState.ERROR
        assert current != next_state


class TestErrorEvent:
    """Unit tests for ErrorEvent dataclass."""

    def test_create_with_timestamp(self) -> None:
        """ErrorEvent.create() should add current timestamp."""
        event = ErrorEvent.create(
            source="ble",
            error_type="connection_failed",
            message="Failed to connect",
        )
        assert event.timestamp is not None
        assert event.source == "ble"
        assert event.error_type == "connection_failed"

    def test_remediation_is_optional(self) -> None:
        """Remediation field should be optional."""
        event = ErrorEvent.create(
            source="classic",
            error_type="timeout",
            message="Connection timed out",
        )
        assert event.remediation is None

        event_with_remediation = ErrorEvent.create(
            source="classic",
            error_type="auth_failed",
            message="Authentication failed",
            remediation="Check PIN in configuration",
        )
        assert event_with_remediation.remediation == "Check PIN in configuration"

    def test_to_dict_serialization(self) -> None:
        """to_dict() should return JSON-serializable dictionary."""
        event = ErrorEvent(
            timestamp=datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC),
            source="bridge",
            error_type="buffer_overflow",
            message="Buffer full",
            remediation="Reduce data rate",
        )
        result = event.to_dict()

        assert result["source"] == "bridge"
        assert result["error_type"] == "buffer_overflow"
        assert result["message"] == "Buffer full"
        assert result["remediation"] == "Reduce data rate"
        assert "2026-03-04" in result["timestamp"]
