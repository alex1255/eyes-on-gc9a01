"""GC9A01 over Linux SPI, using the Waveshare initialization sequence."""

import time

import lgpio
import numpy as np
import spidev
from PIL import ImageChops


# Waveshare LCD_1inch28.Init, pinned upstream source in README.md.
INIT = (
    (0xEF, ""), (0xEB, "14"), (0xFE, ""), (0xEF, ""),
    (0xEB, "14"), (0x84, "40"), (0x85, "ff"), (0x86, "ff"),
    (0x87, "ff"), (0x88, "0a"), (0x89, "21"), (0x8A, "00"),
    (0x8B, "80"), (0x8C, "01"), (0x8D, "01"), (0x8E, "ff"),
    (0x8F, "ff"), (0xB6, "0020"), (0x36, "08"), (0x3A, "05"),
    (0x90, "08080808"), (0xBD, "06"), (0xBC, "00"),
    (0xFF, "600104"), (0xC3, "13"), (0xC4, "13"), (0xC9, "22"),
    (0xBE, "11"), (0xE1, "100e"), (0xDF, "210c02"),
    (0xF0, "45090808262a"), (0xF1, "43707236376f"),
    (0xF2, "45090808262a"), (0xF3, "43707236376f"),
    (0xED, "1b0b"), (0xAE, "77"), (0xCD, "63"),
    (0x70, "0707040e0f09070803"), (0xE8, "34"),
    (0x62, "180d71ed7070180f71ef7070"),
    (0x63, "181171f17070181371f37070"),
    (0x64, "2829f101f10007"), (0x66, "3c00cd67454510000000"),
    (0x67, "003c0000000154103298"),
    (0x74, "10858000004e00"), (0x98, "3e07"),
    (0x35, ""), (0x21, ""),
)


def rgb565(image):
    rgb = np.asarray(image, dtype=np.uint16)
    packed = ((rgb[:, :, 0] & 0xF8) << 8) | ((rgb[:, :, 1] & 0xFC) << 3) | (rgb[:, :, 2] >> 3)
    return packed.astype(">u2").tobytes()


class Display:
    def __init__(self, config):
        self.dc = config["dc"]
        self.reset = config["reset"]
        self.chip = lgpio.gpiochip_open(config["gpiochip"])
        self.spi = spidev.SpiDev()
        self.previous = None
        try:
            lgpio.gpio_claim_output(self.chip, self.dc, 0)
            lgpio.gpio_claim_output(self.chip, self.reset, 1)
            self.spi.open(config["spi_bus"], config["spi_device"])
            self.spi.max_speed_hz = config["spi_hz"]
            self.spi.mode = 0
            time.sleep(0.02)
            lgpio.gpio_write(self.chip, self.reset, 0)
            time.sleep(0.02)
            lgpio.gpio_write(self.chip, self.reset, 1)
            time.sleep(0.12)
            for command, data in INIT:
                self.command(command, bytes.fromhex(data))
            self.command(0x11)
            time.sleep(0.12)
            self.command(0x29)
            time.sleep(0.02)
        except BaseException:
            self.close()
            raise

    def command(self, command, data=b""):
        lgpio.gpio_write(self.chip, self.dc, 0)
        self.spi.writebytes([command])
        if data:
            lgpio.gpio_write(self.chip, self.dc, 1)
            self.spi.writebytes(list(data))

    def show(self, image):
        if image.size != (240, 240) or image.mode != "RGB":
            raise ValueError("Display needs a 240x240 RGB image")
        bounds = (0, 0, 240, 240) if self.previous is None else ImageChops.difference(image, self.previous).getbbox()
        if bounds is None:
            return
        left, top, right, bottom = bounds
        self.command(0x2A, left.to_bytes(2, "big") + (right - 1).to_bytes(2, "big"))
        self.command(0x2B, top.to_bytes(2, "big") + (bottom - 1).to_bytes(2, "big"))
        self.command(0x2C)
        lgpio.gpio_write(self.chip, self.dc, 1)
        self.spi.writebytes2(rgb565(image.crop(bounds)))
        self.previous = image.copy()

    def close(self):
        self.spi.close()
        lgpio.gpiochip_close(self.chip)
