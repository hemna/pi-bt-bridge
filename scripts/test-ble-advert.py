#!/usr/bin/env python3
"""
Standalone BLE advertising test script.
Run this directly on the Pi to test if BLE advertising works.

Usage:
    cd ~/pi-bt-bridge
    source .venv/bin/activate
    python scripts/test-ble-advert.py
"""

import asyncio
import subprocess
import sys
import signal

# Nordic UART Service UUIDs (what aprs-chat-ios expects)
NUS_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # Write (from central)
NUS_RX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # Notify (to central)

DEVICE_NAME = "PiBTBridge"


def setup_adapter():
    """Configure the Bluetooth adapter before starting BLE server."""
    print(f"[SETUP] Configuring adapter as '{DEVICE_NAME}'...")

    # Unblock bluetooth
    subprocess.run(["sudo", "rfkill", "unblock", "bluetooth"], capture_output=True)

    # Bring up adapter
    subprocess.run(["sudo", "hciconfig", "hci0", "up"], capture_output=True)

    # Set adapter name/alias
    subprocess.run(["bluetoothctl", "system-alias", DEVICE_NAME], capture_output=True)

    # Make discoverable (for classic BT discovery in iOS Settings)
    subprocess.run(["bluetoothctl", "discoverable", "on"], capture_output=True)

    # Make pairable
    subprocess.run(["bluetoothctl", "pairable", "on"], capture_output=True)

    print("[SETUP] Adapter configured")


async def main():
    """Run the BLE advertising test."""

    # Import bless here to catch import errors early
    try:
        from bless import BlessServer, GATTCharacteristicProperties, GATTAttributePermissions
    except ImportError as e:
        print(f"[ERROR] Cannot import bless: {e}")
        print("Make sure you're in the venv: source .venv/bin/activate")
        return 1

    # Setup adapter first
    setup_adapter()

    print(f"\n[INFO] Creating BLE GATT server with name '{DEVICE_NAME}'")
    print(f"[INFO] Service UUID: {NUS_SERVICE_UUID}")

    # Create server
    server = BlessServer(name=DEVICE_NAME, loop=None)

    # Define GATT tree
    gatt = {
        NUS_SERVICE_UUID: {
            NUS_TX_CHAR_UUID: {
                "Properties": (
                    GATTCharacteristicProperties.write
                    | GATTCharacteristicProperties.write_without_response
                ),
                "Permissions": GATTAttributePermissions.writeable,
                "Value": bytearray(b""),
            },
            NUS_RX_CHAR_UUID: {
                "Properties": (
                    GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify
                ),
                "Permissions": GATTAttributePermissions.readable,
                "Value": bytearray(b""),
            },
        }
    }

    # Add GATT tree and start
    print("[INFO] Adding GATT tree...")
    await server.add_gatt(gatt)

    print("[INFO] Starting BLE server...")
    await server.start()

    print("\n" + "=" * 60)
    print(f"[SUCCESS] BLE server started, advertising as '{DEVICE_NAME}'")
    print("=" * 60)
    print("\nNow test discovery:")
    print("  1. On iPhone, open the aprs-chat app")
    print("  2. Go to Settings -> Serial KISS")
    print("  3. Tap 'Scan for Devices'")
    print(f"  4. Look for '{DEVICE_NAME}' in the list")
    print("\nAlternatively, use 'nRF Connect' app to scan for BLE devices")
    print("\nPress Ctrl+C to stop...")
    print("=" * 60 + "\n")

    # Check if advertising
    is_adv = await server.is_advertising()
    print(f"[STATUS] is_advertising: {is_adv}")

    # Wait for Ctrl+C
    stop_event = asyncio.Event()

    def handle_signal(sig, frame):
        print("\n[INFO] Stopping...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    await stop_event.wait()

    # Cleanup
    print("[INFO] Stopping BLE server...")
    await server.stop()
    print("[INFO] Done")

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted")
        sys.exit(0)
