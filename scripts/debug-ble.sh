#!/bin/bash
# Debug script to verify BLE advertising is working correctly
# Run this on the Pi while the daemon is running

set -e

echo "=== BLE Advertising Debug ==="
echo

# Check if hci0 is up
echo "1. Checking Bluetooth adapter..."
if hciconfig hci0 2>/dev/null | grep -q "UP RUNNING"; then
    echo "   [OK] hci0 is UP and RUNNING"
else
    echo "   [WARN] hci0 may not be up. Running: rfkill unblock bluetooth && hciconfig hci0 up"
    sudo rfkill unblock bluetooth
    sudo hciconfig hci0 up
    sleep 1
fi

# Show adapter info
echo
echo "2. Adapter information:"
hciconfig hci0 name
hciconfig hci0 class

# Check if advertising
echo
echo "3. Checking advertising status..."
sudo btmgmt info 2>/dev/null | grep -E "(current settings|name)" || true

# Check for our GATT application in D-Bus
echo
echo "4. Checking D-Bus for GATT application..."
if busctl tree org.bluez 2>/dev/null | grep -q "gatt"; then
    echo "   [OK] GATT application registered"
    busctl tree org.bluez 2>/dev/null | grep -E "(gatt|advertisement)" || true
else
    echo "   [WARN] No GATT application found in D-Bus"
fi

# Check for advertisements
echo
echo "5. Checking LEAdvertisingManager..."
busctl introspect org.bluez /org/bluez/hci0 2>/dev/null | grep -E "LEAdvertising" || echo "   No LEAdvertisingManager found"

# Try to see current advertisements
echo
echo "6. Active advertisements:"
dbus-send --system --dest=org.bluez --print-reply /org/bluez/hci0 org.freedesktop.DBus.Properties.Get string:org.bluez.LEAdvertisingManager1 string:ActiveInstances 2>/dev/null || echo "   Could not query active instances"

# Show discoverable status
echo
echo "7. Discoverable status:"
bluetoothctl show 2>/dev/null | grep -E "(Discoverable|Pairable|Alias|Name)" || true

echo
echo "=== To test with iPhone ==="
echo "1. Open the aprs-chat app and go to Settings -> Serial KISS"
echo "2. Tap 'Scan for Devices'"
echo "3. You should see 'PiBTBridge' (or your configured name) in the list"
echo
echo "If not visible, try:"
echo "  - Restart the bt-bridge service: sudo systemctl restart bt-bridge"
echo "  - Check logs: journalctl -u bt-bridge -f"
echo "  - Use 'nRF Connect' app on iPhone to scan for ALL BLE devices"
