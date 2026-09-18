#!/usr/bin/env python3
"""
rs10_startup_raw_capture.py

Passive capture for the Gamma RS10 plug-in/startup sequence.

IMPORTANT:
- READ ONLY: never writes to RS485.
- Start while the RS10 is disconnected.
- Then connect the RS10 and let the capture finish.
- Saves the physical serial bytes BEFORE any FF normalization.

Outputs:
  rs10-startup-physical.log  timestamp + exact bytes returned by serial.read()
  rs10-startup-physical.bin  same byte stream concatenated as binary
"""

import argparse
import time
from datetime import datetime
from pathlib import Path
import serial

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB1")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--seconds", type=float, default=45.0)
    ap.add_argument("--text", default="rs10-startup-physical.log")
    ap.add_argument("--binary", default="rs10-startup-physical.bin")
    args = ap.parse_args()

    text_path = Path(args.text)
    bin_path = Path(args.binary)

    print("Gamma RS10 physical startup capture")
    print("READ ONLY - no bytes will be transmitted.")
    print("1. RS10 must be disconnected before starting.")
    print("2. Start capture.")
    print("3. Connect RS10 after about 5 seconds.")
    print("4. Do not operate the RS10 during capture.")
    print(f"Capture duration: {args.seconds:g} s")
    print(f"Text log : {text_path}")
    print(f"Binary   : {bin_path}\n")

    t0 = time.monotonic()
    chunks = 0
    total = 0

    with serial.Serial(
        args.port,
        args.baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.001,
    ) as ser, text_path.open("w", encoding="ascii") as txt, bin_path.open("wb") as rawout:

        while time.monotonic() - t0 < args.seconds:
            chunk = ser.read(4096)
            if not chunk:
                continue

            mono = time.monotonic()
            wall = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            elapsed = mono - t0

            # Preserve exactly what pyserial returned. No FF stripping/deinterleaving.
            rawout.write(chunk)
            rawout.flush()

            txt.write(f"{wall} +{elapsed:012.6f}s {chunk.hex()}\n")
            txt.flush()

            chunks += 1
            total += len(chunk)

    print(f"\nFinished: {chunks} read chunks, {total} physical bytes.")
    print("Please upload BOTH output files.")

if __name__ == "__main__":
    main()
