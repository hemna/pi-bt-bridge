"""Web service for the BT bridge daemon."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiohttp_jinja2
import jinja2
from aiohttp import web

from src.config import DEFAULT_CONFIG_PATH, ConfigurationError, save_config
from src.models.tnc_history import TNCDevice, TNCHistory, TNCProtocol
from src.services.scanner_service import get_pairing_manager
from src.util.logging import get_logger
from src.web.models import (
    BLEStatus,
    BridgeStatus,
    ClassicStatus,
    ConnectionState,
    PacketStatistics,
)

if TYPE_CHECKING:
    from src.config import Configuration
    from src.models.state import BridgeState
    from src.services.bridge import BridgeService
    from src.services.classic_service import ClassicService

logger = get_logger("web_service")

# Path to templates directory
TEMPLATES_DIR = Path(__file__).parent.parent / "web" / "templates"
STATIC_DIR = Path(__file__).parent.parent / "web" / "static"

# MAC address validation pattern
MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

# Valid log levels
VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


class WebService:
    """
    HTTP web service for bridge status and configuration.

    Provides a web interface for viewing bridge status, configuring settings,
    and managing Bluetooth pairing.

    Attributes:
        host: Host address to bind to.
        port: Port number to listen on.
        config: Bridge configuration.
        bridge_state: Runtime bridge state (optional, for status).
    """

    def __init__(
        self,
        host: str,
        port: int,
        config: Configuration,
        bridge_state: BridgeState | None = None,
        classic_service: ClassicService | None = None,
        bridge_service: BridgeService | None = None,
    ) -> None:
        """
        Initialize the web service.

        Args:
            host: Host address to bind to (e.g., "0.0.0.0").
            port: Port number to listen on.
            config: Bridge configuration.
            bridge_state: Runtime bridge state for status display.
            classic_service: Classic SPP service for live target switching.
            bridge_service: Bridge service for protocol switching on TNC change.
        """
        self.host = host
        self.port = port
        self.config = config
        self.bridge_state = bridge_state
        self._classic_service = classic_service
        self._bridge_service = bridge_service

        # Runtime state
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._started_at: datetime | None = None

        # Pairing manager (lazy-loaded to avoid D-Bus issues on non-Linux)
        self._pairing_manager = None

        # TNC history for quick switching between radios
        self._tnc_history = TNCHistory(path=config.history_file)

        # SSE clients for real-time updates
        self._sse_clients: list[web.StreamResponse] = []
        self._max_sse_clients = 5

    def _get_pairing_manager(self):
        """Get or create the pairing manager."""
        if self._pairing_manager is None:
            self._pairing_manager = get_pairing_manager()
        return self._pairing_manager

    def _get_stats(self) -> PacketStatistics:
        """Get packet statistics from bridge state or defaults."""
        if self.bridge_state:
            # Pull stats from the actual bridge state
            return PacketStatistics(
                # TX = data sent to TNC (from BLE)
                packets_tx=self.bridge_state.frames_bridged,  # Approximate
                packets_rx=self.bridge_state.frames_bridged,  # Approximate (bidirectional)
                bytes_tx=self.bridge_state.classic.bytes_tx,
                bytes_rx=self.bridge_state.classic.bytes_rx,
                errors=len(self.bridge_state.errors),
            )
        else:
            # Return empty stats when no bridge state
            return PacketStatistics()

    async def start(self) -> None:
        """
        Start the web server.

        Raises:
            RuntimeError: If server fails to start.
        """
        logger.info("Starting web server on %s:%d", self.host, self.port)

        self._started_at = datetime.now()

        # Create aiohttp application
        self._app = web.Application()

        # Setup Jinja2 templates (request_processor injects 'request' into
        # every template context so base.html can use request.path for nav).
        aiohttp_jinja2.setup(
            self._app,
            loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
            context_processors=[aiohttp_jinja2.request_processor],
        )

        # Register routes
        self._setup_routes()

        # Create and start runner
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, self.host, self.port)

        try:
            await self._site.start()
            logger.info("Web server started successfully")
        except OSError as e:
            logger.error("Failed to start web server: %s", e)
            raise RuntimeError(f"Failed to bind to {self.host}:{self.port}: {e}") from e

    async def stop(self) -> None:
        """Stop the web server gracefully."""
        logger.info("Stopping web server")

        # Close SSE clients
        for client in self._sse_clients:
            await client.write_eof()
        self._sse_clients.clear()

        # Cleanup runner
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        self._app = None
        self._site = None
        logger.info("Web server stopped")

    def _setup_routes(self) -> None:
        """Register HTTP routes."""
        if not self._app:
            return

        # HTML pages
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_get("/pairing", self._handle_pairing_page)
        self._app.router.add_get("/settings", self._handle_settings_page)
        self._app.router.add_get("/stats", self._handle_stats_page)

        # API endpoints
        self._app.router.add_get("/api/status", self._handle_api_status)
        self._app.router.add_get("/api/status/stream", self._handle_api_status_stream)
        self._app.router.add_get("/api/stats", self._handle_api_stats)
        self._app.router.add_get("/api/settings", self._handle_api_settings_get)
        self._app.router.add_post("/api/settings", self._handle_api_settings_post)
        self._app.router.add_post("/api/restart", self._handle_api_restart)

        # Pairing API
        self._app.router.add_post("/api/pairing/scan", self._handle_api_pairing_scan)
        self._app.router.add_get("/api/pairing/devices", self._handle_api_pairing_devices)
        self._app.router.add_post("/api/pairing/pair", self._handle_api_pairing_pair)
        self._app.router.add_post("/api/pairing/pin", self._handle_api_pairing_pin)
        self._app.router.add_get("/api/pairing/status", self._handle_api_pairing_status)
        self._app.router.add_post("/api/pairing/use", self._handle_api_pairing_use)

        # TNC History API
        self._app.router.add_get("/api/tnc-history", self._handle_api_tnc_history_list)
        self._app.router.add_post("/api/tnc-history", self._handle_api_tnc_history_add)
        self._app.router.add_get("/api/tnc-history/{address}", self._handle_api_tnc_history_get)
        self._app.router.add_put("/api/tnc-history/{address}", self._handle_api_tnc_history_update)
        self._app.router.add_delete(
            "/api/tnc-history/{address}", self._handle_api_tnc_history_delete
        )
        self._app.router.add_post(
            "/api/tnc-history/{address}/select", self._handle_api_tnc_history_select
        )
        self._app.router.add_post(
            "/api/tnc-history/{address}/connect", self._handle_api_tnc_history_connect
        )

        # Static files
        self._app.router.add_static("/static", STATIC_DIR, name="static")

    def _get_bridge_status(self) -> BridgeStatus:
        """Get current bridge status."""
        # If we have bridge state, use it
        if self.bridge_state:
            ble_status = BLEStatus(
                state=ConnectionState.CONNECTED
                if self.bridge_state.ble.is_connected
                else ConnectionState.IDLE,
                device_name=self.bridge_state.ble.device_name,
                device_address=self.bridge_state.ble.device_address,
                connected_at=self.bridge_state.ble.connected_at,
                advertising=getattr(self.bridge_state.ble, "advertising", False),
            )
            classic_status = ClassicStatus(
                state=ConnectionState.CONNECTED
                if self.bridge_state.classic.is_connected
                else ConnectionState.IDLE,
                target_address=self.bridge_state.classic.target_address,
                target_name=getattr(self.bridge_state.classic, "device_name", None),
                connected_at=self.bridge_state.classic.connected_at,
                rfcomm_channel=self.config.rfcomm_channel,
            )
        else:
            # Default status when no bridge state available
            ble_status = BLEStatus(state=ConnectionState.IDLE)
            classic_status = ClassicStatus(
                state=ConnectionState.IDLE,
                target_address=self.config.target_address,
                rfcomm_channel=self.config.rfcomm_channel,
            )

        return BridgeStatus(
            ble=ble_status,
            classic=classic_status,
            started_at=self._started_at or datetime.now(),
        )

    # --- HTML Page Handlers ---

    @aiohttp_jinja2.template("status.html")
    async def _handle_index(self, request: web.Request) -> dict[str, Any]:
        """Handle index page request."""
        status = self._get_bridge_status()
        return {
            "status": status,
            "config": self.config,
        }

    @aiohttp_jinja2.template("pairing.html")
    async def _handle_pairing_page(self, request: web.Request) -> dict[str, Any]:
        """Handle pairing page request."""
        return {
            "session": self._get_pairing_manager().session,
            "config": self.config,
        }

    @aiohttp_jinja2.template("settings.html")
    async def _handle_settings_page(self, request: web.Request) -> dict[str, Any]:
        """Handle settings page request."""
        return {"config": self.config}

    @aiohttp_jinja2.template("stats.html")
    async def _handle_stats_page(self, request: web.Request) -> dict[str, Any]:
        """Handle statistics page request."""
        return {
            "stats": self._get_stats(),
            "status": self._get_bridge_status(),
        }

    # --- API Handlers ---

    async def _handle_api_status(self, request: web.Request) -> web.Response:
        """Handle GET /api/status."""
        status = self._get_bridge_status()
        return web.json_response(status.to_dict())

    async def _handle_api_status_stream(self, request: web.Request) -> web.StreamResponse:
        """Handle GET /api/status/stream (SSE)."""
        # Check client limit
        if len(self._sse_clients) >= self._max_sse_clients:
            return web.Response(
                status=503,
                text="Too many SSE clients",
            )

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        await response.prepare(request)

        self._sse_clients.append(response)
        logger.debug("SSE client connected (%d total)", len(self._sse_clients))

        try:
            # Send initial status
            status = self._get_bridge_status()
            await self._send_sse_event(response, "status", status.to_dict())

            # Keep connection alive with periodic pings
            while True:
                await asyncio.sleep(30)
                await self._send_sse_event(response, "ping", {"time": datetime.now().isoformat()})
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            if response in self._sse_clients:
                self._sse_clients.remove(response)
            logger.debug("SSE client disconnected (%d remaining)", len(self._sse_clients))

        return response

    async def _send_sse_event(
        self,
        response: web.StreamResponse,
        event: str,
        data: dict[str, Any],
    ) -> None:
        """Send an SSE event to a client."""
        message = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        await response.write(message.encode("utf-8"))

    async def broadcast_status_update(self) -> None:
        """Broadcast status update to all SSE clients."""
        if not self._sse_clients:
            return

        status = self._get_bridge_status()
        dead_clients = []

        for client in self._sse_clients:
            try:
                await self._send_sse_event(client, "status", status.to_dict())
            except (ConnectionResetError, asyncio.CancelledError):
                dead_clients.append(client)

        # Remove dead clients
        for client in dead_clients:
            self._sse_clients.remove(client)

    async def _handle_api_stats(self, request: web.Request) -> web.Response:
        """Handle GET /api/stats."""
        return web.json_response(self._get_stats().to_dict())

    async def _handle_api_settings_get(self, request: web.Request) -> web.Response:
        """Handle GET /api/settings."""
        return web.json_response(
            {
                "device_name": self.config.device_name,
                "target_address": self.config.target_address,
                "rfcomm_channel": self.config.rfcomm_channel,
                "log_level": self.config.log_level,
                "web_port": self.config.web_port,
            }
        )

    async def _handle_api_settings_post(self, request: web.Request) -> web.Response:
        """Handle POST /api/settings."""
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response(
                {"error": "Invalid JSON"},
                status=400,
            )

        # Validate settings
        errors: dict[str, str] = {}

        # Validate device_name
        device_name = data.get("device_name", self.config.device_name)
        if not isinstance(device_name, str) or not device_name:
            errors["device_name"] = "Device name is required"
        elif len(device_name) > 20:
            errors["device_name"] = "Device name must be 20 characters or less"
        elif not re.match(r"^[A-Za-z0-9\-]+$", device_name):
            errors["device_name"] = "Device name must be alphanumeric (hyphens allowed)"

        # Validate target_address
        target_address = data.get("target_address", self.config.target_address)
        if not isinstance(target_address, str) or not target_address:
            errors["target_address"] = "Target address is required"
        elif not MAC_PATTERN.match(target_address):
            errors["target_address"] = "Invalid MAC address format (use XX:XX:XX:XX:XX:XX)"

        # Validate rfcomm_channel
        rfcomm_channel = data.get("rfcomm_channel", self.config.rfcomm_channel)
        try:
            rfcomm_channel = int(rfcomm_channel)
            if not 1 <= rfcomm_channel <= 30:
                errors["rfcomm_channel"] = "RFCOMM channel must be 1-30"
        except (TypeError, ValueError):
            errors["rfcomm_channel"] = "RFCOMM channel must be a number"

        # Validate log_level
        log_level = data.get("log_level", self.config.log_level)
        if not isinstance(log_level, str):
            errors["log_level"] = "Log level must be a string"
        elif log_level.upper() not in VALID_LOG_LEVELS:
            errors["log_level"] = f"Log level must be one of: {', '.join(sorted(VALID_LOG_LEVELS))}"

        # Validate web_port
        web_port = data.get("web_port", self.config.web_port)
        try:
            web_port = int(web_port)
            if not 1024 <= web_port <= 65535:
                errors["web_port"] = "Web port must be 1024-65535"
        except (TypeError, ValueError):
            errors["web_port"] = "Web port must be a number"

        # Return validation errors if any
        if errors:
            return web.json_response(
                {
                    "error": "Validation failed",
                    "details": errors,
                },
                status=400,
            )

        # Determine what requires restart
        restart_required = (
            device_name != self.config.device_name
            or target_address != self.config.target_address
            or rfcomm_channel != self.config.rfcomm_channel
            or web_port != self.config.web_port
        )

        # Update config object
        self.config.device_name = device_name
        self.config.target_address = target_address
        self.config.rfcomm_channel = rfcomm_channel
        self.config.log_level = log_level.upper()
        self.config.web_port = web_port

        # Save to file
        try:
            config_path = os.environ.get("BT_BRIDGE_CONFIG", DEFAULT_CONFIG_PATH)
            save_config(self.config, config_path)
            logger.info("Configuration saved to %s", config_path)
        except ConfigurationError as e:
            return web.json_response(
                {"error": f"Failed to save configuration: {e}"},
                status=500,
            )

        return web.json_response(
            {
                "status": "saved",
                "message": "Configuration saved successfully.",
                "restart_required": restart_required,
            }
        )

    async def _handle_api_restart(self, request: web.Request) -> web.Response:
        """Handle POST /api/restart."""
        logger.info("Restart requested via web interface")

        # Schedule restart after response is sent
        async def do_restart() -> None:
            await asyncio.sleep(1.0)  # Give time for response to be sent
            logger.info("Restarting daemon...")
            # Send SIGTERM to trigger graceful shutdown; systemd will restart us
            os.kill(os.getpid(), signal.SIGTERM)
            # If SIGTERM doesn't kill us (e.g. stuck child process), force exit
            await asyncio.sleep(5.0)
            logger.warning("SIGTERM did not exit, forcing exit")
            os._exit(1)

        asyncio.create_task(do_restart())

        return web.json_response(
            {
                "status": "restarting",
                "message": "Bridge will restart in 1 second",
            },
            status=202,
        )

    # --- Pairing API Handlers ---

    async def _handle_api_pairing_scan(self, request: web.Request) -> web.Response:
        """Handle POST /api/pairing/scan."""
        pm = self._get_pairing_manager()

        if pm.session.state.value == "scanning":
            return web.json_response(
                {"error": "Scan already in progress"},
                status=409,
            )

        # Start scan in background
        asyncio.create_task(self._run_scan())

        return web.json_response(
            {
                "status": "scanning",
                "message": "Scan started, results in 10-15 seconds",
            },
            status=202,
        )

    async def _run_scan(self) -> None:
        """Run Bluetooth scan in background."""
        pm = self._get_pairing_manager()
        try:
            await pm.start_scan(timeout=12)
        except Exception as e:
            logger.error("Scan error: %s", e)

    async def _handle_api_pairing_devices(self, request: web.Request) -> web.Response:
        """Handle GET /api/pairing/devices."""
        pm = self._get_pairing_manager()
        session = pm.session

        return web.json_response(
            {
                "state": session.state.value,
                "devices": [d.to_dict() for d in session.discovered_devices],
            }
        )

    async def _handle_api_pairing_pair(self, request: web.Request) -> web.Response:
        """Handle POST /api/pairing/pair."""
        try:
            data = await request.json()
            address = data.get("address")
        except (json.JSONDecodeError, KeyError):
            return web.json_response(
                {"error": "Invalid request, 'address' required"},
                status=400,
            )

        if not address:
            return web.json_response(
                {"error": "Address is required"},
                status=400,
            )

        pm = self._get_pairing_manager()

        if pm.session.state.value == "pairing":
            return web.json_response(
                {"error": "Pairing already in progress"},
                status=409,
            )

        # Start pairing in background
        asyncio.create_task(self._run_pair(address))

        return web.json_response(
            {
                "status": "pairing",
                "message": f"Pairing initiated with {address}",
            },
            status=202,
        )

    async def _run_pair(self, address: str) -> None:
        """Run pairing in background."""
        pm = self._get_pairing_manager()
        try:
            await pm.pair_device(address)
        except Exception as e:
            logger.error("Pairing error: %s", e)

    async def _handle_api_pairing_pin(self, request: web.Request) -> web.Response:
        """Handle POST /api/pairing/pin."""
        try:
            data = await request.json()
            pin = data.get("pin")
        except (json.JSONDecodeError, KeyError):
            return web.json_response(
                {"error": "Invalid request, 'pin' required"},
                status=400,
            )

        pm = self._get_pairing_manager()

        if not pm.session.pin_required:
            return web.json_response(
                {"error": "No PIN requested"},
                status=400,
            )

        try:
            await pm.submit_pin(pin)
            return web.json_response(
                {
                    "status": "success",
                    "message": "PIN submitted",
                }
            )
        except Exception as e:
            return web.json_response(
                {"error": str(e)},
                status=500,
            )

    # --- TNC History API Handlers ---

    def _device_to_response(self, device: TNCDevice) -> dict[str, Any]:
        """Convert TNCDevice to API response dict with runtime fields.

        Adds is_current, is_paired, and connection_state fields that
        depend on runtime state.

        Args:
            device: TNCDevice to convert.

        Returns:
            Dictionary suitable for JSON response.
        """
        data = device.to_dict()
        data["display_name"] = device.display_name
        is_current = device.address == self.config.target_address.upper()
        data["is_current"] = is_current
        # Check paired status via BlueZ (best-effort)
        data["is_paired"] = self._check_device_paired(device.address)

        # Include Classic connection state for the active TNC
        if is_current and self._classic_service is not None:
            conn = self._classic_service.connection
            data["connection_state"] = conn.state.value
            data["is_connected"] = self._classic_service.is_connected
            data["last_error"] = conn.last_error
            data["reconnect_attempts"] = conn.reconnect_attempts
        else:
            data["connection_state"] = None
            data["is_connected"] = False
            data["last_error"] = None
            data["reconnect_attempts"] = 0

        return data

    def _check_device_paired(self, address: str) -> bool:
        """Check if a device is paired at Bluetooth level.

        Args:
            address: MAC address to check.

        Returns:
            True if paired, False otherwise (or on error).
        """
        try:
            pm = self._get_pairing_manager()
            if pm and hasattr(pm, "scanner") and pm.scanner:
                return pm.scanner.is_device_paired(address)
        except Exception:
            pass
        # Default to True if we can't check (avoid false warnings)
        return True

    async def _handle_api_tnc_history_list(self, request: web.Request) -> web.Response:
        """Handle GET /api/tnc-history - List all TNC devices in history."""
        devices = self._tnc_history.list_all()
        return web.json_response(
            {
                "devices": [self._device_to_response(d) for d in devices],
                "count": len(devices),
                "current_address": self.config.target_address,
            }
        )

    async def _handle_api_tnc_history_get(self, request: web.Request) -> web.Response:
        """Handle GET /api/tnc-history/{address} - Get single TNC device."""
        address = request.match_info["address"]
        device = self._tnc_history.get(address)

        if device is None:
            return web.json_response(
                {"success": False, "message": "TNC not found in history", "address": address},
                status=404,
            )

        return web.json_response(self._device_to_response(device))

    async def _handle_api_tnc_history_add(self, request: web.Request) -> web.Response:
        """Handle POST /api/tnc-history - Add TNC device to history."""
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response(
                {"success": False, "message": "Invalid JSON"},
                status=400,
            )

        # Validate required fields
        errors: dict[str, str] = {}
        address = data.get("address", "")
        bluetooth_name = data.get("bluetooth_name", "")
        rfcomm_channel = data.get("rfcomm_channel", 2)

        if not address or not MAC_PATTERN.match(address):
            errors["address"] = "Invalid MAC address format"
        if not bluetooth_name:
            errors["bluetooth_name"] = "bluetooth_name is required"
        try:
            rfcomm_channel = int(rfcomm_channel)
            if not 1 <= rfcomm_channel <= 30:
                errors["rfcomm_channel"] = "Must be 1-30"
        except (TypeError, ValueError):
            errors["rfcomm_channel"] = "Must be a number"

        if errors:
            return web.json_response(
                {"success": False, "message": "Validation failed", "errors": errors},
                status=400,
            )

        existing = self._tnc_history.get(address)
        try:
            device = TNCDevice(
                address=address,
                bluetooth_name=bluetooth_name,
                friendly_name=data.get("friendly_name"),
                rfcomm_channel=rfcomm_channel,
            )
            self._tnc_history.add(device)
        except (ValueError, OSError) as e:
            return web.json_response(
                {"success": False, "message": str(e)},
                status=400,
            )

        status_code = 200 if existing else 201
        message = "TNC updated in history" if existing else "TNC added to history"
        return web.json_response(
            {"success": True, "message": message, "device": self._device_to_response(device)},
            status=status_code,
        )

    async def _handle_api_tnc_history_update(self, request: web.Request) -> web.Response:
        """Handle PUT /api/tnc-history/{address} - Update TNC device."""
        address = request.match_info["address"]
        device = self._tnc_history.get(address)

        if device is None:
            return web.json_response(
                {"success": False, "message": "TNC not found in history"},
                status=404,
            )

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response(
                {"success": False, "message": "Invalid JSON"},
                status=400,
            )

        # Update allowed fields
        if "friendly_name" in data:
            friendly_name = data["friendly_name"]
            if friendly_name is not None:
                if not isinstance(friendly_name, str) or len(friendly_name) == 0:
                    return web.json_response(
                        {
                            "success": False,
                            "message": "friendly_name must be a non-empty string or null",
                        },
                        status=400,
                    )
                if len(friendly_name) > 50:
                    return web.json_response(
                        {
                            "success": False,
                            "message": "friendly_name must be 50 characters or less",
                        },
                        status=400,
                    )
            device.friendly_name = friendly_name

        if "rfcomm_channel" in data:
            try:
                channel = int(data["rfcomm_channel"])
                if not 1 <= channel <= 30:
                    return web.json_response(
                        {"success": False, "message": "rfcomm_channel must be 1-30"},
                        status=400,
                    )
                device.rfcomm_channel = channel
            except (TypeError, ValueError):
                return web.json_response(
                    {"success": False, "message": "rfcomm_channel must be a number"},
                    status=400,
                )

        if "protocol" in data:
            try:
                device.protocol = TNCProtocol(data["protocol"])
            except ValueError:
                valid = ", ".join(p.value for p in TNCProtocol)
                return web.json_response(
                    {"success": False, "message": f"protocol must be one of: {valid}"},
                    status=400,
                )

        try:
            self._tnc_history.add(device)
        except OSError as e:
            return web.json_response(
                {"success": False, "message": f"Failed to save: {e}"},
                status=500,
            )

        return web.json_response(
            {"success": True, "message": "TNC updated", "device": self._device_to_response(device)},
        )

    async def _handle_api_tnc_history_delete(self, request: web.Request) -> web.Response:
        """Handle DELETE /api/tnc-history/{address} - Remove TNC from history."""
        address = request.match_info["address"]

        # Prevent deletion of currently active TNC
        if address.upper() == self.config.target_address.upper():
            return web.json_response(
                {
                    "success": False,
                    "message": "Cannot remove currently active TNC. Select a different TNC first.",
                },
                status=409,
            )

        if not self._tnc_history.remove(address):
            return web.json_response(
                {"success": False, "message": "TNC not found in history"},
                status=404,
            )

        return web.json_response(
            {"success": True, "message": "TNC removed from history"},
        )

    async def _handle_api_tnc_history_select(self, request: web.Request) -> web.Response:
        """Handle POST /api/tnc-history/{address}/select - Select TNC as active target."""
        address = request.match_info["address"]
        device = self._tnc_history.get(address)

        if device is None:
            return web.json_response(
                {"success": False, "message": "TNC not found in history"},
                status=404,
            )

        # Check if paired
        if not self._check_device_paired(device.address):
            return web.json_response(
                {
                    "success": False,
                    "message": "TNC is not paired. Please pair the device first.",
                    "is_paired": False,
                },
                status=400,
            )

        # Update config
        self.config.target_address = device.address
        self.config.rfcomm_channel = device.rfcomm_channel

        # Save config
        try:
            config_path = os.environ.get("BT_BRIDGE_CONFIG", DEFAULT_CONFIG_PATH)
            save_config(self.config, config_path)
        except ConfigurationError as e:
            return web.json_response(
                {"success": False, "message": f"Failed to save configuration: {e}"},
                status=500,
            )

        # Update last_used timestamp
        device.last_used = datetime.now(UTC)
        try:
            self._tnc_history.add(device)
        except OSError as e:
            logger.warning("Failed to update last_used in history: %s", e)

        # Hot-swap: disconnect from old target and connect to new one
        if self._classic_service is not None:
            asyncio.create_task(
                self._classic_service.switch_target(device.address, device.rfcomm_channel)
            )
            logger.info("Live-switching to TNC: %s (%s)", device.display_name, device.address)
        else:
            logger.warning("No classic service available, restart required for target change")

        # Update bridge protocol mode for the new TNC
        if self._bridge_service is not None:
            self._bridge_service.set_tnc_protocol(device.protocol)
            logger.info("Bridge protocol set to %s for %s", device.protocol.value, device.address)

        logger.info("TNC selected: %s (%s)", device.display_name, device.address)

        return web.json_response(
            {
                "success": True,
                "message": "TNC selected, connecting...",
                "device": self._device_to_response(device),
                "connecting": True,
            }
        )

    async def _handle_api_tnc_history_connect(self, request: web.Request) -> web.Response:
        """Handle POST /api/tnc-history/{address}/connect - Force immediate connection attempt.

        Cancels any pending backoff timer and initiates a new connection
        right away.  Only works for the currently active TNC.
        """
        address = request.match_info["address"]
        device = self._tnc_history.get(address)

        if device is None:
            return web.json_response(
                {"success": False, "message": "TNC not found in history"},
                status=404,
            )

        # Only allow connecting to the currently active TNC
        if address.upper() != self.config.target_address.upper():
            return web.json_response(
                {
                    "success": False,
                    "message": "Can only connect to the currently active TNC. Select it first.",
                },
                status=400,
            )

        if self._classic_service is None:
            return web.json_response(
                {"success": False, "message": "Classic service not available"},
                status=503,
            )

        # Already connected?
        if self._classic_service.is_connected:
            return web.json_response(
                {"success": True, "message": "Already connected", "already_connected": True}
            )

        # Force immediate reconnect
        asyncio.create_task(self._classic_service.reconnect_now())
        logger.info("Manual connect triggered for %s (%s)", device.display_name, device.address)

        return web.json_response(
            {
                "success": True,
                "message": "Connecting...",
                "device": self._device_to_response(device),
            }
        )

    async def _handle_api_pairing_status(self, request: web.Request) -> web.Response:
        """Handle GET /api/pairing/status."""
        pm = self._get_pairing_manager()
        return web.json_response(pm.session.to_dict())

    async def _handle_api_pairing_use(self, request: web.Request) -> web.Response:
        """Handle POST /api/pairing/use - Set a paired device as the target TNC."""
        try:
            data = await request.json()
            address = data.get("address")
        except (json.JSONDecodeError, KeyError):
            return web.json_response(
                {"error": "Invalid request, 'address' required"},
                status=400,
            )

        if not address:
            return web.json_response(
                {"error": "Address is required"},
                status=400,
            )

        # Validate MAC address format
        if not MAC_PATTERN.match(address):
            return web.json_response(
                {"error": "Invalid MAC address format"},
                status=400,
            )

        # Update config with new target
        self.config.target_address = address

        # Try to get device name from pairing manager
        pm = self._get_pairing_manager()
        device_name = None
        for device in pm.session.discovered_devices:
            if device.address == address:
                device_name = device.name
                break

        # Save config
        try:
            config_path = os.environ.get("BT_BRIDGE_CONFIG", DEFAULT_CONFIG_PATH)
            save_config(self.config, config_path)
            logger.info(
                "Target TNC updated to %s (%s)",
                address,
                device_name or "Unknown",
            )
        except ConfigurationError as e:
            return web.json_response(
                {"error": f"Failed to save configuration: {e}"},
                status=500,
            )

        # Auto-add to TNC history
        try:
            self._tnc_history.add(
                TNCDevice(
                    address=address,
                    bluetooth_name=device_name or "Unknown",
                    rfcomm_channel=self.config.rfcomm_channel,
                    last_used=datetime.now(UTC),
                )
            )
        except (ValueError, OSError) as e:
            logger.warning("Failed to add device to TNC history: %s", e)

        # Hot-swap: disconnect from old target and connect to new one
        if self._classic_service is not None:
            asyncio.create_task(
                self._classic_service.switch_target(address, self.config.rfcomm_channel)
            )
            logger.info("Live-switching to TNC: %s (%s)", address, device_name or "Unknown")

        return web.json_response(
            {
                "status": "saved",
                "message": f"Target TNC set to {device_name or address}. Connecting...",
                "target_address": address,
                "target_name": device_name,
                "restart_required": False,
            }
        )
