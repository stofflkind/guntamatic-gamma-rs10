#!/usr/bin/env python3
"""
rs10_startup_capture.py
Passive capture of a Gamma RS10 startup/handshake.

READ ONLY: never writes to the serial port.

Usage:
  python3 rs10_startup_capture.py --seconds 60
Start the script first, then power/reconnect ONLY the RS10.
"""

import argparse
import time
from datetime import datetime
import serial

MODE_NAMES = {
    0x00: "automatic",
    0x03: "heating",
    0x04: "reduced",
    0x13: "party",
    0x14: "away",
}

def crc16_kermit(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
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

            f = bytes(self.buf[:total])
            if f[-1] != 0x03:
                del self.buf[0]
                continue

            stored = f[-3] | (f[-2] << 8)
            if crc16_kermit(f[1:-3]) != stored:
                del self.buf[0]
                continue

            frames.append(f)
            del self.buf[:total]
        return frames

def type_code(f):
    return (f[3] << 8) | f[4]

def extra(f):
    typ = type_code(f)
    if typ == 0x2806 and len(f) > 10:
        p7 = f[10]
        return f" P7={p7:02X}({MODE_NAMES.get(p7,'?')})"
    return ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB1")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--output", default="rs10-startup.log")
    args = ap.parse_args()

    deint = FFDeinterleaver()
    ext = GammaExtractor()

    print(f"Passive startup capture on {args.port} for {args.seconds:g} seconds")
    print("No bytes will be transmitted.")
    print("Start this script FIRST, then power/reconnect ONLY the RS10.")
    print(f"Log: {args.output}\n")

    start = time.monotonic()
    prev = None
    count = 0

    with open(args.output, "w", encoding="ascii") as log, serial.Serial(
        args.port, args.baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.005
    ) as ser:
        while time.monotonic() - start < args.seconds:
            raw = ser.read(256)
            if not raw:
                continue

            for f in ext.feed(deint.feed(raw)):
                now = time.monotonic()
                wall = datetime.now().strftime("%H:%M:%S.%f")
                delta = "" if prev is None else f" +{(now-prev)*1000:8.2f} ms"
                prev = now
                count += 1

                line = (
                    f"{wall} {f[1]:02X}->{f[2]:02X} "
                    f"{type_code(f):04X}{extra(f)}"
                    f"{delta} HEX={f.hex()}"
                )
                print(line)
                log.write(line + "\n")
                log.flush()

    print(f"\nFinished. CRC-valid frames: {count}")
    print(f"Saved to: {args.output}")

if __name__ == "__main__":
    main()
