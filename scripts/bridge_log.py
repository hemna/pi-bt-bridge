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

# Try to import dbus for pairing agent
try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib

    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False
    print("Warning: dbus not installed, pairing agent disabled")

NUS_SERVICE = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_RX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# Config file path
CONFIG_FILE = Path("/etc/bt-bridge/config.json")

# Default TNC configuration (can be overridden by config file)
DEFAULT_TNC_MAC = "24:71:89:8D:26:EF"
DEFAULT_TNC_CHANNEL = 2
SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"

# Current TNC config (loaded from file or defaults)
tnc_config = {"mac": DEFAULT_TNC_MAC, "channel": DEFAULT_TNC_CHANNEL, "name": "TH-D74"}

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
agent = None  # D-Bus pairing agent

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


# D-Bus Pairing Agent - auto-accepts all pairing requests
AGENT_INTERFACE = "org.bluez.Agent1"
AGENT_PATH = "/com/pibtbridge/agent"

if HAS_DBUS:

    class PairingAgent(dbus.service.Object):
        """BlueZ pairing agent that auto-accepts all requests."""

        @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
        def Release(self):
            print("[Agent] Released", flush=True)

        @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
        def AuthorizeService(self, device, uuid):
            print(f"[Agent] AuthorizeService {device} {uuid}", flush=True)

        @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="s")
        def RequestPinCode(self, device):
            print(f"[Agent] RequestPinCode {device}", flush=True)
            return "0000"

        @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="u")
        def RequestPasskey(self, device):
            print(f"[Agent] RequestPasskey {device}", flush=True)
            return dbus.UInt32(0)

        @dbus.service.method(AGENT_INTERFACE, in_signature="ouq", out_signature="")
        def DisplayPasskey(self, device, passkey, entered):
            print(f"[Agent] DisplayPasskey {device}: {passkey:06d}", flush=True)

        @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
        def DisplayPinCode(self, device, pincode):
            print(f"[Agent] DisplayPinCode {device}: {pincode}", flush=True)

        @dbus.service.method(AGENT_INTERFACE, in_signature="ou", out_signature="")
        def RequestConfirmation(self, device, passkey):
            print(
                f"[Agent] RequestConfirmation {device}: {passkey:06d} - AUTO ACCEPTING", flush=True
            )
            # Auto-accept by not raising an exception

        @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="")
        def RequestAuthorization(self, device):
            print(f"[Agent] RequestAuthorization {device} - AUTO ACCEPTING", flush=True)
            # Auto-accept

        @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
        def Cancel(self):
            print("[Agent] Cancel", flush=True)


def load_config():
    """Load TNC configuration from file."""
    global tnc_config
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
                tnc_config["mac"] = data.get("tnc_mac", DEFAULT_TNC_MAC)
                tnc_config["channel"] = data.get("tnc_channel", DEFAULT_TNC_CHANNEL)
                tnc_config["name"] = data.get("tnc_name", "Unknown")
                print(f"Loaded config: {tnc_config['name']} at {tnc_config['mac']}", flush=True)
        except Exception as e:
            print(f"Failed to load config: {e}", flush=True)
    else:
        print(f"No config file found, using defaults", flush=True)


def save_config():
    """Save TNC configuration to file."""
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(
                {
                    "tnc_mac": tnc_config["mac"],
                    "tnc_channel": tnc_config["channel"],
                    "tnc_name": tnc_config["name"],
                },
                f,
                indent=2,
            )
        print(f"Saved config: {tnc_config['name']} at {tnc_config['mac']}", flush=True)
        return True
    except Exception as e:
        print(f"Failed to save config: {e}", flush=True)
        return False


