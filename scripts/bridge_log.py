#!/usr/bin/env python3
"""Bridge with packet logging and web interface for debugging."""

import asyncio
import json
import subprocess
import socket  # Raw socket for TX (works!)
import bluetooth  # PyBluez for RX (required for receiving)
from datetime import datetime
from pathlib import Path
from bless import BlessServer, GATTCharacteristicProperties, GATTAttributePermissions

# Try to import aiohttp for web interface
try:
    from aiohttp import web

    HAS_WEB = True
except ImportError:
    HAS_WEB = False
    print("Warning: aiohttp not installed, web interface disabled")

NUS_SERVICE = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_RX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# TH-D74 configuration
TH_D74_MAC = "24:71:89:8D:26:EF"
SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"
SPP_CHANNEL = 2  # TH-D74 SPP channel

# Web server port
WEB_PORT = 8080

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
reader_task = None  # TNC reader task

# Statistics
stats = {
    "started_at": None,
    "packets_tx": 0,
    "packets_rx": 0,
    "bytes_tx": 0,
    "bytes_rx": 0,
    "ble_connected": False,
    "classic_connected": False,
}


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


def ble_write(char, value, **kwargs):
    global rfcomm_tx
    data = bytes(value)
    log(f"iPhone -> TNC: {len(data)} bytes")
    log(f"  Hex: {data.hex()}")
    log(f"  {decode_kiss(data)}")
    stats["ble_connected"] = True
    if rfcomm_tx:
        try:
            sent = rfcomm_tx.send(data)
            stats["packets_tx"] += 1
            stats["bytes_tx"] += sent
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
                stats["packets_rx"] += 1
                stats["bytes_rx"] += len(data)
                if server:
                    char = server.get_characteristic(NUS_RX)
                    if char:
                        char.value = bytearray(data)
                        server.update_value(NUS_SERVICE, NUS_RX)
                        log(f"  -> Forwarded to iPhone via BLE notify")
        except Exception as e:
            log(f"TNC read error: {e}")
            break


# --- Connection Management ---


async def connect_classic():
    """Connect to Classic Bluetooth TNC."""
    global rfcomm_tx, rfcomm_rx, reader_task

    if stats["classic_connected"]:
        log("Classic BT already connected")
        return True, "Already connected"

    log("Connecting to TNC...")

    # 1. Connect raw socket for TX
    try:
        rfcomm_tx = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        rfcomm_tx.settimeout(15)
        rfcomm_tx.connect((TH_D74_MAC, SPP_CHANNEL))
        rfcomm_tx.settimeout(None)
        stats["classic_connected"] = True
        log("Raw TX socket CONNECTED!")
    except Exception as e:
        log(f"Failed to connect raw TX socket: {e}")
        stats["classic_connected"] = False
        rfcomm_tx = None
        return False, str(e)

    # 2. Try PyBluez socket for RX
    try:
        rfcomm_rx = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        rfcomm_rx.connect((TH_D74_MAC, SPP_CHANNEL))
        log("PyBluez RX socket CONNECTED!")
    except Exception as e:
        log(f"PyBluez RX socket failed (expected): {e}")
        log("Using raw socket for both TX and RX")
        rfcomm_rx = rfcomm_tx

    # Start reader task
    reader_task = asyncio.create_task(tnc_reader())
    log("TNC connection established")
    return True, "Connected"


async def disconnect_classic():
    """Disconnect Classic Bluetooth TNC."""
    global rfcomm_tx, rfcomm_rx, reader_task

    if not stats["classic_connected"]:
        log("Classic BT already disconnected")
        return True, "Already disconnected"

    log("Disconnecting from TNC...")

    # Cancel reader task
    if reader_task:
        reader_task.cancel()
        try:
            await reader_task
        except asyncio.CancelledError:
            pass
        reader_task = None

    # Close sockets
    if rfcomm_rx and rfcomm_rx != rfcomm_tx:
        try:
            rfcomm_rx.close()
        except Exception:
            pass
    rfcomm_rx = None

    if rfcomm_tx:
        try:
            rfcomm_tx.close()
        except Exception:
            pass
    rfcomm_tx = None

    stats["classic_connected"] = False
    log("TNC disconnected")
    return True, "Disconnected"


async def restart_ble():
    """Restart BLE advertising."""
    global server

    log("Restarting BLE advertising...")

    # Re-enable discoverable and advertising
    try:
        subprocess.run(["bluetoothctl", "discoverable", "on"], capture_output=True, timeout=5)
    except subprocess.TimeoutExpired:
        pass

    try:
        subprocess.run(["sudo", "btmgmt", "advertising", "on"], capture_output=True, timeout=5)
    except subprocess.TimeoutExpired:
        pass

    # Reset BLE connection status (will be set true when phone writes)
    stats["ble_connected"] = False
    log("BLE advertising restarted")
    return True, "BLE restarted"


