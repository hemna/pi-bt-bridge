#!/usr/bin/env python3
"""Bridge with packet logging for debugging."""

import asyncio
import subprocess
import socket  # Raw socket for TX (works!)
import bluetooth  # PyBluez for RX (required for receiving)
from datetime import datetime
from bless import BlessServer, GATTCharacteristicProperties, GATTAttributePermissions

NUS_SERVICE = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_RX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# TH-D74 configuration
TH_D74_MAC = "24:71:89:8D:26:EF"
SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"
SPP_CHANNEL = 2  # TH-D74 SPP channel

# KISS Protocol Constants
KISS_FEND = 0xC0  # Frame End
KISS_CMD_TXDELAY = 0x01  # TX delay command (in 10ms units)
KISS_CMD_SLOT_TIME = 0x03  # Slot time command (in 10ms units)
KISS_CMD_TX_TAIL = 0x04  # TX tail command (in 10ms units)

# Default KISS parameters (matching Android app values)
DEFAULT_TXDELAY_MS = 500  # 500ms = 50 units
DEFAULT_SLOT_TIME_MS = 100  # 100ms = 10 units
DEFAULT_TX_TAIL_MS = 50  # 50ms = 5 units
KISS_COMMAND_DELAY_S = 0.05  # 50ms delay between commands

# Global connections - we use BOTH socket types!
rfcomm_tx = None  # Raw socket for TX (this works for transmitting)
rfcomm_rx = None  # PyBluez socket for RX (required for receiving)
server = None
log_file = None


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    if log_file:
        log_file.write(line + "\n")
        log_file.flush()


def decode_kiss(data):
    """Try to decode KISS frame for logging."""
    if len(data) < 3:
        return f"(too short: {len(data)} bytes)"
    if data[0] == 0xC0 and data[-1] == 0xC0:
        # Strip FEND markers and command byte
        payload = data[2:-1] if len(data) > 3 else b""
        # Try to extract callsigns from AX.25
        try:
            if len(payload) >= 14:
                dest = bytes([(b >> 1) for b in payload[0:6]]).decode("ascii").strip()
                src = bytes([(b >> 1) for b in payload[7:13]]).decode("ascii").strip()
                return f"KISS: {src} -> {dest} ({len(payload)} bytes)"
        except:
            pass
        return f"KISS frame: {len(payload)} bytes payload"
    return f"Raw: {len(data)} bytes"


def configure_kiss_parameters(sock):
    """
    Configure TNC with KISS parameters after connection.

    Sends TX delay, slot time, and TX tail settings. This may be required
    for some TNCs (like TH-D74) to properly recognize the Bluetooth connection.
    Based on Android app's configureKissParameters() function.
    """
    import time

    log("Configuring KISS parameters...")

    # Set TX delay (time to wait after keying before sending data)
    # 500ms = 50 units (in 10ms units)
    txdelay_units = DEFAULT_TXDELAY_MS // 10
    txdelay_cmd = bytes([KISS_FEND, KISS_CMD_TXDELAY, txdelay_units, KISS_FEND])
    log(f"  Setting TXDELAY to {DEFAULT_TXDELAY_MS}ms ({txdelay_units} units)")
    sock.send(txdelay_cmd)
    time.sleep(KISS_COMMAND_DELAY_S)

    # Set slot time (interval between channel checks)
    # 100ms = 10 units (in 10ms units)
    slot_time_units = DEFAULT_SLOT_TIME_MS // 10
    slot_time_cmd = bytes([KISS_FEND, KISS_CMD_SLOT_TIME, slot_time_units, KISS_FEND])
    log(f"  Setting SLOT_TIME to {DEFAULT_SLOT_TIME_MS}ms ({slot_time_units} units)")
    sock.send(slot_time_cmd)
    time.sleep(KISS_COMMAND_DELAY_S)

    # Set TX tail (time to keep transmitter keyed after data)
    # 50ms = 5 units (in 10ms units)
    tx_tail_units = DEFAULT_TX_TAIL_MS // 10
    tx_tail_cmd = bytes([KISS_FEND, KISS_CMD_TX_TAIL, tx_tail_units, KISS_FEND])
    log(f"  Setting TX_TAIL to {DEFAULT_TX_TAIL_MS}ms ({tx_tail_units} units)")
    sock.send(tx_tail_cmd)
    time.sleep(KISS_COMMAND_DELAY_S)

    log("KISS parameters configured successfully!")


def ble_write(char, value, **kwargs):
    global rfcomm_tx
    data = bytes(value)
    log(f"iPhone -> TNC: {len(data)} bytes")
    log(f"  Hex: {data.hex()}")
    log(f"  {decode_kiss(data)}")
    if rfcomm_tx:
        try:
            sent = rfcomm_tx.send(data)
            log(f"  -> Forwarded to TH-D74 via RAW socket! ({sent} bytes sent)")
        except Exception as e:
            log(f"  ERROR sending to TNC: {e}")
    else:
        log(f"  WARNING: TNC TX socket not connected!")


