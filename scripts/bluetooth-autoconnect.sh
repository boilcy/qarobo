#!/bin/bash

BLUETOOTH_MAC="58:EA:1F:FF:1C:19"
BLUETOOTH_SINK_NAME="bluez_sink.58_EA_1F_FF_1C_19.a2dp_sink"
RETRY_DELAY=5 # seconds to wait between connection attempts
LOG_FILE="$HOME/.local/share/bluetooth-autoconnect.log"
POLLING_INTERVAL=10 # seconds to check if device is still connected

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"
# --- Functions ---
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}
is_bluetooth_connected() {
    bluetoothctl info "$BLUETOOTH_MAC" | grep -q "Connected: yes"
}
set_default_sink() {
    # Check if pipewire or pulseaudio is active
    if systemctl --user is-active pulseaudio.service &> /dev/null; then
        log_message "PulseAudio is active. Attempting to set default sink using pactl..."
        pactl set-default-sink "$BLUETOOTH_SINK_NAME"
        return $?
    elif systemctl --user is-active pipewire-pulse.service &> /dev/null || systemctl --user is-active pipewire.service &> /dev/null; then
        log_message "PipeWire is active. Attempting to set default sink..."
        # PipeWire has PulseAudio compatibility, so pactl should work
        if pactl list sinks short | grep -q "$BLUETOOTH_SINK_NAME"; then
            pactl set-default-sink "$BLUETOOTH_SINK_NAME"
            return $?
        else
            log_message "Sink $BLUETOOTH_SINK_NAME not found in audio system yet. It may need more time to register."
            return 1
        fi
    else
        log_message "Neither PipeWire nor PulseAudio appear to be active as user service."
        return 1
    fi
}
# --- Main Logic ---
log_message "Script started. Waiting for Bluetooth adapter to be ready and audio services."
# Wait for XDG_RUNTIME_DIR to be set and PulseAudio/PipeWire to be running
# This is crucial for user services accessing audio sockets
# We'll rely on systemd dependencies for audio services, but an initial wait for bluetoothctl is good.
# Also, ensure bluetoothd is running (system service)
until systemctl is-active bluetooth.service &> /dev/null && bluetoothctl show | grep -q 'Powered: yes'; do
    log_message "Waiting for system Bluetooth service and adapter to be powered on..."
    sleep $RETRY_DELAY
done
log_message "Bluetooth adapter is powered on."

# Wait for audio service to be ready (PulseAudio or PipeWire)
log_message "Waiting for audio service to be ready..."
until systemctl --user is-active pulseaudio.service &> /dev/null || \
      systemctl --user is-active pipewire-pulse.service &> /dev/null || \
      systemctl --user is-active pipewire.service &> /dev/null; do
    log_message "Waiting for PulseAudio or PipeWire to start..."
    sleep 2
done
log_message "Audio service is active."
# Loop indefinitely to maintain connection
while true; do
    if is_bluetooth_connected; then
        log_message "Device $BLUETOOTH_MAC is already connected."
        if set_default_sink; then
            log_message "Set $BLUETOOTH_SINK_NAME as default audio sink."
        else
            log_message "Failed to set $BLUETOOTH_SINK_NAME as default audio sink. Will retry."
        fi
        # Keep checking if it's still connected
        while is_bluetooth_connected; do
            sleep $POLLING_INTERVAL
        done
        log_message "Device $BLUETOOTH_MAC disconnected. Attempting to reconnect..."
    else
        log_message "Device $BLUETOOTH_MAC not connected. Attempting to connect..."
        bluetoothctl connect "$BLUETOOTH_MAC" &> /dev/null
        if [ $? -eq 0 ]; then
            log_message "Successfully initiated connect for $BLUETOOTH_MAC. Waiting short for full connection..."
            sleep 5 # Give it a moment to fully establish
            if is_bluetooth_connected; then
                log_message "Device $BLUETOOTH_MAC is now fully connected."
                if set_default_sink; then
                    log_message "Set $BLUETOOTH_SINK_NAME as default audio sink."
                else
                    log_message "Failed to set $BLUETOOTH_SINK_NAME as default audio sink after connection."
                fi
            else
                log_message "Device $BLUETOOTH_MAC connect command returned success, but device not truly connected."
            fi
        else
            log_message "Failed to connect to $BLUETOOTH_MAC. Retrying in $RETRY_DELAY seconds."
        fi
    fi
    sleep $RETRY_DELAY
done