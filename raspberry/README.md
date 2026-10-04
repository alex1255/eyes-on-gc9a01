# Raspberry Pi GC9A01 eyes

Target: Raspberry Pi 3B+, Raspberry Pi OS Lite 64-bit.
No desktop or browser is needed on the Pi. Control page: http://<pi-ip>:8080.

## Wiring

| Display | BCM GPIO | Physical pin |
| --- | --- | --- |
| VCC | 3.3 V | 1 |
| GND | Ground | 6 |
| SCL | 11 / SPI0 SCLK | 23 |
| SDA | 10 / SPI0 MOSI | 19 |
| CS | 8 / SPI0 CE0 | 24 |
| DC | 25 | 22 |
| RST | 27 | 13 |

No backlight GPIO was supplied; the application does not claim one.
All configurable hardware values and the saved eye settings are in config.json.
Default: two eyes, 25 fps target, 32 MHz SPI. For long wires or image corruption,
lower spi_hz to 16000000 and restart the service.
Only changed pixel rectangles are transmitted; every first frame is sent in full.

## Installation

Enable SPI with raspi-config nonint do_spi 0 and reboot if spidev is absent.
From this directory run `sudo ./install.sh`. It installs the apt dependencies,
copies the daemon to /opt/uncanny-eyes and enables the systemd service. Existing
configuration on the Pi is preserved.

```sh
systemctl status uncanny-eyes.service
journalctl -u uncanny-eyes.service -n 30 --no-pager
```

The control page is intended for the local network. Do not expose its port to the internet.
Settings survive restarting the service and rebooting the Pi.

## Preview

```sh
python3 eyes.py --render /tmp/eyes-twin.png --mode twin
python3 eyes.py --render /tmp/eyes-single.png --mode single
```

## Driver provenance

The initialization register values in display.py follow the Waveshare driver
LCD_1inch28.py, retrieved through acromtech's animated-eyes project at commit
cd0e603542506fddecf83d3937c6ffb5d25e9a74:
https://github.com/acromtech/Waveshare-1.28inch-LCD-Module-animated-eyes/blob/cd0e603542506fddecf83d3937c6ffb5d25e9a74/lib/LCD_1inch28.py

Original hardware interface attribution: Waveshare team, 2019-06-21.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