async def tnc_reader():
    global rfcomm_rx, server
    import select

    log("TNC reader started (using PyBluez socket)")
    loop = asyncio.get_event_loop()

    # Use select() for non-blocking reads
    fd = rfcomm_rx.fileno()

    def blocking_read():
        """Blocking read with select - runs in executor."""
        readable, _, _ = select.select([fd], [], [], 1.0)
        if readable:
            return rfcomm_rx.recv(1024)
        return None

    while rfcomm_rx:
        try:
            data = await loop.run_in_executor(None, blocking_read)
            if data:
                log(f"TNC -> iPhone: {len(data)} bytes")
                log(f"  Hex: {data.hex()}")
                log(f"  {decode_kiss(data)}")
                if server:
                    char = server.get_characteristic(NUS_RX)
                    if char:
                        char.value = bytearray(data)
                        server.update_value(NUS_SERVICE, NUS_RX)
                        log(f"  -> Forwarded to iPhone via BLE notify")
        except Exception as e:
            log(f"TNC read error: {e}")
            break


async def main():
    global rfcomm_tx, rfcomm_rx, server, log_file

    log_file = open("/tmp/bridge_packets.log", "w")

    subprocess.run(["sudo", "hciconfig", "hci0", "name", "PiBTBridge"], capture_output=True)
    subprocess.run(["bluetoothctl", "system-alias", "PiBTBridge"], capture_output=True)

    # DISCOVERY: Raw socket works for TX, PyBluez works for RX
    # Try connecting raw socket FIRST, then see if PyBluez can also connect

    # 1. Connect raw socket for TRANSMITTING (connect first!)
    log("Connecting raw socket for TX...")
    rfcomm_tx = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    rfcomm_tx.settimeout(15)
    try:
        rfcomm_tx.connect((TH_D74_MAC, SPP_CHANNEL))
        rfcomm_tx.settimeout(None)
        log("Raw TX socket CONNECTED!")
    except Exception as e:
        log(f"Failed to connect raw TX socket: {e}")
        return

    # Skip KISS parameters - they might be interfering
    # configure_kiss_parameters(rfcomm_tx)
    log("Skipping KISS parameter configuration (testing)")

    # 2. Try to connect PyBluez socket for RECEIVING
    log("Attempting PyBluez socket for RX...")
    try:
        rfcomm_rx = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        rfcomm_rx.connect((TH_D74_MAC, SPP_CHANNEL))
        log("PyBluez RX socket CONNECTED!")
    except Exception as e:
        log(f"PyBluez RX socket failed (expected): {e}")
        log("Using raw socket for both TX and RX")
        rfcomm_rx = rfcomm_tx

    log("Starting BLE server...")
    server = BlessServer(name="PiBTBridge", loop=None)
    server.write_request_func = ble_write

    gatt = {
        NUS_SERVICE: {
            NUS_TX: {
                "Properties": GATTCharacteristicProperties.write
                | GATTCharacteristicProperties.write_without_response,
                "Permissions": GATTAttributePermissions.writeable,
                "Value": bytearray(b""),
            },
            NUS_RX: {
                "Properties": GATTCharacteristicProperties.read
                | GATTCharacteristicProperties.notify,
                "Permissions": GATTAttributePermissions.readable,
                "Value": bytearray(b""),
            },
        }
    }

    await server.add_gatt(gatt)
    await server.start()

    # Set discoverable and enable advertising - these might fail/timeout, which is OK
    try:
        subprocess.run(["bluetoothctl", "discoverable", "on"], capture_output=True, timeout=5)
    except subprocess.TimeoutExpired:
        log("Warning: bluetoothctl discoverable timed out")

    try:
        subprocess.run(["sudo", "btmgmt", "advertising", "on"], capture_output=True, timeout=5)
    except subprocess.TimeoutExpired:
        log("Warning: btmgmt advertising timed out (may already be advertising)")

    name = "PiBTBridge"
    adv = bytearray([0x02, 0x01, 0x06, len(name) + 1, 0x09]) + name.encode()
    adv = adv.ljust(31, b"\x00")
    try:
        subprocess.run(
            ["sudo", "hcitool", "cmd", "0x08", "0x0008", f"0x{len(name) + 5:02x}"]
            + [f"0x{b:02x}" for b in adv],
            capture_output=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        log("Warning: hcitool advertising data timed out")

    log("")
    log("=" * 60)
    log("BRIDGE READY!")
    log("  iPhone <--BLE--> Pi <--RFCOMM--> TH-D74")
    log("Connect from iPhone and send a packet!")
    log("=" * 60)
    log("")

    # Start TNC reader task
    reader_task = asyncio.create_task(tnc_reader())

    # Run indefinitely (for systemd service)
    try:
        while True:
            await asyncio.sleep(3600)  # Sleep 1 hour at a time
    except asyncio.CancelledError:
        pass

    reader_task.cancel()
    rfcomm_rx.close()
    if rfcomm_tx and rfcomm_tx != rfcomm_rx:
        rfcomm_tx.close()
    await server.stop()
    log_file.close()
    log("Bridge stopped")


if __name__ == "__main__":
    asyncio.run(main())