async def scan_bluetooth_devices(duration=8):
    """Scan for nearby Bluetooth Classic devices."""
    log(f"Scanning for Bluetooth devices ({duration}s)...")
    devices = []

    try:
        # Use bluetoothctl for scanning
        proc = await asyncio.create_subprocess_exec(
            "bluetoothctl",
            "--timeout",
            str(duration),
            "scan",
            "on",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # Get list of discovered devices
        proc = await asyncio.create_subprocess_exec(
            "bluetoothctl",
            "devices",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        for line in stdout.decode().strip().split("\n"):
            if line.startswith("Device "):
                parts = line.split(" ", 2)
                if len(parts) >= 3:
                    mac = parts[1]
                    name = parts[2] if len(parts) > 2 else "Unknown"
                    devices.append({"mac": mac, "name": name})

        log(f"Found {len(devices)} devices")
    except Exception as e:
        log(f"Scan error: {e}")

    return devices


async def pair_device(mac):
    """Pair with a Bluetooth device."""
    log(f"Pairing with {mac}...")

    try:
        # Trust the device first
        proc = await asyncio.create_subprocess_exec(
            "bluetoothctl",
            "trust",
            mac,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # Pair with the device
        proc = await asyncio.create_subprocess_exec(
            "bluetoothctl",
            "pair",
            mac,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        output = stdout.decode() + stderr.decode()
        if "Pairing successful" in output or "already paired" in output.lower():
            log(f"Paired with {mac}")
            return True, "Paired successfully"
        else:
            log(f"Pairing failed: {output}")
            return False, output
    except Exception as e:
        log(f"Pairing error: {e}")
        return False, str(e)


async def find_spp_channel(mac):
    """Find the SPP (Serial Port) channel for a device."""
    log(f"Looking up SPP channel for {mac}...")

    try:
        # Use sdptool to find SPP service
        proc = await asyncio.create_subprocess_exec(
            "sdptool",
            "search",
            "--bdaddr",
            mac,
            "SP",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        output = stdout.decode()
        # Parse output for channel number
        for line in output.split("\n"):
            if "Channel:" in line:
                try:
                    channel = int(line.split(":")[-1].strip())
                    log(f"Found SPP channel: {channel}")
                    return channel
                except ValueError:
                    pass

        # Default to channel 1 if not found
        log("SPP channel not found, defaulting to 1")
        return 1
    except Exception as e:
        log(f"SPP lookup error: {e}")
        return 1


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

    log(f"Connecting to TNC at {tnc_config['mac']} channel {tnc_config['channel']}...")

    # 1. Connect raw socket for TX
    try:
        rfcomm_tx = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        rfcomm_tx.settimeout(15)
        rfcomm_tx.connect((tnc_config["mac"], tnc_config["channel"]))
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
        rfcomm_rx.connect((tnc_config["mac"], tnc_config["channel"]))
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
        .btn-secondary {{ background: #6c757d; color: white; }}
        .btn:hover {{ opacity: 0.8; }}
        .btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        .controls {{ margin-top: 10px; }}
        .toast {{ position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #333; color: white; padding: 12px 24px; border-radius: 8px; display: none; z-index: 1000; }}
        .toast.show {{ display: block; animation: fadeIn 0.3s; }}
        @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
        .device-list {{ margin: 10px 0; max-height: 200px; overflow-y: auto; }}
        .device-item {{ padding: 10px; margin: 5px 0; background: white; border-radius: 4px; display: flex; justify-content: space-between; align-items: center; }}
        .device-item.selected {{ border: 2px solid #007bff; }}
        .device-name {{ font-weight: bold; }}
        .device-mac {{ font-size: 12px; color: #666; font-family: monospace; }}
        .scanning {{ color: #666; font-style: italic; }}
        #scan-results {{ min-height: 50px; }}
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
        <p>Target: <code>{tnc_config["mac"]}</code> (RFCOMM {tnc_config["channel"]}) - {tnc_config["name"]}</p>
    </div>

    <div class="card">
        <h3>TNC Selection</h3>
        <p>Scan for nearby Bluetooth devices to select a different TNC.</p>
        <button class="btn btn-primary" onclick="startScan()" id="scan-btn">Scan for Devices</button>
        <div id="scan-results"></div>
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
        <p>Version: 1.2.0</p>
        <div class="controls">
            <button class="btn btn-danger" onclick="action('restart')">Restart Bridge</button>
        </div>
    </div>
    
    <div id="toast" class="toast"></div>
    
    <script>
        let autoRefresh = true;
        
        async function action(name) {{
            autoRefresh = false;
            const toast = document.getElementById('toast');
            toast.textContent = 'Working...';
            toast.classList.add('show');
            
            try {{
                const resp = await fetch('/api/action/' + name, {{ method: 'POST' }});
                const data = await resp.json();
                toast.textContent = data.message || (data.success ? 'Success' : 'Failed');
                
                const delay = (name === 'restart') ? 8000 : 1500;
                if (name === 'restart') {{
                    toast.textContent = 'Restarting... page will reload in 8s';
                }}
                setTimeout(() => {{
                    toast.classList.remove('show');
                    location.reload();
                }}, delay);
            }} catch (e) {{
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

        async function startScan() {{
            autoRefresh = false;
            const btn = document.getElementById('scan-btn');
            const results = document.getElementById('scan-results');
            
            btn.disabled = true;
            btn.textContent = 'Scanning...';
            results.innerHTML = '<p class="scanning">Scanning for Bluetooth devices (8 seconds)...</p>';
            
            try {{
                const resp = await fetch('/api/scan', {{ method: 'POST' }});
                const data = await resp.json();
                
                if (data.devices && data.devices.length > 0) {{
                    let html = '<div class="device-list">';
                    for (const dev of data.devices) {{
                        html += `<div class="device-item">
                            <div>
                                <div class="device-name">${{dev.name}}</div>
                                <div class="device-mac">${{dev.mac}}</div>
                            </div>
                            <button class="btn btn-primary" onclick="selectDevice('${{dev.mac}}', '${{dev.name}}')">Select</button>
                        </div>`;
                    }}
                    html += '</div>';
                    results.innerHTML = html;
                }} else {{
                    results.innerHTML = '<p>No devices found. Make sure your TNC is in pairing mode.</p>';
                }}
            }} catch (e) {{
                results.innerHTML = '<p>Scan failed: ' + e.message + '</p>';
            }}
            
            btn.disabled = false;
            btn.textContent = 'Scan for Devices';
        }}

        async function selectDevice(mac, name) {{
            const toast = document.getElementById('toast');
            toast.textContent = 'Selecting device...';
            toast.classList.add('show');
            
            try {{
                const resp = await fetch('/api/select', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ mac: mac, name: name }})
                }});
                const data = await resp.json();
                toast.textContent = data.message || (data.success ? 'Device selected!' : 'Failed');
                setTimeout(() => {{
                    toast.classList.remove('show');
                    location.reload();
                }}, 1500);
            }} catch (e) {{
                toast.textContent = 'Error: ' + e.message;
                setTimeout(() => toast.classList.remove('show'), 3000);
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
            "target_address": tnc_config["mac"],
            "rfcomm_channel": tnc_config["channel"],
            "tnc_name": tnc_config["name"],
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


async def handle_api_scan(request):
    """Scan for nearby Bluetooth devices."""
    log("Starting Bluetooth scan from web interface...")
    try:
        devices = await scan_bluetooth_devices()
        return web.json_response({"success": True, "devices": devices})
    except Exception as e:
        log(f"Scan error: {e}")
        return web.json_response({"success": False, "error": str(e), "devices": []})


async def handle_api_select(request):
    """Select a new TNC device."""
    global tnc_config

    try:
        data = await request.json()
        mac = data.get("mac")
        name = data.get("name", "Unknown")

        if not mac:
            return web.json_response({"success": False, "message": "MAC address required"})

        log(f"Selecting new TNC: {name} ({mac})")

        # Disconnect from current TNC if connected
        if stats["classic_connected"]:
            await disconnect_classic()

        # Pair with the new device
        success, pair_msg = await pair_device(mac)
        if not success and "already paired" not in pair_msg.lower():
            log(f"Pairing failed, continuing anyway: {pair_msg}")

        # Find the SPP channel
        channel = await find_spp_channel(mac)

        # Update config
        tnc_config["mac"] = mac
        tnc_config["channel"] = channel
        tnc_config["name"] = name

        # Save to file
        save_config()

        # Try to connect to the new TNC
        connect_success, connect_msg = await connect_classic()

        return web.json_response(
            {
                "success": True,
                "message": f"Selected {name} on channel {channel}",
                "connected": connect_success,
                "channel": channel,
            }
        )

    except Exception as e:
        log(f"Select error: {e}")
        return web.json_response({"success": False, "message": str(e)})


async def start_web_server():
    """Start the web server."""
    if not HAS_WEB:
        return None

    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/status", handle_api_status)
    app.router.add_post("/api/action/{action}", handle_api_action)
    app.router.add_post("/api/scan", handle_api_scan)
    app.router.add_post("/api/select", handle_api_select)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEB_PORT)
    await site.start()
    log(f"Web interface started on http://0.0.0.0:{WEB_PORT}")
    return runner


async def main():
    global rfcomm_tx, rfcomm_rx, server, log_file, reader_task, agent

    # Load TNC config from file (or use defaults)
    load_config()

    stats["started_at"] = datetime.now()
    log_file = open("/tmp/bridge_packets.log", "w")

    subprocess.run(["sudo", "hciconfig", "hci0", "name", "PiBTBridge"], capture_output=True)
    subprocess.run(["bluetoothctl", "system-alias", "PiBTBridge"], capture_output=True)

    # Start D-Bus pairing agent to auto-accept BLE pairing
    if HAS_DBUS:
        log("Starting D-Bus pairing agent...")
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            bus = dbus.SystemBus()

            # Create and register the agent
            agent = PairingAgent(bus, AGENT_PATH)

            # Get the AgentManager and register our agent
            agent_manager = dbus.Interface(
                bus.get_object("org.bluez", "/org/bluez"), "org.bluez.AgentManager1"
            )
            agent_manager.RegisterAgent(AGENT_PATH, "NoInputNoOutput")
            agent_manager.RequestDefaultAgent(AGENT_PATH)
            log("D-Bus pairing agent registered successfully")

            # Start GLib main loop in a thread for D-Bus events
            import threading

            def run_glib():
                loop = GLib.MainLoop()
                loop.run()

            glib_thread = threading.Thread(target=run_glib, daemon=True)
            glib_thread.start()
        except Exception as e:
            log(f"Failed to register D-Bus agent: {e}")
    else:
        log("D-Bus not available, pairing may fail")

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

    # Set up BLE advertising using raw HCI commands
    # Must disable advertising first, then set parameters, then re-enable
    log("Configuring BLE advertising via raw HCI...")

    # 1. Disable any existing advertising
    subprocess.run(
        ["sudo", "hcitool", "-i", "hci0", "cmd", "0x08", "0x000A", "00"],
        capture_output=True,
        timeout=5,
    )
    await asyncio.sleep(0.5)

    # 2. Set advertising parameters (ADV_IND - connectable undirected)
    subprocess.run(
        [
            "sudo",
            "hcitool",
            "-i",
            "hci0",
            "cmd",
            "0x08",
            "0x0006",
            "20",
            "00",
            "40",
            "00",  # Min/max interval
            "00",  # ADV_IND
            "00",
            "00",  # Own/peer address type
            "00",
            "00",
            "00",
            "00",
            "00",
            "00",  # Peer address
            "07",
            "00",
        ],  # Channel map, filter
        capture_output=True,
        timeout=5,
    )

    # 3. Set advertising data: Flags + Complete Local Name "PiBTBridge"
    subprocess.run(
        [
            "sudo",
            "hcitool",
            "-i",
            "hci0",
            "cmd",
            "0x08",
            "0x0008",
            "0E",  # Length
            "02",
            "01",
            "06",  # Flags: General Discoverable
            "0B",
            "09",  # Length + Complete Local Name type
            "50",
            "69",
            "42",
            "54",
            "42",
            "72",
            "69",
            "64",
            "67",
            "65",
        ],  # "PiBTBridge"
        capture_output=True,
        timeout=5,
    )

    # 4. Set scan response with NUS UUID (128-bit little-endian)
    subprocess.run(
        [
            "sudo",
            "hcitool",
            "-i",
            "hci0",
            "cmd",
            "0x08",
            "0x0009",
            "12",  # Length
            "11",
            "07",  # Length + Complete 128-bit UUIDs type
            "9E",
            "CA",
            "DC",
            "24",
            "0E",
            "E5",
            "A9",
            "E0",
            "93",
            "F3",
            "A3",
            "B5",
            "01",
            "00",
            "40",
            "6E",
        ],
        capture_output=True,
        timeout=5,
    )

    # 5. Enable advertising
    result = subprocess.run(
        ["sudo", "hcitool", "-i", "hci0", "cmd", "0x08", "0x000A", "01"],
        capture_output=True,
        timeout=5,
    )
    if b"20 00" in result.stdout:
        log("BLE advertising enabled successfully")
    else:
        log(f"BLE advertising result: {result.stdout.decode() if result.stdout else 'no output'}")

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
