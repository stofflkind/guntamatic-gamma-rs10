#!/usr/bin/env python3

import argparse
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Analyze raw FT232R bit samples from the Gamma/RS10 bus."
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

# alle LOW-Flanken suchen, denen eine längere HIGH-Pause vorausgeht
# => wahrscheinlicher Beginn eines Telegramms
starts = []

last_edge = 0

for i in range(1, len(rx)):

    if rx[i - 1] == 1 and rx[i] == 0:

        high_before = 0
        j = i - 1

        while j >= 0 and rx[j] == 1:
            high_before += 1
            j -= 1

        # mindestens 20 Bitzeiten HIGH davor
        if high_before >= 20 * SPB:
            starts.append((i, high_before))


print("FT232R Rohbit-Analyse")
print("=====================")
print()
print(f"Telegramm-Kandidaten: {len(starts)}")
print()

for nr, (start, pause) in enumerate(starts[:20]):

    print(
        f"--- Kandidat {nr} ---"
    )

    print(
        f"Start-Sample : {start}"
    )

    print(
        f"Pause davor  : {pause} Samples "
        f"= {pause / SPB:.1f} Bitzeiten"
    )

    bits = []

    # 128 Bit ab Startposition lesen
    for n in range(128):

        pos = int(
            start +
            (n + 0.5) * SPB
        )

        if pos >= len(rx):
            break

        bits.append(rx[pos])

    # gruppiert zu je 8 Bits ausgeben
    print("Bits:")

    for n in range(0, len(bits), 8):

        chunk = bits[n:n + 8]

        print(
            f"{n:03d}: "
            + "".join(str(x) for x in chunk)
        )

    print()

    # zusätzlich Runs in Bitzeiten
    print("Runs:")

    if bits:

        state = bits[0]
        count = 1

        result = []

        for b in bits[1:]:

            if b == state:
                count += 1

            else:
                result.append(
                    (state, count)
                )

                state = b
                count = 1

        result.append(
            (state, count)
        )

        print(
            " ".join(
                f"{'H' if state else 'L'}{count}"
                for state, count in result
            )
        )

    print()
