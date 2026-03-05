"""Bluetooth device scanner service using D-Bus BlueZ API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.web.models import DiscoveredDevice, PairingSession, PairingState

logger = logging.getLogger("bt-bridge.scanner")

# BlueZ D-Bus constants
BLUEZ_SERVICE = "org.bluez"
ADAPTER_INTERFACE = "org.bluez.Adapter1"
DEVICE_INTERFACE = "org.bluez.Device1"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
OBJECT_MANAGER_INTERFACE = "org.freedesktop.DBus.ObjectManager"

# SPP UUID for Serial Port Profile
SPP_UUID = "00001101-0000-1000-8000-00805f9b34fb"

# Scan timeout in seconds
DEFAULT_SCAN_TIMEOUT = 12


@dataclass
class ScannerState:
    """Internal scanner state."""

    scanning: bool = False
    scan_start_time: datetime | None = None
    discovered_devices: dict[str, DiscoveredDevice] = field(default_factory=dict)


class BluetoothScanner:
    """
    Bluetooth device scanner using D-Bus BlueZ API.

    Scans for Bluetooth Classic devices and identifies those with
    Serial Port Profile (SPP) for TNC compatibility.
    """

    def __init__(self) -> None:
        """Initialize the scanner."""
        self._state = ScannerState()
        self._bus: Any = None
        self._adapter: Any = None
        self._scan_task: asyncio.Task[None] | None = None
        self._device_callbacks: list[Callable[[DiscoveredDevice], None]] = []

    @property
    def is_scanning(self) -> bool:
        """Check if scan is in progress."""
        return self._state.scanning

    @property
    def discovered_devices(self) -> list[DiscoveredDevice]:
        """Get list of discovered devices."""
        return list(self._state.discovered_devices.values())

    def add_device_callback(self, callback: Callable[[DiscoveredDevice], None]) -> None:
        """Add callback for device discovery events."""
        self._device_callbacks.append(callback)

    def remove_device_callback(self, callback: Callable[[DiscoveredDevice], None]) -> None:
        """Remove device discovery callback."""
        if callback in self._device_callbacks:
            self._device_callbacks.remove(callback)

    async def start_scan(self, timeout: int = DEFAULT_SCAN_TIMEOUT) -> None:
        """
        Start scanning for Bluetooth devices.

        Args:
            timeout: Scan duration in seconds.

        Raises:
            RuntimeError: If scan is already in progress or D-Bus unavailable.
        """
        if self._state.scanning:
            raise RuntimeError("Scan already in progress")

        try:
            import dbus

            if not self._bus:
                self._bus = dbus.SystemBus()

            # Get adapter
            adapter_obj = self._bus.get_object(BLUEZ_SERVICE, "/org/bluez/hci0")
            self._adapter = dbus.Interface(adapter_obj, ADAPTER_INTERFACE)

            # Clear previous results
            self._state.discovered_devices.clear()
            self._state.scanning = True
            self._state.scan_start_time = datetime.now()

            logger.info("Starting Bluetooth scan (timeout: %ds)", timeout)

            # Start discovery
            self._adapter.StartDiscovery()

            # Run scan for specified duration
            self._scan_task = asyncio.create_task(self._run_scan(timeout))

        except ImportError as err:
            raise RuntimeError("D-Bus not available - are you running on Linux?") from err
        except Exception as e:
            self._state.scanning = False
            logger.error("Failed to start scan: %s", e)
            raise RuntimeError(f"Failed to start Bluetooth scan: {e}") from e

    async def stop_scan(self) -> None:
        """Stop the current scan."""
        if not self._state.scanning:
            return

        try:
            if self._adapter:
                self._adapter.StopDiscovery()
        except Exception as e:
            logger.warning("Error stopping discovery: %s", e)

        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None

        self._state.scanning = False
        logger.info("Bluetooth scan stopped, found %d devices", len(self._state.discovered_devices))

    async def _run_scan(self, timeout: int) -> None:
        """Run scan for specified duration."""
        try:
            # Poll for devices during scan
            end_time = asyncio.get_event_loop().time() + timeout

            while asyncio.get_event_loop().time() < end_time:
                await self._poll_devices()
                await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            pass
        finally:
            await self.stop_scan()

    async def _poll_devices(self) -> None:
        """Poll for discovered devices via D-Bus ObjectManager."""
        if not self._bus:
            return

        try:
            import dbus

            # Get all managed objects
            om = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE, "/"),
                OBJECT_MANAGER_INTERFACE,
            )
            objects = om.GetManagedObjects()

            for path, interfaces in objects.items():
                if DEVICE_INTERFACE not in interfaces:
                    continue

                device_props = interfaces[DEVICE_INTERFACE]
                address = str(device_props.get("Address", ""))

                if not address:
                    continue

                # Skip if already discovered
                if address in self._state.discovered_devices:
                    # Update RSSI if changed
                    if "RSSI" in device_props:
                        self._state.discovered_devices[address].rssi = int(device_props["RSSI"])
                    continue

                # Create device entry
                device = self._parse_device(device_props, path)
                self._state.discovered_devices[address] = device

                logger.debug(
                    "Discovered: %s (%s) SPP=%s",
                    device.name or "Unknown",
                    device.address,
                    device.has_spp,
                )

                # Notify callbacks
                for callback in self._device_callbacks:
                    try:
                        callback(device)
                    except Exception as e:
                        logger.warning("Device callback error: %s", e)

        except Exception as e:
            logger.warning("Error polling devices: %s", e)

    def _parse_device(self, props: dict[str, Any], path: str) -> DiscoveredDevice:  # noqa: ARG002
        """Parse D-Bus device properties into DiscoveredDevice."""
        address = str(props.get("Address", ""))
        name = props.get("Name")
        if name:
            name = str(name)

        rssi = props.get("RSSI")
        if rssi is not None:
            rssi = int(rssi)

        device_class = props.get("Class")
        if device_class is not None:
            device_class = int(device_class)

        paired = bool(props.get("Paired", False))
        trusted = bool(props.get("Trusted", False))

        # Check for SPP UUID
        uuids = props.get("UUIDs", [])
        has_spp = SPP_UUID.lower() in [str(u).lower() for u in uuids]

        return DiscoveredDevice(
            address=address,
            name=name,
            rssi=rssi,
            device_class=device_class,
            paired=paired,
            trusted=trusted,
            has_spp=has_spp,
        )

    def get_paired_devices(self) -> list[DiscoveredDevice]:
        """Get list of already-paired devices."""
        devices = []

        try:
            import dbus

            if not self._bus:
                self._bus = dbus.SystemBus()

            om = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE, "/"),
                OBJECT_MANAGER_INTERFACE,
            )
            objects = om.GetManagedObjects()

            for path, interfaces in objects.items():
                if DEVICE_INTERFACE not in interfaces:
                    continue

                device_props = interfaces[DEVICE_INTERFACE]
                if not device_props.get("Paired", False):
                    continue

                device = self._parse_device(device_props, path)
                devices.append(device)

        except Exception as e:
            logger.error("Failed to get paired devices: %s", e)

        return devices


class PairingManager:
    """
    Manages Bluetooth pairing sessions via D-Bus.

    Handles the pairing workflow including device selection,
    PIN entry, and trust configuration.
    """

    def __init__(self, scanner: BluetoothScanner) -> None:
        """
        Initialize the pairing manager.

        Args:
            scanner: BluetoothScanner instance for device discovery.
        """
        self._scanner = scanner
        self._session = PairingSession()
        self._bus: Any = None
        self._pin_callback: Callable[[str], None] | None = None
        self._pending_pin: asyncio.Future[str] | None = None

    @property
    def session(self) -> PairingSession:
        """Get current pairing session."""
        return self._session

    def set_pin_callback(self, callback: Callable[[str], None] | None) -> None:
        """Set callback for PIN requests (called when TNC requests PIN)."""
        self._pin_callback = callback

    async def start_scan(self, timeout: int = DEFAULT_SCAN_TIMEOUT) -> None:
        """Start device discovery scan."""
        self._session.reset()
        self._session.state = PairingState.SCANNING
        self._session.started_at = datetime.now()

        try:
            await self._scanner.start_scan(timeout)

            # Wait for scan to complete
            while self._scanner.is_scanning:
                await asyncio.sleep(0.5)
                self._session.discovered_devices = self._scanner.discovered_devices

            self._session.state = PairingState.SCAN_COMPLETE
            self._session.discovered_devices = self._scanner.discovered_devices
            logger.info("Scan complete, found %d devices", len(self._session.discovered_devices))

        except Exception as e:
            self._session.state = PairingState.FAILED
            self._session.error_message = str(e)
            logger.error("Scan failed: %s", e)
            raise

    async def pair_device(self, address: str) -> None:
        """
        Initiate pairing with a device.

        Args:
            address: MAC address of device to pair.

        Raises:
            RuntimeError: If pairing fails.
        """
        self._session.state = PairingState.PAIRING
        self._session.target_address = address

        # Find device name from discovered devices
        for device in self._session.discovered_devices:
            if device.address == address:
                self._session.target_name = device.name
                break

        try:
            import dbus

            if not self._bus:
                self._bus = dbus.SystemBus()

            # Convert MAC to D-Bus path format
            device_path = f"/org/bluez/hci0/dev_{address.replace(':', '_')}"

            device_obj = self._bus.get_object(BLUEZ_SERVICE, device_path)
            device_iface = dbus.Interface(device_obj, DEVICE_INTERFACE)
            props_iface = dbus.Interface(device_obj, PROPERTIES_INTERFACE)

            # Check if already paired
            paired = props_iface.Get(DEVICE_INTERFACE, "Paired")
            if paired:
                logger.info("Device %s already paired, marking trusted", address)
                props_iface.Set(DEVICE_INTERFACE, "Trusted", dbus.Boolean(True))
                self._session.state = PairingState.SUCCESS
                return

            logger.info("Initiating pairing with %s", address)

            # Run pairing in executor to not block
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, device_iface.Pair)

            # Mark as trusted
            props_iface.Set(DEVICE_INTERFACE, "Trusted", dbus.Boolean(True))

            self._session.state = PairingState.SUCCESS
            logger.info("Pairing successful with %s", address)

        except Exception as e:
            error_msg = str(e)
            self._session.state = PairingState.FAILED
            self._session.error_message = error_msg
            logger.error("Pairing failed with %s: %s", address, error_msg)
            raise RuntimeError(f"Pairing failed: {error_msg}") from e

    async def submit_pin(self, pin: str) -> None:
        """
        Submit PIN for pairing.

        Args:
            pin: PIN code to submit.
        """
        if self._pending_pin:
            self._pending_pin.set_result(pin)
            self._pending_pin = None
            self._session.pin_required = False

    def cancel(self) -> None:
        """Cancel current pairing session."""
        self._session.reset()
        if self._pending_pin:
            self._pending_pin.cancel()
            self._pending_pin = None


# Global instances (created on first use)
_scanner: BluetoothScanner | None = None
_pairing_manager: PairingManager | None = None


def get_scanner() -> BluetoothScanner:
    """Get or create the global Bluetooth scanner."""
    global _scanner
    if _scanner is None:
        _scanner = BluetoothScanner()
    return _scanner


def get_pairing_manager() -> PairingManager:
    """Get or create the global pairing manager."""
    global _pairing_manager
    if _pairing_manager is None:
        _pairing_manager = PairingManager(get_scanner())
    return _pairing_manager