# --- Web Interface ---


async def handle_index(request):
    """Serve the main status page."""
    uptime = 0
    if stats["started_at"]:
        uptime = (datetime.now() - stats["started_at"]).total_seconds()

    # Pre-define buttons to avoid backslash in f-string (Python 3.11 compat)
    connect_btn = (
        "<button class='btn btn-success' onclick=\"action('classic_connect')\">Connect</button>"
    )
    disconnect_btn = "<button class='btn btn-danger' onclick=\"action('classic_disconnect')\">Disconnect</button>"

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Pi BT Bridge</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .card {{ background: #f5f5f5; border-radius: 8px; padding: 15px; margin: 10px 0; }}
        .status {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 14px; }}
        .connected {{ background: #d4edda; color: #155724; }}
        .disconnected {{ background: #f8d7da; color: #721c24; }}
        h1 {{ color: #333; }}
        h3 {{ margin: 0 0 10px 0; color: #666; }}
        .stat {{ display: inline-block; text-align: center; padding: 10px 20px; }}
        .stat-value {{ font-size: 24px; font-weight: bold; }}
        .stat-label {{ font-size: 12px; color: #666; }}
        .btn {{ padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; margin: 4px; }}
        .btn-primary {{ background: #007bff; color: white; }}
        .btn-success {{ background: #28a745; color: white; }}
        .btn-danger {{ background: #dc3545; color: white; }}
        .btn-warning {{ background: #ffc107; color: #333; }}
        .btn:hover {{ opacity: 0.8; }}
        .btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        .controls {{ margin-top: 10px; }}
        .toast {{ position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #333; color: white; padding: 12px 24px; border-radius: 8px; display: none; z-index: 1000; }}
        .toast.show {{ display: block; animation: fadeIn 0.3s; }}
        @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
    </style>
</head>
<body>
    <h1>Pi BT Bridge</h1>
    
    <div class="card">
        <h3>Connections</h3>
        <p>BLE (Phone): <span class="status {"connected" if stats["ble_connected"] else "disconnected"}">
            {"Connected" if stats["ble_connected"] else "Waiting"}</span>
            <button class="btn btn-warning" onclick="action('ble_restart')">Restart BLE</button>
        </p>
        <p>Classic (TNC): <span class="status {"connected" if stats["classic_connected"] else "disconnected"}">
            {"Connected" if stats["classic_connected"] else "Disconnected"}</span>
            {disconnect_btn if stats["classic_connected"] else connect_btn}
        </p>
        <p>Target: <code>{TH_D74_MAC}</code> (RFCOMM {SPP_CHANNEL})</p>
    </div>
    
    <div class="card">
        <h3>Statistics</h3>
        <div class="stat">
            <div class="stat-value">{stats["packets_tx"]}</div>
            <div class="stat-label">Packets TX</div>
        </div>
        <div class="stat">
            <div class="stat-value">{stats["packets_rx"]}</div>
            <div class="stat-label">Packets RX</div>
        </div>
        <div class="stat">
            <div class="stat-value">{stats["bytes_tx"]}</div>
            <div class="stat-label">Bytes TX</div>
        </div>
        <div class="stat">
            <div class="stat-value">{stats["bytes_rx"]}</div>
            <div class="stat-label">Bytes RX</div>
        </div>
    </div>
    
    <div class="card">
        <h3>System</h3>
        <p>Uptime: {int(uptime)}s</p>
        <p>Version: 1.1.0</p>
        <div class="controls">
            <button class="btn btn-danger" onclick="action('restart')">Restart Bridge</button>
        </div>
    </div>
    
    <div id="toast" class="toast"></div>
    
    <script>
        let autoRefresh = true;
        
        async function action(name) {{
            autoRefresh = false;  // Pause auto-refresh during action
            const toast = document.getElementById('toast');
            toast.textContent = 'Working...';
            toast.classList.add('show');
            
            try {{
                const resp = await fetch('/api/action/' + name, {{ method: 'POST' }});
                const data = await resp.json();
                toast.textContent = data.message || (data.success ? 'Success' : 'Failed');
                
                // Longer delay for restart since service needs time to come back
                const delay = (name === 'restart') ? 8000 : 1500;
                if (name === 'restart') {{
                    toast.textContent = 'Restarting... page will reload in 8s';
                }}
                setTimeout(() => {{
                    toast.classList.remove('show');
                    location.reload();
                }}, delay);
            }} catch (e) {{
                // For restart, connection error is expected - wait and reload
                if (name === 'restart') {{
                    toast.textContent = 'Restarting... page will reload in 8s';
                    setTimeout(() => location.reload(), 8000);
                }} else {{
                    toast.textContent = 'Error: ' + e.message;
                    setTimeout(() => {{
                        toast.classList.remove('show');
                        autoRefresh = true;
                    }}, 3000);
                }}
            }}
        }}
        
        // Auto-refresh every 5 seconds
        setTimeout(() => {{ if (autoRefresh) location.reload(); }}, 5000);
    </script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")


async def handle_api_status(request):
    """Return JSON status."""
    uptime = 0
    if stats["started_at"]:
        uptime = (datetime.now() - stats["started_at"]).total_seconds()

    return web.json_response(
        {
            "ble_connected": stats["ble_connected"],
            "classic_connected": stats["classic_connected"],
            "target_address": TH_D74_MAC,
            "rfcomm_channel": SPP_CHANNEL,
            "packets_tx": stats["packets_tx"],
            "packets_rx": stats["packets_rx"],
            "bytes_tx": stats["bytes_tx"],
            "bytes_rx": stats["bytes_rx"],
            "uptime_seconds": uptime,
        }
    )


async def handle_api_action(request):
    """Handle control actions."""
    action = request.match_info.get("action", "")
    log(f"Web action requested: {action}")

    if action == "classic_connect":
        success, message = await connect_classic()
        return web.json_response({"success": success, "message": message})

    elif action == "classic_disconnect":
        success, message = await disconnect_classic()
        return web.json_response({"success": success, "message": message})

    elif action == "ble_restart":
        success, message = await restart_ble()
        return web.json_response({"success": success, "message": message})

    elif action == "restart":
        log("Restart requested via web interface")
        # Use systemctl to restart the service (will kill this process)
        import os

        os.system("sudo systemctl restart bt-bridge &")
        return web.json_response({"success": True, "message": "Restarting..."})

    else:
        return web.json_response(
            {"success": False, "message": f"Unknown action: {action}"}, status=400
        )


async def start_web_server():
    """Start the web server."""
    if not HAS_WEB:
        return None

    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/status", handle_api_status)
    app.router.add_post("/api/action/{action}", handle_api_action)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEB_PORT)
    await site.start()
    log(f"Web interface started on http://0.0.0.0:{WEB_PORT}")
    return runner


async def main():
    global rfcomm_tx, rfcomm_rx, server, log_file, reader_task

    stats["started_at"] = datetime.now()
    log_file = open("/tmp/bridge_packets.log", "w")

    subprocess.run(["sudo", "hciconfig", "hci0", "name", "PiBTBridge"], capture_output=True)
    subprocess.run(["bluetoothctl", "system-alias", "PiBTBridge"], capture_output=True)

    # Start web server
    web_runner = await start_web_server()

    # Try to connect to TNC at startup
    log("Attempting initial TNC connection...")
    await connect_classic()

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

    # Wait a moment for bless/BlueZ to settle
    await asyncio.sleep(1)

    # Set up BLE advertising using bluetoothctl
    # This registers a proper advertisement with BlueZ that iOS can see
    log("Configuring BLE advertising...")

    # Use bluetoothctl to set up advertising with NUS UUID
    # Run in a subprocess that stays alive to keep the advertisement active
    adv_script = """
menu advertise
name PiBTBridge  
uuids 6e400001-b5a3-f393-e0a9-e50e24dcca9e
discoverable on
back
advertise peripheral
"""
    # Start bluetoothctl with advertisement config
    adv_proc = subprocess.Popen(
        ["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    adv_proc.stdin.write(adv_script.encode())
    adv_proc.stdin.flush()
    # Don't close stdin - keep process alive to maintain advertisement
    await asyncio.sleep(2)
    log("BLE advertising configured via bluetoothctl")

    log("")
    log("=" * 60)
    log("BRIDGE READY!")
    log("  iPhone <--BLE--> Pi <--RFCOMM--> TH-D74")
    log(f"  Web interface: http://<pi-ip>:{WEB_PORT}")
    log("Connect from iPhone and send a packet!")
    log("=" * 60)
    log("")

    # Run indefinitely (for systemd service)
    try:
        while True:
            await asyncio.sleep(3600)  # Sleep 1 hour at a time
    except asyncio.CancelledError:
        pass

    # Cleanup
    if reader_task:
        reader_task.cancel()
        try:
            await reader_task
        except asyncio.CancelledError:
            pass
    if rfcomm_rx:
        rfcomm_rx.close()
    if rfcomm_tx and rfcomm_tx != rfcomm_rx:
        rfcomm_tx.close()
    await server.stop()
    if web_runner:
        await web_runner.cleanup()
    log_file.close()
    log("Bridge stopped")


if __name__ == "__main__":
    asyncio.run(main())
