#!/usr/bin/env python3

import argparse
from pathlib import Path
from collections import Counter

parser = argparse.ArgumentParser(
    description="Analyze signal timing of an FT232R raw Gamma/RS10 capture."
)
parser.add_argument(
    "capture",
    type=Path,
    help="FT232R raw capture file",
)
args = parser.parse_args()

FILE = args.capture

raw = FILE.read_bytes()

# D1 / RXD
rx = [(b >> 1) & 1 for b in raw]

print("FT232R Timing-Analyse")
print("=====================")
print()
print(f"Samples insgesamt: {len(rx)}")

if not rx:
    raise SystemExit("Keine Samples vorhanden.")

runs = []

state = rx[0]
start = 0

for i in range(1, len(rx)):

    if rx[i] != state:

        length = i - start

        runs.append(
            (state, length, start)
        )

        state = rx[i]
        start = i

# letzten Abschnitt hinzufügen
runs.append(
    (
        state,
        len(rx) - start,
        start
    )
)

print(f"Signalabschnitte : {len(runs)}")
print()

low_lengths = Counter()
high_lengths = Counter()

for state, length, start in runs:

    if state == 0:
        low_lengths[length] += 1
    else:
        high_lengths[length] += 1


def show(counter, title):

    print(title)
    print("-" * len(title))

    for length, count in counter.most_common(30):

        print(
            f"{length:5d} Samples : "
            f"{count:5d} mal"
        )

    print()


show(low_lengths, "LOW-Längen")
show(high_lengths, "HIGH-Längen")


print("Erste 100 Signalabschnitte")
print("--------------------------")

for n, (state, length, start) in enumerate(runs[:100]):

    print(
        f"{n:3d}: "
        f"{'HIGH' if state else 'LOW ':4s} "
        f"{length:5d} Samples "
        f"Start={start}"
    )
