#!/usr/bin/env python3
"""
rs10_timing_v2.py
Passive timing logger for the Gamma RS10 bus.

- READ ONLY: never writes to the serial port.
- Removes only the physical 0xFF separator bytes.
- Preserves a genuine logical 0xFF represented by FF FF FF.
- Extracts frames by the known Gamma length field.
- Accepts only CRC-16/KERMIT-valid frames.
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
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc & 0xFFFF


class FFDeinterleaver:
    """
    Physical stream normally looks like:
        82 FF 23 FF 10 FF ...
    A genuine logical FF therefore appears as:
        ... FF FF FF ...
    State is retained across serial read() boundaries.
    """
    def __init__(self):
        self.expect_separator = False

    def feed(self, data: bytes) -> bytes:
        out = bytearray()
        for b in data:
            if self.expect_separator:
                if b == 0xFF:
                    self.expect_separator = False
                    continue
                # Lost/missing separator: treat this byte as next logical byte.
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

            # Known format:
            # 82 SRC DST LL CONTENT(LL+1 bytes) CRClo CRChi 03
            ll = self.buf[3]
            total = ll + 8

            if total < 8 or total > 300:
                del self.buf[0]
                continue

            if len(self.buf) < total:
                break

            candidate = bytes(self.buf[:total])

            if candidate[-1] != 0x03:
                del self.buf[0]
                continue

            stored = candidate[-3] | (candidate[-2] << 8)
            calc = crc16_kermit(candidate[1:-3])

            if stored != calc:
                del self.buf[0]
                continue

            frames.append(candidate)
            del self.buf[:total]

        return frames


def describe(frame: bytes) -> str:
    src, dst = frame[1], frame[2]
    # Type is the first two content bytes, displayed in observed byte order.
    typ = f"{frame[4]:02X}{frame[5]:02X}" if len(frame) >= 6 else "????"
    extra = ""

    if typ == "2806" and len(frame) > 10:
        # P7 is frame index 10 in our confirmed 2806 mapping.
        extra = f" P7={frame[10]:02X}"

    return f"{src:02X}->{dst:02X}  {typ}{extra}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB1")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--seconds", type=float, default=30.0)
    args = ap.parse_args()

    deint = FFDeinterleaver()
    extractor = GammaExtractor()

    print(f"Passive listen on {args.port} for {args.seconds:g} seconds")
    print("No bytes will be transmitted.")
    print()

    previous_frame_time = None
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

            logical = deint.feed(raw)

            for frame in extractor.feed(logical):
                now = time.monotonic()
                wall = datetime.now()
                valid += 1

                if previous_frame_time is None:
                    delta = ""
                else:
                    delta = f" +{(now - previous_frame_time) * 1000:8.2f} ms"

                previous_frame_time = now
                print(
                    f"{wall.strftime('%H:%M:%S.%f')}  "
                    f"{describe(frame):18s}{delta}"
                )

    print()
    print(f"Finished. CRC-valid frames: {valid}")


if __name__ == "__main__":
    main()
