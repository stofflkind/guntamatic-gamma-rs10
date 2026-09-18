#!/usr/bin/env python3

import argparse
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Test UART framing modes on an FT232R raw Gamma/RS10 capture."
)
parser.add_argument(
    "capture",
    type=Path,
    help="FT232R raw capture file",
)
args = parser.parse_args()

FILE = args.capture

SAMPLES_PER_BIT = 32.0

raw = FILE.read_bytes()
rx = [(b >> 1) & 1 for b in raw]


def sample_bit(start, bit_position):
    """
    bit_position:
      0 = Startbit
      1 = Datenbit 0
      ...
    Abtastung jeweils in der Bitmitte.
    """
    pos = int(round(
        start + (bit_position + 0.5) * SAMPLES_PER_BIT
    ))

    if pos >= len(rx):
        return None

    return rx[pos]


def decode(mode):
    decoded = []

    framing_errors = 0
    parity_errors = 0

    i = 1

    while i < len(rx):

        # fallende Flanke = möglicher Beginn eines Startbits
        if rx[i - 1] != 1 or rx[i] != 0:
            i += 1
            continue

        start = i

        # Startbit prüfen
        if sample_bit(start, 0) != 0:
            i += 1
            continue

        value = 0
        valid = True

        # 8 Datenbits, LSB first
        for bit in range(8):

            b = sample_bit(start, bit + 1)

            if b is None:
                valid = False
                break

            value |= b << bit

        if not valid:
            break

        if mode == "8N1":

            stop = sample_bit(start, 9)

            if stop != 1:
                framing_errors += 1
                i += 1
                continue

            frame_bits = 10

        else:

            parity = sample_bit(start, 9)
            stop = sample_bit(start, 10)

            if parity is None or stop is None:
                break

            if stop != 1:
                framing_errors += 1
                i += 1
                continue

            ones = bin(value).count("1")

            if mode == "8E1":
                expected_parity = ones & 1

            elif mode == "8O1":
                expected_parity = 1 - (ones & 1)

            else:
                raise ValueError(mode)

            if parity != expected_parity:
                parity_errors += 1
                i += 1
                continue

            frame_bits = 11

        decoded.append((start, value))

        # Bis ungefähr ans Ende des erfolgreich
        # dekodierten Zeichens springen.
        i = int(
            start +
            frame_bits * SAMPLES_PER_BIT
        )

    return decoded, framing_errors, parity_errors


print("FT232R UART Framing-Test")
print("========================")
print()
print(f"Samples     : {len(rx)}")
print(f"Samples/Bit : {SAMPLES_PER_BIT}")
print()


for mode in ("8N1", "8E1", "8O1"):

    decoded, framing, parity = decode(mode)

    print(mode)
    print("-" * len(mode))

    print(f"Bytes          : {len(decoded)}")
    print(f"Framing-Fehler : {framing}")

    if mode != "8N1":
        print(f"Parity-Fehler  : {parity}")

    print()

    values = [value for _, value in decoded]

    for n in range(0, min(len(values), 128), 16):

        chunk = values[n:n + 16]

        print(
            f"{n:04d}: "
            + " ".join(
                f"{value:02X}"
                for value in chunk
            )
        )

    print()
    print()
