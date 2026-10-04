#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo: sudo ./install.sh" >&2
    exit 1
fi

if [ ! -e /dev/spidev0.0 ]; then
    echo "SPI0 is not ready. Run 'raspi-config nonint do_spi 0', reboot, then retry." >&2
    exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APP_DIR=/opt/uncanny-eyes

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-pil python3-numpy python3-spidev python3-lgpio

install -d -m 755 "$APP_DIR"
install -m 644 "$SCRIPT_DIR/eyes.py" "$APP_DIR/eyes.py"
install -m 644 "$SCRIPT_DIR/display.py" "$APP_DIR/display.py"
install -m 644 "$SCRIPT_DIR/control.html" "$APP_DIR/control.html"
if [ ! -e "$APP_DIR/config.json" ]; then
    install -m 644 "$SCRIPT_DIR/config.json" "$APP_DIR/config.json"
fi
install -m 644 "$SCRIPT_DIR/uncanny-eyes.service" /etc/systemd/system/uncanny-eyes.service

systemctl daemon-reload
systemctl enable --now uncanny-eyes.service
systemctl --no-pager --full status uncanny-eyes.service
