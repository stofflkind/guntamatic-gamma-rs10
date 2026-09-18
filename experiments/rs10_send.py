#!/usr/bin/env python3
"""
rs10_send.py - cautious one-shot Gamma RS10 mode write experiment.

IMPORTANT:
- Stop guntamatic.py before using this script.
- Default is DRY RUN: it never writes unless --send is supplied.
- Initially supports only automatic (P7=0x00) and heating (P7=0x03).
- Uses the observed RS10 0x23 -> 0x20 TYPE 2806 frame as template.
"""

import argparse
import time
import serial

START = 0x82
END = 0x03

MODES = {
    "automatic": 0x00,
    "heating": 0x03,
}

# Exact logical 23 -> 20 / 2806 frame observed in the capture for AUTOMATIC.
# P7 is changed at runtime and CRC is recalculated.
AUTOMATIC_FRAME = bytes.fromhex(
    "82232028062b002a000000000064000900004100090003092a"
    "200000000003002a200000000003002a20000000226903"
)

def crc16_kermit(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return crc & 0xFFFF

def validate_frame(frame: bytes) -> None:
    if len(frame) != 48:
        raise ValueError(f"Unexpected frame length: {len(frame)}")
    if frame[0] != START or frame[-1] != END:
        raise ValueError("Bad start/end byte")
    if frame[1:5] != bytes.fromhex("23 20 28 06"):
        raise ValueError("Template is not 23->20 / 2806")
    expected = crc16_kermit(frame[1:-3])
    stored = frame[-3] | (frame[-2] << 8)
    if expected != stored:
        raise ValueError(
            f"Template CRC mismatch: calculated 0x{expected:04X}, stored 0x{stored:04X}"
        )

def make_mode_frame(mode: str) -> bytes:
    frame = bytearray(AUTOMATIC_FRAME)
    # Frame indices: 0=82,1=src,2=dst,3=LL,4=type; payload P1 starts at 5.
    # Observed 2806 mode byte (P7) is frame index 10.
    frame[10] = MODES[mode]
    crc = crc16_kermit(frame[1:-3])
    frame[-3] = crc & 0xFF
    frame[-2] = (crc >> 8) & 0xFF
    return bytes(frame)

def physical_bytes(logical: bytes, interleave_ff: bool) -> bytes:
    # DO NOT assume this is required. It is an explicit experiment option only.
    if not interleave_ff:
        return logical
    out = bytearray()
    for b in logical:
        out.extend((b, 0xFF))
    return bytes(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=MODES)
    ap.add_argument("--port", default="/dev/ttyUSB1")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--send", action="store_true",
                    help="actually write once; without this flag this is dry-run only")
    ap.add_argument("--interleave-ff", action="store_true",
                    help="EXPERIMENTAL: append FF after each logical byte")
    ap.add_argument("--idle-ms", type=int, default=250,
                    help="required receive silence before write (default 250 ms)")
    args = ap.parse_args()

    validate_frame(AUTOMATIC_FRAME)
    logical = make_mode_frame(args.mode)
    validate_frame(logical)

    print(f"mode       : {args.mode} (P7=0x{MODES[args.mode]:02X})")
    print(f"logical    : {logical.hex(' ')}")
    print(f"CRC        : 0x{(logical[-2] << 8 | logical[-3]):04X}")
    print(f"dry-run    : {not args.send}")

    if not args.send:
        print("No serial port opened; nothing transmitted.")
        return

    wire = physical_bytes(logical, args.interleave_ff)
    print(f"wire mode  : {'logical+FF separators' if args.interleave_ff else 'logical bytes'}")
    print(f"wire bytes : {wire.hex(' ')}")
    print()
    print("Opening bus read-only first. Ctrl-C aborts before transmission.")

    with serial.Serial(
        args.port,
        args.baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.02,
    ) as ser:
        # Observe traffic first, then require a real idle interval.
        observed = 0
        last_rx = time.monotonic()
        start = last_rx

        while True:
            data = ser.read(4096)
            now = time.monotonic()
            if data:
                observed += len(data)
                last_rx = now

            # Require some traffic first so a disconnected bus is not mistaken for idle.
            if observed and (now - last_rx) * 1000 >= args.idle_ms:
                break

            if now - start > 20:
                raise SystemExit("Abort: no suitable bus-idle interval found within 20 s.")

        print(f"Observed {observed} physical RX bytes.")
        print(f"Bus quiet for >= {args.idle_ms} ms.")
        print("TRANSMITTING EXACTLY ONCE...")
        ser.write(wire)
        ser.flush()
        print("Write completed. No automatic repeat.")
        print("Observe RS10/boiler state and restart the passive logger.")

if __name__ == "__main__":
    main()
