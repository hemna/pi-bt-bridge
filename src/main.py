"""Main entry point for the BT bridge daemon."""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

from src.config import DEFAULT_CONFIG_PATH, Configuration, ConfigurationError, load_config
from src.models.connection import BLEConnection, ClassicConnection
from src.models.kiss import KISSParser
from src.models.state import BridgeState
from src.services.ble_service import BLEService
from src.services.bridge import BridgeService
from src.services.classic_service import ClassicService
from src.services.pairing_agent import PairingAgent
from src.util.logging import get_logger, setup_logging

logger = get_logger("main")


class DaemonError(Exception):
    """Error during daemon startup or operation."""

    pass


async def run_daemon(config: Configuration) -> None:
    """
    Run the bridge daemon.

    Args:
        config: Daemon configuration.
    """
    logger.info("Starting BT bridge daemon")
    logger.info("Target TNC: %s (RFCOMM channel %d)", config.target_address, config.rfcomm_channel)
    logger.info("Device name: %s", config.device_name)

    # Start pairing agent for auto-accepting Bluetooth connections
    pairing_agent = PairingAgent(device_name=config.device_name)
    pairing_agent.start()

    # Create connection states
    ble_conn = BLEConnection()
    classic_conn = ClassicConnection(target_address=config.target_address)

    # Create services
    ble_service = BLEService(
        device_name=config.device_name,
        connection=ble_conn,
    )
    classic_service = ClassicService(
        target_address=config.target_address,
        target_pin=config.target_pin,
        reconnect_max_delay=config.reconnect_max_delay,
        rfcomm_channel=config.rfcomm_channel,
        connection=classic_conn,
    )

    # Create bridge state
    state = BridgeState(
        ble=ble_conn,
        classic=classic_conn,
        ble_parser=KISSParser(),
        classic_parser=KISSParser(),
    )

    # Create bridge service
    bridge = BridgeService(
        ble_service=ble_service,
        classic_service=classic_service,
        state=state,
    )

    # Set up signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()

    def handle_shutdown(signum: int, frame: object) -> None:  # noqa: ARG001
        logger.info("Received signal %d, initiating shutdown", signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    try:
        # Start the bridge
        await bridge.start()

        logger.info("Daemon started successfully")

        # Wait for shutdown signal
        await shutdown_event.wait()

    finally:
        # Graceful shutdown
        logger.info("Shutting down daemon")
        await bridge.stop()
        pairing_agent.stop()
        logger.info("Daemon stopped")


def validate_startup() -> None:
    """
    Validate startup prerequisites.

    Raises:
        DaemonError: If prerequisites are not met.
    """
    # Check if running on Linux (required for BlueZ)
    if sys.platform != "linux":
        logger.warning(
            "Running on %s - Bluetooth functionality may not work",
            sys.platform,
        )

    # Check for Bluetooth adapter
    # This is a basic check - real implementation would use D-Bus
    hci0_path = Path("/sys/class/bluetooth/hci0")
    if not hci0_path.exists():
        logger.warning("Bluetooth adapter hci0 not found")


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    # Load configuration
    config_path = DEFAULT_CONFIG_PATH

    # Allow override via environment variable
    import os

    if "BT_BRIDGE_CONFIG" in os.environ:
        config_path = os.environ["BT_BRIDGE_CONFIG"]

    try:
        config = load_config(config_path)
    except ConfigurationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Set up logging
    setup_logging(
        level=config.log_level,
        log_file=config.log_file,
    )

    # Validate startup
    try:
        validate_startup()
    except DaemonError as e:
        logger.error("Startup validation failed: %s", e)
        return 1

    # Run the daemon
    try:
        asyncio.run(run_daemon(config))
        return 0
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
