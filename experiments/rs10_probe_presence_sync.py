#!/usr/bin/env python3
"""
RS10 synchronized presence probe.

Purpose:
- physical RS10 (heating-circuit address 3) MUST be disconnected
- observe a complete 0905 burst (5 valid frames)
- wait a measured interval from the 5th 0905
- send exactly one known 23->AA / 0100 frame
- then listen only

Default timing is based on the user's no-RS10 capture:
last 0905 -> next 2004 ~= 2524..2530 ms
native RS10 23->AA -> next 2004 ~= 125..130 ms

Thus default send delay after 5th 0905 = 2395 ms.

No 2806 and no known parameter write is transmitted.
"""

import argparse
import time
from datetime import datetime
import serial

PRESENCE = bytes.fromhex("8223aa0100019b4803")

def crc16_kermit(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc & 0xFFFF

def valid_frame(f: bytes) -> bool:
    return (
        len(f) >= 8
        and f[0] == 0x82
        and f[-1] == 0x03
        and (f[-3] | (f[-2] << 8)) == crc16_kermit(f[1:-3])
    )

def type_code(f: bytes) -> int:
    return (f[3] << 8) | f[4]

class FFDeinterleaver:
    def __init__(self):
        self.expect_separator = False

    def feed(self, data: bytes) -> bytes:
        out = bytearray()
        for b in data:
            if self.expect_separator and b == 0xFF:
                self.expect_separator = False
                continue
            out.append(b)
            self.expect_separator = True
        return bytes(out)

class Extractor:
    def __init__(self):
        self.buf = bytearray()

    def feed(self, data: bytes):
        self.buf.extend(data)
        out = []
        while True:
            try:
                i = self.buf.index(0x82)
            except ValueError:
                self.buf.clear()
                break

            if i:
                del self.buf[:i]

            if len(self.buf) < 4:
                break

            total = self.buf[3] + 8
            if total < 8 or total > 300:
                del self.buf[0]
                continue

            if len(self.buf) < total:
                break

            f = bytes(self.buf[:total])
            if not valid_frame(f):
                del self.buf[0]
                continue

            out.append(f)
            del self.buf[:total]

        return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB1")
    ap.add_argument(
        "--delay-ms",
        type=float,
        default=2395.0,
        help="Delay from 5th 0905 to 23->AA/0100 send (default: 2395 ms)",
    )
    ap.add_argument("--observe", type=float, default=6.0)
    ap.add_argument("--send", action="store_true")
    args = ap.parse_args()

    print("RS10 synchronized 23->AA presence probe")
    print("IMPORTANT: physical RS10 address 3 must be disconnected.")
    print("frame   :", PRESENCE.hex())
    print("CRC     :", "OK" if valid_frame(PRESENCE) else "INVALID")
    print("delay   :", args.delay_ms, "ms after 5th 0905")
    print("observe :", args.observe, "s")
    print("dry-run :", not args.send)

    if not args.send:
        return

    deint = FFDeinterleaver()
    ext = Extractor()

    with serial.Serial(
        args.port,
        9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.002,
    ) as ser:

        print("\nWaiting for a complete 0905 burst (5 frames) ...")

        consecutive_0905 = 0
        fifth_0905_time = None
        deadline = time.monotonic() + 20.0

        while time.monotonic() < deadline:
            raw = ser.read(256)
            if not raw:
                continue

            for f in ext.feed(deint.feed(raw)):
                tc = type_code(f)

                if f[1] == 0x10 and f[2] == 0x20 and tc == 0x0905:
                    consecutive_0905 += 1
                    print(
                        datetime.now().strftime("%H:%M:%S.%f"),
                        f"0905 #{consecutive_0905}"
                    )
                    if consecutive_0905 == 5:
                        fifth_0905_time = time.monotonic()
                        break
                else:
                    consecutive_0905 = 0

            if fifth_0905_time is not None:
                break

        if fifth_0905_time is None:
            raise SystemExit("No complete 5-frame 0905 burst seen; NOTHING SENT.")

        target = fifth_0905_time + args.delay_ms / 1000.0

        while True:
            now = time.monotonic()
            remaining = target - now
            if remaining <= 0:
                break
            if remaining > 0.002:
                time.sleep(min(remaining - 0.001, 0.005))

        ser.write(PRESENCE)
        ser.flush()
        sent = time.monotonic()

        print(
            datetime.now().strftime("%H:%M:%S.%f"),
            f"SENT ONCE 23->AA 0100 "
            f"(actual delay {(sent - fifth_0905_time)*1000:.2f} ms)"
        )
        print("Listening only...\n")

        end = sent + args.observe
        count = 0

        while time.monotonic() < end:
            raw = ser.read(256)
            if not raw:
                continue

            for f in ext.feed(deint.feed(raw)):
                count += 1
                tc = type_code(f)
                ms = (time.monotonic() - sent) * 1000.0

                marks = []
                if f[1] == 0x10 and f[2] == 0xAA and tc == 0x0100:
                    marks.append("10->AA/0100")
                if f[1] == 0x10 and f[2] == 0x20 and tc == 0x1005:
                    marks.append("1005")
                if f[1] == 0x10 and f[2] == 0x20 and tc == 0x2806:
                    marks.append("2806")
                if f[1] == 0x10 and f[2] == 0x20 and tc == 0x4002:
                    marks.append("4002")
                if f[1] == 0x10 and f[2] == 0x20 and tc == 0x8001:
                    marks.append("8001")

                suffix = ""
                if marks:
                    suffix = "  <== " + ", ".join(marks)

                print(
                    f"{datetime.now().strftime('%H:%M:%S.%f')} "
                    f"+{ms:8.1f} ms "
                    f"{f[1]:02X}->{f[2]:02X} {tc:04X} "
                    f"HEX={f.hex()}{suffix}"
                )

        print("\nObserved CRC-valid frames:", count)

if __name__ == "__main__":
    main()
