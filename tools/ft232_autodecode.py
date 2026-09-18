#!/usr/bin/env python3

import argparse
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Automatically analyze UART framing of an FT232R raw Gamma/RS10 capture."
)
parser.add_argument(
    "capture",
    type=Path,
    help="FT232R raw capture file",
)
args = parser.parse_args()

FILE = args.capture

SPB = 32
raw = FILE.read_bytes()
rx = [(b >> 1) & 1 for b in raw]


def bit(pos):
    if pos < 0 or pos >= len(rx):
        return None
    return rx[pos]


def decode_frame(start, mode, phase):
    """
    start = erkannte fallende Flanke
    phase = Korrektur der Sampleposition
    """

    def sample(n):
        pos = int(
            start +
            phase +
            (n + 0.5) * SPB
        )
        return bit(pos)

    # Startbit
    if sample(0) != 0:
        return None

    value = 0

    # 8 Datenbits
    for n in range(8):
        b = sample(n + 1)

        if b is None:
            return None

        value |= b << n

    if mode == "8N1":

        if sample(9) != 1:
            return None

        return value, 10 * SPB

    parity = sample(9)
    stop = sample(10)

    if parity is None or stop != 1:
        return None

    ones = bin(value).count("1")

    if mode == "8E1":
        expected = ones & 1
    else:
        expected = 1 - (ones & 1)

    if parity != expected:
        return None

    return value, 11 * SPB


def scan(mode, phase):

    result = []

    i = 1

    while i < len(rx):

        # Nur echte HIGH -> LOW Flanke
        if rx[i - 1] == 1 and rx[i] == 0:

            frame = decode_frame(
                i,
                mode,
                phase
            )

            if frame is not None:

                value, length = frame

                result.append(
                    (i, value)
                )

                # hinter erfolgreiches Zeichen springen
                i += length
                continue

        i += 1

    return result


print("FT232R UART Autoanalyse")
print("=======================")
print()
print(f"Samples : {len(rx)}")
print(f"SPB     : {SPB}")
print()

results = []

for mode in ("8N1", "8E1", "8O1"):

    for phase in range(-12, 13):

        decoded = scan(
            mode,
            phase
        )

        results.append(
            (
                len(decoded),
                mode,
                phase,
                decoded
            )
        )


results.sort(
    key=lambda x: x[0],
    reverse=True
)

print("Beste Ergebnisse")
print("----------------")
print()

for count, mode, phase, decoded in results[:15]:

    print(
        f"{mode:4s} "
        f"Phase {phase:+3d}: "
        f"{count:4d} Bytes"
    )


print()
print("Beste Variante")
print("--------------")

count, mode, phase, decoded = results[0]

print()
print(f"Modus : {mode}")
print(f"Phase : {phase:+d}")
print(f"Bytes : {count}")
print()

values = [value for _, value in decoded]

for n in range(0, min(len(values), 256), 16):

    chunk = values[n:n + 16]

    print(
        f"{n:04d}: "
        + " ".join(
            f"{v:02X}"
            for v in chunk
        )
    )


print()
print("Bytes mit Sampleposition")
print("------------------------")

for n, (pos, value) in enumerate(decoded[:100]):

    print(
        f"{n:4d}  "
        f"sample={pos:7d}  "
        f"0x{value:02X}"
    )
