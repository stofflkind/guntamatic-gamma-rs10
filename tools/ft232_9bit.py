#!/usr/bin/env python3

import argparse
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Decode an FT232R raw capture as Gamma/RS10 9-bit characters."
)
parser.add_argument(
    "capture",
    type=Path,
    help="FT232R raw capture file",
)
args = parser.parse_args()

FILE = args.capture

SPB = 32.0

raw = FILE.read_bytes()
rx = [(b >> 1) & 1 for b in raw]


def sample(start, bitpos):
    """
    bitpos:
      0      Startbit
      1..8   Datenbits D0..D7
      9      neuntes Bit / Paritätsbit
      10     Stopbit
    """
    pos = int(round(
        start + (bitpos + 0.5) * SPB
    ))

    if pos < 0 or pos >= len(rx):
        return None

    return rx[pos]


def parity_class(value, bit9):
    """
    Beschreibt lediglich, welcher klassischen
    Parität das beobachtete 9. Bit entsprechen würde.
    Es wird NICHT vorausgesetzt, dass das Protokoll
    dieses Bit tatsächlich als Parität verwendet.
    """
    ones = bin(value).count("1")

    even_bit = ones & 1
    odd_bit = 1 - even_bit

    if bit9 == even_bit:
        return "EVEN"

    if bit9 == odd_bit:
        return "ODD"

    return "?"


frames = []

i = 1

while i < len(rx):

    # Startbit beginnt mit HIGH -> LOW
    if not (rx[i - 1] == 1 and rx[i] == 0):
        i += 1
        continue

    start = i

    # Startbit in der Mitte nochmals prüfen
    if sample(start, 0) != 0:
        i += 1
        continue

    value = 0
    valid = True

    # 8 Datenbits LSB first
    for n in range(8):

        b = sample(start, n + 1)

        if b is None:
            valid = False
            break

        value |= b << n

    if not valid:
        break

    bit9 = sample(start, 9)
    stop = sample(start, 10)

    if bit9 is None or stop is None:
        break

    # Ein echtes Zeichen muss ein HIGH-Stopbit besitzen.
    if stop != 1:
        i += 1
        continue

    pclass = parity_class(value, bit9)

    frames.append(
        {
            "sample": start,
            "value": value,
            "bit9": bit9,
            "parity": pclass,
        }
    )

    # Nach einem gültigen 11-Bit-Zeichen nicht innerhalb
    # desselben Zeichens erneut nach Startbits suchen.
    i = int(round(
        start + 11 * SPB
    ))


print("FT232R Gamma/RS10 9-Bit-Analyse")
print("================================")
print()

print(f"Samples          : {len(rx)}")
print(f"Samples/Bit      : {SPB}")
print(f"erkannte Frames  : {len(frames)}")
print()

print(
    " Nr     Sample   Byte  Bit9  Klasse   Abstand"
)
print(
    "----  ---------  ----  ----  -------  -------"
)

previous = None

for nr, frame in enumerate(frames):

    if previous is None:
        distance = "-"
    else:
        distance = str(
            frame["sample"] - previous
        )

    print(
        f"{nr:4d}  "
        f"{frame['sample']:9d}  "
        f"{frame['value']:02X}     "
        f"{frame['bit9']}    "
        f"{frame['parity']:7s}  "
        f"{distance:>7s}"
    )

    previous = frame["sample"]


print()
print("Byte + Bit9 kompakt")
print("-------------------")
print()

for n in range(0, len(frames), 8):

    chunk = frames[n:n + 8]

    print(
        f"{n:04d}: "
        + " ".join(
            f"{f['value']:02X}/{f['bit9']}"
            for f in chunk
        )
    )


print()
print("Statistik")
print("---------")

even = sum(
    1 for f in frames
    if f["parity"] == "EVEN"
)

odd = sum(
    1 for f in frames
    if f["parity"] == "ODD"
)

bit9_0 = sum(
    1 for f in frames
    if f["bit9"] == 0
)

bit9_1 = sum(
    1 for f in frames
    if f["bit9"] == 1
)

print(f"Bit9 = 0 : {bit9_0}")
print(f"Bit9 = 1 : {bit9_1}")
print(f"EVEN     : {even}")
print(f"ODD      : {odd}")
