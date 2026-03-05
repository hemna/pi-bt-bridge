"""Bluetooth pairing agent for auto-accepting connections."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gi.repository import GLib

logger = logging.getLogger("bt-bridge.agent")

# Agent constants
AGENT_INTERFACE = "org.bluez.Agent1"
AGENT_PATH = "/org/bluez/pi_bt_bridge/agent"
CAPABILITY = "NoInputNoOutput"  # Auto-accept without user interaction


class PairingAgent:
    """
    Bluetooth pairing agent that auto-accepts pairing requests.

    This agent runs in a separate thread and handles all Bluetooth
    pairing requests automatically, allowing devices like iPhones
    to pair without manual intervention on the Pi.
    """

    def __init__(self, device_name: str = "PiBTBridge") -> None:
        """
        Initialize the pairing agent.

        Args:
            device_name: Name to advertise for the Bluetooth adapter.
        """
        self._device_name = device_name
        self._agent = None
        self._mainloop: GLib.MainLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        """Start the pairing agent in a background thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_agent, daemon=True)
        self._thread.start()
        logger.info("Pairing agent started")

    def stop(self) -> None:
        """Stop the pairing agent."""
        self._running = False

        if self._mainloop:
            self._mainloop.quit()

        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

        logger.info("Pairing agent stopped")

    def _run_agent(self) -> None:
        """Run the agent main loop (called in background thread)."""
        try:
            import dbus
            import dbus.mainloop.glib
            import dbus.service
            from gi.repository import GLib

            # Set up D-Bus main loop
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            bus = dbus.SystemBus()

            # Create and register the agent
            self._agent = self._create_agent_class(dbus)(bus, AGENT_PATH)

            manager = dbus.Interface(
                bus.get_object("org.bluez", "/org/bluez"),
                "org.bluez.AgentManager1",
            )

            manager.RegisterAgent(AGENT_PATH, CAPABILITY)
            manager.RequestDefaultAgent(AGENT_PATH)
            logger.info("Pairing agent registered with BlueZ")

            # Configure adapter
            self._configure_adapter(bus)

            # Run main loop
            self._mainloop = GLib.MainLoop()
            while self._running:
                # Run with timeout so we can check _running flag
                context = self._mainloop.get_context()
                context.iteration(True)

            # Cleanup
            try:
                manager.UnregisterAgent(AGENT_PATH)
            except Exception:
                pass

        except Exception as e:
            logger.error("Pairing agent error: %s", e)

    def _configure_adapter(self, bus) -> None:
        """Configure the Bluetooth adapter for discovery."""
        try:
            import dbus

            adapter = dbus.Interface(
                bus.get_object("org.bluez", "/org/bluez/hci0"),
                "org.freedesktop.DBus.Properties",
            )

            adapter.Set("org.bluez.Adapter1", "Alias", dbus.String(self._device_name))
            adapter.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(True))
            adapter.Set("org.bluez.Adapter1", "Pairable", dbus.Boolean(True))

            # Set discoverable timeout to 0 (always discoverable)
            adapter.Set("org.bluez.Adapter1", "DiscoverableTimeout", dbus.UInt32(0))

            logger.info("Adapter configured: %s (discoverable, pairable)", self._device_name)

        except Exception as e:
            logger.warning("Could not configure adapter: %s", e)

    def _create_agent_class(self, dbus_module):
        """Create the D-Bus agent class dynamically."""

        class Agent(dbus_module.service.Object):
            """D-Bus Bluetooth pairing agent."""

            @dbus_module.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
            def Release(self):
                logger.debug("Agent released")

            @dbus_module.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
            def AuthorizeService(self, device, uuid):
                logger.info("AuthorizeService: %s %s - accepting", device, uuid)
                return

            @dbus_module.service.method(AGENT_INTERFACE, in_signature="o", out_signature="s")
            def RequestPinCode(self, device):
                logger.info("RequestPinCode: %s - returning 0000", device)
                return "0000"

            @dbus_module.service.method(AGENT_INTERFACE, in_signature="o", out_signature="u")
            def RequestPasskey(self, device):
                logger.info("RequestPasskey: %s - returning 0", device)
                return dbus_module.UInt32(0)

            @dbus_module.service.method(AGENT_INTERFACE, in_signature="ouq", out_signature="")
            def DisplayPasskey(self, device, passkey, entered):
                logger.debug("DisplayPasskey: %s %d %d", device, passkey, entered)

            @dbus_module.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
            def DisplayPinCode(self, device, pincode):
                logger.debug("DisplayPinCode: %s %s", device, pincode)

            @dbus_module.service.method(AGENT_INTERFACE, in_signature="ou", out_signature="")
            def RequestConfirmation(self, device, passkey):
                logger.info("RequestConfirmation: %s %d - auto-accepting", device, passkey)
                return  # Empty return = accept

            @dbus_module.service.method(AGENT_INTERFACE, in_signature="o", out_signature="")
            def RequestAuthorization(self, device):
                logger.info("RequestAuthorization: %s - auto-accepting", device)
                return

            @dbus_module.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
            def Cancel(self):
                logger.info("Pairing cancelled")

        return Agent
