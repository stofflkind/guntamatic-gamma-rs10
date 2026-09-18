#!/usr/bin/env python3
"""
rs10_send_slot.py - cautious one-shot Gamma RS10 mode write experiment.

Safety model:
- Dry-run by default.
- Opens /dev/ttyUSB1 only with --send.
- Passively waits for a CRC-valid 10->20 / 8001 frame.
- Then waits 500 ms.
- If another CRC-valid Gamma frame appears during that guard interval, it aborts
  that slot and waits for the next 8001.
- Sends exactly ONE 23->20 / 2806 frame.
- No retries.

Stop guntamatic.py before use.
"""

import argparse
import time
import serial

MODES = {"automatic": 0x00, "heating": 0x03}

AUTOMATIC_FRAME = bytes.fromhex(
    "82232028062b002a000000000064000900004100090003092a"
    "200000000003002a200000000003002a20000000226903"
)

def crc16_kermit(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if (crc & 1) else (crc >> 1)
    return crc & 0xFFFF

def make_mode_frame(mode: str) -> bytes:
    frame = bytearray(AUTOMATIC_FRAME)
    frame[10] = MODES[mode]  # confirmed P7
    crc = crc16_kermit(frame[1:-3])
    frame[-3] = crc & 0xff
    frame[-2] = (crc >> 8) & 0xff
    return bytes(frame)

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
                p = self.buf.index(0x82)
            except ValueError:
                self.buf.clear()
                break
            if p:
                del self.buf[:p]
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

def type_code(frame: bytes):
    # Gamma type is LL byte + first content byte:
    # e.g. 82 23 10 01 06 ... = 0106
    return (frame[3] << 8) | frame[4]

def describe(frame: bytes):
    return f"{frame[1]:02X}->{frame[2]:02X} {type_code(frame):04X}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=MODES)
    ap.add_argument("--port", default="/dev/ttyUSB1")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--guard-ms", type=int, default=500)
    ap.add_argument("--send", action="store_true")
    args = ap.parse_args()

    tx = make_mode_frame(args.mode)

    print(f"mode    : {args.mode} (P7=0x{MODES[args.mode]:02X})")
    print(f"frame   : {tx.hex(' ')}")
    print(f"CRC     : 0x{(tx[-2] << 8 | tx[-3]):04X}")
    print(f"guard   : {args.guard_ms} ms after valid 10->20 / 8001")
    print(f"dry-run : {not args.send}")

    if not args.send:
        print("No serial port opened; nothing transmitted.")
        return

    deint = FFDeinterleaver()
    ext = GammaExtractor()

    with serial.Serial(
        args.port, args.baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.005,
    ) as ser:
        print("Listening for end-of-cycle 10->20 / 8001 ...")

        deadline = time.monotonic() + 30.0

        while time.monotonic() < deadline:
            raw = ser.read(256)
            if not raw:
                continue

            for f in ext.feed(deint.feed(raw)):
                if f[1] == 0x10 and f[2] == 0x20 and type_code(f) == 0x8001:
                    print("Found 10->20 / 8001. Guard interval starts.")

                    guard_end = time.monotonic() + args.guard_ms / 1000.0
                    collision = False

                    while time.monotonic() < guard_end:
                        r = ser.read(256)
                        if not r:
                            continue
                        new_frames = ext.feed(deint.feed(r))
                        if new_frames:
                            print("Valid frame appeared during guard:")
                            for nf in new_frames:
                                print(" ", describe(nf))
                            print("Slot rejected; waiting for next 8001.")
                            collision = True
                            break

                    if collision:
                        continue

                    print("Guard interval clear.")
                    print("TRANSMITTING EXACTLY ONCE...")
                    ser.write(tx)
                    ser.flush()
                    print("Transmission completed. No retry.")
                    return

        raise SystemExit("Abort: no suitable 8001 slot found within 30 seconds.")

if __name__ == "__main__":
    main()
