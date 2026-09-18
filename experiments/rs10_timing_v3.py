#!/usr/bin/env python3
"""
rs10_timing_v3.py
Passive Gamma RS10 timing/state logger.

READ ONLY: this script never writes to the serial port.

Fixes vs v2:
- Correct Gamma "type" display: bytes frame[3:5], e.g. 28 06 -> 2806.
- Shows P7 for 2806 frames so controller and RS10 operating-mode state can
  be compared directly.
"""

import argparse
import time
from datetime import datetime
import serial


def crc16_kermit(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if (crc & 1) else crc >> 1
    return crc & 0xFFFF


class FFDeinterleaver:
    def __init__(self):
        self.expect_separator = False

    def feed(self, data: bytes) -> bytes:
        out = bytearray()
        for b in data:
            if self.expect_separator:
                if b == 0xFF:
                    self.expect_separator = False
                    continue
                out.append(b)
                self.expect_separator = True
            else:
                out.append(b)
                self.expect_separator = True
        return bytes(out)


class GammaExtractor:
    def __init__(self):
        self.buf = bytearray()

    def feed(self, data: bytes):
        self.buf.extend(data)
        frames = []

        while True:
            try:
                start = self.buf.index(0x82)
            except ValueError:
                self.buf.clear()
                break

            if start:
                del self.buf[:start]

            if len(self.buf) < 4:
                break

            total = self.buf[3] + 8

            if total < 8 or total > 300:
                del self.buf[0]
                continue

            if len(self.buf) < total:
                break

            frame = bytes(self.buf[:total])

            if frame[-1] != 0x03:
                del self.buf[0]
                continue

            stored = frame[-3] | (frame[-2] << 8)
            calc = crc16_kermit(frame[1:-3])

            if stored != calc:
                del self.buf[0]
                continue

            frames.append(frame)
            del self.buf[:total]

        return frames


MODE_NAMES = {
    0x00: "automatic",
    0x03: "heating",
    0x04: "reduced",
    0x13: "party",
    0x14: "away",
}


def type_code(frame: bytes) -> int:
    return (frame[3] << 8) | frame[4]


def describe(frame: bytes) -> str:
    src, dst = frame[1], frame[2]
    typ = type_code(frame)
    extra = ""

    if typ == 0x2806 and len(frame) > 10:
        p7 = frame[10]
        extra = f" P7={p7:02X} ({MODE_NAMES.get(p7, 'unknown')})"

    return f"{src:02X}->{dst:02X}  {typ:04X}{extra}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB1")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--seconds", type=float, default=20.0)
    args = ap.parse_args()

    deint = FFDeinterleaver()
    extractor = GammaExtractor()

    print(f"Passive listen on {args.port} for {args.seconds:g} seconds")
    print("No bytes will be transmitted.")
    print()

    previous_time = None
    started = time.monotonic()
    valid = 0

    with serial.Serial(
        args.port,
        args.baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.005,
    ) as ser:
        while time.monotonic() - started < args.seconds:
            raw = ser.read(256)
            if not raw:
                continue

            for frame in extractor.feed(deint.feed(raw)):
                now = time.monotonic()
                wall = datetime.now()
                valid += 1

                delta = ""
                if previous_time is not None:
                    delta = f" +{(now - previous_time) * 1000:8.2f} ms"
                previous_time = now

                print(
                    f"{wall.strftime('%H:%M:%S.%f')}  "
                    f"{describe(frame):34s}{delta}"
                )

    print()
    print(f"Finished. CRC-valid frames: {valid}")


if __name__ == "__main__":
    main()
