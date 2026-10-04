"""Headless animated eyes and a small LAN control page."""

import argparse
import io
import json
import logging
import math
from pathlib import Path
import random
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger("eyes")


class Renderer:
    def __init__(self):
        self.orbs = {radius: self.make_orb(radius) for radius in (48, 108)}
        self.fronts = {mode: self.make_front(mode) for mode in ("single", "twin")}

    @staticmethod
    def geometry(mode):
        return [(120, 120, 106)] if mode == "single" else [(65, 120, 46), (175, 120, 46)]

    @staticmethod
    def make_orb(radius):
        y, x = np.mgrid[-radius:radius + 1, -radius:radius + 1].astype(np.float32) / radius
        r = np.sqrt(x * x + y * y)
        angle = np.arctan2(y, x)
        z = np.sqrt(np.maximum(0, 1 - r * r))
        light = np.clip(0.50 + 0.57 * z + 0.24 * x - 0.10 * y, 0.12, 1.10)
        fibers = (np.sin(angle * 91 + r * 17) + np.sin(angle * 173 - r * 23)) * 0.013
        orange = np.clip((r - 0.55) / 0.43, 0, 1)
        rgb = np.stack((241 + 10 * z, 217 - 138 * orange, 7 + 20 * orange), axis=-1)
        rgb *= (light + fibers)[:, :, None]
        rgb[r > 1] = (3, 2, 5)
        return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))

    @classmethod
    def make_front(cls, mode):
        image = Image.new("RGB", (240, 240), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        for cx, cy, radius in cls.geometry(mode):
            for delta, color, width in (
                (9, (8, 12, 16), 4), (6, (19, 125, 153), 2),
                (4, (58, 40, 81), 3), (1, (123, 68, 228), 2),
            ):
                r = radius + delta
                draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=width)
            r = radius + 6
            draw.arc((cx - r, cy - r, cx + r, cy + r), 195, 310, fill=(94, 215, 228), width=1)
        return image

    def frame(self, mode, gaze, blink, pupil):
        image = self.fronts[mode].copy()
        for cx, cy, radius in self.geometry(mode):
            orb_radius = 108 if mode == "single" else 48
            tile = self.orbs[orb_radius].copy()
            draw = ImageDraw.Draw(tile)
            dx = gaze[0] * radius * 0.24
            dy = gaze[1] * radius * 0.17
            px, py = orb_radius + dx, orb_radius + dy
            pr = radius * pupil
            draw.ellipse((px - pr - 1, py - pr - 1, px + pr + 1, py + pr + 1), fill=(64, 34, 11))
            draw.ellipse((px - pr, py - pr, px + pr, py + pr), fill=(13, 10, 14))
            # Keep the opening entirely inside its own rim, including during a blink.
            mask = Image.new("L", tile.size, 0)
            half_height = radius * max(0, 1 - blink)
            if half_height > 0.3:
                ImageDraw.Draw(mask).ellipse(
                    (orb_radius - radius, orb_radius - half_height,
                     orb_radius + radius, orb_radius + half_height), fill=255)
            image.paste(tile, (cx - orb_radius, cy - orb_radius), mask)
        return image


class Motion:
    def __init__(self):
        self.start = time.monotonic()
        self.next_gaze = self.start
        self.next_blink = self.start + 2.5
        self.blink_start = -100
        self.origin = (0.0, 0.0)
        self.target = (0.0, 0.0)
        self.gaze = (0.0, 0.0)
        self.move_start = self.start

    def update(self, now, wander, force_blink):
        if force_blink or now >= self.next_blink:
            self.blink_start = now
            self.next_blink = now + random.uniform(3.0, 6.5)
        age = now - self.blink_start
        # Fast closing, slightly slower opening, with a fully closed middle frame.
        if age < 0.11:
            blink = min(1, age / 0.09)
        elif age < 0.27:
            blink = 1 - (age - 0.11) / 0.16
        else:
            blink = 0
        if now >= self.next_gaze:
            self.origin = self.gaze
            self.target = (random.uniform(-0.9, 0.9), random.uniform(-0.65, 0.65))
            self.move_start = now
            self.next_gaze = now + random.uniform(0.7, 2.7)
        amount = min(1, (now - self.move_start) / 0.20)
        amount = amount * amount * (3 - 2 * amount)
        self.gaze = tuple(a + (b - a) * amount for a, b in zip(self.origin, self.target))
        return self.gaze if wander else (0, 0), max(0, min(1, blink))


