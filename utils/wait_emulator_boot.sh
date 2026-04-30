#!/bin/bash
# Wait for Android emulator to fully boot, then enable ADB over TCP

export ANDROID_HOME=/opt/android-sdk
export PATH=$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools:$PATH

LOG_FILE="/opt/CAPEv2/logs/emulator.log"
TIMEOUT=300
ELAPSED=0

echo "[$(date)] Waiting for emulator device..." >> "$LOG_FILE"

# MobSF container talks to host ADB over 172.17.0.1:5037, so start adb in external mode.
adb -a start-server >> "$LOG_FILE" 2>&1 || true

# Ensure Docker bridge proxy for emulator ADB port exists.
if command -v socat >/dev/null 2>&1; then
    if ! ss -ltn 2>/dev/null | grep -q "172.17.0.1:5555"; then
        nohup socat TCP-LISTEN:5555,bind=172.17.0.1,fork,reuseaddr TCP:127.0.0.1:5555 >> "$LOG_FILE" 2>&1 &
    fi
fi

while ! adb devices | grep -q "emulator-"; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    if [ $ELAPSED -ge $TIMEOUT ]; then
        echo "[$(date)] Timed out waiting for emulator device." >> "$LOG_FILE"
        exit 1
    fi
done

DEVICE=$(adb devices | grep "emulator-" | awk '{print $1}' | head -1)
echo "[$(date)] Emulator device found ($DEVICE). Waiting for boot to complete..." >> "$LOG_FILE"

until adb -s "$DEVICE" shell getprop sys.boot_completed 2>/dev/null | grep -q "1"; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    if [ $ELAPSED -ge $TIMEOUT ]; then
        echo "[$(date)] Timed out waiting for boot_completed." >> "$LOG_FILE"
        exit 1
    fi
done

echo "[$(date)] Emulator boot completed. Enabling ADB over TCP and rooting..." >> "$LOG_FILE"
DEVICE=$(adb devices | grep "emulator-" | awk '{print $1}' | head -1)
adb -s "$DEVICE" root
sleep 2
adb -s "$DEVICE" tcpip 5555
sleep 2

echo "[$(date)] Emulator ready (device: $DEVICE, TCP port 5555)." >> "$LOG_FILE"
