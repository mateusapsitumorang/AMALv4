#!/bin/bash
# Start Android Emulator for MobSF Dynamic Analysis

export ANDROID_HOME=/opt/android-sdk
export PATH=$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools:$PATH

AVD_NAME="MobSF_AVD"
LOG_FILE="/opt/CAPEv2/logs/emulator.log"

mkdir -p "$(dirname "$LOG_FILE")"

# Clear stale lock files
rm -f "$HOME/.android/avd/${AVD_NAME}.avd/multiinstance.lock"
rm -f "$HOME/.android/avd/${AVD_NAME}.avd/hardware-qemu.ini.lock"
rm -rf /run/user/$(id -u)/avd/running/ 2>/dev/null

echo "[$(date)] Starting Android Emulator: $AVD_NAME" >> "$LOG_FILE"

exec emulator \
    -avd "$AVD_NAME" \
    -accel on \
    -cores 4 \
    -no-snapshot -no-audio -no-window -no-boot-anim \
    -no-metrics -netfast \
    -memory 8072 \
    -writable-system -selinux permissive \
    -gpu swiftshader_indirect \
    >> "$LOG_FILE" 2>&1