class App:
    def __init__(self, config_path):
        self.path = config_path
        self.config = json.loads(config_path.read_text())
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.blink = False
        self.image = Image.new("RGB", (240, 240))
        self.measured_fps = 0.0

    def settings(self):
        with self.lock:
            return {key: self.config[key] for key in ("mode", "wander", "pupil")} | {"fps": self.measured_fps}

    def update(self, values):
        if not isinstance(values, dict) or set(values) - {"mode", "wander", "pupil", "blink"}:
            raise ValueError("Unknown setting")
        if "mode" in values and values["mode"] not in ("single", "twin"):
            raise ValueError("Unknown mode")
        if "wander" in values and type(values["wander"]) is not bool:
            raise ValueError("wander must be a boolean")
        if "pupil" in values and (type(values["pupil"]) not in (int, float)
                                  or not math.isfinite(values["pupil"])
                                  or not 0.15 <= values["pupil"] <= 0.42):
            raise ValueError("Pupil out of range")
        with self.lock:
            next_config = self.config | {k: v for k, v in values.items() if k != "blink"}
            if next_config != self.config:
                temporary = self.path.with_suffix(".tmp")
                temporary.write_text(json.dumps(next_config, indent=2) + "\n")
                temporary.replace(self.path)
                self.config = next_config
            self.blink = self.blink or values.get("blink") is True

    def handler(self):
        app = self

        class Handler(BaseHTTPRequestHandler):
            def reply(self, status, content_type, body):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                if path == "/":
                    self.reply(200, "text/html; charset=utf-8", (ROOT / "control.html").read_bytes())
                elif path == "/api":
                    self.reply(200, "application/json", json.dumps(app.settings()).encode())
                elif path == "/preview.png":
                    with app.lock:
                        image = app.image.copy()
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    self.reply(200, "image/png", buffer.getvalue())
                else:
                    self.reply(404, "text/plain", b"Not found")

            def do_POST(self):
                if self.path != "/api":
                    self.reply(404, "text/plain", b"Not found")
                    return
                origin = self.headers.get("Origin")
                if origin and origin != "http://" + self.headers.get("Host", ""):
                    self.reply(403, "text/plain", b"Origin rejected")
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 1024:
                        raise ValueError("Invalid request size")
                    app.update(json.loads(self.rfile.read(size)))
                except (ValueError, TypeError) as exc:
                    self.reply(400, "text/plain", str(exc).encode())
                    return
                self.reply(200, "application/json", json.dumps(app.settings()).encode())

            def log_message(self, *_args):
                pass

        return Handler

    def run(self):
        from display import Display

        renderer, motion = Renderer(), Motion()
        period = 1 / self.config["fps"]
        server = ThreadingHTTPServer(("0.0.0.0", self.config["port"]), self.handler())
        server.daemon_threads = True
        server.timeout = 2
        display = None
        started, frames = time.monotonic(), 0
        try:
            display = Display(self.config)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            LOG.info("GC9A01 ready: SPI0 CE0, DC=%s, RST=%s, controls on port %s",
                     self.config["dc"], self.config["reset"], self.config["port"])
            while not self.stop.is_set():
                now = time.monotonic()
                with self.lock:
                    settings = self.config.copy()
                    force_blink, self.blink = self.blink, False
                gaze, blink = motion.update(now, settings["wander"], force_blink)
                image = renderer.frame(settings["mode"], gaze, blink, settings["pupil"])
                display.show(image)
                frames += 1
                elapsed = time.monotonic() - started
                with self.lock:
                    self.image = image
                    if elapsed >= 5:
                        self.measured_fps = round(frames / elapsed, 1)
                if elapsed >= 5:
                    LOG.info("Animation: %.1f fps, mode=%s", self.measured_fps, settings["mode"])
                    started, frames = time.monotonic(), 0
                self.stop.wait(max(0, period - (time.monotonic() - now)))
        finally:
            if display:
                server.shutdown()
                try:
                    display.show(Image.new("RGB", (240, 240)))
                finally:
                    display.close()
            server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--render", type=Path, help="Render a preview without GPIO")
    parser.add_argument("--mode", choices=("single", "twin"), default="twin")
    args = parser.parse_args()
    if args.render:
        Renderer().frame(args.mode, (0.2, -0.1), 0, 0.29).save(args.render)
        return
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    app = App(args.config)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: app.stop.set())
    app.run()


if __name__ == "__main__":
    main()
