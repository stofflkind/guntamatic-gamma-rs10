#!/usr/bin/env python3
"""
rs10_probe_presence_06.py

Conservative one-shot presence probe for Gamma/RS10.

Purpose:
- Physical RS10 must be DISCONNECTED.
- Wait passively for the short-address scan sequence:
    90 x5 -> 21 x5 -> 22 x5 -> first A3
- Immediately send exactly ONE raw byte: 0x06
- Then listen only for a controller startup frame 10->AA / type 0100.
- No 0101, no 2806, no other writes.

Default is DRY RUN. Use --send to actually transmit 0x06.
"""

import argparse
import sys
import time
from collections import deque

try:
    import serial
except ImportError:
    print("pyserial missing: pip install pyserial", file=sys.stderr)
    raise

DEFAULT_PORT = "/dev/ttyUSB1"
BAUD = 9600

TARGETS = [0x90, 0x21, 0x22]
COUNT_PER_GROUP = 5

# Known logical controller startup frames begin:
# 82 10 AA 01 00 ...
LOGICAL_PREFIX = bytes.fromhex("82 10 aa 01 00")

def crc16_kermit(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if (crc & 1) else (crc >> 1)
    return crc & 0xFFFF

def parse_frames(buf: bytearray):
    """
    Parse ordinary logical 82...03 frames from a deinterleaved byte stream.
    Returns (frames, remaining_buffer).
    """
    out = []
    i = 0
    while i < len(buf):
        try:
            s = buf.index(0x82, i)
        except ValueError:
            return out, bytearray()
        if len(buf) - s < 8:
            return out, buf[s:]

        ll = buf[s + 3]
        total = ll + 8
        if len(buf) - s < total:
            return out, buf[s:]

        fr = bytes(buf[s:s+total])
        if fr[-1] == 0x03:
            got = fr[-3] | (fr[-2] << 8)
            calc = crc16_kermit(fr[1:-3])
            if got == calc:
                out.append(fr)
                i = s + total
                continue
        i = s + 1
    return out, bytearray()

class SeparatorAware:
    """
    Very small pragmatic decoder for the observed FTDI capture where ordinary
    Gamma frames appear as FF BYTE FF BYTE ... on RX.

    We keep two candidate streams:
      A: drop 0xFF when it acts as separator
      B: raw bytes unchanged
    For this probe that is sufficient because we only need to recognize
    10->AA / 0100 after sending 0x06.
    """
    def __init__(self):
        self.logical = bytearray()
        self.raw = bytearray()
        self.expect_data_after_ff = False

    def feed(self, b: int):
        self.raw.append(b)

        # Observed physical representation is often FF,DATA,FF,DATA...
        # If we have just seen a separator FF, take the next byte as data.
        if self.expect_data_after_ff:
            self.logical.append(b)
            self.expect_data_after_ff = False
            return

        if b == 0xFF:
            self.expect_data_after_ff = True
        else:
            # Non-interleaved bytes can exist on the same line; keep them too.
            self.logical.append(b)

        if len(self.logical) > 4096:
            del self.logical[:-2048]
        if len(self.raw) > 4096:
            del self.raw[:-2048]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--send", action="store_true",
                    help="actually send the single 0x06 byte")
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="seconds to wait for scan sequence")
    ap.add_argument("--listen", type=float, default=4.0,
                    help="seconds to listen after A3/0x06")
    args = ap.parse_args()

    print("RS10 presence 0x06 probe")
    print("IMPORTANT: physical RS10 address 3 must be DISCONNECTED.")
    print("target  : 90x5 -> 21x5 -> 22x5 -> first A3")
    print("TX byte : 06")
    print("dry-run :", not args.send)
    print()

    ser = serial.Serial(
        port=args.port,
        baudrate=BAUD,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.02,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )
    ser.reset_input_buffer()

    state = 0
    count = 0
    last_match = None
    started = time.monotonic()
    a3_time = None
    decoder = SeparatorAware()

    print(f"Waiting up to {args.timeout:.0f} s for scan sequence ...")

    try:
        while time.monotonic() - started < args.timeout:
            data = ser.read(256)
            if not data:
                continue
            now = time.monotonic()

            for b in data:
                decoder.feed(b)

                target = TARGETS[state] if state < len(TARGETS) else None

                if state < 3:
                    if b == target:
                        # Scan repetitions are roughly 16/32 ms apart.
                        if last_match is not None and now - last_match > 0.080:
                            count = 0
                        count += 1
                        last_match = now
                        if count >= COUNT_PER_GROUP:
                            print(f"  matched {target:02X} x5")
                            state += 1
                            count = 0
                            last_match = None
                    elif b in (0x90, 0x21, 0x22, 0xA3):
                        # Seeing another scan value before completing the
                        # expected group means restart conservatively.
                        if b == 0x90:
                            state = 0
                            count = 1
                            last_match = now
                        elif state > 0:
                            count = 0
                            last_match = None

                else:
                    # After 90x5,21x5,22x5, trigger on the FIRST A3 only.
                    if b == 0xA3:
                        a3_time = time.monotonic()
                        print("  first A3 seen")
                        if args.send:
                            ser.write(b"\x06")
                            ser.flush()
                            print("  SENT exactly one byte: 06")
                        else:
                            print("  DRY RUN: would send exactly one byte: 06")
                        break

            if a3_time is not None:
                break

        if a3_time is None:
            print("Scan sequence not seen; NOTHING SENT.")
            return 2

        print(f"Listening {args.listen:.1f} s for 10->AA / 0100 ...")
        logical_buf = decoder.logical

        deadline = time.monotonic() + args.listen
        found = False

        while time.monotonic() < deadline:
            data = ser.read(256)
            if data:
                for b in data:
                    decoder.feed(b)

                frames, rem = parse_frames(decoder.logical)
                decoder.logical = rem
                for fr in frames:
                    src, dst, ll = fr[1], fr[2], fr[3]
                    typ = (ll << 8) | fr[4]
                    dt_ms = (time.monotonic() - a3_time) * 1000.0
                    print(f"  +{dt_ms:7.1f} ms  {src:02X}->{dst:02X} type={typ:04X}  {fr.hex()}")
                    if src == 0x10 and dst == 0xAA and typ == 0x0100:
                        found = True
                        print("*** SUCCESS: controller emitted 10->AA / 0100 ***")
                        break
                if found:
                    break

        if not found:
            print("No CRC-valid 10->AA / 0100 seen.")
        return 0 if found else 1

    finally:
        ser.close()

if __name__ == "__main__":
    raise SystemExit(main())
